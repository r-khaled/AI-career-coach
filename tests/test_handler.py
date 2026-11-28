import json
import unittest
from unittest.mock import Mock, patch

from career_coach import handler
from career_coach.sessions import SessionService
from career_coach.store import MemoryStore


def event(method, path, body=None, token=""):
    return {"rawPath": path, "requestContext": {"http": {"method": method}, "requestId": "test-http"},
            "headers": {"x-session-token": token}, "body": json.dumps(body or {})}


class SessionHandlerTests(unittest.TestCase):
    def test_named_stage_path_normalization_preserves_routes(self):
        e = event("POST", "/prod/v2/sessions")
        e["requestContext"]["stage"] = "prod"
        self.assertEqual(handler.event_path(e), "/v2/sessions")
        self.assertEqual(handler.Application(SessionService(MemoryStore())).handle(e)["statusCode"], 201)
        self.assertEqual(handler.event_path({"rawPath": "/prod/generate-plan", "requestContext": {"stage": "prod"}}), "/generate-plan")

    def test_create_resume_recreation_auth_expiry(self):
        clock = [1000]
        store = MemoryStore()
        service = SessionService(store, clock=lambda: clock[0])
        result = handler.Application(service).handle(event("POST", "/v2/sessions"))
        self.assertEqual(result["statusCode"], 201)
        data = json.loads(result["body"])
        self.assertNotIn("token", result["body"])
        self.assertNotIn("proof_hash", result["body"])
        path = "/v2/sessions/" + data["session_id"]
        token = result["headers"]["X-Session-Token"]
        fresh = handler.Application(SessionService(store, clock=lambda: clock[0]))
        self.assertEqual(fresh.handle(event("GET", path, token=token))["statusCode"], 200)
        self.assertEqual(fresh.handle(event("GET", path))["statusCode"], 403)
        clock[0] += 604801
        self.assertEqual(fresh.handle(event("GET", path, token=token))["statusCode"], 410)

    def test_default_store_wiring_does_not_call_aws(self):
        client = Mock()
        with patch.object(handler, "_application", None), patch.dict("os.environ", {
                "SESSIONS_TABLE": "sessions", "DYNAMODB_TABLE": "plans", "GENERATION_QUEUE_URL": "https://sqs.example/queue"}), \
                patch("boto3.client", return_value=client):
            application = handler.default_application()
            self.assertIs(application.sessions.store.client, client)
            self.assertEqual(application.sessions.store.table_name, "sessions")

    def test_unknown_routes_invalid_json_and_service_errors_are_safe(self):
        service = Mock()
        service.read.side_effect = RuntimeError("SECRET provider detail")
        result = handler.Application(service).handle(event("GET", "/v2/sessions/a", token="secret"))
        self.assertEqual(result["statusCode"], 503)
        self.assertNotIn("SECRET", result["body"])
        bad = event("POST", "/v2/sessions")
        bad["body"] = "[]"
        self.assertEqual(handler.Application(service).handle(bad)["statusCode"], 400)
