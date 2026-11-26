"""Offline gross cost estimate for the documented architecture; never calls AWS."""
import argparse
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path

MODEL = Path(__file__).resolve().parents[1] / "docs/cost-model.json"


def estimate(config, assumptions):
    a = {k: Decimal(str(v)) for k, v in assumptions.items()}
    r = {k: Decimal(str(v)) for k, v in config["rates"].items()}
    if any(not v.is_finite() or v < 0 for v in a.values()):
        raise ValueError("All usage assumptions must be finite and nonnegative")
    n, million = a["requests"], Decimal(1_000_000)
    gb = Decimal(1024 ** 3)
    item_gb = n * a["item_kib"] * 1024 / gb
    log_gb = n * a["log_kib"] * 1024 / gb
    units = a["item_kib"].to_integral_value(rounding=ROUND_CEILING)
    parts = {
        "opensearch_compute": a["hours"] * (a["indexing_ocus"] * r["indexing_ocu_hour"] + a["search_ocus"] * r["search_ocu_hour"]),
        "opensearch_storage": a["vector_gb"] * r["vector_storage_gb_month"],
        "nova_generation": n * (a["input_tokens"] * r["nova_input_million_tokens"] + a["output_tokens"] * r["nova_output_million_tokens"]) / million,
        "titan_query_embeddings": n * a["query_tokens"] * r["titan_million_tokens"] / million,
        "titan_source_embeddings": a["syncs"] * a["source_tokens"] * r["titan_million_tokens"] / million,
        "application_lambda": n * (Decimal("0.5") * a["duration_seconds"] * r["lambda_gb_second"] + r["lambda_million_requests"] / million),
        "ingestion_lambda": a["syncs"] * (Decimal("0.25") * a["ingestion_seconds"] * r["lambda_gb_second"] + r["lambda_million_requests"] / million),
        "http_api": n * r["http_api_million_requests"] / million,
        "dynamodb_writes": n * units * r["dynamodb_million_wru"] / million,
        "dynamodb_storage": item_gb * r["dynamodb_storage_gb_month"],
        "application_logs": log_gb * (r["logs_ingest_gb"] + r["logs_archive_gb_month"]),
        "s3": a["s3_gb"] * r["s3_storage_gb_month"] + a["s3_puts"] * r["s3_put_thousand"] / 1000 + a["s3_gets"] * r["s3_get_thousand"] / 1000,
        "scheduler": a["syncs"] * r["scheduler_million_invocations"] / million,
    }
    total = sum(parts.values())
    return {"currency": "USD", "region": config["region"], "as_of": config["as_of"],
        "basis": config["basis"], "assumptions": {k: float(v) for k, v in a.items()},
        "breakdown": {k: round(float(v), 8) for k, v in parts.items()},
        "total_usd": round(float(total), 6), "excluded": config["excluded"]}


def main():
    config = json.loads(MODEL.read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    for key, default in config["assumptions"].items():
        parser.add_argument("--" + key.replace("_", "-"), type=Decimal, default=Decimal(str(default)))
    args = parser.parse_args()
    try:
        result = estimate(config, vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
