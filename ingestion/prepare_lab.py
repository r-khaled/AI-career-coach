"""Build local lab artifacts only. No boto3, AWS calls, uploads or deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from ingestion.course_chunker import chunk_catalog

ROOT = Path(__file__).resolve().parents[1]
def prepare(*, bucket, intermediate_bucket, account_id, region, stack_name, prefix="kb-intermediate/"):
    if bucket == intermediate_bucket:
        raise ValueError("Bedrock requires a separate transformation intermediate bucket")
    BUCKET, PREFIX = intermediate_bucket, prefix
    SOURCE = f"s3://{bucket}/internal_courses.md"
    FUNCTION_ARN = f"arn:aws:lambda:{region}:{account_id}:function:{stack_name}-ingestion-transform"
    raw = (ROOT / "internal_courses.md").read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    chunks = chunk_catalog(raw.decode("utf-8"))
    destination = ROOT / ".lab/ingestion-deployment"
    destination.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        (destination / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    object_arn = f"arn:aws:s3:::{BUCKET}/{PREFIX}*"
    bucket_arn = f"arn:aws:s3:::{BUCKET}"
    write("lambda-execution-s3-policy.json", {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": object_arn}
    ]})
    write("kb-role-transformation-policy.json", {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": [FUNCTION_ARN, FUNCTION_ARN + ":$LATEST"]},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": object_arn},
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": bucket_arn,
         "Condition": {"StringLike": {"s3:prefix": [PREFIX.rstrip("/"), PREFIX + "*"]}}},
    ]})
    write("lambda-environment.json", {
        "INTERMEDIATE_BUCKET": BUCKET, "INTERMEDIATE_PREFIX": PREFIX, "CATALOG_SOURCE_URI": SOURCE,
    })
    write("vector-ingestion-configuration.json", {
        "chunkingConfiguration": {"chunkingStrategy": "NONE"},
        "customTransformationConfiguration": {
            "intermediateStorage": {"s3Location": {"uri": f"s3://{BUCKET}/{PREFIX}"}},
            "transformations": [{"transformationFunction": {"transformationLambdaConfiguration": {"lambdaArn": FUNCTION_ARN}},
                                 "stepToApply": "POST_CHUNKING"}],
        },
    })
    write("catalog-batch.json", {"fileContents": [{"contentType": "TEXT", "contentBody": raw.decode(), "contentMetadata": {}}]})
    write("lambda-test-event.json", {
        "version": "1.0", "knowledgeBaseId": "LOCALTEST0", "dataSourceId": "LOCALTEST0",
        "ingestionJobId": "manual-test", "bucketName": BUCKET, "priorTask": "CHUNKING",
        "inputFiles": [{"originalFileLocation": {"type": "S3", "s3_location": {"uri": SOURCE}},
                        "fileMetadata": {}, "contentBatches": [{"key": PREFIX + "manual-test/catalog-batch.json"}]}],
    })
    write("retrieval-query.json", {"text": "Which internal course covers identity, authentication, and authorization, and what are its prerequisites?"})
    write("retrieval-unfiltered.json", {"vectorSearchConfiguration": {"numberOfResults": 5}})
    security_track = next(c["contentMetadata"]["track"] for c in chunks if c["contentMetadata"].get("course_id") == "SEC-201")
    write("retrieval-filter-example.json", {"vectorSearchConfiguration": {
        "numberOfResults": 5,
        "filter": {"andAll": [
            {"equals": {"key": "record_type", "value": "course"}},
            {"equals": {"key": "level", "value": "Intermediate"}},
            {"equals": {"key": "track", "value": security_track}},
            {"lessThanOrEquals": {"key": "duration_hours", "value": 20}},
        ]},
    }})  # 20 is an illustrative per-course cap, NOT a user-agreed business value.
    zip_path = destination / "course-transform.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ["__init__.py", "course_chunker.py", "transform.py"]:
            info = zipfile.ZipInfo("ingestion/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / "ingestion" / name).read_bytes())
    counts = {
        "course_chunks": sum(c["contentMetadata"]["record_type"] == "course" for c in chunks),
        "context_chunks": sum(c["contentMetadata"]["record_type"] == "catalog_context" for c in chunks),
    }
    preview = {"status": "local_only_not_synced", "source_sha256": source_hash,
               "policy": "course boundaries; zero cross-course overlap; built-in NONE plus custom Lambda",
               "token_counts": "not measured; word and character counts are not tokens",
               **counts, "fileContents": chunks}
    preview_path = ROOT / ".local-ar/experiments/course-chunking/course-aware-preview.json"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {"status": "prepared_locally_not_deployed", "source_sha256": source_hash,
                "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                "artifact_s3_key": "lambda-artifacts/" + hashlib.sha256(zip_path.read_bytes()).hexdigest() + ".zip",
                "region": region, "stack_name": stack_name, "bucket": bucket, "intermediate_bucket": intermediate_bucket, **counts}
    write("manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--intermediate-bucket", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack-name", required=True)
    args = parser.parse_args()
    prepare(bucket=args.bucket, intermediate_bucket=args.intermediate_bucket, account_id=args.account_id, region=args.region, stack_name=args.stack_name)
