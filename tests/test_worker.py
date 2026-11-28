import copy
import base64
import gzip
import json
import unittest
from unittest.mock import patch

from career_coach import worker
from career_coach.planning import PlanningError
from tests.test_jobs import setup
from tests.test_planning import candidate, source


class FakePipeline:
    def __init__(self, fail=False): self.calls=0; self.fail=fail
    def generate(self, profile, *, plan_id, revision, change_request, stage_callback):
        self.calls += 1
        stage_callback('generation')
        if self.fail: raise PlanningError('safe')
        return {'plan':candidate({'profile':profile,'plan_id':plan_id,'revision':revision,'internal':source()}), 'trace':{'internal':{'records':[{'text':'catalog excerpt','rank':1}]}}}


class WorkerTests(unittest.TestCase):
    def test_complete_then_redelivery_does_not_regenerate_and_revision_is_immutable(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        job = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
        pipeline = FakePipeline(); runner=worker.JobWorker(jobs,pipeline)
        runner.process(sid,job['job_id']); runner.process(sid,job['job_id'])
        self.assertEqual(pipeline.calls, 1)
        self.assertEqual(jobs.status(sid,proof,job['job_id'])['status'],'completed')
        self.assertEqual(jobs.read_plan(sid,proof,job['plan_id'],1)['revision'],1)
        saved = plans.load(sid,job['plan_id'],1)
        trace = json.loads(gzip.decompress(base64.b64decode(saved['trace_gzip_b64'])))
        self.assertEqual(trace['internal']['records'][0]['text'], 'catalog excerpt')
        self.assertNotIn('trace_gzip_b64', jobs.read_plan(sid,proof,job['plan_id'],1))
        revision = jobs.create(sid,proof,{'request_id':'r2','profile_version':1,'base_revision':1,'change_request':'More practice'}, plan_id=job['plan_id'])
        runner.process(sid,revision['job_id'])
        self.assertEqual(jobs.read_plan(sid,proof,job['plan_id'],2)['revision'],2)
        self.assertEqual(jobs.read_plan(sid,proof,job['plan_id'],1)['revision'],1)

    def test_pipeline_failure_is_terminal(self):
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        job = jobs.create(sid,proof,{'request_id':'r1','profile_version':1})
        worker.JobWorker(jobs, FakePipeline(fail=True)).process(sid,job['job_id'])
        self.assertEqual(jobs.status(sid,proof,job['job_id'])['status'],'failed')

    def test_oversized_trace_fails_without_false_completion(self):
        class LargePipeline(FakePipeline):
            def generate(self, *args, **kwargs):
                result = super().generate(*args, **kwargs)
                result['trace'] = {'oversized':'x' * (3 * 1024 * 1024)}
                return result
        clock, sessions, queue, plans, jobs, sid, proof = setup()
        job = jobs.create(sid,proof,{'request_id':'r1','profile_version':1})
        worker.JobWorker(jobs, LargePipeline()).process(sid,job['job_id'])
        self.assertEqual(jobs.status(sid,proof,job['job_id'])['status'],'failed')
        self.assertIsNone(plans.load(sid,job['plan_id'],1))

    def test_early_recovery_rejects_wrong_goal_and_corrupt_trace(self):
        for corruption in ('goal', 'trace'):
            clock, sessions, queue, plans, jobs, sid, proof = setup()
            job = jobs.create(sid, proof, {'request_id':'r1','profile_version':1})
            claim = jobs.claim(sid, job['job_id'])
            plan = candidate({'profile':claim['profile'], 'plan_id':job['plan_id'], 'revision':1, 'internal':source()})
            if corruption == 'goal':
                plan['goal'] = 'Different goal'
            jobs.save_plan(sid, job['job_id'], claim['claim_token'], plan, {})
            if corruption == 'trace':
                plans._items[(sid, 'PLAN#'+job['plan_id']+'#REV#000001')]['trace_gzip_b64'] = 'invalid'
            clock.value += 211
            pipeline = FakePipeline()
            worker.JobWorker(jobs,pipeline).process(sid,job['job_id'])
            self.assertEqual(jobs.status(sid,proof,job['job_id'])['status'], 'failed')
            self.assertEqual(pipeline.calls, 0)

    def test_sqs_partial_batch_failures(self):
        class Runner:
            def process(self, sid, jid):
                if jid == 'bad': raise RuntimeError('unavailable')
        event = {'Records':[{'messageId':'a','body':json.dumps({'session_id':'s','job_id':'ok'})},
                            {'messageId':'b','body':json.dumps({'session_id':'s','job_id':'bad'})}]}
        with patch.object(worker, '_WORKER', Runner()):
            result = worker.lambda_handler(event,None)
        self.assertEqual(result, {'batchItemFailures':[{'itemIdentifier':'b'}]})
