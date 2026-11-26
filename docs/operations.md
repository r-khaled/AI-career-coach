# Operations

[Documentation](README.md) · [Deployment](deployment.md) · [Costs](costs.md)

## Verify deployment state

Read the target account/Region and stack status before operating. Code present in a repository is not proof that resources were deployed.

```bash
aws sts get-caller-identity --profile YOUR_PROFILE --region us-east-2
aws cloudformation describe-stacks --stack-name career-coach-lab --profile YOUR_PROFILE --region us-east-2
aws cloudformation list-stack-resources --stack-name career-coach-lab --profile YOUR_PROFILE --region us-east-2
```

The main stack has 14 baseline/ingestion resources before schedule binding and 18 after its Scheduler/group/role/DLQ are created. An early read-only check on 2026-11-26 found 14 resources and no Scheduler. A subsequent authorized setup deployment completed with UPDATE_COMPLETE and 18 resources, a successful Sync with zero document failures, and a passing filtered Retrieve smoke check. Scheduler is now ENABLED for Sunday 03:00 Africa/Cairo in that reference environment. Live target IDs, role policy/trust and encrypted fourteen-day DLQ were verified. The future weekly execution has not yet been observed. These are dated acceptance records, not guarantees about another account; pushing Git alone does not deploy resources.

## Verify scheduling

Read SyncScheduleName, SyncScheduleGroup and SyncScheduleState from main-stack Outputs. If these Outputs are absent, the source-ID binding has not provisioned Scheduler. If present, inspect the actual schedule rather than assuming a default:

```bash
aws scheduler get-schedule --name SCHEDULE_NAME_FROM_OUTPUTS --group-name GROUP_FROM_OUTPUTS --profile YOUR_PROFILE --region us-east-2
```

Check State=ENABLED, expression/timezone and target input KB/source IDs, role ARN, retry policy and DLQ. First-use setup is `python -m ingestion.setup_lab setup ... --apply --enable-schedule`; it performs initial Sync immediately and binds Scheduler afterward. Scheduled execution only refreshes an already uploaded source. An existing enabled schedule continues during later setup unless deliberately disabled.

For maintenance, create a reviewed main-stack UPDATE preserving all current parameters and override only SyncScheduleState=DISABLED. Do not remove KnowledgeBaseDataSourceId: that condition removes the schedule resources and the wrapper refuses unintended removal. The complete template also needs the current artifact key/version. Console disable is possible under EventBridge Scheduler but must be reconciled with CloudFormation parameters. Disabling future triggers does not cancel an active job or remove search capacity charges.

## Publish catalog changes

Edit and validate `internal_courses.md`, then run setup again to upload the versioned source and Sync. The source schema is strict and the hook supports one exact URI. Do not place source files in the intermediate bucket or ingest the whole artifacts bucket.

```bash
python -m unittest discover -s tests -v
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --apply
```

Matching ZIP/catalog bytes are reused after verification. Existing model/KB/schedule settings are preserved unless explicitly overridden. An initial upload performed outside the tool may need one new version to record its verified hash metadata.

## Manual Sync and status

```bash
# Refresh S3 content already uploaded; local edits are NOT uploaded by this action.
python -m ingestion.setup_lab sync --profile YOUR_PROFILE --region us-east-2 --apply
python -m ingestion.setup_lab status --profile YOUR_PROFILE --region us-east-2
```

Sync waits for an existing active ingestion job or starts a new one, then requires COMPLETE plus explicit zero failed documents. Inspect statistics/failureReasons and expected course IDs/output. The reference catalog yields 40 course units and two context units. A successful ingestion may precede search visibility; the CLI retries bounded filtered Retrieve calls without automatically re-ingesting. It does not call generation.

## Update ingestion code

Change the pure extractor/adapter deliberately, run contract/package tests and cfn-lint, then run setup. It builds the three-file deterministic ZIP and supplies a new hash-derived key plus exact S3 object version to CloudFormation. Overwriting content at an unchanged key does not by itself signal a Lambda code update. Source schema or embedding/chunking changes require a data migration/retrieval regression plan, not just a function-code release. Do not change the working model invocation while publishing an ingestion-only update.

## Evidence and monitoring

Each setup session stores the plan, package manifest/fixtures, paged change sets, stack/events snapshots, Sync job/statistics, retrieval smoke result and final Outputs in ignored `.lab/setup/<session>/`. Archive them according to your data policy. The repository excludes credentials, environment files, `.lab/` and `.local/`.

CloudWatch's ingestion group is `/aws/lambda/<stack>-ingestion-transform` with seven-day retention. Application logs are in its own Lambda log group with no explicit template retention. DynamoDB holds successful plans, not execution logs. Scheduler delivery metrics and the encrypted SQS DLQ reveal submission failures; accepted ingestion jobs can still fail documents and require independent status checks. No job-completion monitor/alarms are created by this revision.

Inspect API/Lambda errors and Bedrock usage together for timeouts. The 30-second API timeout is shorter than Lambda's 60 seconds; a 504 is not proof that model work stopped. Avoid automatic duplicate generation retries.

## Failure diagnosis

- IAM tag/pass-role failures: inspect CloudFormation Events and the **deployer** identity's grants, not runtime permissions. CAPABILITY_NAMED_IAM acknowledges named roles; it does not grant caller permissions.
- KB creation failure: inspect API/CloudTrail errors, Bedrock role trust, model access, collection/index existence and IAM/data/network policies. IAM global events are inspected in us-east-1. Do not repeat quick-create and accumulate collections.
- Source creation failure: verify separate source/intermediate buckets, correct prefix and hook ARN; check both KB-role invocation grants and the function's KB/account-scoped resource permission.
- Transformation failure: inspect Lambda logs and actual parsed JSON. Supported text types are TEXT/PLAIN_TEXT; schema, sizes, metadata and original URI must match the contract.
- COMPLETE with failed documents: read failureReasons and failed count. This is not accepted indexing success.
- Empty Retrieve: inspect ingestion/output/count/filter types and index refresh before altering chunking. Unsupported queries can return semantic neighbours; refusal is application logic.
- Scheduler creation rejects missing KnowledgeBaseId/DataSourceId: the universal target requires PascalCase input keys `KnowledgeBaseId` and `DataSourceId`, even though boto3 Bedrock calls use lower-camel-case keys. Wait for rollback completion, correct the payload and rerun setup against the same stack; do not delete the baseline.
- Local API_URL error: read ApiEndpoint and restart Flask. A GET to the POST-only endpoint is not an application test. A 403 can be unsigned/wrong-Region/denied execute-api invocation.

## Rollback and recovery

The wrapper refuses removals and unexpected replacements, saves proposals before execution and confirms a terminal event from the new request. No-op changes are accepted. An UPDATE_ROLLBACK_COMPLETE stack can be retried after fixing the cause; initial ROLLBACK_COMPLETE, REVIEW_IN_PROGRESS, failed rollback or in-progress states require deliberate inspection/recovery. The tool never deletes the baseline automatically.

For code rollback, create a reviewed UPDATE using the earlier ZIP key/object version while preserving current model/KB/source/schedule parameters. Do not apply bootstrap.json as rollback: it omits application resources. Reusing an external KB does not rewrite its ownership/configuration; update an owned RAG stack explicitly when needed.

## Cleanup

Disable future schedule triggers and inspect active jobs first. Keep the main stack's schedule disabled while deleting only the companion RAG stack you own; source deletion must finish while its index/role still exist. Reused external KB/collection resources need separate owner-approved deletion. Removing the main stack does not remove them or stop their bill.

Before deleting main infrastructure, decide retention/export for DynamoDB records and logs. Versioned buckets must have all versions/delete markers deliberately removed; emptying only current objects is insufficient. Review a deletion plan against exact account/Region/resource IDs. Main-stack cleanup includes its Scheduler/group/role/DLQ. There is no automatic teardown timer, and retained object/log versions may remain billable.
