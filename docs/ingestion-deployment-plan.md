# Deploy the ingestion transformation into the existing stack

[Architecture](01-architecture.md) · [Decision](decisions/course-aware-chunking.md) · [Guided runbook: step 6B](08-guided-execution-us-east-2.md)

## 1. Boundary, actors and prerequisites

The assistant prepares documents/code, uploads the artifact, reviews and executes an UPDATE change set, then performs a direct Lambda fixture test. The user inspects Console resources and later creates the Knowledge Base. This release does NOT create KB/OpenSearch, start Sync, test retrieval, change budgets or rebuild the TypeScript application.

Use profile devops, explicit us-east-2 and stack career-coach-lab. Confirm identity, stack state, deployed template and source-object version first. The baseline bucket already exists and is versioned; it also hosts the code under a separate lambda-artifacts/ prefix. A fresh account needs a bootstrap bucket before artifact upload; this template is an update workflow, not a single-step fresh-account bootstrap.

The caller must have scoped artifact upload/read, CloudFormation update, IAM role/policy/tag management and iam:PassRole, Lambda creation/invocation and log-group management permissions. A successful validate-template does not prove these permissions. Do not broaden a caller policy automatically on AccessDenied; record the exact missing action/resource.

## 2. Local build, artifact version and reviewed UPDATE

The packaging helper makes no AWS calls; it uses the selected account/Region/stack and the bucket discovered from Outputs to build consistent environment values, policies, test fixtures, retrieval examples and a deterministic three-file ZIP. It contains ingestion/__init__.py, course_chunker.py and transform.py; no venv, credentials, tests or private docs.

```bash
# Run from the repository root in Ubuntu/WSL.
export LAB_REGION=us-east-2
export LAB_STACK=career-coach-lab
export AWS_PROFILE=devops
export AWS_DEFAULT_REGION="$LAB_REGION"
aws sts get-caller-identity --profile devops --region "$LAB_REGION"
LAB_ACCOUNT=$(aws sts get-caller-identity --profile devops --region "$LAB_REGION" --query Account --output text)
LAB_BUCKET=$(aws cloudformation describe-stacks --stack-name "$LAB_STACK" --profile devops --region "$LAB_REGION" --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue | [0]" --output text)
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/cfn-lint -t CloudFormation.yaml
LAB_INTERMEDIATE_BUCKET="${LAB_STACK}-kb-intermediate-${LAB_ACCOUNT}"
.venv/bin/python -m ingestion.prepare_lab --stack-name "$LAB_STACK" --region "$LAB_REGION" --account-id "$LAB_ACCOUNT" --bucket "$LAB_BUCKET" --intermediate-bucket "$LAB_INTERMEDIATE_BUCKET"
LAB_ARTIFACT_SHA=$(.venv/bin/python -c 'import json; print(json.load(open(".lab/ingestion-deployment/manifest.json"))["zip_sha256"])')
LAB_ARTIFACT_KEY="lambda-artifacts/$LAB_ARTIFACT_SHA.zip"
aws s3api put-object --profile devops --region "$LAB_REGION" --bucket "$LAB_BUCKET" --key "$LAB_ARTIFACT_KEY" --body .lab/ingestion-deployment/course-transform.zip --checksum-algorithm SHA256 --metadata "sha256=$LAB_ARTIFACT_SHA" > .lab/ingestion-deployment/artifact-upload.json
LAB_ARTIFACT_VERSION=$(.venv/bin/python -c 'import json; print(json.load(open(".lab/ingestion-deployment/artifact-upload.json"))["VersionId"])')
aws s3api head-object --profile devops --region "$LAB_REGION" --bucket "$LAB_BUCKET" --key "$LAB_ARTIFACT_KEY" --version-id "$LAB_ARTIFACT_VERSION" --checksum-mode ENABLED
aws cloudformation validate-template --profile devops --region "$LAB_REGION" --template-body file://CloudFormation.yaml
LAB_CHANGE_SET="ingestion-$(date -u +%Y%m%d-%H%M%S)"
aws cloudformation create-change-set --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK" --change-set-name "$LAB_CHANGE_SET" --change-set-type UPDATE --template-body file://CloudFormation.yaml --capabilities CAPABILITY_NAMED_IAM --parameters ParameterKey=FoundationModelId,UsePreviousValue=true ParameterKey=KnowledgeBaseId,UsePreviousValue=true ParameterKey=IngestionCodeS3Key,ParameterValue="$LAB_ARTIFACT_KEY" ParameterKey=IngestionCodeS3ObjectVersion,ParameterValue="$LAB_ARTIFACT_VERSION"
aws cloudformation wait change-set-create-complete --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK" --change-set-name "$LAB_CHANGE_SET"
aws cloudformation describe-change-set --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK" --change-set-name "$LAB_CHANGE_SET"
# STOP AND REVIEW against current state: source/intermediate must differ; inspect all changes/replacements before execute.
aws cloudformation execute-change-set --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK" --change-set-name "$LAB_CHANGE_SET"
aws cloudformation wait stack-update-complete --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK"
aws cloudformation describe-stacks --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK"
aws cloudformation list-stack-resources --profile devops --region "$LAB_REGION" --stack-name "$LAB_STACK"
```
Expected resources added: IngestionLogGroup, IngestionLambdaExecutionRole, IngestionTransformationFunction. The original nine logical/physical resources, application code and both original parameter values remain unchanged. Log group retention is seven days. The new role permits intermediate S3 Get/Put and writes to that log group only. This role does not need model, OpenSearch or DynamoDB actions.

Review the actual change-set ID, status, all changes and replacement flags. Stop on any unexpected existing-resource modification, delete or replacement, or on a different account/Region/template. Executing an accepted plan is separate from creating/describing it. Poll Events and stack state until UPDATE_COMPLETE; an accepted execute call alone is not success.

## 3. Direct deployed fixture test, not KB Sync

```bash
aws s3api put-object --profile devops --region "$LAB_REGION" --bucket "$LAB_INTERMEDIATE_BUCKET" --key kb-intermediate/manual-test/catalog-batch.json --body .lab/ingestion-deployment/catalog-batch.json --content-type application/json
aws lambda invoke --profile devops --region "$LAB_REGION" --function-name "$LAB_STACK-ingestion-transform" --payload fileb://.lab/ingestion-deployment/lambda-test-event.json .lab/ingestion-deployment/live-invoke.json
# Inspect FunctionError in CLI metadata AND outputFiles in live-invoke.json.
# Read the returned intermediate S3 key, then compare every record with local preview.
```
The test uploads a synthetic parsed batch under intermediate storage and invokes the function directly with matching source URI. LOCALTEST0 is a fixture identifier; no KB is created or called. Assert 42 records, exactly 40 unique course IDs and two catalog contexts; compare every contentBody and metadata value to the local preview. Preserve source-object version and original resource IDs. Inspect function State/LastUpdateStatus, handler/runtime/memory/timeout/environment/role, code hash and seven-day log retention. Confirm a log stream appears.

Inspect IAM: Lambda trust principal; Get/Put limited to kb-intermediate/*; log actions limited to the new group; no extra runtime privileges. Preserve request/output evidence locally. The fixture lives outside source inclusion; it is not evidence of the real parser's behavior or retrieval quality. Do not automatically start a Sync.

## 4. Evidence, failure and rollback

Save baseline template/state/resource IDs/source head, artifact SHA/key/version, exact change-set ID/review, events, final Outputs and fixture comparison under ignored .lab/. Never store secrets or credential files. Public docs use placeholders/Outputs; local Arabic docs can show this lab's concrete Console values.

If creation of the update fails, inspect ResourceStatusReason and automatic rollback. Preserve the baseline; never delete the stack to recover an ingestion addition. If the stack enters UPDATE_ROLLBACK_FAILED, diagnose that condition rather than continuing. To revert a completed update, prepare and review a new UPDATE using the saved baseline template and original parameter values; this removes only the three additions. Archive needed logs before removing their group. Uploaded S3 objects/versions and manual KB resources are separate from stack rollback and need explicit cleanup decisions.

## 5. User handoff and later tests

Read IngestionFunctionName, IngestionFunctionArn, IngestionExecutionRoleArn, IngestionLogGroupName and IngestionIntermediateS3Uri from Outputs. The user configures a vector-store KB in Ohio: source internal_courses.md only, default parser, built-in NONE, the output transformation ARN and intermediate URI. Use Titan Text Embeddings V2, 1024 dimensions, matching float index; inspect OpenSearch capacity/cost before Create.

Create/inspect the KB service role at that Console boundary: source read, intermediate access, exact Lambda invocation, embedding invocation and vector-store permissions including OpenSearch data/network controls. The prepared kb-role-transformation-policy.json is an ADDITION, not the full KB role. The infrastructure update does not silently attach policies to a future role.

After real Sync, inspect parser output, chunk coverage/metadata and errors. Then evaluate Retrieve top five before RetrieveAndGenerate, apply explicit metadata filters and record results. Finally update KnowledgeBaseId through CloudFormation while preserving the two artifact parameters with UsePreviousValue=true, so environment and retrieval IAM scope change together. API/UI end-to-end testing follows. Stop this release at verified Lambda readiness.

## Historical failed attempt and resolved scoped correction

The first ingestion UPDATE was executed after a three-Add review, then automatically rolled back because the caller lacked iam:TagRole specifically on the new ingestion role. The log-group creation was cancelled as a consequence, not a separate demonstrated log permission failure. All original resource IDs and the catalog version were verified unchanged. No ingestion function was deployed by this attempt.

The administrator added the required statement allowing iam:TagRole on arn:aws:iam::ACCOUNT_ID:role/STACK_NAME-ingestion-role to the deployment identity; keep the existing application-role statement. The prepared exact lab JSON is in the ignored release evidence directory. No iam:SimulatePrincipalPolicy grant is required for deploying this release. For a similar future failure, after the administrator confirms the change, create a NEW UPDATE change set using the already verified artifact key/version, review the same three additions and execute it. Do not execute the already-consumed change set again. Preserve failed-attempt evidence beside the retry.

## Verified successful retry

The new three-Add UPDATE completed successfully after the caller grant was corrected. A live fixture invocation matched all 42 records (40 unique courses and two contexts) to the local parser output, including typed metadata. Code hash, function configuration, role trust/inline policies, seven-day retention, log stream, source object preservation and the original API IAM route were checked. The original nine resource IDs remained unchanged. The release is ready for user-Console KB creation; real parser/Sync and retrieval quality are not yet validated. See current state in the guided runbook. No KB/vector store or audit permission expansion was performed.

## Real integration supersedes the initial same-bucket recipe

The first three-Add release is historical. The current template owns fourteen resources; two subsequent additions are the separate intermediate bucket and KB-scoped Bedrock Lambda permission. With the present template, bind KnowledgeBaseId BEFORE Sync so SourceArn matches the real KB. The source bucket still holds catalog and ZIP, while fixtures/parsed batches go to LAB_INTERMEDIATE_BUCKET. The adapter supports and preserves real PLAIN_TEXT as well as TEXT. KB/data source were completed through API after explicit user delegation; Sync and Retrieve passed, generation remains pending. Read the current guided runbook rather than replaying stale three-Add reviews.
