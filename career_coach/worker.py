"""SQS generation worker with fenced claims and partial batch failure responses."""
import json
import os

from .contracts import ContractError
from .jobs import JobService, RetryableJob, SQSQueue
from .planning import PlanningError, PlanningPipeline
from .plans import DynamoPlanStore, PlanConflict


class JobWorker:
    def __init__(self, jobs, pipeline):
        self.jobs, self.pipeline = jobs, pipeline

    def process(self, sid, jid):
        job = self.jobs.claim(sid, jid)
        if job is None:
            return
        token = job['claim_token']
        try:
            existing = self.jobs.plans.load(sid, job['plan_id'], job['plan_revision'])
            if existing is not None:
                if not self.jobs._reconcile_saved(sid, job):
                    raise PlanConflict('Saved plan cannot be reconciled')
                return
            else:
                result = self.pipeline.generate(job['profile'], plan_id=job['plan_id'],
                    revision=job['plan_revision'], change_request=job.get('change_request'),
                    stage_callback=lambda stage: self.jobs.set_stage(sid, jid, token, stage))
                self.jobs.save_plan(sid, jid, token, result['plan'], result['trace'])
            self.jobs.complete(sid, jid, token)
        except (PlanningError, PlanConflict, ContractError, ValueError):
            self.jobs.fail(sid, jid, token)


_WORKER = None


def _default_worker():
    import boto3
    from botocore.config import Config
    from .external import ExternalSearch
    from .models import BedrockModel
    from .retrieval import InternalRetriever
    from .sessions import SessionService
    from .store import DynamoStore
    config = Config(connect_timeout=3, read_timeout=10, retries={'total_max_attempts':1})
    session = boto3.Session()
    dynamo = session.client('dynamodb', config=config)
    store = DynamoStore(dynamo, os.environ['SESSIONS_TABLE'])
    sessions = SessionService(store)
    plans = DynamoPlanStore(dynamo, os.environ['DYNAMODB_TABLE'])
    queue = SQSQueue(session.client('sqs', config=config), os.environ['GENERATION_QUEUE_URL'])
    jobs = JobService(sessions, plans, queue)
    runtime = session.client('bedrock-agent-runtime', config=config)
    model_client = session.client('bedrock-runtime', config=Config(connect_timeout=3, read_timeout=25, retries={'total_max_attempts':1}))
    model = BedrockModel(os.environ['PLANNER_MODEL_ID'], client=model_client)
    internal = InternalRetriever(runtime, os.environ['KNOWLEDGE_BASE_ID'])
    secret_arn = os.environ.get('SERPER_SECRET_ARN', 'NOT_CONFIGURED')
    external_factory = None
    if secret_arn != 'NOT_CONFIGURED':
        secrets = session.client('secretsmanager', config=config)
        external_factory = lambda: ExternalSearch(secret_arn, secrets)
    return JobWorker(jobs, PlanningPipeline(model, internal, external_factory))


def lambda_handler(event, context):
    global _WORKER
    if _WORKER is None:
        _WORKER = _default_worker()
    failures = []
    for record in event.get('Records', []):
        try:
            body = json.loads(record['body'])
            if (not isinstance(body, dict) or set(body) != {'session_id','job_id'} or
                any(not isinstance(body[key], str) or not 1 <= len(body[key]) <= 128 for key in body)):
                raise ValueError('Invalid queue message')
            _WORKER.process(body['session_id'], body['job_id'])
        except Exception:
            failures.append({'itemIdentifier':record['messageId']})
    return {'batchItemFailures':failures}
