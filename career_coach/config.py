"""Versioned, explicit initial policy settings for the new application.

Values are proposed starting limits, not evidence of production readiness. The
legacy handler retains its own independent model settings.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PolicyV1:
    schema_version: str = "1.0"
    session_ttl_seconds: int = 7 * 24 * 60 * 60
    max_core_questions: int = 10
    max_followups: int = 4
    max_followups_per_axis: int = 2
    claim_lease_seconds: int = 60
    claim_max_recoveries: int = 2
    retrieval_results: int = 15
    retrieval_search_type: str = "SEMANTIC"
    retrieval_filter_key: str = "record_type"
    retrieval_filter_value: str = "course"
    prerequisite_max_depth: int = 10
    prerequisite_max_requests: int = 30
    search_max_requests: int = 3  # Includes retries.
    search_candidates_per_request: int = 5
    search_max_page_reads: int = 5
    page_max_redirects: int = 3
    page_max_bytes: int = 1_000_000
    page_timeout_seconds: int = 10
    intake_max_tokens: int = 512
    outline_max_tokens: int = 1024
    final_max_tokens: int = 2048
    repair_max_tokens: int = 4096
    max_repairs: int = 1
    temperature: float = 0.2
    model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0"


DEFAULTS = PolicyV1()


def model_resource_arn(model_id, region, account_id):
    """Return a foundation model ARN or preserve a typed Bedrock resource ARN.

    Inference profiles must be supplied as full ARNs to avoid treating a
    profile identifier as a foundation model. account_id is retained for the
    caller interface; foundation model ARNs do not contain an account ID.
    """
    if not isinstance(model_id, str) or not isinstance(region, str) or not region:
        raise ValueError("Model ID and region are required")
    if model_id.startswith("arn:"):
        pattern = (r"arn:[a-z0-9-]+:bedrock:[a-z0-9-]+:"
                   r"(?:[0-9]{12}:inference-profile/[A-Za-z0-9._:-]+|"
                   r"[0-9]{12}:application-inference-profile/[A-Za-z0-9._:-]+|"
                   r":foundation-model/[A-Za-z0-9._:-]+)")
        if not re.fullmatch(pattern, model_id):
            raise ValueError("Expected a Bedrock model or inference profile ARN")
        return model_id
    # Geographic inference-profile IDs require an explicit full ARN.
    if (not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9._:-]+", model_id)
            or model_id.split(".", 1)[0].lower() in
            {"us", "eu", "apac", "global", "jp", "au", "ca", "emea"}):
        raise ValueError("Expected a foundation model ID or full profile ARN")
    return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
