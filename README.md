# AI Career Coach: understand, run, rebuild

A learning project based on [crafting-the-cloud/aws-ai-powered-application](https://github.com/crafting-the-cloud/aws-ai-powered-application). It accepts a current role and goal, retrieves evidence from 40 synthetic internal courses, generates a plan through Bedrock, and saves successful requests/results in DynamoDB.

<!-- INGESTION_STATUS_START -->
**Verified current state:** the stack is UPDATE_COMPLETE with fourteen resources. The Knowledge Base is ACTIVE on the existing OpenSearch collection/index; the latest real Sync indexed the catalog with zero document failures. The index contains 42 records (40 courses plus two contexts). All 13 labelled retrieval cases found their expected course IDs within top five; one out-of-scope case was also inspected. Exact-level/track/per-course-hour filter tests passed. KB configuration is connected to the application, but generation/end-to-end UI tests and application enforcement of strict plan constraints remain pending.
<!-- INGESTION_STATUS_END -->

## Read in this order

1. [Learning plan](docs/00-learning-plan.md): Python reference -> manual TypeScript/Console -> Terraform.
2. [Complete architecture](docs/01-architecture.md): system boundaries, Sync versus question-time, five Mermaid diagrams, roles, API and failure behavior.
3. [Course-aware chunking decision](docs/decisions/course-aware-chunking.md): actual measurements, alternatives and the selected policy.
4. [Code walkthrough](docs/02-code-walkthrough.md): Flask, inline application handler and packaged ingestion function.
5. [AWS identity and Region](docs/03-aws-access-and-region.md), then [cost controls](docs/04-cost-controls.md).
6. [Background runbook](docs/05-run-original-demo.md), [Ohio execution checkpoints](docs/08-guided-execution-us-east-2.md), and [ingestion deployment commands](docs/ingestion-deployment-plan.md).
7. [Manual TypeScript rebuild](docs/06-manual-typescript-console.md), followed by [Terraform](docs/07-terraform-rebuild.md).

## What this revision contains

- Local Flask UI with configurable API URL and server-side IAM signing; no deployed frontend or employee identity system.
- CloudFormation baseline plus ingestion addition: fourteen resources after the integration corrections. The application handler stays inline; ingestion is a versioned ZIP with a separate execution role and seven-day log group.
- One 40-course Markdown source. Custom chunking extracts typed metadata and keeps each course intact; 40 course units and two context units are output in transport batches, not forty new source files.
- Default parser + built-in NONE + a POST_CHUNKING transformation is the selected KB configuration. Real parser/Sync and the initial retrieval/filter suite have passed; generation and full application constraints are not yet tested.
- KB, its service role/data source, embedding configuration and OpenSearch collection/index/policies are outside CloudFormation ownership. After the user delegated the failed Console remainder, the existing vector store was reused and KB/Sync/Retrieve completed through API.

## Lifecycle and historical evidence

An initial Ohio deployment rolled back because the caller lacked iam:TagRole; a later retry created the baseline successfully and the catalog was uploaded. The failed attempt is history, not the current state. An older us-east-1 review was not executed and must not be confused with Ohio.

Infrastructure/code deployment is separate from document updates and Sync. No GitHub Actions or cron job is required for the lab. The current template targets an existing baseline bucket: a fresh account requires bootstrap before uploading the versioned ingestion artifact.

CloudWatch stores execution logs; DynamoDB stores successful plan records; S3 stores source, intermediate and deployment objects under separate scopes. Saving conversations does not train model weights. A USD 5 target is not a configured spending cap, and no budget is created by this update. The existing OpenSearch collection remains billable independently of the stack; track its ownership and cleanup separately.
