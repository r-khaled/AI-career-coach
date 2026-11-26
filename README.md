# AI Career Coach: understand, run, rebuild

A learning project based on [crafting-the-cloud/aws-ai-powered-application](https://github.com/crafting-the-cloud/aws-ai-powered-application). It accepts a current role and goal, retrieves evidence from 40 synthetic internal courses, generates a plan through Bedrock, and saves successful requests/results in DynamoDB.

<!-- INGESTION_STATUS_START -->
**Verified current state:** the stack is UPDATE_COMPLETE with fourteen resources. The Knowledge Base is ACTIVE on the existing OpenSearch collection/index; the latest real Sync indexed the catalog with zero document failures. The index contains 42 records (40 courses plus two contexts). All 13 labelled retrieval cases found their expected course IDs within top five; one out-of-scope case was also inspected. Exact-level/track/per-course-hour filter tests passed. KB configuration is connected to the application, but generation/end-to-end UI tests and application enforcement of strict plan constraints remain pending.
<!-- INGESTION_STATUS_END -->

## Read in this order

1. [Learning plan](docs/00-learning-plan.md): Python reference -> manual TypeScript/Console -> Terraform.
2. [Complete architecture](docs/01-architecture.md): system boundaries, Sync versus question-time, six Mermaid diagrams, roles, API and failure behavior.
3. [Course-aware chunking decision](docs/decisions/course-aware-chunking.md): actual measurements, alternatives and the selected policy.
4. [Code walkthrough](docs/02-code-walkthrough.md): Flask, inline application handler and packaged ingestion function.
5. [AWS identity and Region](docs/03-aws-access-and-region.md), then [cost controls](docs/04-cost-controls.md).
6. [Background runbook](docs/05-run-original-demo.md), [Ohio execution checkpoints](docs/08-guided-execution-us-east-2.md), and [ingestion deployment commands](docs/ingestion-deployment-plan.md).
7. [Reproducible setup and weekly Sync](docs/automation.md): preview/apply commands, bootstrap, reuse, permissions, monitoring and cleanup.
8. [Manual TypeScript rebuild](docs/06-manual-typescript-console.md), followed by [Terraform](docs/07-terraform-rebuild.md).

## What this revision contains

- Local Flask UI with configurable API URL and server-side IAM signing; no deployed frontend or employee identity system.
- CloudFormation baseline plus ingestion addition: fourteen resources after the integration corrections. The application handler stays inline; ingestion is a versioned ZIP with a separate execution role and seven-day log group.
- One 40-course Markdown source. Custom chunking extracts typed metadata and keeps each course intact; 40 course units and two context units are output in transport batches, not forty new source files.
- Default parser + built-in NONE + a POST_CHUNKING transformation is the selected KB configuration. Real parser/Sync and the initial retrieval/filter suite have passed; generation and full application constraints are not yet tested.
- KB, its service role/data source, embedding configuration and OpenSearch collection/index/policies are outside CloudFormation ownership. After the user delegated the failed Console remainder, the existing vector store was reused and KB/Sync/Retrieve completed through API.

## Lifecycle and historical evidence

An initial Ohio deployment rolled back because the caller lacked iam:TagRole; a later retry created the baseline successfully and the catalog was uploaded. The failed attempt is history, not the current state. An older us-east-1 review was not executed and must not be confused with Ohio.

Infrastructure/code deployment is separate from document updates and Sync. No GitHub Actions pipeline is required. The optional [setup command](docs/automation.md) bootstraps a fresh account and adds weekly AWS EventBridge Scheduler Sync inside the main stack. It reuses an already configured KB; the new RAG/Scheduler templates have not been deployed by this publication. No live schedule was enabled. The main template needs a bucket bootstrap before uploading its first versioned ingestion artifact.

CloudWatch stores execution logs; DynamoDB stores successful plan records; S3 stores source, intermediate and deployment objects under separate scopes. Saving conversations does not train model weights. A USD 5 target is not a configured spending cap, and no budget is created by this update. The existing OpenSearch collection remains billable independently of the stack; track its ownership and cleanup separately.

## Run the project

Use Python 3.12, AWS CLI v2, a supported Region and an IAM user/role CLI profile (not root). Examples below are Bash/WSL; use your own profile and account guard. See [required permissions and recovery](docs/automation.md) before provisioning billable resources.

```bash
git clone https://github.com/r-khaled/AI-career-coach.git
cd AI-career-coach
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
aws sts get-caller-identity --profile YOUR_PROFILE --region us-east-2
# For SSO: aws sso login --profile YOUR_PROFILE
python -m unittest discover -s tests -v
cfn-lint CloudFormation.yaml infrastructure/*.json

# Preview only: read AWS state, no uploads/provisioning/Sync.
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2
# Create/reconcile infrastructure, upload data, initial Sync + Retrieve, then enable weekly refresh.
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --apply --enable-schedule
# Inspect recent jobs; COMPLETE must also have zero document failures.
python -m ingestion.setup_lab status --profile YOUR_PROFILE --region us-east-2
```

First-time setup bootstraps the two S3 buckets, deploys the application/custom chunking, creates or reuses the KB, binds its ID and Lambda invocation permission, creates the new data source, runs the first Sync and a Retrieve smoke check, then binds the recurring Scheduler. The smoke check is not full retrieval evaluation or generation acceptance. No database migration framework is involved: CloudFormation creates the DynamoDB table; ingestion prepares the search index.

**EventBridge is part of the main stack.** `CloudFormation.yaml` includes the schedule/group/execution role/encrypted DLQ, conditional on real KB/data-source IDs. The live lab still has fourteen resources; applying this binding adds four, making eighteen. Weekly Sync defaults to Sunday 03:00 Africa/Cairo after opt-in. Change it with `--schedule-expression 'rate(7 days)'` and/or `--schedule-timezone UTC`; otherwise existing settings are preserved. A new account's KB/OpenSearch resources are managed by the companion RAG stack; already configured external KB resources are reused. Scheduler does not upload local edits or provision resources: it refreshes the uploaded source through Bedrock. [Full setup/scheduling guide](docs/automation.md).

After retrieval validation, start the local application with the main stack's ApiEndpoint. The caller needs `execute-api:Invoke` on ApiInvokeArn; see [AWS access](docs/03-aws-access-and-region.md). Model-generation permission and availability must also be verified in your destination account.

```bash
export AWS_PROFILE=YOUR_PROFILE
export AWS_DEFAULT_REGION=us-east-2
export API_URL="$(aws cloudformation describe-stacks --stack-name career-coach-lab --profile "$AWS_PROFILE" --region "$AWS_DEFAULT_REGION" --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue | [0]" --output text)"
python app.py
```

Open `http://localhost:5001`. Test a generated plan, citations, the DynamoDB record and Lambda logs separately; the release's earlier verified lab state covers ingestion/Retrieve, not end-to-end generation. Strict level/track/duration requirements remain pending in the UI/backend.

For data changes, rerun setup to validate/upload/Sync your local catalog. To Sync **already uploaded** source objects only:

```bash
python -m ingestion.setup_lab sync --profile YOUR_PROFILE --region us-east-2 --apply
```

## Moving accounts and model ARNs

The handler is unchanged. Its current foundation-model ARN uses the stack Region and model ID with an empty account field; it is not hardcoded to the original account. The KB ID, source buckets and Lambda/API resources must be rebuilt/rebound for a new account. If a future model choice uses an inference-profile ARN, use the destination account's ARN and matching IAM grants; the current FoundationModelId parameter accepts foundation-model IDs, not profile ARNs. Read the [migration notes](docs/automation.md#8-moving-to-a-different-account-or-region-modelkb-binding) before changing the working invocation.

No live Scheduler was activated during this repository publication. Arabic study material and deployment evidence remain local/ignored. Regional resource charges continue independently of schedule state; this code does not impose a spending cap.
