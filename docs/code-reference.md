# Code reference

[Documentation](README.md) · [Architecture](architecture.md)

## Repository layout

```text
app.py                         Flask request handling, IAM signing and presentation
CloudFormation.yaml            Main infrastructure and inline application Lambda
templates/index.html           Jinja form and generated-plan presentation
internal_courses.md            Source catalog: 40 courses, ten tracks
ingestion/
  __init__.py                  Package marker for importable Lambda handler
  course_chunker.py            Pure catalog validation and record extraction
  transform.py                 Bedrock transformation-event adapter and S3 I/O
  prepare_lab.py               Deterministic ZIP, manifest and configuration fixtures
  setup_lab.py                 Setup / Sync / status CLI and deployment checks
  README.md                    Package entry points and runtime/build boundary
infrastructure/
  bootstrap.json               First revision of the main stack: two S3 buckets
  knowledge-base.json          Companion RAG resources and gated data source
tests/                         UI/signing, chunking, packaging and setup tests
requirements.txt               Flask, requests and boto3
requirements-dev.txt           Runtime dependencies plus cfn-lint
scripts/estimate_cost.py        Offline usage-based cost calculation
```

The `.local/AR` and `.local/English` directories contain private archived material and are excluded from Git. `.lab/` holds generated deployment evidence; neither is application source.

## Local request handling: app.py

`API_URL` is read at process startup; restart Flask after changing it. `request_career_plan()` creates a boto3 session, requires a configured Region and credentials, serializes the exact JSON body, signs it with SigV4 for `execute-api`, and posts it with a 35-second timeout and redirects disabled. Frozen credentials keep the request signature consistent when using temporary sessions.

`index()` handles GET/POST `/`. GET renders the form. POST requires `current_role` and `goal`, calls the signed API, checks the response and displays upstream/configuration errors. `format_career_plan()` turns numbered text sections into the structure expected by Jinja; it is presentation parsing, not schema validation of the model's plan. `section_items` avoids collision with dictionary `.items()` in Jinja. The Flask process listens on port 5001; debug mode requires `FLASK_DEBUG=1`.

`templates/index.html` is the UI template. It is not the `index.py` handler created for Lambda. Only two business fields are submitted; there are no implemented level/track/duration controls or a citation inspector.

## Cloud backend: generated index.py

`CareerCoachFunction.Properties.Code.ZipFile` in `CloudFormation.yaml` contains the actual Python backend source. CloudFormation packages this inline source as `index.py`; `Handler: index.lambda_handler` resolves that module/function. There is no independently maintained backend `index.py` file in this repository.

The handler parses a proxy event's JSON `body`, requires current role/goal, optionally accepts `user_id` or generates a UUID, builds a career-development prompt, and calls `bedrock-agent-runtime.retrieve_and_generate`. It passes KNOWLEDGE_BASE_ID, MODEL_ARN, top five retrieval results and `maxTokens=800`. It requests internal courses, skills, timeline and additional resources; the prompt is not deterministic enforcement of internal-only or duration/prerequisite rules.

On success, the handler saves user_id/timestamp/current_role/goal/career_plan/citations with DynamoDB `PutItem`, then returns JSON and Content-Type/CORS headers. Missing fields return 400. Bedrock/configuration/persistence exceptions return 500. No plan is saved before model success, and persistence failure can occur after model charges. UTC timestamps have no timezone suffix. The current implementation does not handle every proxy-body format or idempotent retries; citation numeric values need an end-to-end serialization check.

## Pure extraction: ingestion/course_chunker.py

`chunk_catalog(text)` normalizes line endings, requires a catalog-version declaration and detects `### Course ID: TRACK-NNN` record boundaries. It validates unique IDs, exactly nine single-line fields, allowed levels, the duration grammar and known prerequisite IDs. Text outside the supported structure is rejected instead of silently discarded.

Each course body includes its heading and complete fields. Metadata includes catalog_version, parsed_source_sha256, record_type, course_id/course_name, track, level/level_rank, duration_hours, has_prerequisites and nonempty prerequisites. Catalog preamble and final notes become separate context records. Current output is 40 courses plus two contexts. Each course/context is capped at 6,000 characters as an application guard, not a token/model limit.

The module uses only the standard library and performs no AWS calls. It defines evidence boundaries, not file-upload batching or retrieval. [Schema and decision](knowledge-pipeline.md).

## Runtime hook: ingestion/transform.py

`lambda_handler()` creates an S3 client and supplies environment variables INTERMEDIATE_BUCKET, INTERMEDIATE_PREFIX and CATALOG_SOURCE_URI to `transform()`.

`transform()` checks event version 1.0, the configured intermediate bucket, the exact original source URI and a nonempty list of input files/batches. Keys must stay under the configured prefix and may not traverse with `..`. It reads Bedrock's parsed JSON batches, accepts TEXT or observed PLAIN_TEXT, requires a consistent content type and rejects unexpected inherited chunk metadata pending an explicit merge policy.

The aggregate parsed input guard is 2,000,000 bytes per source file with at most 20 transport batches. The complete catalog is reassembled before splitting, so course boundaries can span incoming batches. It calls the pure extractor, preserves the input content type, writes transformed JSON under `kb-intermediate/custom/<digest>.json`, and returns S3 batch references in `outputFiles`, preserving original location/file metadata. Input streaming bodies are closed. Failures propagate to ingestion rather than writing partial evidence silently.

The hook requires intermediate GetObject/PutObject and execution logs only. It does not read the original source directly, invoke Titan, write OpenSearch, retrieve courses or serve user requests. Bedrock's service role owns those responsibilities.

## Packaging: ingestion/prepare_lab.py

`prepare()` validates the source, rejects identical source/intermediate buckets and writes IAM/configuration examples, a manual event fixture, parsed catalog fixture, retrieval/filter examples, a local preview and manifest. Output-directory/preview overrides allow setup sessions to be isolated. The default personal preview is under `.local/AR/experiments/`; generated package files are under `.lab/`.

The ZIP includes only `ingestion/__init__.py`, `course_chunker.py` and `transform.py`. Fixed ZIP timestamps and file modes make identical source produce identical ZIP bytes. The manifest records source/ZIP SHA-256, unit counts and `lambda-artifacts/<sha256>.zip`. Setup/build modules are not deployed in the Lambda ZIP; boto3 is supplied by the Python Lambda runtime.

## Infrastructure CLI: ingestion/setup_lab.py

`main()` exposes `setup`, `sync` and `status`. Preview is read-only unless `--apply` is supplied. It validates the catalog, account guard, Region/stack name and IAM identity, reads the current stack, and validates an already configured KB's source/model/hook contract before reuse. It describes models before paid provisioning but does not prove model inference access.

`deploy()` creates and pages through a change set, preserves unspecified parameters, saves/prints the proposal, refuses removals/unexpected replacements, executes and waits for a terminal event bearing the same request token. This avoids mistaking a previous successful revision for completion of a new update. Only the KB-scoped ingestion permission may be replaced during explicit binding. No-op changes succeed; failures save events and never auto-delete the baseline.

`upload_if_changed()` verifies a versioned object's metadata **and actual bytes**, reusing matching versions or uploading/checking a new immutable version. `validate_kb()` checks ACTIVE vector/OpenSearch/Titan-1024/FLOAT32 and one exact catalog source with default parser/NONE/expected hook/intermediate location. `sync()` reuses an active job or starts one with a fresh idempotency token, waits and requires COMPLETE plus explicit zero failed documents. `retrieval_smoke()` performs bounded Retrieve reads with a known course_id filter for search visibility; it never generates a plan or measures full ranking quality.

Fresh setup applies the bootstrap revision, uploads ZIP, applies main infrastructure, uploads catalog, provisions the companion RAG stack with source disabled, binds the KB ID/permission, enables the source, Syncs, checks retrieval and binds source ID/Scheduler parameters in the main stack. Partial KB/source setup can resume. Configured external KBs are reused without importing/reconfiguring their infrastructure. A separate pre-existing CloudFormation execution role needs explicit RAG provisioning/data-plane access; the wrapper does not infer its grants.

## Infrastructure templates

The main template stores application code inline and ingestion code by S3 key plus exact version. KB ID and FoundationModelId configure the backend. Scheduler is conditional on real KB/source IDs; state/expression/timezone are independent parameters. The separate RAG template declares Titan v2, FLOAT32, 1024 dimensions, a faiss/HNSW OpenSearch index, managed encryption and default parser/NONE/custom transformation. It allows public endpoint connectivity for this configuration while IAM/data-access policies still restrict documents. It does not provide a private-endpoint production network design.

## Tests and acceptance

`test_app.py` covers local form behavior, configuration failures, upstream errors, SigV4 signing and credential/Region requirements. `test_course_ingestion.py` covers complete course/context extraction, metadata/prerequisites, malformed input and the transformation event/S3 contract including PLAIN_TEXT. `test_ingestion_package.py` checks deterministic ZIP contents and bucket/configuration examples. `test_setup_lab.py` covers preview safety, account checks, existing-KB reuse, initial deployment order, scoped Scheduler payload, parameter preservation, no-op/rollback/deletion/replacement handling, active-job reuse and delayed index visibility.

Run `python -m unittest discover -s tests -v` and `cfn-lint CloudFormation.yaml infrastructure/*.json`. Local mocks/schema checks do not prove new-account provisioning, the scheduled target or end-to-end generation. Deployment and operations documents define those acceptance steps.
