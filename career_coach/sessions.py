"""Anonymous session access and fenced, idempotent turn claims."""
import copy
import hashlib
import hmac
import json
import secrets
import time

from .config import DEFAULTS
from .errors import APIError
from .store import StoreConflict, encode_item

MAX_REQUESTS = 32
MAX_CAS_ATTEMPTS = 8


def _bad(status, code, message):
    raise APIError(status, code, message)


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _request_hash(payload):
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        _bad(400, 'invalid_request', 'Invalid request')
    if len(encoded.encode('utf-8')) > 16 * 1024:
        _bad(400, 'invalid_request', 'Invalid request')
    return _hash(encoded)


def _bounded(value, limit):
    try:
        if len(encode_item(value).encode('utf-8')) > limit:
            raise ValueError()
    except (ValueError, TypeError):
        _bad(400, 'invalid_request', 'Invalid result')


def _op(pk, sk, item, expected):
    return {'pk': pk, 'sk': sk, 'item': item, 'expected_revision': expected}


def _public(record):
    return copy.deepcopy(record['state'])


class SessionService:
    def __init__(self, store, clock=time.time, token_factory=secrets.token_urlsafe):
        self.store, self.clock, self.token_factory = store, clock, token_factory

    def _now(self):
        return int(self.clock())

    def _load(self, sid, token):
        if (not isinstance(sid, str) or not 1 <= len(sid) <= 128 or
                not isinstance(token, str) or not 1 <= len(token) <= 256):
            _bad(403, 'unauthorized', 'Unauthorized')
        pk = 'SESSION#' + sid
        record = self.store.get(pk, 'STATE')
        if not record or not hmac.compare_digest(record['proof_hash'], _hash(token)):
            _bad(403, 'unauthorized', 'Unauthorized')
        if record['expires_at'] <= self._now():
            _bad(410, 'expired', 'Session expired')
        return pk, record

    def _renew(self, pk, state, excluded=()):
        """Renew all indexed receipts atomically with their parent session.

        The 32-turn and 8-job caps keep indexed children within DynamoDB's
        transaction limits. Missing receipts fail closed.
        """
        ops = []
        for request_id in state['request_ids']:
            req_sk = 'REQUEST#' + request_id
            if req_sk in excluded:
                continue
            request = self.store.get(pk, req_sk)
            if request is None:
                _bad(503, 'temporary_failure', 'Session temporarily unavailable')
            keys = [req_sk]
            if request['status'] == 'completed':
                keys.append('TURN#' + request_id)
            for sk in keys:
                if sk in excluded:
                    continue
                child = request if sk == req_sk else self.store.get(pk, sk)
                if child is None:
                    _bad(503, 'temporary_failure', 'Session temporarily unavailable')
                old = child['revision']
                child['revision'] += 1
                child['expires_at'] = state['expires_at']
                ops.append(_op(pk, sk, child, old))
        for ref in state.get('job_refs', []):
            for sk in ('JOB#' + ref['job_id'], ref['request_key']):
                if sk in excluded:
                    continue
                child = self.store.get(pk, sk)
                if child is None:
                    _bad(503, 'temporary_failure', 'Session temporarily unavailable')
                old = child['revision']
                child.update(revision=old + 1, expires_at=state['expires_at'])
                ops.append(_op(pk, sk, child, old))
        return ops

    def create(self, initial_state=None):
        now = self._now()
        sid, token = self.token_factory(32), self.token_factory(32)
        state = {'session_id': sid, 'schema_version': '1.0', 'state_version': 1,
                 'stage': 'direction', 'status': 'awaiting_answer',
                 'current_question': None, 'profile': {'schema_version': '1.0',
                     'profile_version': 1, 'facts': [], 'assumptions': [],
                     'confirmed_assumption_ids': [], 'approved_profile_version': None,
                     'unresolved': []},
                 'counters': {'core': 0, 'followups': 0, 'per_axis': {}}}
        if initial_state is not None:
            if not isinstance(initial_state, dict) or set(initial_state) - {'stage', 'status', 'current_question', 'profile', 'counters'}:
                _bad(400, 'invalid_request', 'Invalid initial state')
            state.update(copy.deepcopy(initial_state))
        _bounded(state, 96 * 1024)
        record = {'revision': 1, 'proof_hash': _hash(token), 'expires_at': now + DEFAULTS.session_ttl_seconds,
                  'state': state, 'request_count': 0, 'request_ids': [], 'active_request': None}
        try:
            encode_item(record)
            self.store.transact([_op('SESSION#'+sid, 'STATE', record, None)])
        except (ValueError, TypeError):
            _bad(400, 'invalid_request', 'Invalid initial state')
        return _public(record), token

    def read(self, sid, token):
        for _ in range(MAX_CAS_ATTEMPTS):
            pk, record = self._load(sid, token)
            old = record['revision']; record['revision'] += 1
            record['expires_at'] = self._now() + DEFAULTS.session_ttl_seconds
            try:
                self.store.transact([_op(pk, 'STATE', record, old)] + self._renew(pk, record))
                return _public(record)
            except StoreConflict:
                continue
        _bad(409, 'conflict', 'Session changed; retry')

    def claim(self, sid, token, request_id, payload, state_version):
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or
                isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 1):
            _bad(400, 'invalid_request', 'Invalid request')
        digest = _request_hash({'payload': payload, 'state_version': state_version})
        sk = 'REQUEST#' + request_id
        for _ in range(MAX_CAS_ATTEMPTS):
            pk, state = self._load(sid, token); now = self._now()
            request = self.store.get(pk, sk)
            if request and request['digest'] != digest:
                _bad(409, 'request_conflict', 'Request ID already used')
            if request and request['status'] == 'failed':
                self.read(sid, token)
                return {'status': 'failed', 'response': copy.deepcopy(request['response'])}
            if request and request['status'] == 'completed':
                # Slide the session expiry as part of successful replay.
                self.read(sid, token)
                return {'status': 'replay', 'response': copy.deepcopy(request['response'])}
            if state['state']['state_version'] != state_version:
                _bad(409, 'stale_version', 'Session version is stale')
            if state['active_request'] and state['active_request'] != request_id:
                active_id = state['active_request']
                active = self.store.get(pk, 'REQUEST#' + active_id)
                if active is None or active['status'] != 'processing':
                    _bad(503, 'temporary_failure', 'Session temporarily unavailable')
                if active['lease_until'] > now:
                    _bad(409, 'processing', 'Another request is processing')
                try:
                    self._finish_failure(pk, state, active_id, active, 'claim_expired')
                except StoreConflict:
                    continue
                continue
            if request and request['lease_until'] > now:
                self.read(sid, token)
                return {'status': 'processing'}
            if request and request['recoveries'] >= DEFAULTS.claim_max_recoveries:
                try:
                    self._finish_failure(pk, state, request_id, request, 'recovery_exhausted')
                except StoreConflict:
                    continue
                _bad(409, 'recovery_exhausted', 'Request recovery limit reached')
            if request is None and state['request_count'] >= MAX_REQUESTS:
                _bad(429, 'request_limit', 'Session request limit reached')
            claim_token = self.token_factory(32)
            old_state = state['revision']; state['revision'] += 1
            state['active_request'] = request_id
            state['expires_at'] = now + DEFAULTS.session_ttl_seconds
            old_req = request['revision'] if request else None
            if request is None:
                state['request_count'] += 1
                state['request_ids'].append(request_id)
                request = {'revision': 1, 'digest': digest, 'recoveries': 0}
            else:
                request['revision'] += 1; request['recoveries'] += 1
            request.update(status='processing', claim_hash=_hash(claim_token),
                           lease_until=now + DEFAULTS.claim_lease_seconds,
                           expires_at=state['expires_at'])
            try:
                self.store.transact([_op(pk, 'STATE', state, old_state), _op(pk, sk, request, old_req)] + self._renew(pk, state, {sk}))
                return {'status': 'claimed', 'claim_token': claim_token}
            except StoreConflict:
                continue
        _bad(409, 'conflict', 'Session changed; retry')

    def complete(self, sid, token, request_id, claim_token, new_state, response, turn):
        for _ in range(MAX_CAS_ATTEMPTS):
            pk, state = self._load(sid, token); sk = 'REQUEST#'+request_id
            request = self.store.get(pk, sk); now = self._now()
            if not request or request['status'] != 'processing' or not isinstance(claim_token, str) or not hmac.compare_digest(request['claim_hash'], _hash(claim_token)) or request['lease_until'] <= now or state['active_request'] != request_id:
                _bad(409, 'claim_lost', 'Request claim is no longer valid')
            if not isinstance(new_state, dict) or new_state.get('session_id') != sid or new_state.get('state_version') != state['state']['state_version'] + 1:
                _bad(400, 'invalid_request', 'Invalid new state')
            _bounded(new_state, 96 * 1024)
            _bounded(response, 64 * 1024)
            _bounded(turn, 16 * 1024)
            old_state, old_request = state['revision'], request['revision']
            state.update(revision=old_state+1, state=copy.deepcopy(new_state), active_request=None,
                         expires_at=now+DEFAULTS.session_ttl_seconds)
            request.update(revision=old_request+1, status='completed', response=copy.deepcopy(response), expires_at=state['expires_at'])
            turn_record = {'revision': 1, 'expires_at': state['expires_at'], 'turn': copy.deepcopy(turn)}
            try:
                self.store.transact([_op(pk, 'STATE', state, old_state), _op(pk, sk, request, old_request),
                                     _op(pk, 'TURN#'+request_id, turn_record, None)] + self._renew(pk, state, {sk, 'TURN#'+request_id}))
                return copy.deepcopy(response)
            except StoreConflict:
                continue
            except (ValueError, TypeError):
                _bad(400, 'invalid_request', 'Invalid result')
        _bad(409, 'conflict', 'Session changed; retry')

    def _finish_failure(self, pk, state, request_id, request, code):
        old_state, old_req = state['revision'], request['revision']
        state.update(revision=old_state+1, active_request=None,
                     expires_at=self._now()+DEFAULTS.session_ttl_seconds)
        response = {'code': code, 'message': 'Request could not be completed'}
        request.update(revision=old_req+1, status='failed', response=response,
                       expires_at=state['expires_at'])
        sk = 'REQUEST#'+request_id
        self.store.transact([_op(pk, 'STATE', state, old_state),
                             _op(pk, sk, request, old_req)] + self._renew(pk, state, {sk}))
        return response

    def fail(self, sid, token, request_id, claim_token):
        """Record a safe terminal failure without changing the current question."""
        for _ in range(MAX_CAS_ATTEMPTS):
            pk, state = self._load(sid, token)
            request = self.store.get(pk, 'REQUEST#'+request_id)
            if (not request or request['status'] != 'processing' or
                not isinstance(claim_token, str) or
                not hmac.compare_digest(request['claim_hash'], _hash(claim_token)) or
                request['lease_until'] <= self._now() or state['active_request'] != request_id):
                _bad(409, 'claim_lost', 'Request claim is no longer valid')
            try:
                return self._finish_failure(pk, state, request_id, request, 'temporary_failure')
            except StoreConflict:
                continue
        _bad(409, 'conflict', 'Session changed; retry')
