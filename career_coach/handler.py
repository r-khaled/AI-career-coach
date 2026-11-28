"""Thin API Gateway v2 adapter. Providers are injected for offline conformance."""
import base64
import copy
import hashlib
import json
import os
import re
import time
import uuid

from career_coach.errors import APIError


def event_path(event):
    path = event.get("rawPath") or event.get("requestContext", {}).get("http", {}).get("path") or "/generate-plan"
    stage = event.get("requestContext", {}).get("stage")
    if stage and stage != "$default" and path.startswith("/" + stage + "/"):
        path = path[len(stage) + 1:]
    return path


class Application:
    def __init__(self, sessions, wizard=None, jobs=None, model=None):
        self.sessions = sessions
        self.wizard = wizard
        self.jobs = jobs
        self.model = model

    def handle(self, event):
        request_id = str(event.get("requestContext", {}).get("requestId") or uuid.uuid4().hex)
        try:
            method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
            path = event_path(event)
            headers = {key.lower(): value for key, value in event.get("headers", {}).items()}
            proof = headers.get("x-session-token", "")
            raw = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                raw = base64.b64decode(raw, validate=True).decode("utf-8")
            if len(raw.encode("utf-8")) > 16000:
                raise APIError(400, "invalid_input", "Request is too large")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise APIError(400, "invalid_input", "Expected a JSON object")
            if method == "POST" and path == "/v2/sessions":
                if body:
                    raise APIError(400, "invalid_input", "Session creation takes no fields")
                initial = self.wizard.initial_state() if self.wizard else None
                state, token = self.sessions.create(initial)
                # This signed server response is consumed by Flask, never browser JSON.
                return self.response(201, self.envelope(state),
                                     {"X-Session-Token": token})
            match = re.fullmatch(r"/v2/sessions/([A-Za-z0-9_-]+)(?:/(.*))?", path)
            if not match:
                raise APIError(404, "not_found", "Route not found")
            sid, action = match.groups()
            state = self.sessions.read(sid, proof)
            if method == "GET" and not action:
                return self.response(200, self.envelope(state))
            if method == "POST" and action in {"answers", "review"} and self.wizard:
                from career_coach.contracts import validate
                validate("answer-request" if action == "answers" else "review-request", body)
                rid = body.get("request_id") or ("review-" + hashlib.sha256(
                    json.dumps(body, sort_keys=True).encode()).hexdigest())
                claim = self.sessions.claim(sid, proof, rid, {"action": action, **body}, body["state_version"])
                if claim["status"] == "processing":
                    return self.response(202, {"status": "processing", "request_id": rid})
                if claim["status"] == "replay":
                    return claim["response"]
                if claim["status"] == "failed":
                    raise APIError(503, claim["response"]["code"], claim["response"]["message"])
                try:
                    if action == "answers":
                        if isinstance(getattr(self.model, "usage", None), list):
                            self.model.usage.clear()
                        updated = self.wizard.answer(state, body, self.model)
                    else:
                        updated = self.wizard.review(state, body)
                    result = self.response(200, self.envelope(updated))
                    return self.sessions.complete(sid, proof, rid, claim["claim_token"], updated, result,
                                                  {"action": action, "request_id": rid,
                                                   "question": state.get("current_question"), "submission": body,
                                                   "model_usage": copy.deepcopy(getattr(self.model, "usage", []))
                                                       if action == "answers" else []})
                except Exception:
                    if action == "answers":
                        print(json.dumps({"event": "intake_failed", "request_id": request_id,
                                          "model_usage": getattr(self.model, "usage", [])}))
                    try:
                        self.sessions.fail(sid, proof, rid, claim["claim_token"])
                    except Exception:
                        # Commit acknowledgement may have been lost. The same
                        # request ID will replay its durable receipt on retry.
                        pass
                    raise
            if self.jobs:
                if method == "POST" and action == "plans":
                    return self.response(202, self.jobs.create(sid, proof, body))
                job_match = re.fullmatch(r"jobs/([A-Za-z0-9_-]+)", action or "")
                if method == "GET" and job_match:
                    return self.response(200, self.jobs.status(sid, proof, job_match.group(1)))
                plan_match = re.fullmatch(r"plans/([A-Za-z0-9_-]+)(/revisions)?", action or "")
                if plan_match:
                    pid, revision_action = plan_match.groups()
                    if method == "POST" and revision_action:
                        return self.response(202, self.jobs.create(sid, proof, body, plan_id=pid))
                    if method == "GET" and not revision_action:
                        query = event.get("queryStringParameters") or {}
                        if set(query) - {"revision"}:
                            raise APIError(400, "invalid_input", "Unknown query parameter")
                        value = query.get("revision", "1")
                        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,5}", value):
                            raise APIError(400, "invalid_input", "Invalid revision")
                        return self.response(200, self.jobs.read_plan(sid, proof, pid, int(value)))
            raise APIError(404, "not_found", "Route not found")
        except APIError as error:
            return self.response(error.status, {"error": {"code": error.code, "message": error.message,
                                                         "request_id": request_id}})
        except (ValueError, UnicodeError):
            return self.response(400, {"error": {"code": "invalid_input", "message": "Invalid request",
                                                "request_id": request_id}})
        except Exception:
            return self.response(503, {"error": {"code": "temporarily_unavailable",
                                                "message": "Service temporarily unavailable",
                                                "request_id": request_id}})

    @staticmethod
    def public(state):
        return {"schema_version": state["schema_version"], "state_version": state["state_version"],
                "stage": state["stage"], "status": state["status"],
                "next_question": state.get("current_question"), "review": state.get("review")}

    @classmethod
    def envelope(cls, state):
        return {"session_id": state["session_id"], "state": cls.public(state), "profile": state.get("profile")}

    @staticmethod
    def response(status, body, headers=None):
        return {"statusCode": status, "headers": {"Content-Type": "application/json",
                "Cache-Control": "no-store", **(headers or {})}, "body": json.dumps(body, allow_nan=False)}


_application = None


def default_application():
    global _application
    if _application is None:
        from career_coach.sessions import SessionService
        from career_coach.store import DynamoStore
        from career_coach import wizard
        from career_coach.models import BedrockModel
        from career_coach.config import DEFAULTS
        from career_coach.jobs import JobService, SQSQueue
        from career_coach.plans import DynamoPlanStore
        from botocore.config import Config
        import boto3
        client = boto3.client("dynamodb", config=Config(connect_timeout=3, read_timeout=5,
                                                      retries={"total_max_attempts": 1}))
        sessions = SessionService(DynamoStore(client, os.environ["SESSIONS_TABLE"]))
        queue = SQSQueue(boto3.client("sqs", config=Config(connect_timeout=3, read_timeout=10,
                                                        retries={"total_max_attempts": 1})), os.environ["GENERATION_QUEUE_URL"])
        jobs = JobService(sessions, DynamoPlanStore(client, os.environ["DYNAMODB_TABLE"]), queue)
        _application = Application(sessions, wizard=wizard, jobs=jobs,
                                   model=BedrockModel(os.environ.get("INTAKE_MODEL_ID", DEFAULTS.model_id)))
    return _application


def dispatch_stream(event):
    """Trusted DynamoDB outbox input; API Gateway JSON cannot select this path."""
    from career_coach.jobs import RetryableJob
    failures = []
    for record in event.get("Records", []):
        sequence = record.get("dynamodb", {}).get("SequenceNumber", "")
        if record.get("eventName") not in {"INSERT", "MODIFY"}:
            continue
        try:
            image = record["dynamodb"]["NewImage"]
            pk, sk = image["pk"]["S"], image["sk"]["S"]
            if not pk.startswith("SESSION#") or not sk.startswith("JOB#"):
                continue
            service = default_application().jobs
            try:
                service.dispatch(pk[8:], sk[4:])
            except RetryableJob as busy:
                delay = getattr(busy, "retry_after_seconds", None)
                if delay is None or not 0 <= delay <= 15:
                    raise
                # Do not acknowledge a lease-update event before its owner can
                # have crashed. Waiting here preserves a durable retry trigger.
                time.sleep(delay + 0.05)
                service.dispatch(pk[8:], sk[4:])
        except Exception:
            failures.append({"itemIdentifier": sequence})
    return {"batchItemFailures": failures}


def lambda_handler(event, context):
    records = event.get("Records")
    if records and all(record.get("eventSource") == "aws:dynamodb" for record in records):
        return dispatch_stream(event)
    path = event_path(event)
    if path == "/generate-plan":
        from career_coach.legacy import lambda_handler as legacy
        return legacy(event, context)
    try:
        return default_application().handle(event)
    except Exception:
        return Application.response(503, {"error": {"code": "temporarily_unavailable",
            "message": "Service temporarily unavailable", "request_id": str(
                event.get("requestContext", {}).get("requestId") or uuid.uuid4().hex)}})
