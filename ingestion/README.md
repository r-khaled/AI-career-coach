# Catalog-aware Bedrock ingestion (lab)

The S3 source remains one Markdown catalog. `course_chunker.py` emits one intact
course per chunk, with typed course metadata, plus separate catalog-wide notes.
It validates the current nine-field schema and rejects malformed, oversized, or
unknown records instead of silently truncating them. It does not use a tokenizer;
character guards are application safeguards, not embedding-model token limits.

`transform.py` implements the Bedrock custom transformation input/output contract.
Configure **default parser + built-in chunking NONE + POST_CHUNKING Lambda**.
The hook reads parsed batches from an intermediate S3 prefix and writes references
to the resulting batches. It does not call a model or change the original source.
The Lambda is separate from the career-plan API Lambda.

## Prepare locally

From the repository root (WSL):

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m ingestion.prepare_lab --bucket "$LAB_BUCKET" --intermediate-bucket "$LAB_INTERMEDIATE_BUCKET" --account-id "$LAB_ACCOUNT" --region "$LAB_REGION" --stack-name "$LAB_STACK"
```

Preparation makes no AWS calls. It writes a ZIP, policies, example event and batch,
and retrieval request files under ignored `.lab/ingestion-deployment/`; the local
chunk preview is under ignored `.local-ar/experiments/course-chunking/`.
The helper deploys nothing. Policy/example files derive from the selected stack Outputs and identity passed as arguments.
Review them before attaching them to a role. See docs/ingestion-deployment-plan.md for discovering these variables and the reviewed CloudFormation update. The template owns the ingestion role/function/log group, separate intermediate bucket and KB-scoped Bedrock invoke permission; do not create a duplicate function manually.

## Lambda configuration

- Runtime: Python 3.12; handler: `ingestion.transform.lambda_handler`.
- ZIP contains `ingestion/` at its root. boto3 is supplied by the Lambda runtime.
- `INTERMEDIATE_BUCKET`: the dedicated intermediate bucket (different from the source bucket).
- `INTERMEDIATE_PREFIX`: `kb-intermediate/` (trailing slash required).
- `CATALOG_SOURCE_URI`: exact S3 URI of `internal_courses.md`.
- Suggested lab settings: 256 MB, 60-second timeout.
- Source inclusion must select the catalog object, excluding intermediate files.

The execution role needs basic CloudWatch logging and Get/Put on the intermediate
prefix. The KB role separately needs invocation permission on this Lambda and its $LATEST ARN; the function also needs a resource-based grant to the exact Bedrock KB/account,
read/write/delete/list access scoped to intermediate storage, and its usual
source/model/vector-store permissions. Prepared JSON separates these grants.
SSE-KMS requires additional key permissions if enabled; the JSON assumes the lab's
normal S3-managed encryption. Never add credentials to environment variables.

## Limits and validation

This is a prototype for the current catalog schema, not a generic document parser
or a proven 10,000-record ingestion system. Parsed batches are bounded at 2 MB per
file (20 batches), records and context sections at 6,000 characters. Oversized
records fail pending a deliberate within-course subdivision policy. Parsed TEXT
must preserve the Markdown headings/fields. Unexpected existing chunk metadata
fails pending an explicit merge policy. A real Bedrock sync passed after preserving the observed PLAIN_TEXT content type; 42 indexed units and initial retrieval/filter cases were verified. Generation was not tested.

Live acceptance: inspect actual parser output, confirm every course and its typed
metadata in intermediate output, then call Retrieve before RetrieveAndGenerate.
Built-in chunking changes require a new data source. Prefer a separate evaluation
KB/index when comparing policies to prevent old chunks contaminating results.
Metadata enables filters; the application does not yet apply the agreed strict
constraints. Total-plan hours require deterministic application validation.

References: [Bedrock custom transformation](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-custom-transformation.html),
[AWS permissions example](https://github.com/aws-samples/amazon-bedrock-samples/blob/main/rag/knowledge-bases/features-examples/utils/knowledge_base.py).

## Optional reproducible setup and weekly Sync

See the [automation runbook](../docs/automation.md) for the read-only preview, guarded setup command and weekly EventBridge Scheduler resources inside the main CloudFormation stack. Existing configured KB resources are reused; new accounts use bucket bootstrap, a separate RAG stack, KB-ID binding, source creation, Sync and a Retrieve smoke check in that order. Weekly scheduling is code added by this release, not an already enabled live resource. No generation or strict application-constraint implementation is implied. Historical checkpoints above describe the earlier manual execution.

The first setup/Sync runs from the CLI; recurring Scheduler calls only StartIngestionJob after resources exist. Schedule state, expression and timezone are main-stack parameters. Moving accounts requires new KB/resource Outputs; the working foundation-model ARN is Region-derived with an empty account field. A future inference-profile ARN must belong to the destination account and have matching IAM grants. See the automation guide before changing model invocation.
