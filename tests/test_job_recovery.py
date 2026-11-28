"""Adversarial integration checks across session, job and retained-plan stores."""
import copy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from career_coach.errors import APIError
from career_coach.jobs import JobService, RetryableJob, WORKER_LEASE
from career_coach.plans import MemoryPlanStore
from career_coach.sessions import SessionService
from career_coach.store import MemoryStore
from career_coach.worker import JobWorker
from career_coach import handler


class Queue:
    def __init__(self):
        self.messages = []
        self.lose_ack = False

    def send(self, sid, jid):
        self.messages.append((sid, jid))
        if self.lose_ack:
            raise RuntimeError('acknowledgement lost')


class JobRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.store = MemoryStore()
        self.sessions = SessionService(self.store, clock=lambda: self.now)
        path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
        goal = json.loads(path.read_text())['goal']
        profile = {'schema_version':'1.0', 'profile_version':1, 'approved_profile_version':1,
                   'facts':[{'key':'goal', 'value':goal, 'source_question_id':'goal', 'basis':'user_reported'}],
                   'assumptions':[], 'confirmed_assumption_ids':[], 'unresolved':[]}
        state, self.proof = self.sessions.create({'profile':profile})
        self.sid = state['session_id']
        self.plans = MemoryPlanStore()
        self.queue = Queue()
        self.jobs = JobService(self.sessions, self.plans, self.queue, clock=lambda: self.now)

    def create(self, request='request-1'):
        return self.jobs.create(self.sid, self.proof, {'request_id':request, 'profile_version':1})

    def test_lost_dispatch_ack_and_duplicate_dispatch_reuse_one_job(self):
        self.queue.lose_ack = True
        first = self.create()
        self.assertGreaterEqual(len(self.queue.messages), 1)
        self.queue.lose_ack = False
        replay = self.create()
        self.assertEqual(first['job_id'], replay['job_id'])
        self.jobs.dispatch(self.sid, first['job_id'])
        self.assertTrue(all(message == (self.sid, first['job_id']) for message in self.queue.messages))
        with self.assertRaises(APIError) as error:
            self.jobs.create(self.sid, self.proof, {'request_id':'request-1', 'profile_version':2})
        self.assertEqual(error.exception.code, 'request_conflict')

    def test_expired_owner_is_fenced_after_reclaim(self):
        job = self.create(); jid = job['job_id']
        old = self.jobs.claim(self.sid, jid)
        self.now += WORKER_LEASE
        new = self.jobs.claim(self.sid, jid)
        self.assertNotEqual(old['claim_token'], new['claim_token'])
        with self.assertRaises(RetryableJob): self.jobs.set_stage(self.sid, jid, old['claim_token'], 'generation')
        with self.assertRaises(RetryableJob): self.jobs.complete(self.sid, jid, old['claim_token'])
        self.jobs.set_stage(self.sid, jid, new['claim_token'], 'generation')

    def test_reclaim_racing_plan_save_rejects_stale_transaction(self):
        from career_coach.store import StoreConflict
        job = self.create(); jid = job['job_id']; old = self.jobs.claim(self.sid, jid)
        path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
        plan = json.loads(path.read_text())
        plan.update(plan_id=job['plan_id'], revision=1, profile_version=1)
        original = self.plans.save_fenced
        def reclaim(*args):
            self.now += WORKER_LEASE
            self.jobs.claim(self.sid, jid)
            return original(*args)
        self.plans.save_fenced = reclaim
        with self.assertRaises(StoreConflict): self.jobs.save_plan(self.sid, jid, old['claim_token'], plan)
        self.assertIsNone(self.plans.load(self.sid, job['plan_id'], 1))

    def test_snapshot_is_immutable_and_status_detects_profile_edit(self):
        job = self.create(); jid = job['job_id']
        pk = 'SESSION#' + self.sid
        state = self.store.get(pk, 'STATE'); old = state['revision']
        state['revision'] += 1
        state['state']['profile']['profile_version'] = 2
        state['state']['profile']['approved_profile_version'] = None
        self.store.transact([{'pk':pk, 'sk':'STATE', 'item':state, 'expected_revision':old}])
        claimed = self.jobs.claim(self.sid, jid)
        self.assertEqual(claimed['profile']['profile_version'], 1)
        self.assertTrue(self.jobs.status(self.sid, self.proof, jid)['stale_profile'])

    def test_exhausted_claims_fail_and_release_revision_reservation(self):
        job = self.create(); jid = job['job_id']
        for _ in range(3):
            self.assertIsNotNone(self.jobs.claim(self.sid, jid))
            self.now += WORKER_LEASE
        self.assertIsNone(self.jobs.claim(self.sid, jid))
        status = self.jobs.status(self.sid, self.proof, jid)
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['error']['code'], 'recovery_exhausted')

    def test_session_activity_renews_job_receipt_and_preserves_replay(self):
        job = self.create(); self.now += 600000
        self.sessions.read(self.sid, self.proof)
        self.now += 10000
        with self.store._lock:
            self.store._items = {key:value for key,value in self.store._items.items()
                                 if value.get('expires_at', self.now+1) > self.now}
        self.assertEqual(self.create()['job_id'], job['job_id'])
        self.assertEqual(self.jobs.status(self.sid, self.proof, job['job_id'])['job_id'], job['job_id'])

    def test_competing_revisions_reserve_only_once(self):
        first = self.create(); jid = first['job_id']; pid = first['plan_id']
        claim = self.jobs.claim(self.sid, jid)
        self.plans.save(self.sid, pid, 1, jid, {'revision':1})
        self.jobs.complete(self.sid, jid, claim['claim_token'])
        barrier = threading.Barrier(2); results = []
        def submit(rid):
            barrier.wait()
            try:
                results.append(self.jobs.create(self.sid, self.proof, {'request_id':rid, 'base_revision':1,
                    'profile_version':1, 'change_request':'Change direction'}, plan_id=pid))
            except APIError as exc:
                results.append(exc.code)
        threads = [threading.Thread(target=submit, args=(str(n),)) for n in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn('revision_conflict', results)
        self.assertEqual(self.plans.load(self.sid, pid, 1)['plan'], {'revision':1})

    def test_saved_plan_ack_loss_and_redelivery_do_not_regenerate(self):
        class Pipeline:
            calls = 0
            def generate(self, profile, *, plan_id, revision, change_request, stage_callback):
                self.calls += 1
                path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
                plan = json.loads(path.read_text())
                plan.update(plan_id=plan_id, revision=revision, profile_version=profile['profile_version'])
                return {'plan':plan, 'trace':{}}
        pipeline = Pipeline(); worker = JobWorker(self.jobs, pipeline)
        job = self.create(); jid = job['job_id']
        original = self.plans.save_fenced
        def lost_ack(*args):
            original(*args)
            raise RuntimeError('response lost after durable save')
        self.plans.save_fenced = lost_ack
        with self.assertRaises(RuntimeError): worker.process(self.sid, jid)
        self.assertEqual(pipeline.calls, 1)
        self.now += WORKER_LEASE
        self.plans.save_fenced = original
        worker.process(self.sid, jid)
        self.assertEqual(self.jobs.status(self.sid, self.proof, jid)['status'], 'completed')
        worker.process(self.sid, jid)
        self.assertEqual(pipeline.calls, 1)

    def test_storage_failure_never_marks_completed(self):
        class Pipeline:
            def generate(self, profile, *, plan_id, revision, change_request, stage_callback):
                path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
                plan = json.loads(path.read_text())
                plan.update(plan_id=plan_id, revision=revision, profile_version=profile['profile_version'])
                return {'plan':plan, 'trace':{}}
        job = self.create(); jid = job['job_id']
        def fail(*args):
            raise RuntimeError('storage unavailable')
        self.plans.save_fenced = fail
        with self.assertRaises(RuntimeError): JobWorker(self.jobs, Pipeline()).process(self.sid, jid)
        self.assertNotEqual(self.jobs.status(self.sid, self.proof, jid)['status'], 'completed')

    def test_three_failed_saves_then_fourth_delivery_marks_failed(self):
        class Pipeline:
            def generate(self, profile, *, plan_id, revision, change_request, stage_callback):
                path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
                plan = json.loads(path.read_text())
                plan.update(plan_id=plan_id, revision=revision, profile_version=profile['profile_version'])
                return {'plan':plan, 'trace':{}}
        job = self.create(); jid = job['job_id']; worker = JobWorker(self.jobs, Pipeline())
        def unavailable(*args):
            raise RuntimeError('plan storage unavailable')
        self.plans.save_fenced = unavailable
        for _ in range(3):
            with self.assertRaises(RuntimeError): worker.process(self.sid, jid)
            self.assertNotEqual(self.jobs.status(self.sid, self.proof, jid)['status'], 'completed')
            self.now += WORKER_LEASE
        self.assertIsNone(worker.process(self.sid, jid))
        status = self.jobs.status(self.sid, self.proof, jid)
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['error']['code'], 'recovery_exhausted')

    def test_saved_final_attempt_ack_loss_reconciles_before_exhaustion(self):
        class Pipeline:
            calls = 0
            def generate(self, profile, *, plan_id, revision, change_request, stage_callback):
                self.calls += 1
                path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
                plan = json.loads(path.read_text())
                plan.update(plan_id=plan_id, revision=revision, profile_version=profile['profile_version'])
                return {'plan':plan, 'trace':{}}
        job = self.create(); jid = job['job_id']; pipeline = Pipeline(); worker = JobWorker(self.jobs, pipeline)
        original = self.plans.save_fenced; attempts = 0
        def flaky(*args):
            nonlocal attempts
            attempts += 1
            if attempts == 3:
                original(*args)
            raise RuntimeError('response unavailable')
        self.plans.save_fenced = flaky
        for _ in range(3):
            with self.assertRaises(RuntimeError): worker.process(self.sid, jid)
            self.now += WORKER_LEASE
        self.assertEqual(self.jobs.status(self.sid, self.proof, jid)['status'], 'completed')
        self.assertEqual(pipeline.calls, 3)
        self.assertIsNone(worker.process(self.sid, jid))
        self.assertEqual(pipeline.calls, 3)

    def test_exhausted_recovery_rejects_wrong_owner_and_corrupt_trace(self):
        for corruption in ('owner', 'trace'):
            with self.subTest(corruption=corruption):
                self.setUp()
                job = self.create(); jid = job['job_id']; pid = job['plan_id']
                path = Path(__file__).resolve().parents[1] / 'career_coach/fixtures/career-plan.json'
                plan = json.loads(path.read_text())
                plan.update(plan_id=pid, revision=1, profile_version=1)
                self.plans.save(self.sid, pid, 1, jid if corruption == 'trace' else 'wrong-job', plan, {})
                if corruption == 'trace':
                    with self.plans._lock:
                        self.plans._items[(self.sid, 'PLAN#'+pid+'#REV#000001')]['trace_gzip_b64'] = 'not-base64!'
                for _ in range(3):
                    self.jobs.claim(self.sid, jid)
                    self.now += WORKER_LEASE
                self.assertEqual(self.jobs.status(self.sid, self.proof, jid)['status'], 'failed')
    def test_stream_retries_abandoned_dispatch_lease_without_polling(self):
        job = self.create(); jid = job['job_id']; pk = 'SESSION#' + self.sid
        record = self.store.get(pk, 'JOB#'+jid); old = record['revision']
        record.update(revision=old+1, status='queued', dispatch_pending=True,
                      dispatch_lease_until=self.now+15, dispatch_attempts=1, dispatch_token='dead-owner')
        self.store.transact([{'pk':pk, 'sk':'JOB#'+jid, 'item':record, 'expected_revision':old}])
        before = len(self.queue.messages)
        event = {'Records':[{'eventSource':'aws:dynamodb', 'eventName':'MODIFY', 'dynamodb':{
            'SequenceNumber':'seq', 'NewImage':{'pk':{'S':pk}, 'sk':{'S':'JOB#'+jid}}}}]}
        class App: pass
        app = App(); app.jobs = self.jobs
        delays = []
        def advance(delay):
            delays.append(delay); self.now += delay
        with patch.object(handler, 'default_application', return_value=app), patch.object(handler.time, 'sleep', side_effect=advance):
            self.assertEqual(handler.lambda_handler(event, None), {'batchItemFailures':[]})
        self.assertEqual(len(delays), 1)
        self.assertGreaterEqual(delays[0], 15)
        self.assertEqual(self.queue.messages[before:], [(self.sid,jid)])


if __name__ == '__main__': unittest.main()
