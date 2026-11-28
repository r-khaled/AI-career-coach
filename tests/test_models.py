import unittest
from unittest.mock import Mock

from career_coach.models import BedrockModel, ModelError


class ModelAdapterTests(unittest.TestCase):
    def test_profile_arn_passes_through_and_budgets_are_explicit(self):
        arn = "arn:aws:bedrock:us-east-2:123456789012:inference-profile/us.test"
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": '{"facts": []}'}]}},
                                        "usage": {"inputTokens": 10, "outputTokens": 4}}
        model = BedrockModel(arn, client)
        self.assertEqual(model.generate("analysis", {}, max_tokens=512), {"facts": []})
        self.assertEqual(client.converse.call_args.kwargs["modelId"], arn)
        self.assertEqual(client.converse.call_args.kwargs["inferenceConfig"], {"maxTokens": 512, "temperature": 0.2})
        self.assertEqual(len(model.usage), 1)

    def test_invalid_json_is_one_attempt_and_safe_failure(self):
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": "invalid"}]}}}
        with self.assertRaises(ModelError):
            BedrockModel("example-model", client).generate("analysis", {}, max_tokens=512)
        self.assertEqual(client.converse.call_count, 1)

    def test_failed_attempt_has_unknown_usage_and_safe_timing(self):
        client = Mock()
        client.converse.side_effect = RuntimeError("PRIVATE provider exception")
        model = BedrockModel("example-model", client)
        with self.assertRaises(ModelError):
            model.generate("outline", {}, max_tokens=1024)
        self.assertEqual(model.usage[0]["status"], "failed")
        self.assertIsNone(model.usage[0]["usage"])
        self.assertGreaterEqual(model.usage[0]["elapsed_seconds"], 0)
        self.assertNotIn("PRIVATE", str(model.usage))
