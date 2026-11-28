import copy
import json
import unittest

from career_coach.errors import APIError
from career_coach.jobs import JobService, RetryableJob, SQSQueue
from career_coach.plans import MemoryPlanStore
from career_coach.sessions import SessionService
from career_coach.store import MemoryStore
from tests.test_planning import profile


class Clock:
    def __init__(self): self.value = 1000
    def __call__(self): return self.value


class Queue:
    def __init__(self): self.messages=[]; self.fail=False
    def send(self, sid, jid):
        self.messages.append((sid,jid))
        if self.fail: raise RuntimeError('send failed')


def setup():
    clock = Clock(); store = MemoryStore(); sessions = SessionService(store, clock=clock)
    state, proof = sessions.create({'stage':'review','status':'ready_to_generate','profile':profile()})
    queue = Queue(); plans = MemoryPlanStore()
    return clock, sessions, queue, plans, JobService(sessions, plans, queue, clock=clock), state['session_id'], proof


class JobTests(unittest.TestCase):
    def test_create_replay_conflict_and_status_are_scoped(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        first = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
        replay = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
        self.assertEqual(first['job_id'], replay['job_id'])
        self.assertEqual(len(queue.messages), 1)
        with self.assertRaises(APIError) as error:
            jobs.create(sid, proof, {'request_id':'r1','profile_version':2})
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(APIError): jobs.status(sid, 'wrong', first['job_id'])
        self.assertEqual(first['status'], 'queued')

    def test_dispatch_failures_retry_bounded_and_busy_has_delay(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        queue.fail=True
        job = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
        # Create and status may each attempt a failed dispatch.
        for _ in range(5):
            status = jobs.status(sid, proof, job['job_id'])
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(len(queue.messages), 3)
        other = jobs.create(sid, proof, {'request_id':'r2','profile_version':1})
        record = jobs._get(sid, other['job_id']); old=record['revision']
        record.update(revision=old+1, dispatch_pending=True, dispatch_lease_until=clock()+10)
        sessions.store.transact([{'pk':'SESSION#'+sid,'sk':'JOB#'+other['job_id'],'item':record,'expected_revision':old}])
        with self.assertRaises(RetryableJob) as exc: jobs.dispatch(sid, other['job_id'])
        self.assertEqual(exc.exception.retry_after_seconds, 10)

    def test_queue_body_contains_only_identifiers(self):
        class Client:
            def send_message(self, **kwargs): self.kwargs=kwargs
        client = Client(); SQSQueue(client, 'url').send('s','j')
        self.assertEqual(json.loads(client.kwargs['MessageBody']), {'session_id':'s','job_id':'j'})

    def test_stale_profile_is_observed_after_edit(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        job = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
        record = sessions.store.get('SESSION#'+sid,'STATE'); old=record['revision']
        record['revision'] += 1; record['state']['profile']['profile_version'] = 2
        sessions.store.transact([{'pk':'SESSION#'+sid,'sk':'STATE','item':record,'expected_revision':old}])
        self.assertTrue(jobs.status(sid,proof,job['job_id'])['stale_profile'])
        self.assertEqual(jobs._get(sid,job['job_id'])['profile']['profile_version'], 1)

    def test_expired_claim_retry_is_fenced(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        job = jobs.create(sid,proof,{'request_id':'r1','profile_version':1})
        first = jobs.claim(sid,job['job_id'])
        with self.assertRaises(RetryableJob): jobs.claim(sid,job['job_id'])
        clock.value += 211
        second = jobs.claim(sid,job['job_id'])
        self.assertNotEqual(first['claim_token'],second['claim_token'])
        with self.assertRaises(RetryableJob): jobs.set_stage(sid,job['job_id'],first['claim_token'],'generation')
