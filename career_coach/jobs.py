"""Durable, idempotent job submission, dispatch and fenced worker claims."""
import copy
import base64
import binascii
import gzip
import io
import json
import time
import uuid
import zlib

from .config import DEFAULTS
from .contracts import ContractError, validate
from .errors import APIError
from .sessions import _op, _request_hash
from .store import StoreConflict, encode_item

MAX_JOBS = 8
MAX_ATTEMPTS = 3
DISPATCH_LEASE = 15
WORKER_LEASE = 210
CAS_ATTEMPTS = 8


class RetryableJob(Exception):
    def __init__(self, message, retry_after_seconds=0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SQSQueue:
    def __init__(self, client, url):
        if not url:
            raise ValueError('Queue URL required')
        self.client, self.url = client, url

    def send(self, sid, jid):
        self.client.send_message(QueueUrl=self.url, MessageBody=json.dumps({'session_id':sid, 'job_id':jid}, separators=(',', ':')))


def _job_key(jid):
    return 'JOB#' + jid


def _head_key(pid):
    return 'PLANHEAD#' + pid


def _error(status, code, message):
    raise APIError(status, code, message)


def _mark_stage(job, stage, now, *, terminal=False):
    job['stage'] = stage
    job['stage_changed_at'] = now
    job.setdefault('stage_history', []).append({'stage':stage, 'at':now, 'attempt':job.get('claim_attempts', 0)})
    job['stage_history'] = job['stage_history'][-24:]
    if terminal:
        job['finished_at'] = now


class JobService:
    def __init__(self, sessions, plans, queue, clock=time.time):
        self.sessions, self.store, self.plans, self.queue, self.clock = sessions, sessions.store, plans, queue, clock

    def _now(self):
        return int(self.clock())

    def _get(self, sid, jid):
        if not isinstance(sid, str) or not sid or not isinstance(jid, str) or not jid:
            raise ValueError('Invalid job key')
        job = self.store.get('SESSION#' + sid, _job_key(jid))
        if not job or job['expires_at'] <= self._now():
            return None
        return job

    def _public(self, job, state):
        out = {'schema_version':'1.0', 'job_id':job['job_id'], 'status':job['status'], 'stage':job['stage'],
               'plan_id':job['plan_id'], 'revision':job['plan_revision'], 'profile_version':job['profile_version'],
               'stale_profile':state['profile']['profile_version'] != job['profile_version']}
        if job.get('error'):
            out['error'] = copy.deepcopy(job['error'])
        validate('job', out)
        return out

    def create(self, sid, proof, request, plan_id=None):
        try:
            validate('revision-request' if plan_id is not None else 'generate-request', request)
        except ContractError:
            _error(400, 'invalid_request', 'Invalid job request')
        if plan_id is not None and (not isinstance(plan_id, str) or not plan_id or len(plan_id) > 128 or '#' in plan_id):
            _error(400, 'invalid_request', 'Invalid plan ID')
        digest = _request_hash({'plan_id':plan_id, 'request':request})
        request_key = 'JOBREQUEST#' + request['request_id']
        for _ in range(CAS_ATTEMPTS):
            pk, session = self.sessions._load(sid, proof)
            receipt = self.store.get(pk, request_key)
            if receipt and receipt['expires_at'] > self._now():
                if receipt['digest'] != digest:
                    _error(409, 'request_conflict', 'Request ID already used')
                return self.status(sid, proof, receipt['job_id'])
            if receipt:
                _error(409, 'request_expired', 'Request has expired')
            state = session['state']; profile = state['profile']
            if (profile['approved_profile_version'] != profile['profile_version'] or
                    profile['profile_version'] != request['profile_version']):
                _error(409, 'profile_not_approved', 'Approved profile is required')
            if session.get('job_count', 0) >= MAX_JOBS:
                _error(429, 'job_limit', 'Session job limit reached')
            pid = plan_id or uuid.uuid4().hex
            head_key = _head_key(pid)
            head = self.store.get(pk, head_key)
            if plan_id is None:
                if head:
                    continue
                head = {'revision':1, 'completed_revision':0, 'active_job':None}
                head_expected = None
                plan_revision = 1
            else:
                active = self._get(sid, head['active_job']) if head and head.get('active_job') else None
                if not head or head['completed_revision'] != request['base_revision'] or active:
                    _error(409, 'revision_conflict', 'Plan revision is not current')
                head_expected = head['revision']
                head['revision'] += 1
                plan_revision = request['base_revision'] + 1
                if plan_revision > 999999:
                    _error(409, 'revision_limit', 'Plan revision limit reached')
            jid = uuid.uuid4().hex
            expiry = self._now() + DEFAULTS.session_ttl_seconds
            job = {'revision':1,'job_id':jid,'plan_id':pid,'plan_revision':plan_revision,
                   'profile_version':profile['profile_version'],'profile':copy.deepcopy(profile),
                   'change_request':request.get('change_request'), 'request_key':request_key,
                   'status':'queued','stage':'queued','dispatch_pending':True,'dispatch_attempts':0,
                   'dispatch_lease_until':0,'claim_attempts':0,'claim_token':None,'lease_until':0,
                   'expires_at':expiry, 'created_at':self._now(), 'first_started_at':None, 'finished_at':None,
                   'stage_changed_at':self._now(), 'stage_history':[{'stage':'queued','at':self._now(),'attempt':0}]}
            # Reserve room for the bounded stage history and terminal error fields.
            if len(encode_item(profile).encode('utf-8')) > 64 * 1024 or len(encode_item(job).encode('utf-8')) > 76 * 1024:
                _error(400, 'profile_too_large', 'Profile exceeds the job size limit')
            head['active_job'] = jid
            receipt = {'revision':1,'digest':digest,'job_id':jid,'expires_at':expiry}
            old = session['revision']; session['revision'] += 1
            session['job_count'] = session.get('job_count', 0) + 1
            session.setdefault('job_refs', []).append({'job_id':jid, 'request_key':request_key})
            session['expires_at'] = expiry
            operations = [_op(pk,'STATE',session,old), _op(pk,head_key,head,head_expected),
                          _op(pk,_job_key(jid),job,None), _op(pk,request_key,receipt,None)]
            try:
                self.store.transact(operations + self.sessions._renew(pk, session, {_job_key(jid), request_key}))
                try:
                    self.dispatch(sid, jid)
                except Exception:
                    pass  # Persisted outbox remains recoverable by stream or a later read.
                return self.status(sid, proof, jid)
            except StoreConflict:
                continue
        _error(409, 'conflict', 'Session changed; retry')

    def status(self, sid, proof, jid):
        pk, session = self.sessions._load(sid, proof)
        job = self._get(sid, jid)
        if not job:
            _error(404, 'not_found', 'Job not found')
        if job['status'] == 'running' and job['lease_until'] <= self._now():
            try:
                self._recover_stalled(sid, jid)
                job = self._get(sid, jid)
            except (StoreConflict, RetryableJob):
                pass
        if job['status'] == 'queued' and job['dispatch_pending']:
            try:
                self.dispatch(sid, jid)
            except Exception:
                pass
        for _ in range(CAS_ATTEMPTS):
            pk, session = self.sessions._load(sid, proof)
            job = self._get(sid, jid)
            if not job:
                _error(404, 'not_found', 'Job not found')
            receipt = self.store.get(pk, job['request_key'])
            if not receipt or receipt['expires_at'] <= self._now():
                _error(404, 'not_found', 'Job not found')
            expiry = self._now() + DEFAULTS.session_ttl_seconds
            old_session, old_job, old_receipt = session['revision'], job['revision'], receipt['revision']
            session.update(revision=old_session+1, expires_at=expiry)
            job.update(revision=old_job+1, expires_at=expiry)
            receipt.update(revision=old_receipt+1, expires_at=expiry)
            try:
                self.store.transact([_op(pk,'STATE',session,old_session), _op(pk,_job_key(jid),job,old_job),
                    _op(pk,job['request_key'],receipt,old_receipt)] + self.sessions._renew(pk, session, {_job_key(jid), job['request_key']}))
                return self._public(job, session['state'])
            except StoreConflict:
                continue
        _error(409, 'conflict', 'Session changed; retry')

    def read_plan(self, sid, proof, pid, revision):
        self.sessions.read(sid, proof)
        try:
            head = self.store.get('SESSION#' + sid, _head_key(pid))
            if not head or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1 or revision > head['completed_revision']:
                _error(404, 'not_found', 'Plan not found')
            item = self.plans.load(sid, pid, revision)
        except ValueError:
            _error(400, 'invalid_request', 'Invalid plan revision')
        if not item:
            _error(404, 'not_found', 'Plan not found')
        return item['plan']

    def _recover_stalled(self, sid, jid):
        pk = 'SESSION#' + sid
        for _ in range(CAS_ATTEMPTS):
            job = self._get(sid, jid)
            if not job or job['status'] != 'running' or job['lease_until'] > self._now():
                return
            if job['claim_attempts'] >= MAX_ATTEMPTS:
                try:
                    if self._reconcile_saved(sid, job):
                        return
                    self._finish_failed(sid, job, 'recovery_exhausted')
                    return
                except StoreConflict:
                    continue
            old = job['revision']
            job.update(revision=old+1, status='queued', stage='queued', claim_token=None,
                       dispatch_pending=True, dispatch_lease_until=0)
            _mark_stage(job, 'queued', self._now())
            try:
                self.store.transact([_op(pk,_job_key(jid),job,old)])
                return
            except StoreConflict:
                continue
        raise RetryableJob('Recovery contention')

    def _reconcile_saved(self, sid, job):
        """Finish a durable final save without allocating another model claim."""
        item = self.plans.load(sid, job['plan_id'], job['plan_revision'])
        if not isinstance(item, dict) or item.get('job_id') != job['job_id']:
            return False
        try:
            plan, profile = item['plan'], job['profile']
            validate('career-plan', plan)
            validate('profile', profile)
            goal = [f for f in profile['facts'] if f['key'] == 'goal' and f['basis'] == 'user_reported']
            if (profile['approved_profile_version'] != job['profile_version'] or
                profile['profile_version'] != job['profile_version'] or len(goal) != 1 or
                plan['goal'] != goal[0]['value'] or plan['plan_id'] != job['plan_id'] or
                plan['revision'] != job['plan_revision'] or plan['profile_version'] != job['profile_version']):
                return False
            compressed = base64.b64decode(item['trace_gzip_b64'], validate=True)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
                raw = source.read(3 * 1024 * 1024 + 1)
            if (len(raw) > 3 * 1024 * 1024 or len(raw) != item['trace_raw_size'] or
                    not isinstance(json.loads(raw), dict)):
                return False
        except (ContractError, KeyError, TypeError, ValueError, OSError, EOFError, binascii.Error, zlib.error):
            return False
        pk = 'SESSION#' + sid
        head = self.store.get(pk, _head_key(job['plan_id']))
        if not head or head.get('active_job') != job['job_id'] or head['completed_revision'] != job['plan_revision'] - 1:
            raise RetryableJob('Plan head changed')
        old_job, old_head = job['revision'], head['revision']
        job.update(revision=old_job+1, status='completed', stage='complete', claim_token=None, dispatch_pending=False)
        _mark_stage(job, 'complete', self._now(), terminal=True)
        head.update(revision=old_head+1, active_job=None, completed_revision=job['plan_revision'])
        self.store.transact([_op(pk,_job_key(job['job_id']),job,old_job),
                             _op(pk,_head_key(job['plan_id']),head,old_head)])
        return True

    def _finish_failed(self, sid, job, code):
        pk = 'SESSION#' + sid
        head = self.store.get(pk, _head_key(job['plan_id']))
        if not head or head.get('active_job') != job['job_id']:
            raise RetryableJob('Plan head changed')
        old_job, old_head = job['revision'], head['revision']
        job.update(revision=old_job+1, status='failed', stage='failed', dispatch_pending=False,
                   claim_token=None, error={'code':code,'message':'Plan generation could not be completed'})
        _mark_stage(job, 'failed', self._now(), terminal=True)
        head.update(revision=old_head+1, active_job=None)
        self.store.transact([_op(pk,_job_key(job['job_id']),job,old_job), _op(pk,_head_key(job['plan_id']),head,old_head)])

    def dispatch(self, sid, jid):
        pk = 'SESSION#' + sid
        for _ in range(CAS_ATTEMPTS):
            job = self._get(sid, jid)
            if not job or job['status'] != 'queued' or not job['dispatch_pending']:
                return
            if job['dispatch_lease_until'] > self._now():
                raise RetryableJob('Dispatch is leased', retry_after_seconds=job['dispatch_lease_until'] - self._now())
            if job['dispatch_attempts'] >= MAX_ATTEMPTS:
                try:
                    self._finish_failed(sid, job, 'dispatch_exhausted')
                    return
                except StoreConflict:
                    continue
            token = uuid.uuid4().hex
            old = job['revision']
            job.update(revision=old+1, dispatch_attempts=job['dispatch_attempts']+1,
                       dispatch_lease_until=self._now()+DISPATCH_LEASE, dispatch_token=token)
            try:
                self.store.transact([_op(pk,_job_key(jid),job,old)])
            except StoreConflict:
                continue
            sent = False
            try:
                self.queue.send(sid, jid)
                sent = True
            except Exception:
                pass
            for _ in range(CAS_ATTEMPTS):
                current = self._get(sid, jid)
                if not current or current.get('dispatch_token') != token or current['status'] != 'queued':
                    return
                old = current['revision']
                current.update(revision=old+1, dispatch_pending=not sent, dispatch_lease_until=0)
                try:
                    self.store.transact([_op(pk,_job_key(jid),current,old)])
                    return
                except StoreConflict:
                    continue
            raise RetryableJob('Dispatch state changed')
        raise RetryableJob('Dispatch contention')

    def claim(self, sid, jid):
        pk = 'SESSION#' + sid
        for _ in range(CAS_ATTEMPTS):
            job = self._get(sid, jid)
            if not job:
                return None
            if job['status'] in {'completed','failed'}:
                return None
            if job['status'] == 'running' and job['lease_until'] > self._now():
                raise RetryableJob('Job already running')
            if job['claim_attempts'] >= MAX_ATTEMPTS:
                try:
                    if self._reconcile_saved(sid, job):
                        return None
                    self._finish_failed(sid, job, 'recovery_exhausted')
                    return None
                except StoreConflict:
                    continue
            token = uuid.uuid4().hex
            old = job['revision']
            job.update(revision=old+1, status='running', stage='outline', claim_token=token,
                       lease_until=self._now()+WORKER_LEASE, claim_attempts=job['claim_attempts']+1, dispatch_pending=False)
            if job.get('first_started_at') is None:
                job['first_started_at'] = self._now()
            _mark_stage(job, 'outline', self._now())
            try:
                self.store.transact([_op(pk,_job_key(jid),job,old)])
                return copy.deepcopy(job)
            except StoreConflict:
                continue
        raise RetryableJob('Claim contention')

    def _claimed(self, sid, jid, token):
        job = self._get(sid, jid)
        if not job or job['status'] != 'running' or job.get('claim_token') != token or job['lease_until'] <= self._now():
            raise RetryableJob('Job claim lost')
        return job

    def set_stage(self, sid, jid, token, stage):
        if stage not in {'outline','retrieval','external_search','generation','validation'}:
            raise ValueError('Invalid stage')
        pk = 'SESSION#' + sid
        for _ in range(CAS_ATTEMPTS):
            job = self._claimed(sid, jid, token); old = job['revision']
            job.update(revision=old+1, stage=stage)
            _mark_stage(job, stage, self._now())
            try:
                self.store.transact([_op(pk,_job_key(jid),job,old)])
                return
            except StoreConflict:
                continue
        raise RetryableJob('Stage contention')

    def complete(self, sid, jid, token):
        pk = 'SESSION#' + sid
        for _ in range(CAS_ATTEMPTS):
            job = self._claimed(sid, jid, token)
            saved = self.plans.load(sid, job['plan_id'], job['plan_revision'])
            if not saved or saved['job_id'] != jid:
                raise RetryableJob('Plan is not saved')
            head = self.store.get(pk, _head_key(job['plan_id']))
            if not head or head.get('active_job') != jid:
                raise RetryableJob('Plan head changed')
            old_job, old_head = job['revision'], head['revision']
            job.update(revision=old_job+1, status='completed', stage='complete', claim_token=None)
            _mark_stage(job, 'complete', self._now(), terminal=True)
            head.update(revision=old_head+1, active_job=None, completed_revision=job['plan_revision'])
            try:
                self.store.transact([_op(pk,_job_key(jid),job,old_job), _op(pk,_head_key(job['plan_id']),head,old_head)])
                return
            except StoreConflict:
                continue
        raise RetryableJob('Completion contention')

    def save_plan(self, sid, jid, token, plan, trace=None):
        job = self._claimed(sid, jid, token)
        if (plan.get('plan_id') != job['plan_id'] or plan.get('revision') != job['plan_revision'] or
                plan.get('profile_version') != job['profile_version']):
            raise ValueError('Plan identity mismatch')
        validate('career-plan', plan)
        self.plans.save_fenced(sid, job['plan_id'], job['plan_revision'], jid, plan, self.store, job['revision'], trace)

    def fail(self, sid, jid, token):
        for _ in range(CAS_ATTEMPTS):
            job = self._claimed(sid, jid, token)
            try:
                self._finish_failed(sid, job, 'generation_failed')
                return
            except StoreConflict:
                continue
        raise RetryableJob('Failure contention')
