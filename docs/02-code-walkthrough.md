<div dir="ltr" lang="en">

# 02. Code walkthrough

[README](../README.md) | [Previous: architecture](01-architecture.md) | [Next: access and Region](03-aws-access-and-region.md)

Open [app.py](../app.py), [CloudFormation.yaml](../CloudFormation.yaml), and [the HTML template](../templates/index.html) alongside this guide. Function names and resource names are more durable anchors than line numbers.

## 1. Python needed to read this project

- `import` loads a module, similar in purpose to a TypeScript import.
- `def` defines a function. Indentation defines the block instead of braces.
- A dictionary such as `{'goal': goal}` is analogous to a plain JavaScript object.
- `os.environ` reads process environment variables, like `process.env`.
- `json.loads` parses JSON; `json.dumps` serializes it.
- An f-string such as `f"Current role: {current_role}"` resembles a JavaScript template string.
- `try/except` corresponds to `try/catch`.

These are enough to follow the request path; you do not need to rewrite the whole application in Python.

## 2. `app.py`: the local web server

### Startup and configuration

`app = Flask(__name__)` constructs the Flask application. `API_URL` is read from the environment once at import/startup. Changing that environment variable requires restarting the process.

The app listens on port 5001 when started with `python app.py`. Debug mode is enabled only when `FLASK_DEBUG=1`. The built-in Flask server is suitable for this local lab; the template does not deploy this UI to AWS.

### `request_career_plan(payload)`

This function makes the cloud API request:

1. `boto3.Session()` resolves configuration and credentials from the local environment/provider chain.
2. `session.region_name` supplies the signing Region. Missing configuration produces a useful error.
3. `session.get_credentials()` finds credentials; missing credentials prevent the request.
4. `json.dumps(...).encode('utf-8')` creates the exact bytes that will be sent.
5. `AWSRequest` holds the method, URL, body, and content type.
6. `SigV4Auth(..., 'execute-api', region)` signs the request for API Gateway. `get_frozen_credentials()` takes a consistent snapshot of the resolved credentials for this signature.
7. `requests.post` sends those same bytes and signed headers over HTTPS. Redirect following is disabled so the signed request is not forwarded to another destination.

Boto3 does not shell out to the AWS CLI. They can share configuration files and credential sources. The local AWS secret is used to calculate the signature; it is not sent as the request body or embedded in HTML.

### `index()`

The route handles both GET and POST on `/`:

- GET renders the empty form.
- POST reads the two fields with `request.form.get`.
- Missing input or an unset `API_URL` produces a visible message without calling AWS.
- The function calls `request_career_plan`, checks the HTTP status, parses the returned JSON, extracts `career_plan`, and formats it.
- `render_template` passes `career_plan` and `error_message` to Jinja.

Cloud API errors are shown inside the rendered page. Flask does not currently preserve the cloud error status as the local page's HTTP status; a visible error can still be returned in a local HTTP 200 page.

### `format_career_plan(plan_text)`

This converts free-form text into a title, sections, bullet items, and a note for HTML display. The regular expression splits around single-digit numbered headings. `section_items` avoids a naming collision with dictionary `.items()` in Jinja.

This is formatting logic, not model reasoning. It is heuristic: unexpected headings, Markdown formatting, multi-digit numbering, or note placement can produce imperfect output. `lstrip('Note:')` strips a set of leading characters rather than a literal prefix. We will prefer an explicit output contract when designing the replacement; this walkthrough does not silently fix those inherited limitations.

### `templates/index.html`

The form submits to Flask's `/` route. Jinja conditionals display errors/results, and loops render sections. The page loads Tailwind from a CDN and declares a Google font. It has no JavaScript AWS SDK, credential handling, or direct Bedrock request.

## 3. The Lambda source inside CloudFormation

Look under `CareerCoachFunction.Properties.Code.ZipFile`. CloudFormation packages this inline Python as `index.py`, which explains `Handler: index.lambda_handler`.

### Module initialization

```python
bedrock_agent = boto3.client('bedrock-agent-runtime')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
```

These objects are initialized outside the handler so a reused execution environment can reuse them. Here Boto3 obtains temporary credentials from the Lambda execution role and the AWS runtime environment, not your laptop's `devops` profile.

### Input processing

`lambda_handler(event, context)` parses `event['body']`, reads `current_role` and `goal`, and chooses a provided `user_id` or a generated UUID. Missing required fields return a JSON 400 response.

The current handler has limited validation. Malformed JSON, a non-object body, unexpected field types, whitespace-only values, and overly long input are not separately handled as clean client errors. They matter when we design the TypeScript version.

### Prompt creation

The f-string contains the career-coach instruction, the current role and goal, and requests:

1. Internal training courses from the knowledge base.
2. Skills to develop.
3. A three-to-six-month timeline.
4. Additional certifications or learning resources.

This is the request text sent to `RetrieveAndGenerate`, not a custom trained model or a separate system-role configuration. The service uses its knowledge-base generation/orchestration behavior around it. User text is interpolated directly; the demo does not implement prompt-injection defenses or enforce catalog-only recommendations.

### Configuration checks and the model call

The handler rejects the placeholder KB ID. The active call passes:

```python
input={'text': prompt}
# Plus retrieveAndGenerateConfiguration:
# type: KNOWLEDGE_BASE
# knowledgeBaseId: from KNOWLEDGE_BASE_ID
# modelArn: from MODEL_ARN
# maxTokens: 800
# numberOfResults: 5
```

The model is selected by `MODEL_ARN`; the embedding model is selected separately in the Knowledge Base. There is no model downloading/loading in Lambda and no endpoint URL hardcoded for Bedrock: the SDK selects a regional service endpoint.

The output token limit bounds generated length, not total input cost, request count, or latency. Five results means retrieval chunks, not necessarily five distinct courses. The code extracts `response['output']['text']` and any `citations`; it does not use a returned conversation session ID for subsequent turns.

### Persistence

`table.put_item` writes `user_id`, `timestamp`, `current_role`, `goal`, `career_plan`, and `citations`. Only after this write succeeds does the handler return success.

The timestamp comes from `datetime.utcnow().isoformat()`. A new UUID is typically generated for each form submission, so this is not a stable per-employee history. The table is a storage mechanism, not authorization or model memory.

### Response and exceptions

The success result is a Lambda proxy response with `statusCode`, `headers`, and a serialized JSON `body`. API Gateway turns this into the public HTTP response.

A broad exception handler logs the exception/traceback and returns status 500 with the error text. It does not implement structured error IDs, idempotency, or partial success after a storage failure. If numeric citation metadata appears later, Boto3 DynamoDB serialization may require converting floats to Decimal; this has not been validated end to end.

## 4. Read CloudFormation as a dependency graph

- `Parameters`: deployment-time inputs. `FoundationModelId` currently defaults to Nova Lite. `KnowledgeBaseId` starts as a placeholder.
- `Resources`: desired AWS resources and their properties.
- `Outputs`: useful identifiers/URLs after creation.
- `!Ref`: a parameter value or a resource-specific identifier.
- `!GetAtt Resource.Attribute`: an attribute such as an ARN.
- `!Sub`: interpolation, including pseudo parameters such as `${AWS::Region}`, `${AWS::AccountId}`, and `${AWS::StackName}`.

References let CloudFormation infer dependencies. The stack's selected Region supplies `${AWS::Region}`. The value is not read from `app.py`.

### The fourteen resources (baseline, ingestion and real-integration corrections)

1. **KnowledgeBaseDataBucket:** private S3 bucket with AES256 encryption and versioning. Empty bucket creation does not upload the catalog.
2. **CareerPlansTable:** DynamoDB on-demand billing, `user_id` partition key and `timestamp` sort key. Streams are enabled without a consumer.
3. **LambdaExecutionRole:** trust allows Lambda to assume the role. Policies allow basic execution logging, the selected model, retrieval, and `PutItem` on the selected table. `RetrieveAndGenerate` uses `Resource: '*'` because that action lacks resource-level scoping in the [AWS authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock.html).
4. **CareerCoachFunction:** Python 3.12, 512 MB, 60-second timeout, `index.lambda_handler`, inline code, and three environment variables.
5. **CareerCoachAPI:** HTTP API with broad CORS settings. CORS is not authentication and does not protect a server-to-server request.
6. **ApiIntegration:** Lambda proxy integration with v2 payloads and a 30-second integration timeout.
7. **ApiRoute:** `POST /generate-plan`, with IAM authorization.
8. **ApiStage:** `prod`, automatic API deployments, one request/second rate and burst two as best-effort throttling.
9. **LambdaApiPermission:** permits this API/stage/method/path to invoke this function. This resource policy is distinct from the Lambda execution role.

10. **IngestionLogGroup:** explicit function log group with seven-day retention.
11. **IngestionLambdaExecutionRole:** Lambda trust plus intermediate S3 Get/Put and scoped log writes.
12. **IngestionTransformationFunction:** separate custom chunking hook, Python 3.12, 256 MB, 60 seconds, versioned S3 ZIP and three source/storage environment values. It is not an API handler or retriever.

13. **IngestionIntermediateBucket:** private, encrypted, versioned bucket required to differ from the source bucket.
14. **IngestionBedrockPermission:** function resource policy allowing the exact KB/account to invoke the ingestion hook.

### Outputs and missing resources

Outputs expose bucket name/ARN, Lambda name, API URL, table name, and the route ARN to use in the caller's `execute-api:Invoke` policy. Outputs do not themselves grant permissions.

There are no template resources for the Knowledge Base, its service role, data source, vector collection/index, ingestion job, employee identity provider, pipeline, UI hosting, budgets, or an explicit application log group. A complete Terraform version must account for the manually created resources too.

## 5. What changed during preparation

Compared with the downloaded starting point, preparation added a currently checked model default, a KB ID parameter, IAM route authorization and local SigV4 signing, reduced some permissions, throttling, an output-length bound, an explicit API timeout, configurable API URL, visible UI errors, local tests, and debug-off behavior.

The baseline was subsequently deployed in Ohio and the catalog uploaded; the old us-east-1 review is historical. See the guided runbook for the current ingestion release status. Full KB/API success is still pending.

## 6. Packaging and pipelines

The local UI dependencies are Flask, requests, and Boto3. Inline Lambda currently relies on the Python runtime's included AWS SDK. A more reproducible deployed package would pin and package its SDK dependencies; do not assume the local virtual environment is uploaded with inline code. See [Python Lambda packaging](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html).

No `.github/workflows` pipeline is present. For this learning run, CloudFormation can package the inline Python while Flask runs locally. The manual TypeScript version will need a local compile/bundle/ZIP step; that still does not require GitHub Actions. [AWS explains TypeScript packaging here](https://docs.aws.amazon.com/lambda/latest/dg/typescript-package.html).

## 7. Course-aware ingestion code and packaging

`ingestion/course_chunker.py` is a pure text/schema parser. It validates the nine fields, course IDs, durations, levels and prerequisite references; emits course text plus typed metadata; preserves catalog-wide notes separately; and rejects oversized/unsupported input. It uses Course ID boundaries, not a fixed number of words/tokens.

`ingestion/transform.py` implements Bedrock's POST_CHUNKING adapter. The event names the intermediate bucket, original S3 source and content batch keys. It validates the configured source/bucket/prefix, reads TEXT fileContents, calls the parser, writes a JSON output batch and returns outputFiles with S3 references. It preserves fileMetadata and uses a content/job-based output key for retries. boto3 is lazy-loaded by lambda_handler; no model or vector-store client exists in this module.

`ingestion/prepare_lab.py` takes --bucket, --intermediate-bucket, --account-id, --region and --stack-name, supplied from actual selected Outputs/identity. It builds the ZIP and consistent examples locally without cloud calls. Two new template parameters select S3Key and S3ObjectVersion. The three environment variables are INTERMEDIATE_BUCKET, INTERMEDIATE_PREFIX and CATALOG_SOURCE_URI; they are settings, not credentials or IAM grants. The existing application parameters must be preserved during the UPDATE.

Runtime SDK calls are GetObject/PutObject only. Logs are a separate role policy; the new log group is pre-created. Bedrock's service role later needs InvokeFunction on this exact function and its own source/model/store permissions. Choosing the Lambda in the wizard does not replace that review.

The [deployment plan](ingestion-deployment-plan.md) contains build/review/execute commands. The [decision record](decisions/course-aware-chunking.md) explains the measured boundaries and alternatives. Public API input/output behavior remains unchanged.

> **Checkpoint:** locate the three configuration variables, point to the exact Bedrock call and DynamoDB write, and explain why `app.py` is not the Lambda deployment artifact.

[Previous: architecture](01-architecture.md) | [Next: access and Region](03-aws-access-and-region.md)

</div>
