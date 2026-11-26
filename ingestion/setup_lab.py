"""Reproducible setup and manual Sync. Preview is read-only; --apply changes AWS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

import boto3
from botocore.exceptions import ClientError

from ingestion.course_chunker import chunk_catalog
from ingestion.prepare_lab import prepare

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "UPDATE_AFTER_KB_CREATION"
READY = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def stack_or_none(cfn, name):
    try:
        return cfn.describe_stacks(StackName=name)["Stacks"][0]
    except ClientError as error:
        if error.response["Error"]["Code"] == "ValidationError" and "does not exist" in str(error):
            return None
        raise


def values(stack, key):
    return {p[key + "Key"]: p[key + "Value"] for p in (stack or {}).get(key + "s", [])}


def review_changes(changes, allowed_replacements=()):
    """Never silently delete resources; only the KB-scoped permission may be replaced."""
    for item in changes:
        change = item["ResourceChange"]
        name = change["LogicalResourceId"]
        if change["Action"] not in {"Add", "Modify"}:
            raise RuntimeError(f"Refusing {change['Action']} of {name}; inspect the saved change set")
        if change.get("Replacement", "False") != "False" and name not in allowed_replacements:
            raise RuntimeError(f"Refusing replacement of {name}; inspect the saved change set")


def deploy(cfn, name, template, parameters, evidence, *, allowed_replacements=(), timeout=2700):
    before = stack_or_none(cfn, name)
    if before and before["StackStatus"] not in READY:
        raise RuntimeError(f"{name}: {before['StackStatus']}; resolve this stack before rerunning")
    change_name = "setup-" + uuid.uuid4().hex[:16]
    supplied = [{"ParameterKey": k, "ParameterValue": str(v)} for k, v in parameters.items()]
    existing = values(before, "Parameter")
    supplied += [{"ParameterKey": k, "UsePreviousValue": True} for k in existing if k not in parameters]
    response = cfn.create_change_set(StackName=name, ChangeSetName=change_name,
        ChangeSetType="UPDATE" if before else "CREATE", TemplateBody=template,
        Parameters=supplied, Capabilities=["CAPABILITY_NAMED_IAM"],
        Description="Reproducible AI Career Coach setup; reviewed by ingestion.setup_lab")
    change_id = response["Id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proposal = cfn.describe_change_set(ChangeSetName=change_id)
        if proposal["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
            break
        time.sleep(3)
    else:
        raise TimeoutError(f"Change set is still preparing: {change_id}")
    changes = list(proposal.get("Changes", []))
    page = proposal
    while page.get("NextToken"):
        page = cfn.describe_change_set(ChangeSetName=change_id, NextToken=page["NextToken"])
        changes.extend(page.get("Changes", []))
    proposal["Changes"] = changes
    write_json(evidence / (change_name + ".json"), proposal)
    if proposal["Status"] == "FAILED":
        reason = proposal.get("StatusReason", "")
        if before and ("didn't contain changes" in reason or "No updates are to be performed" in reason):
            cfn.delete_change_set(ChangeSetName=change_id)
            print(f"{name}: no changes")
            return before
        raise RuntimeError(f"{name}: {reason}; change set {change_id}")
    if proposal["Status"] != "CREATE_COMPLETE":
        raise RuntimeError(f"Unexpected change set status: {proposal['Status']}")
    review_changes(changes, allowed_replacements)
    print(json.dumps({"stack": name, "changes": [c["ResourceChange"] for c in changes]}, default=str))
    cfn.execute_change_set(ChangeSetName=change_id, ClientRequestToken=change_name)
    while time.monotonic() < deadline:
        current = stack_or_none(cfn, name)
        state = current["StackStatus"]
        events = cfn.describe_stack_events(StackName=name)
        # DescribeStacks can briefly return the previous successful revision after execution.
        # Require a terminal stack event from THIS request before reporting success/failure.
        terminal = any(e.get("ClientRequestToken") == change_name
            and e.get("ResourceType") == "AWS::CloudFormation::Stack"
            and e.get("LogicalResourceId") == name and e.get("ResourceStatus") == state
            for e in events.get("StackEvents", []))
        if not state.endswith("IN_PROGRESS") and terminal:
            write_json(evidence / (change_name + "-stack.json"), current)
            write_json(evidence / (change_name + "-events.json"), events)
            if state not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
                raise RuntimeError(f"{name}: {state}; inspect saved events. No stack was deleted by this tool.")
            print(f"{name}: {state}")
            return current
        time.sleep(10)
    raise TimeoutError(f"{name}: still running; inspect CloudFormation before rerunning")


def upload_if_changed(s3, bucket, key, body):
    digest = hashlib.sha256(body).hexdigest()
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
            raise
    else:
        # Verify existing bytes too: metadata alone is not proof of content integrity.
        if head.get("VersionId") not in {None, "null"} and head.get("Metadata", {}).get("sha256") == digest:
            stored = s3.get_object(Bucket=bucket, Key=key, VersionId=head["VersionId"])["Body"].read()
            if hashlib.sha256(stored).hexdigest() == digest:
                return head["VersionId"]
    result = s3.put_object(Bucket=bucket, Key=key, Body=body, Metadata={"sha256": digest},
        ServerSideEncryption="AES256", ChecksumAlgorithm="SHA256")
    version = result.get("VersionId")
    if not version or version == "null":
        raise RuntimeError("Expected a versioned bucket; refusing an unversioned deployment")
    stored = s3.get_object(Bucket=bucket, Key=key, VersionId=version)["Body"].read()
    if hashlib.sha256(stored).hexdigest() != digest:
        raise RuntimeError(f"Uploaded object digest mismatch: {key}")
    return version


def validate_kb(agent, kb_id, source, middle, function_arn):
    kb = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
    if kb["knowledgeBaseConfiguration"].get("type") != "VECTOR" or kb.get("storageConfiguration", {}).get("type") != "OPENSEARCH_SERVERLESS":
        raise RuntimeError("Existing KB must be VECTOR / OpenSearch Serverless")
    if kb["status"] != "ACTIVE":
        raise RuntimeError(f"Knowledge Base {kb_id}: {kb['status']}")
    vector = kb["knowledgeBaseConfiguration"].get("vectorKnowledgeBaseConfiguration", {})
    embedding = vector.get("embeddingModelConfiguration", {}).get("bedrockEmbeddingModelConfiguration", {})
    if not vector.get("embeddingModelArn", "").endswith("/amazon.titan-embed-text-v2:0") or embedding.get("dimensions", 1024) != 1024 or embedding.get("embeddingDataType", "FLOAT32") != "FLOAT32":
        raise RuntimeError("Existing KB does not match Titan v2 / 1024 / FLOAT32; refusing to change it")
    summaries = []
    for page in agent.get_paginator("list_data_sources").paginate(knowledgeBaseId=kb_id):
        summaries.extend(page["dataSourceSummaries"])
    matches = []
    for summary in summaries:
        data = agent.get_data_source(knowledgeBaseId=kb_id, dataSourceId=summary["dataSourceId"])["dataSource"]
        config = data.get("dataSourceConfiguration", {}).get("s3Configuration", {})
        if config.get("bucketArn", "").endswith(":::" + source) and config.get("inclusionPrefixes") == ["internal_courses.md"]:
            matches.append(data)
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one catalog data source, found {len(matches)}; inspect Console")
    data = matches[0]
    ingestion = data.get("vectorIngestionConfiguration", {})
    custom = ingestion.get("customTransformationConfiguration", {})
    functions = custom.get("transformations", [])
    expected_uri = f"s3://{middle}/kb-intermediate/"
    actual_function = functions[0].get("transformationFunction", {}).get("transformationLambdaConfiguration", {}).get("lambdaArn", "") if len(functions) == 1 else ""
    if data["status"] != "AVAILABLE" or ingestion.get("chunkingConfiguration", {}).get("chunkingStrategy") != "NONE" or ingestion.get("parsingConfiguration") or custom.get("intermediateStorage", {}).get("s3Location", {}).get("uri", "").rstrip("/") != expected_uri.rstrip("/") or actual_function.removesuffix(":$LATEST") != function_arn or functions[0].get("stepToApply") != "POST_CHUNKING":
        raise RuntimeError("Existing source differs from default parser + NONE + this transformation/intermediate bucket")
    return data["dataSourceId"]


def check_job(job):
    if job["status"] != "COMPLETE" or job.get("statistics", {}).get("numberOfDocumentsFailed") != 0:
        raise RuntimeError("Ingestion did not succeed: " + json.dumps(job, default=str))


def sync(agent, kb_id, source_id, evidence, timeout=1800):
    # Reuse an active ingestion job rather than repeatedly starting conflicting jobs.
    active = []
    for page in agent.get_paginator("list_ingestion_jobs").paginate(knowledgeBaseId=kb_id, dataSourceId=source_id):
        active += [j for j in page["ingestionJobSummaries"] if j["status"] in {"STARTING", "IN_PROGRESS", "STOPPING"}]
    if active:
        job_id = active[0]["ingestionJobId"]
    else:
        job_id = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=source_id,
            clientToken=uuid.uuid4().hex + uuid.uuid4().hex, description="AI Career Coach reproducible setup / manual Sync")["ingestionJob"]["ingestionJobId"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=source_id, ingestionJobId=job_id)["ingestionJob"]
        if job["status"] not in {"STARTING", "IN_PROGRESS", "STOPPING"}:
            write_json(evidence / ("sync-" + job_id + ".json"), job)
            check_job(job)
            print(f"Sync {job_id}: COMPLETE, zero document failures")
            return job
        time.sleep(10)
    raise TimeoutError(f"Sync {job_id} is still running; inspect status before starting another")


def retrieval_smoke(runtime, kb_id, evidence, timeout=300):
    chunks = chunk_catalog((ROOT / "internal_courses.md").read_text(encoding="utf-8"))
    course = next(c for c in chunks if c["contentMetadata"]["record_type"] == "course")
    expected = course["contentMetadata"]["course_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = runtime.retrieve(knowledgeBaseId=kb_id,
            retrievalQuery={"text": course["contentBody"]},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5,
                "filter": {"equals": {"key": "course_id", "value": expected}}}})
        write_json(evidence / "retrieval-smoke.json", result)
        if any(r.get("metadata", {}).get("course_id") == expected for r in result.get("retrievalResults", [])):
            print(f"Retrieve smoke check: {expected} found; no generation call")
            return result
        time.sleep(10)
    raise RuntimeError("Retrieve smoke check remained empty; inspect ingestion/index before re-Sync")


def deployment_principal(session, caller):
    arn = caller["Arn"]
    if ":user/" in arn:
        return arn
    if ":assumed-role/" in arn:
        role_name = arn.split(":assumed-role/", 1)[1].split("/")[0]
        return session.client("iam").get_role(RoleName=role_name)["Role"]["Arn"]
    raise RuntimeError("Use an IAM user or IAM role, not root, for Knowledge Base creation")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "sync", "status"])
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--stack-name", default="career-coach-lab")
    parser.add_argument("--expected-account", help="Optional account ID guard")
    parser.add_argument("--foundation-model-id", help="Preserve current model unless explicitly supplied")
    parser.add_argument("--apply", action="store_true", help="Allow AWS mutations (otherwise preview only)")
    schedule = parser.add_mutually_exclusive_group()
    schedule.add_argument("--enable-schedule", action="store_true", help="Opt in to weekly Sunday 03:00 Sync")
    schedule.add_argument("--disable-schedule", action="store_true", help="Explicitly disable the existing schedule")
    parser.add_argument("--schedule-timezone", help="IANA timezone; preserve existing or default to Africa/Cairo")
    parser.add_argument("--schedule-expression", help="Scheduler cron/rate expression; preserve existing or default to weekly")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,30}", args.stack_name):
        parser.error("stack-name must be 3-31 lowercase letters/digits/hyphens (S3 and AOSS limits)")
    if (args.enable_schedule or args.disable_schedule or args.schedule_timezone or args.schedule_expression) and args.action != "setup":
        parser.error("Schedule options apply only to setup")
    # Validate data before creating any paid resources.
    chunk_catalog((ROOT / "internal_courses.md").read_text(encoding="utf-8"))
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    if session.get_partition_for_region(args.region) != "aws":
        parser.error("This reference app currently supports the commercial aws partition only")
    caller = session.client("sts").get_caller_identity()
    account = caller["Account"]
    if args.expected_account and account != args.expected_account:
        raise RuntimeError(f"Account guard mismatch: authenticated to {account}")
    principal = deployment_principal(session, caller)
    cfn = session.client("cloudformation")
    current = stack_or_none(cfn, args.stack_name)
    outputs, parameters = values(current, "Output"), values(current, "Parameter")
    source = outputs.get("S3BucketName", f"{args.stack_name}-kb-data-{account}")
    middle = outputs.get("IngestionIntermediateBucketName", f"{args.stack_name}-kb-intermediate-{account}")
    function = outputs.get("IngestionFunctionArn", f"arn:aws:lambda:{args.region}:{account}:function:{args.stack_name}-ingestion-transform")
    kb_id = parameters.get("KnowledgeBaseId", PLACEHOLDER)
    schedule_state = "ENABLED" if args.enable_schedule else "DISABLED" if args.disable_schedule else parameters.get("SyncScheduleState", "DISABLED")
    schedule_timezone = args.schedule_timezone or parameters.get("SyncScheduleTimezone", "Africa/Cairo")
    schedule_expression = args.schedule_expression or parameters.get("SyncScheduleExpression", "cron(0 3 ? * SUN *)")
    evidence = ROOT / ".lab/setup" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    plan = {"account": account, "region": args.region, "stack": args.stack_name,
        "current_status": (current or {}).get("StackStatus", "NOT_CREATED"),
        "source_bucket": source, "intermediate_bucket": middle, "knowledge_base_id": kb_id,
        "steps": ["fresh stack only: bootstrap buckets", "upload versioned ZIP; deploy main stack", "upload catalog",
            "reuse configured KB or create RAG stack", "bind KB ID and invocation permission", "Sync and check document failures", "Retrieve smoke check; no generation", "bind data-source ID and add Scheduler to main stack (new schedules disabled unless opted in)"],
        "schedule": {"state": schedule_state, "expression": schedule_expression, "timezone": schedule_timezone},
        "apply": args.apply}
    write_json(evidence / "plan.json", plan)
    print(json.dumps(plan, indent=2))
    agent = session.client("bedrock-agent")
    ds_id = None
    pending_source = False
    if kb_id != PLACEHOLDER:
        owned_rag = stack_or_none(cfn, args.stack_name + "-rag")
        if owned_rag and values(owned_rag, "Output").get("KnowledgeBaseId") == kb_id and values(owned_rag, "Parameter").get("EnableDataSource", "false") == "false":
            pending_source = True
        else:
            ds_id = validate_kb(agent, kb_id, source, middle, function)
    if args.action == "status":
        if not ds_id:
            raise RuntimeError("No configured Knowledge Base yet")
        result = agent.list_ingestion_jobs(knowledgeBaseId=kb_id, dataSourceId=ds_id, maxResults=10)
        write_json(evidence / "recent-jobs.json", result)
        print(json.dumps(result, indent=2, default=str))
        return
    if not args.apply:
        print("Read-only preview finished. Re-run with --apply to execute. Evidence: " + str(evidence))
        return
    if args.action == "sync":
        if not ds_id:
            raise RuntimeError("Run setup before Sync")
        sync(agent, kb_id, ds_id, evidence)
        retrieval_smoke(session.client("bedrock-agent-runtime"), kb_id, evidence)
        return
    bedrock = session.client("bedrock")
    generation_model = args.foundation_model_id or parameters.get("FoundationModelId", "amazon.nova-lite-v1:0")
    for model_id in [generation_model, "amazon.titan-embed-text-v2:0"]:
        details = bedrock.get_foundation_model(modelIdentifier=model_id)["modelDetails"]
        if details.get("modelLifecycle", {}).get("status") != "ACTIVE":
            raise RuntimeError(f"Model {model_id} is not ACTIVE in {args.region}")
    s3 = session.client("s3")
    if current and current.get("RoleARN") and current["RoleARN"] != principal and kb_id == PLACEHOLDER:
        raise RuntimeError("The existing stack uses a separate CloudFormation execution role. Grant that role data-plane index access and provision the RAG template explicitly; this wrapper uses the current caller.")
    if not current:
        current = deploy(cfn, args.stack_name, (ROOT / "infrastructure/bootstrap.json").read_text(), {}, evidence)
    else:
        if current["StackStatus"] not in READY:
            raise RuntimeError(f"Resolve {current['StackStatus']} before deployment")
    # Bucket versioning and Region must be correct, including resumed bootstrap runs.
    for bucket in [source, middle]:
        location = s3.get_bucket_location(Bucket=bucket).get("LocationConstraint") or "us-east-1"
        location = "eu-west-1" if location == "EU" else location
        if location != args.region or s3.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
            raise RuntimeError(f"Bucket {bucket}: Region/versioning mismatch")
    manifest = prepare(bucket=source, intermediate_bucket=middle, account_id=account, region=args.region,
        stack_name=args.stack_name, output_dir=evidence / "package", preview_path=evidence / "chunks.json")
    artifact_version = upload_if_changed(s3, source, manifest["artifact_s3_key"], (evidence / "package/course-transform.zip").read_bytes())
    desired = {"IngestionCodeS3Key": manifest["artifact_s3_key"], "IngestionCodeS3ObjectVersion": artifact_version}
    if args.foundation_model_id:
        desired["FoundationModelId"] = args.foundation_model_id
    main_template = (ROOT / "CloudFormation.yaml").read_text()
    current = deploy(cfn, args.stack_name, main_template, desired, evidence)
    outputs = values(current, "Output")
    function = outputs["IngestionFunctionArn"]
    catalog_version = upload_if_changed(s3, source, "internal_courses.md", (ROOT / "internal_courses.md").read_bytes())
    rag_parameters = None
    if kb_id == PLACEHOLDER:
        # If our RAG stack already exists from a previous partial run, update/reuse it.
        # Never guess an external KB by name: refuse duplicate names instead.
        rag_name = args.stack_name + "-rag"
        rag = stack_or_none(cfn, rag_name)
        if not rag:
            for page in agent.get_paginator("list_knowledge_bases").paginate():
                if any(k["name"] == args.stack_name + "-kb" for k in page["knowledgeBaseSummaries"]):
                    raise RuntimeError("A KB with this name already exists outside the RAG stack; bind its ID in the main stack, then rerun")
        collection = "cc-" + hashlib.sha256((account + args.region + args.stack_name).encode()).hexdigest()[:20]
        rag_parameters = {"SourceBucket": source, "IntermediateBucket": middle, "TransformationArn": function,
             "DeploymentPrincipalArn": principal, "CollectionName": collection, "KnowledgeBaseName": args.stack_name + "-kb"}
        rag = deploy(cfn, rag_name, (ROOT / "infrastructure/knowledge-base.json").read_text(), rag_parameters, evidence)
        kb_id = values(rag, "Output")["KnowledgeBaseId"]
    # This also scopes the Bedrock service resource-based Lambda permission before Sync.
    current = deploy(cfn, args.stack_name, main_template, {**desired, "KnowledgeBaseId": kb_id}, evidence,
        allowed_replacements={"IngestionBedrockPermission"})
    if pending_source:
        deploy(cfn, args.stack_name + "-rag", (ROOT / "infrastructure/knowledge-base.json").read_text(),
            {"EnableDataSource": "true"}, evidence)
        ds_id = validate_kb(agent, kb_id, source, middle, function)
    if rag_parameters is not None:
        deploy(cfn, rag_name, (ROOT / "infrastructure/knowledge-base.json").read_text(),
            {**rag_parameters, "EnableDataSource": "true"}, evidence)
        ds_id = validate_kb(agent, kb_id, source, middle, function)
    sync(agent, kb_id, ds_id, evidence)
    retrieval_smoke(session.client("bedrock-agent-runtime"), kb_id, evidence)
    current = deploy(cfn, args.stack_name, main_template,
        {**desired, "KnowledgeBaseId": kb_id, "KnowledgeBaseDataSourceId": ds_id,
         "SyncScheduleState": schedule_state, "SyncScheduleTimezone": schedule_timezone,
         "SyncScheduleExpression": schedule_expression}, evidence)
    result = {"account": account, "region": args.region, "stack": args.stack_name,
        "knowledge_base_id": kb_id, "data_source_id": ds_id, "catalog_version": catalog_version,
        "artifact_version": artifact_version, "outputs": values(current, "Output"),
        "scheduler": {k: v for k, v in values(current, "Output").items() if k.startswith("Sync")}, "generation_tested": False}
    write_json(evidence / "result.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ClientError, RuntimeError, TimeoutError, ValueError) as error:
        raise SystemExit(str(error)) from error
