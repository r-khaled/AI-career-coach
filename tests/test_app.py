import json
import unittest
from unittest.mock import Mock, patch

import requests
from botocore.credentials import Credentials
from botocore.exceptions import NoCredentialsError

import app as web


class CareerCoachUITests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.payload = {"current_role": "Cloud Engineer", "goal": "AI Architect"}

    def test_form_loads_without_calling_aws(self):
        with patch.object(web, "request_career_plan") as call:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Personalized Career Plan Generator", response.data)
        call.assert_not_called()

    def test_missing_api_configuration_is_visible_and_does_not_send(self):
        with patch.object(web, "API_URL", ""), patch.object(web, "request_career_plan") as call:
            response = self.client.post("/", data=self.payload)
        self.assertIn(b"API_URL is not configured", response.data)
        call.assert_not_called()

    def test_required_fields_are_checked_before_sending(self):
        with patch.object(web, "request_career_plan") as call:
            response = self.client.post("/", data={"current_role": "Cloud Engineer"})
        self.assertIn(b"are required", response.data)
        call.assert_not_called()

    def test_upstream_errors_are_visible_in_html(self):
        with patch.object(web, "API_URL", "https://example.com/prod/generate-plan"), patch.object(
            web, "request_career_plan", side_effect=requests.exceptions.HTTPError("403 Forbidden")
        ):
            response = self.client.post("/", data=self.payload)
        self.assertIn(b"403 Forbidden", response.data)

    def test_success_renders_the_returned_plan(self):
        api_response = Mock(status_code=200)
        api_response.json.return_value = {
            "career_plan": "Development plan\n\n1. Internal courses\n- SDE-210: Serverless Development Patterns"
        }
        with patch.object(web, "API_URL", "https://example.com/prod/generate-plan"), patch.object(
            web, "request_career_plan", return_value=api_response
        ) as call:
            response = self.client.post("/", data=self.payload)
        self.assertIn(b"SDE-210: Serverless Development Patterns", response.data)
        call.assert_called_once_with(self.payload)


class IAMRequestTests(unittest.TestCase):
    def test_request_is_signed_for_execute_api_with_the_sent_body(self):
        session = Mock(region_name="us-east-1")
        session.get_credentials.return_value = Credentials("test-key", "test-secret", "test-session-token")
        payload = {"current_role": "Cloud Engineer", "goal": "AI Architect"}
        with patch.object(web.boto3, "Session", return_value=session), patch.object(
            web, "API_URL", "https://example.com/prod/generate-plan"
        ), patch.object(web.requests, "post") as post:
            web.request_career_plan(payload)
        sent = post.call_args.kwargs
        self.assertEqual(json.loads(sent["data"]), payload)
        self.assertIn("/us-east-1/execute-api/aws4_request", sent["headers"]["Authorization"])
        self.assertEqual(sent["headers"]["X-Amz-Security-Token"], "test-session-token")
        self.assertEqual(sent["headers"]["Content-Type"], "application/json")
        self.assertFalse(sent["allow_redirects"])

    def test_missing_credentials_never_send_a_request(self):
        session = Mock(region_name="us-east-1")
        session.get_credentials.return_value = None
        with patch.object(web.boto3, "Session", return_value=session), patch.object(web.requests, "post") as post:
            with self.assertRaises(NoCredentialsError):
                web.request_career_plan({})
        post.assert_not_called()

    def test_missing_region_never_sends_a_request(self):
        session = Mock(region_name=None)
        with patch.object(web.boto3, "Session", return_value=session), patch.object(web.requests, "post") as post:
            with self.assertRaisesRegex(ValueError, "AWS_DEFAULT_REGION"):
                web.request_career_plan({})
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
