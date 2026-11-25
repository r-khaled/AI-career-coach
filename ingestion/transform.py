"""Bedrock POST_CHUNKING hook. Use built-in chunking NONE with this function.

Only the configured source object and intermediate S3 prefix are accepted.
The runtime's boto3 is loaded lazily; local contract tests need no AWS connection.
"""
import hashlib
import json
import os
from urllib.parse import urlsplit

from ingestion.course_chunker import chunk_catalog

MAX_BATCH_BYTES = 2_000_000
MAX_INPUT_BATCHES = 20


def _allowed_key(key, prefix):
    if not isinstance(key, str) or not key.startswith(prefix) or ".." in key.split("/"):
        raise ValueError("Intermediate key is outside the configured prefix")
    return key


def transform(event, s3, *, bucket, prefix, source_uri):
    if not bucket or not prefix or not prefix.endswith("/") or not source_uri:
        raise ValueError("Configure bucket, nonempty trailing-slash prefix, and source URI")
    source = urlsplit(source_uri)
    if source.scheme != "s3" or not source.netloc or not source.path.strip("/"):
        raise ValueError("Source URI must name one S3 object")
    if source.netloc == bucket and source.path.lstrip("/").startswith(prefix):
        raise ValueError("Source must be outside intermediate storage")
    if event.get("version") != "1.0" or event.get("bucketName") != bucket:
        raise ValueError("Unexpected event version or intermediate bucket")
    # priorTask is documented as a string, not a stable enum; configuration selects POST_CHUNKING.
    files = event.get("inputFiles")
    if not isinstance(files, list) or not files:
        raise ValueError("inputFiles must be a nonempty list")
    output = []
    for file in files:
        location = file.get("originalFileLocation", {})
        if location.get("type") != "S3" or location.get("s3_location", {}).get("uri") != source_uri:
            raise ValueError("Unexpected source object; this function supports the catalog only")
        batches = file.get("contentBatches")
        if not isinstance(batches, list) or not 1 <= len(batches) <= MAX_INPUT_BATCHES:
            raise ValueError("Invalid number of content batches")
        parts, total_bytes = [], 0
        parsed_type = None
        for batch in batches:
            key = _allowed_key(batch.get("key"), prefix)
            response = s3.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            try:
                raw = body.read(MAX_BATCH_BYTES + 1)
            finally:
                body.close()
            total_bytes += len(raw)
            if total_bytes > MAX_BATCH_BYTES:
                raise ValueError("Parsed catalog exceeds lab input-size guard")
            contents = json.loads(raw)["fileContents"]
            if not isinstance(contents, list) or not contents:
                raise ValueError("Missing parsed content")
            for item in contents:
                content_type = item.get("contentType")
                if content_type not in {"TEXT", "PLAIN_TEXT"} or not isinstance(item.get("contentBody"), str):
                    raise ValueError("Only parsed TEXT or PLAIN_TEXT is supported")
                if parsed_type is not None and parsed_type != content_type:
                    raise ValueError("Mixed parsed content types need an explicit normalization policy")
                parsed_type = content_type
                # Refuse to silently discard inherited chunk metadata.
                if item.get("contentMetadata"):
                    raise ValueError("Unexpected preexisting chunk metadata; review merge policy")
                parts.append(item["contentBody"])
        chunks = chunk_catalog("\n\n".join(parts))
        for chunk in chunks:
            chunk["contentType"] = parsed_type
        encoded = json.dumps({"fileContents": chunks}, ensure_ascii=False).encode()
        digest = hashlib.sha256(source_uri.encode() + str(event.get("ingestionJobId", "")).encode() + encoded).hexdigest()
        output_key = f"{prefix}custom/{digest}.json"
        s3.put_object(Bucket=bucket, Key=output_key, Body=encoded, ContentType="application/json")
        output.append({
            "originalFileLocation": location,
            "fileMetadata": file.get("fileMetadata", {}),
            "contentBatches": [{"key": output_key}],
        })
    return {"outputFiles": output}


def lambda_handler(event, context):
    import boto3
    return transform(
        event, boto3.client("s3"),
        bucket=os.environ["INTERMEDIATE_BUCKET"],
        prefix=os.environ["INTERMEDIATE_PREFIX"],
        source_uri=os.environ["CATALOG_SOURCE_URI"],
    )
