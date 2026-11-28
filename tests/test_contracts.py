import copy
import json
from pathlib import Path
import unittest

from career_coach.contracts import ContractError, validate
from career_coach.config import DEFAULTS, model_resource_arn

ROOT = Path(__file__).resolve().parents[1] / "career_coach"


class ContractTests(unittest.TestCase):
    def test_all_fixtures_validate(self):
        for path in sorted((ROOT / "fixtures").glob("*.json")):
            with self.subTest(contract=path.stem):
                validate(path.stem, json.loads(path.read_text(encoding="utf-8")))

    def test_rejects_nested_extra_fields_and_wrong_values(self):
        plan = json.loads((ROOT / "fixtures/career-plan.json").read_text(encoding="utf-8"))
        for mutate in (
            lambda p: p["phases"][0]["practice"].update(extra="secret"),
            lambda p: p["resources"][0].update(kind="imaginary"),
            lambda p: p["evidence"][0].update(retrieved_at="yesterday"),
        ):
            value = copy.deepcopy(plan)
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ContractError) as result:
                validate("career-plan", value)
            self.assertNotIn("secret", str(result.exception))

    def test_rejects_unknown_schema_and_nested_profile_fields(self):
        with self.assertRaises(ContractError):
            validate("../profile", {})
        profile = json.loads((ROOT / "fixtures/profile.json").read_text(encoding="utf-8"))
        profile["facts"] = [{"key": "x", "value": "a", "source_question_id": "q", "basis": "confirmed"}]
        with self.assertRaises(ContractError):
            validate("profile", profile)
        profile["facts"][0]["basis"] = "user_reported"
        profile["facts"][0]["unexpected"] = True
        with self.assertRaises(ContractError):
            validate("profile", profile)

    def test_policy_and_model_resource(self):
        self.assertEqual(DEFAULTS.session_ttl_seconds, 604800)
        self.assertEqual(DEFAULTS.search_max_requests, 3)
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/example"
        self.assertEqual(model_resource_arn(arn, "us-east-1", "123456789012"), arn)
        self.assertEqual(model_resource_arn("vendor.model-id", "us-east-1", "123456789012"),
                         "arn:aws:bedrock:us-east-1::foundation-model/vendor.model-id")

        for invalid in ("us.anthropic.model-v1:0", "arn:aws:s3:::bucket", "arn:aws:bedrock:us-east-1:123456789012:other/foo"):
            with self.subTest(model=invalid), self.assertRaises(ValueError):
                model_resource_arn(invalid, "us-east-1", "123456789012")

    def test_job_shape_and_safe_error(self):
        job = json.loads((ROOT / "fixtures/job.json").read_text(encoding="utf-8"))
        job.update(status="failed", stage="failed", stale_profile=True,
                   error={"code": "TEMPORARY_FAILURE", "message": "Please retry"})
        validate("job", job)
        job["error"]["detail"] = "provider details"
        with self.assertRaises(ContractError):
            validate("job", job)
        job.pop("error")
        job["state"] = "failed"
        with self.assertRaises(ContractError):
            validate("job", job)


if __name__ == "__main__":
    unittest.main()
