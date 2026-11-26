# Guided Ohio execution: baseline, ingestion addition, then manual KB

[README](../README.md) · [Architecture](01-architecture.md) · [Exact ingestion deployment commands](ingestion-deployment-plan.md)

<!-- INGESTION_STATUS_START -->
**Verified current state:** the stack is UPDATE_COMPLETE with fourteen resources. The Knowledge Base is ACTIVE on the existing OpenSearch collection/index; the latest real Sync indexed the catalog with zero document failures. The index contains 42 records (40 courses plus two contexts). All 13 labelled retrieval cases found their expected course IDs within top five; one out-of-scope case was also inspected. Exact-level/track/per-course-hour filter tests passed. KB configuration is connected to the application, but generation/end-to-end UI tests and application enforcement of strict plan constraints remain pending.
<!-- INGESTION_STATUS_END -->

## 1. Identity, names and evidence

Use devops and explicit us-east-2, stack career-coach-lab. Read real identifiers from Outputs. The baseline application function is career-coach-lab-handler with index.lambda_handler; the new function is career-coach-lab-ingestion-transform with ingestion.transform.lambda_handler. Local Flask independently needs AWS_PROFILE/AWS_DEFAULT_REGION and API_URL.

Each step states actor/action/expected evidence. Commands below are Bash/WSL from the repository root. Full versioned artifact and review commands are in the linked ingestion plan. CloudFormation substitutes AWS::Region and AWS::AccountId; no CI/CD is needed to provide them.

## 2. Template, change set and Outputs

YAML is desired infrastructure. Create-change-set computes an AWS-side proposal; describe-change-set reads it; execute-change-set changes resources. Outputs locate the resulting resources and do not perform setup. Deploy is a convenience operation that prepares and normally executes a change set; --no-execute-changeset separates review. Neither an output JSON nor the local evidence file is the editable source template.

## 3. Read-only preflight — assistant

```bash
aws sts get-caller-identity --profile devops --region us-east-2
aws cloudformation describe-stacks --profile devops --region us-east-2 --stack-name career-coach-lab
.venv/bin/cfn-lint -t CloudFormation.yaml
.venv/bin/python -m unittest discover -s tests -v
```

Inspect deployed template, KB list, source-object head and model access. Both generation Nova Lite and embedding Titan V2 were authorized during earlier checks; recheck availability before their actual use. Local tests are not real model inference or retrieval tests.

## 4. Baseline proposal — historical, completed

The initial CREATE change set proposed nine Add operations. It did not create application resources until execute-change-set. Preserve the history separately from the new UPDATE proposal.

## 5. Baseline execution — completed after retry

Initial execution failed at IAM role tagging and rolled back. After the user fixed the caller's scoped permissions, the empty failed stack was removed and a fresh reviewed retry succeeded: CREATE_COMPLETE, nine resources. Do not repeat that historical delete on a populated stack. The account/Region were checked again before this revision.

Console: Ohio -> CloudFormation -> career-coach-lab -> Events, Resources, Parameters and Outputs. The application still has the KB ID placeholder and cannot generate real plans.

## 6. Catalog upload — completed

The expanded 40-course catalog is already uploaded as internal_courses.md. Source bytes: 32,325. Uploading a source object is NOT Sync or indexing. Recheck the current object/version rather than uploading again unnecessarily. Keep code artifacts and intermediates out of source inclusion.

## 6A. Analyze data and choose chunking — local decision completed

Read the [decision record](decisions/course-aware-chunking.md). Course bodies, including heading/labels, are 77–97 words with median 82; these are not tokens. Metadata can be extracted from nine fixed fields. Choose source-level NONE plus our course-aware transformation, not a 90-word fixed chunker. It emits 40 intact course units and two context units without cross-course overlap. Alternative strategies have structural trade-offs, not measured inferior retrieval.

## 6B. Deploy ingestion transformation — completed and live-tested

Follow [the exact build/upload/review/execute/fixture commands](ingestion-deployment-plan.md). The first ingestion release had three Add operations. The current template also contains the dedicated intermediate bucket and exact KB-scoped Bedrock invoke permission; review each update against its actual current baseline, never apply a stale three-Add expectation. Read Outputs and inspect the separate function, role, scoped policies and seven-day log group. Run the direct fixture test and compare every output record with the local preview.

A successful fixture proves deployed ZIP/handler/S3 permissions. It does not prove the real Bedrock parser, a Sync, an indexed KB or retrieval quality. No KB is created in this step. Do not manually create a duplicate ingestion function in Console now that CloudFormation owns it.

## 7. KB creation and real ingestion — completed after user delegated the Console remainder

Select Ohio -> Bedrock -> Knowledge bases -> vector-store-based KB compatible with RetrieveAndGenerate. The Console attempt stopped on IAM policy-management permissions; after the user delegated completion, the API reused its existing collection/index and role. The actual completion record below supersedes the original manual instructions.

1. Name career-coach-lab-kb. Inspect/create a distinct Bedrock KB service role.
2. Select the original internal_courses.md object only; exclude kb-intermediate/ and lambda-artifacts/.
3. Default parser; built-in No chunking (NONE); select IngestionFunctionArn from Outputs as the transformation. Set IngestionIntermediateS3Uri as the intermediate location.
4. Inspect KB-role source read, intermediate read/write/cleanup/list, exact Lambda invocation, embedding invocation and vector access. Use the prepared transformation policy as an addition. This is not the Lambda execution role.
5. Titan Text Embeddings V2, 1024 dimensions, compatible floating-point index mappings. Inspect OpenSearch Serverless generation, capacity, standby choices, encryption, network and data policies and price before Create. A Bedrock budget alone does not cover OpenSearch.
6. Record KB/data-source IDs, service role, collection/index/mappings and lab-owned policies. Select source -> Sync and inspect job errors plus actual parser/output objects. Confirm 40 course records/metadata and preserved notes.
7. Use Retrieve before generation. Evaluate evidence completeness/ranks/duplicates and all tracks. Test exact-level/track/per-course filters separately; total-plan hours require application logic. This app does not yet apply those rules.

The existing vector store was reused; the assistant did not create a second collection. The user explicitly delegated completion after Console failure.

## 8. KB reference and invocation binding — completed before real Sync

Before Sync, set KnowledgeBaseId to the real ID so the Bedrock resource-based invoke permission matches the KB, as well as updating application configuration. This binding was executed. For a future KB replacement, set KnowledgeBaseId to the real ID while preserving FoundationModelId and BOTH ingestion artifact parameters using UsePreviousValue=true. Review, execute and wait for stack-update-complete. This updates the application's environment and retrieval IAM scope together; editing only Lambda env would leave policy drift.

## 9. Signed API test and preview — pending

Grant the caller execute-api:Invoke on ApiInvokeArn. Start Flask with AWS_PROFILE=devops, AWS_DEFAULT_REGION=us-east-2 and API_URL=ApiEndpoint from Outputs. Test a real plan and citations, the DynamoDB business record and application CloudWatch logs. Check missing fields and unsigned requests separately; a pre-KB configuration error is not a successful model test. A timeout can leave Lambda running, so inspect before retrying.

## 10. Learning path and production equivalents

Next rebuild manually with TypeScript and Console, then Terraform. Model/code/infrastructure changes are separate from source data/Sync changes. Production needs versioning, controlled ingestion, deterministic filters/validation, authentication, observability, idempotency, dependency pinning and cleanup ownership. RAG does not train weights.

## 11. Evidence, rollback and cleanup

Keep session evidence in ignored .lab/. Preserve initial failure and successful retry history; do not overwrite them with the ingestion release. For this release save baseline snapshots, artifact hash/version, reviewed change set, events, Outputs and fixture comparison. Inspect failures before retrying; never delete the baseline to fix an addition. A reviewed reverse update can remove the three additions; S3 object versions and manual vector resources remain separate cleanup work. End this release before KB creation; verify cloud state before saying it is ready.

## Completed ingestion retry: actual evidence

After the administrator attached the scoped iam:TagRole grant to the devops caller, a NEW UPDATE change set was created and reviewed: exactly IngestionLogGroup, IngestionLambdaExecutionRole and IngestionTransformationFunction as Add, no existing-resource changes/replacements. It was executed and the stack reached UPDATE_COMPLETE. The previously consumed failed change set was not re-executed.

Live verification: twelve active resources; original nine physical IDs unchanged; exact source object version/bytes unchanged; function Active/Successful with matching ZIP SHA, Python 3.12, 256 MB, 60 seconds and expected environment; trust/inline policies read and checked; source bucket public-access block remains enabled; log group seven-day retention and a real log stream; API route remains AWS_IAM. Full managed-policy inventory was unavailable to this caller (iam:ListAttachedRolePolicies); no extra audit permission was requested.

The deployed fixture returned exactly 42 records with 40 unique courses, two contexts and every body/metadata value equal to local output. It used intermediate S3 only. Zero KBs were found; no real Sync, embedding/indexing, Retrieve or generation test was performed. Failed-attempt and successful-retry evidence remain in separate ignored .lab/ session folders. Stop at step 7: user creates the KB using actual Outputs.


## KB Console creation failure: managed-policy permissions

The next Console attempt did not create a Knowledge Base, but it successfully created an ACTIVE OpenSearch Serverless collection and a 1024-dimension vector index, then created the KB service role and attached its S3 policy. CloudTrail IAM events in us-east-1 show the deployment user denied iam:GetPolicy at 18:28:19 UTC and iam:CreatePolicyVersion at 18:28:20 UTC on the generated FoundationModelPolicyForKnowledgeBase policy. No CreateKnowledgeBase event was found in the inspected Ohio window. The evidenced blocker is caller policy-management permission, not the chunking code or embedding dimensions.

Find the error: CloudTrail -> Event history -> us-east-1 (IAM global events) -> Event name GetPolicy or CreatePolicyVersion -> Event record -> errorCode/errorMessage. For collection/index provisioning use Ohio CreateCollection/CreateIndex events. This failed wizard stage did not invoke the transformation Lambda; its CloudWatch group is not the source of this creation error. Log Deliveries being unset does not disable CloudTrail management-event history.

An administrator must add narrowly scoped GetPolicy/CreatePolicyVersion permissions to the caller IAM user, not to a Lambda execution role. The prepared local policy is limited to generated AmazonBedrock policy names for this wizard suffix. Keep the existing collection/index and role identifiers; do not blindly repeat Quick create and accumulate billable collections. Complete/inspect the existing KB role before selecting it, because automatic setup stopped partway. Preserve this incident's evidence separately from the successful infrastructure release.

Before real Sync, verify intermediateStorage points to kb-intermediate/ (the review showed only bucket root), matching the deployed Lambda's allowed prefix. Also match Lambda invocation permissions to the actual function ARN/version selected ($LATEST in the review). These are subsequent configuration checks, not the proven cause of this creation failure.

## Actual delegated completion and corrections from real AWS contracts

KB creation succeeded on the existing collection/index, with Titan V2 / FLOAT32 / 1024. CreateDataSource then rejected same-bucket intermediate storage, so a reviewed stack UPDATE added a private, encrypted, versioned IngestionIntermediateBucket and changed only the ingestion function's environment/role scope. Source and code artifacts stayed in the original bucket. The reusable builder now requires --intermediate-bucket and rejects source/intermediate equality.

The first two ingestion attempts reported COMPLETE but had one failed document: the exact $LATEST invocation ARN and a separate Bedrock service resource permission were needed. A reviewed update added IngestionBedrockPermission scoped to the account/KB and connected KnowledgeBaseId. API integration had only a dynamic reference update to the same function ARN, verified unchanged. No function/data resource was replaced.

The next attempt reached Lambda and exposed actual parser contentType=PLAIN_TEXT instead of the fixture's TEXT. The adapter now accepts both and preserves the input type; a regression test verifies all text/metadata. A new hash/version ZIP was deployed via an ingestion-function-code-only UPDATE. Eighteen local tests and cfn-lint pass.

Final Sync: one source scanned and indexed, zero failed documents, no failureReasons. The real transformed batch contains exactly 40 course units plus two contexts, with every body/metadata value matching local output. Index _count is 42. First Retrieve was empty immediately after Sync; a subsequent read after index refresh returned courses. Do not mistake immediate search visibility for document loss or change chunking before inspecting count/refresh.

Fourteen English retrieval cases ran: all thirteen labelled cases found all required course IDs in top five. The unsupported-profession case still returned neighbors; refusal logic has not been implemented. Every returned course preserved its complete original body/metadata. SEC-201 prerequisite IDs were verified. Exact Intermediate/security-track/at-most-20-hour filters returned SEC-201; a zero-hour filter returned no courses. Twenty hours is a test value, not an agreed product default; total-plan validation and UI fields are still pending. No generation call was made.

The original catalog/version and collection/index were preserved. KB role trust is restricted to this KB ARN. Its broad wizard S3 policy was backed up and detached after a scoped replacement was verified; source/artifact reads are separated from intermediate Get/Put/Delete. These API-created KB resources remain outside CloudFormation ownership. The new delegated completion evidence supersedes older readiness checkpoints; earlier failures remain recorded for learning.

Runtime IAM cleanup: the accidental managed policy granting iam:TagRole on the ingestion role was inspected, backed up and detached ONLY from the application Lambda role. The deployment user attachment was left unchanged. Application runtime retains only its basic logging managed policy plus the declared Bedrock/DynamoDB inline policies.

## Optional reproducible setup and weekly Sync

See the [automation runbook](automation.md) for the read-only preview, guarded setup command and weekly EventBridge Scheduler resources inside the main CloudFormation stack. Existing configured KB resources are reused; new accounts use bucket bootstrap, a separate RAG stack, KB-ID binding, source creation, Sync and a Retrieve smoke check in that order. Weekly scheduling is code added by this release, not an already enabled live resource. No generation or strict application-constraint implementation is implied. Historical checkpoints above describe the earlier manual execution.

The first setup/Sync runs from the CLI; recurring Scheduler calls only StartIngestionJob after resources exist. Schedule state, expression and timezone are main-stack parameters. Moving accounts requires new KB/resource Outputs; the working foundation-model ARN is Region-derived with an empty account field. A future inference-profile ARN must belong to the destination account and have matching IAM grants. See the automation guide before changing model invocation.
