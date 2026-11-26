# Deployment and local startup

[Documentation](README.md) · [Security](security.md) · [Operations](operations.md) · [Cost model](costs.md)

## Prerequisites

Use Python 3.12, AWS CLI v2 and an authenticated IAM user/role profile. The target account/Region must support Bedrock Knowledge Bases, the selected generation model, Titan Text Embeddings v2, OpenSearch Serverless and the CloudFormation Index resource. Root is unsupported for KB creation. Review [deployer permissions](security.md) and the persistent OpenSearch cost before applying.

Examples use Bash/WSL and `us-east-2` (Ohio). Replace YOUR_PROFILE and, optionally, supply `--expected-account YOUR_12_DIGIT_ACCOUNT_ID`. No account ID, access key or session token belongs in committed configuration. In PowerShell use the corresponding venv activation and environment-variable syntax.

```bash
git clone https://github.com/r-khaled/AI-career-coach.git
cd AI-career-coach
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# SSO profiles: authenticate first with aws sso login --profile YOUR_PROFILE
aws sts get-caller-identity --profile YOUR_PROFILE --region us-east-2
python -m unittest discover -s tests -v
cfn-lint CloudFormation.yaml infrastructure/*.json
```

The default stack name is `career-coach-lab`; the CLI accepts 3–31 lowercase letters/digits/hyphens starting with a letter. Bucket names include account/stack but not Region. Use different stack names for environments in two Regions of the same account to prevent global S3-name collisions.

## 1. Inspect the deployment plan

```bash
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --stack-name career-coach-lab
```

This validates the local catalog and performs read-only account/stack/KB checks. It saves a plan under ignored `.lab/setup/<session>/`, without uploads, change sets, Sync or scheduling. Confirm account, Region, buckets, model/KB bindings and intended steps. Read-only preview cannot prove all future provisioning permissions or inference access.

## 2. Provision and initialize

```bash
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --stack-name career-coach-lab --apply --enable-schedule
```

This is the first-use automation entry point. It creates/reconciles infrastructure, uploads the catalog, initializes knowledge and configures recurring refresh; the recipient does not need to repeat the Console wizard. It does not perform a relational database migration: CloudFormation creates the DynamoDB schema and Bedrock ingestion populates the search index.

The sequence is:

1. Validate the catalog/account/Region and describe the models. Preserve existing model and KB parameters unless explicitly overridden.
2. For a new stack, apply the two-bucket bootstrap revision. Never apply the bootstrap-only template to a completed full stack.
3. Build a deterministic ingestion ZIP, upload and verify its exact S3 version/hash, and apply the main template. Both source/intermediate buckets are private, encrypted and versioned.
4. Upload and verify `internal_courses.md`. This intentionally publishes the local source content. Source inclusion excludes code artifacts.
5. Validate/reuse a configured KB, or provision `<stack>-rag` with the OpenSearch index/role/KB and data source initially gated off.
6. Update the main stack's `KnowledgeBaseId`, including the Bedrock-to-hook permission, then enable/validate the data source. Partial setup can resume.
7. Start/wait for Sync, require COMPLETE and explicit zero failed documents, then perform a bounded filtered Retrieve smoke check.
8. Bind `KnowledgeBaseDataSourceId` and schedule parameters in the main stack. Its four conditional Scheduler resources become available only after both IDs are configured.

Every infrastructure update creates/describes a change set, saves/prints all changes, rejects removals/unexpected replacement and waits for a terminal event belonging to that execution request. Only the ingestion invoke permission can be replaced during explicit KB binding. Unspecified parameters keep previous values and no-op changes succeed. Failure preserves stack/events evidence; the tool does not delete a failed baseline.

Existing external KBs are not imported into CloudFormation. Reuse requires ACTIVE vector/OpenSearch Serverless, Titan v2/FLOAT32/1024 and one AVAILABLE source matching the catalog/default parser/NONE/hook/intermediate configuration. A mismatched or unbound same-name KB stops for inspection. An existing stack using a separate CloudFormation execution role requires explicit RAG provisioning and data-plane grants for that role.

## 3. Schedule configuration

`--enable-schedule` opts into Sunday 03:00 Africa/Cairo. Without a schedule flag, a new schedule is DISABLED and existing state/expression/timezone remain unchanged. Override frequency/timezone when required:

```bash
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --apply --enable-schedule --schedule-expression 'cron(0 2 ? * MON *)' --schedule-timezone UTC
```

Use `--disable-schedule` for reconciliation with scheduling disabled. Setup still reconciles data and Syncs before its final schedule update; use [schedule-only operations](operations.md#verify-scheduling) when an immediate maintenance disable is required. An already-enabled schedule continues running during later setup unless deliberately disabled beforehand.

Scheduler is part of the main CloudFormation stack. It calls StartIngestionJob for an **existing** KB/source; it is not the first-time provisioning mechanism. The CLI completes the first initialization immediately rather than waiting for the first weekly trigger. [Exact ingestion behavior](knowledge-pipeline.md).

## 4. Verify knowledge before generation

```bash
python -m ingestion.setup_lab status --profile YOUR_PROFILE --region us-east-2 --stack-name career-coach-lab
```

Inspect job statistics/failureReasons, transformed output and expected Course IDs. The provided catalog should produce 40 course units and two contexts. COMPLETE may coexist with failed documents; the CLI explicitly rejects that. Search can lag successful ingestion, so the smoke check retries reads for index refresh without automatically starting another ingestion job.

The automated smoke check filters on one known course ID. It verifies visibility/metadata, not complete coverage, ranking quality, prerequisites or plan correctness. Evaluate representative career-transition questions and exact course/prerequisite questions, inspect complete returned evidence and test filters before generation. Instructions and an SDK Retrieve example are in [knowledge pipeline](knowledge-pipeline.md#retrieval-acceptance).

## 5. Start Flask

Grant the local caller `execute-api:Invoke` on the main stack's ApiInvokeArn. IAM permission to deploy resources is distinct from permission to call the API. See [caller policy](security.md#local-caller).

```bash
export AWS_PROFILE=YOUR_PROFILE
export AWS_DEFAULT_REGION=us-east-2
export API_URL="$(aws cloudformation describe-stacks --stack-name career-coach-lab --profile "$AWS_PROFILE" --region "$AWS_DEFAULT_REGION" --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue | [0]" --output text)"
python app.py
```

Open `http://localhost:5001` and submit a current role and goal. API_URL is loaded at startup; restart after changing it. The Flask server signs the cloud request; do not put IAM credentials in the page. There is no deployed public frontend or automatic user sign-in.

## 6. Application acceptance

Confirm a real response contains plan text/citations, the DynamoDB item is written, and Lambda logs show successful execution. Test missing fields and an unsigned request separately. A proxy timeout may leave model work running; inspect before retrying. KB retrieval acceptance alone does not establish generation-model availability, citation serialization or persistence correctness. The current app does not enforce exact-level, strict-track or duration constraints.

## Parameters, outputs and portability

Main parameters are FoundationModelId, KnowledgeBaseId, IngestionCodeS3Key/IngestionCodeS3ObjectVersion, KnowledgeBaseDataSourceId and SyncScheduleState/SyncScheduleExpression/SyncScheduleTimezone. The setup command derives bucket/function values from Outputs and uses account/Region references. A FoundationModelId override must be a supported model ID, not an inference-profile ARN. Keep a working generation configuration unless intentionally changing it.

Read ApiEndpoint/ApiInvokeArn, bucket names, ingestion function ARN/role/log group, intermediate URI, DynamoDB table and conditional SyncScheduleName/SyncScheduleGroup/SyncDeadLetterQueueUrl/state/expression/timezone from Outputs. Companion RAG Outputs contain KB/source IDs, collection and role ARNs. Never reuse those resource IDs across accounts. [Region/model portability](security.md#region-and-model-portability).

CloudFormation provisioning is not a test result. Local tests/schema validation and the existing deployment's ingestion verification do not prove that a new account or scheduled target has passed live acceptance. Preserve the run evidence and verify each destination environment.
