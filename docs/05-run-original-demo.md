# Background runbook: infrastructure, knowledge and application

[README](../README.md) · [Ohio steps 1–11](08-guided-execution-us-east-2.md) · [Ingestion deployment commands](ingestion-deployment-plan.md)

## A. Local checks and preview

From Ubuntu/WSL repository root, run `.venv/bin/python -m unittest discover -s tests -v` and `.venv/bin/cfn-lint -t CloudFormation.yaml`. Tests use mock cloud clients; they do not establish actual model or KB behavior. Flask can render locally without API_URL, but submitting cannot generate a real plan until configuration and KB are complete.

## B. Preserve the existing baseline

Use the explicitly selected account/profile and us-east-2. The Ohio baseline exists, with source catalog uploaded. Do not execute the old us-east-1 review or recreate/delete the current stack. The current template includes two required ingestion artifact parameters: new-account deployment needs a bootstrap bucket and artifact upload first. It is not the old nine-resource single-file create recipe.

## C. Source and chunking decision: steps 6 / 6A

Source upload is separate from Sync. Inspect its current object version before re-uploading. Read the [decision](decisions/course-aware-chunking.md): default parser + NONE + custom course-aware Lambda, one source object, 40 course records and two contexts, typed metadata and no cross-course overlap. No tokenizer or retrieval benchmark result is implied by word measurements.

## D. Ingestion function update: step 6B

Follow the [versioned deployment plan](ingestion-deployment-plan.md). Build and test, upload ZIP to lambda-artifacts/, pass key/version with original parameter values preserved, create an UPDATE change set, describe/review the exact current-state changes (final template has fourteen resources), execute and wait for UPDATE_COMPLETE. Then perform the direct S3 fixture/Lambda test. Do not manually create a second function in Console.

## E. User creates KB: step 7

The user selects source object only, default parser, NONE, output transformation ARN and intermediate S3 URI. Create/inspect KB service role independently. Set Titan V2/1024/float index compatibility; review vector capacity/cost and encryption/network/data policies before creation. Do not select the entire bucket containing artifact/intermediate objects.

Sync and inspect actual parser/output/error records, then Retrieve before generation. Validate evidence and explicit filters; plan totals need application logic. A passing fixture is not passing ingestion or RAG.

## F. Connect and test: steps 8 / 9

Before real Sync, bind KnowledgeBaseId so the KB-scoped Lambda resource permission is valid. For any later KB replacement, create an UPDATE with KnowledgeBaseId=real ID, preserving FoundationModelId AND IngestionCodeS3Key/IngestionCodeS3ObjectVersion with UsePreviousValue=true. Review and execute; update both application environment and IAM retrieval scope together.

Set AWS_PROFILE=devops, AWS_DEFAULT_REGION=us-east-2 and API_URL from ApiEndpoint, then start `.venv/bin/python app.py`. Test signed success, invalid/missing fields and unsigned rejection; check citations, DynamoDB business record and CloudWatch execution logs. A timeout may leave Lambda running; inspect before retries. CORS is not IAM authorization.

## G. Evidence, failures and cleanup

Separate deployment, fixture, real Sync, Retrieve and end-to-end evidence. On a failed update inspect CloudFormation events and rollback; never delete a populated baseline to retry an ingestion addition. A reverse reviewed update can remove the three new resources. Source/artifact/intermediate object versions and Console-created vector resources require separate owned cleanup. The application's automatically created log group is outside the template; the ingestion log group is now inside it.

The USD 5 amount is a target, not an enforced cap. No budget is created here. Creating a KB does not guarantee its independent vector store will be removed with the KB. The TypeScript/Console and Terraform rebuild phases follow the working reference experiment.
