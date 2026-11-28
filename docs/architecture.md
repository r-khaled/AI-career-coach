# Architecture

> **Current cloud status (2026-11-26):** The reference project infrastructure was destroyed at the user's request. Earlier live results and resource diagrams below are historical. Code, contracts and local artifacts remain available; no reference API is running. See [stopping point and next steps](implementation/next-steps.md).

> **Historical live deployment (2026-11-26, subsequently destroyed):** The reference stack reached UPDATE_COMPLETE with 31 resources and a successful live API-to-worker plan journey. External search, real React UI, cross-model and full cost acceptance remain pending. See [recorded live results](implementation/live-deployment.md). Earlier statements below are dated implementation/design snapshots.


## Current source architecture — reviewed 2026-11-28

The legacy form and `POST /generate-plan` remain compatible in source; the inline handler moved to `career_coach/legacy.py`. The guided path uses a backend-controlled Smart Wizard, not an agent loop. React is a future client of the Flask cookie/SigV4 proxy. Application Lambda owns intake, approval and job dispatch; DynamoDB owns session state, bounded request receipts and immutable approved snapshots. A filtered stream retries pending dispatch to generation SQS; a separate worker retrieves evidence, creates and validates plans and persists revisions before completion. Queue and stream mappings are gated by `GuidedEnabled` (default `false`).

```mermaid
flowchart TD
    Browser[Legacy form / future React] --> Flask[Flask: cookie, Origin checks, SigV4]
    Flask --> API[API Gateway: AWS_IAM]
    API --> App[Application Lambda: career_coach.handler]
    App <--> Sessions[DynamoDB sessions and job snapshots]
    Sessions --> Stream[Filtered outbox stream]
    Stream --> App
    App --> Queue[Generation SQS]
    Queue --> Worker[Separate generation Lambda]
    Queue -. failed deliveries .-> DLQ[Generation DLQ]
    Worker --> Evidence[Internal Retrieve + bounded external search]
    Evidence --> KB[Bedrock KB / OpenSearch Serverless]
    Evidence -. secret ARN .-> Serper[Serper + public page evidence]
    Worker --> Models[Bedrock Converse]
    App --> Models
    App --> Plans[DynamoDB plans]
    Worker --> Plans
    Catalog[S3 catalog] --> Ingestion[Bedrock ingestion + custom transform Lambda]
    Ingestion --> KB
    Ingestion <--> Intermediate[S3 intermediate]
    Scheduler[Optional Scheduler + separate Sync DLQ] --> KB
```

This describes the checked-in architecture, not running infrastructure. The reference stack previously had 31 resources; 13 were added or imported. KB/OpenSearch were externally owned and were not among those 13. Both stack and dedicated external resources were destroyed on 2026-11-26. The historical deployed diagram and measurements are in [live results](implementation/live-deployment.md). Ingestion, embeddings and chunk boundaries were preserved; lower-cost vector storage is future work.

## Historical legacy implementation and redesign proposal

The original before/after explanations and diagrams below are retained for comparison. Use the current section above and the versioned schemas for implementation.

[Documentation](README.md) · [Deployment](deployment.md) · [Code reference](code-reference.md)


<!-- REDESIGN_NOTE_START -->
> **Historical design timeline — 2026-11-26:** The paired before/after sections below preserve the legacy implementation and the proposed redesign as written before execution. Their “not implemented” labels are historical; the current implementation and acceptance limits are recorded above. See [Guided Career Planning Redesign](decisions/guided-career-planning-redesign.md). Existing commands do not deploy that target.
<!-- REDESIGN_NOTE_END -->
## Purpose and boundaries

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

The application accepts a current role and career goal, retrieves relevant internal courses, generates a development plan and persists successful results. The supplied source is a synthetic 40-course Markdown catalog spanning ten tracks. It is not connected to an ERP, employee directory or course-registration system.

The web application runs locally with Flask. AWS hosts the IAM-protected HTTP API, application Lambda, DynamoDB and knowledge services. The vector store is Amazon OpenSearch Serverless. CloudFormation manages infrastructure; a Python setup command sequences artifact upload, provisioning, KB binding, initial ingestion and retrieval acceptance.

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart LR
    subgraph Local[Local application]
      Browser[Browser] --> Flask[Flask / Jinja]
    end
    subgraph AWS[AWS account and selected Region]
      API[HTTP API / AWS_IAM] --> App[Application Lambda]
      App --> RAG[Bedrock RetrieveAndGenerate]
      App --> DDB[DynamoDB plans]
      App --> Logs[CloudWatch execution logs]
      RAG --> Index[OpenSearch Serverless vector index]
      RAG --> Model[Nova Lite generation]
      Source[S3 catalog] --> Ingest[Bedrock ingestion]
      Ingest --> Hook[Transformation Lambda]
      Hook <--> Intermediate[S3 intermediate bucket]
      Ingest --> Titan[Titan v2 embeddings]
      Titan --> Index
      Scheduler[EventBridge Scheduler] --> Ingest
      Scheduler --> DLQ[SQS delivery-failure queue]
    end
    Flask -->|SigV4 POST /generate-plan| API
```

The diagram shows the available deployment architecture, not proof that every optional resource is already running. The main stack has 14 application/ingestion resources before schedule binding and 18 after its four conditional Scheduler resources are created. Fresh deployments also use a companion RAG stack. Existing KB/OpenSearch resources can remain externally owned and be reused.


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Roadmap-first guidance adds reviewed capabilities and evidenced external resources. React calls Flask; anonymous sessions and asynchronous planning are added without employee accounts or AgentCore.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart LR
    subgraph BrowserSide["Browser"]
        UI["React: questions, review, roadmap"]
        Cookie["Opaque anonymous-session cookie"]
        UI --- Cookie
    end
    UI --> Web["Flask: same-origin proxy and cookie handling"]
    Web -->|"SigV4 plus session proof"| API["API Gateway / AWS_IAM"]
    API --> App["Application Lambda: bounded dialogue rules"]
    App <--> State["NEW: DynamoDB sessions, turns and jobs"]
    App --> Intake["Bedrock: answer analysis"]
    App -->|"Approved snapshot and job IDs"| Queue["NEW: generation SQS"]
    Queue --> Worker["NEW: generation Lambda"]
    Queue -->|"Repeated delivery or processing failure"| JobDLQ["NEW: generation DLQ"]
    Worker <--> State
    Worker -->|"Retrieve"| KB["Existing KB / OpenSearch"]
    Worker --> Google["NEW: Google results through Serper"]
    Google --> Pages["Selected public page evidence"]
    Pages --> Worker
    Worker --> Model["Bedrock: outline and final plan"]
    Worker --> Plans["Existing plans table: validated revisions"]
    Worker --> Secret["NEW: Secrets Manager / Serper key"]
    Source["Existing S3 catalog"] --> Ingest["Existing parser / custom ingestion / Titan"]
    Ingest --> KB
    Scheduler["Existing weekly Scheduler"] --> Ingest
    Scheduler --> SyncDLQ["Existing Sync delivery DLQ"]
```

**Visual difference:** Compare retained baseline components with the new or changed components and transitions. The target is not deployment evidence.

<!-- REDESIGN_NOTE_END -->
## Request-time flow

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

**Diagram A — before redesign: current implementation.**

```mermaid
sequenceDiagram
    actor User
    participant Web as Flask
    participant API as API Gateway
    participant App as Application Lambda
    participant KB as Bedrock KB
    participant Search as OpenSearch
    participant FM as Generation model
    participant DB as DynamoDB
    User->>Web: current_role + goal
    Web->>API: IAM-signed JSON POST
    API->>App: Lambda proxy event v2
    App->>KB: RetrieveAndGenerate(prompt, KB ID, model ARN)
    KB->>Search: retrieve relevant embedded evidence
    Search-->>KB: top-five evidence units
    KB->>FM: prompt + retrieved context
    FM-->>KB: generated text
    KB-->>App: text + citations
    App->>DB: PutItem(successful plan)
    App-->>Web: JSON result
    Web-->>User: formatted plan
```

The application Lambda builds the career-coach prompt and requests up to five retrieval results and 800 generated output tokens. Model context includes retrieved evidence and service instructions, so input-token usage is larger than the user's form text. The transformation Lambda is never called by this question-time path.

The API exposes only `POST /generate-plan` under the `prod` stage. A browser GET to the API URL is not a health check. API Gateway authorizes the caller's signed request; its Lambda resource-based permission separately authorizes invoking the backend function. Flask signs requests server-side and does not put AWS credentials in browser JavaScript.


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Intake becomes versioned question/answer turns with state in DynamoDB. Approved profiles create background jobs returning 202; the worker separates Retrieve from model generation and persists validated revisions.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
sequenceDiagram
    actor User
    participant UI as React
    participant Web as Flask
    participant API as API Gateway
    participant App as Application Lambda
    participant State as DynamoDB sessions and jobs
    participant FM as Bedrock models
    participant Q as Generation SQS
    participant Worker as Generation Lambda
    participant KB as Bedrock Retrieve
    participant Search as Serper and public pages
    participant Plans as DynamoDB plans
    User->>UI: Start or resume anonymous journey
    UI->>Web: Session request with cookie
    Web->>API: SigV4 request with session proof
    API->>App: Validate session and route
    App->>State: Create or read persisted question
    App-->>UI: Question via API and Flask
    loop Eligible questions within 10 core and 4 follow-ups
        User->>UI: Answer
        UI->>Web: question_id, answer, state_version, request_id
        Web->>API: Signed answer request
        API->>App: Validate current question and state
        App->>State: Claim request before model call
        App->>FM: Relevant definitions, facts and latest answer
        FM-->>App: Proposed facts and question wording
        App->>App: Validate patch and select eligible question
        App->>State: Save answer, counters and next question
        App-->>UI: Saved next question or review via API and Flask
    end
    User->>UI: Confirm profile and assumptions
    UI->>Web: Approve review, then request plan
    Web->>API: Signed approval and plan requests
    API->>App: Validate approved profile version
    App->>State: Persist immutable snapshot and dispatchable job
    App->>Q: Enqueue job identifiers
    App-->>UI: 202 and job_id via API and Flask
    Q->>Worker: Deliver job
    Worker->>State: Claim job and load snapshot
    Worker->>FM: Draft capabilities and phases
    Worker->>KB: Focused course retrieval and prerequisite IDs
    KB-->>Worker: Text, metadata and source evidence
    Worker->>Search: Bounded generic queries and page reads
    Search-->>Worker: Evidence with explicit unknowns
    Worker->>FM: Generate structured plan from evidence
    FM-->>Worker: Candidate plan
    Worker->>Worker: Validate references, prerequisites and totals
    alt Validated and persisted
        Worker->>Plans: Save immutable plan revision
        Worker->>State: Mark completed with plan reference
    else Repair fails or job cannot complete
        Worker->>State: Mark failed with safe reason
    end
    loop Poll until completed or failed
        UI->>Web: Read job status with cookie
        Web->>API: Signed status request
        API->>App: Read authorized job
        App->>State: Read job state
        App-->>UI: State and stage via API and Flask
    end
    UI->>Web: Fetch completed plan revision
    Web->>API: Signed plan read
    API->>App: Check session access
    App->>Plans: Read authorized revision
    App-->>UI: Structured roadmap and evidence via API and Flask
```

**Visual difference:** One synchronous generation becomes bounded intake, review, a 202 job, polling and an authorized plan read. At most one repair is allowed; claim/replay branches are detailed under persistence.

<!-- REDESIGN_NOTE_END -->
## Knowledge ingestion

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart TB
    Trigger[Initial setup / manual Sync / scheduled Sync] --> Bedrock[Bedrock ingestion job]
    Catalog[S3 internal_courses.md] --> Parser[Default text parser]
    Bedrock --> Parser
    Parser --> None[Built-in chunking NONE]
    None --> Parsed[Parsed JSON batches in separate intermediate S3]
    Parsed --> Hook[POST_CHUNKING transformation Lambda]
    Hook --> Validate[Validate schema and Course ID boundaries]
    Validate --> Units[40 whole courses + 2 catalog contexts]
    Units --> Output[Transformed JSON batch references in S3]
    Output --> Embeddings[Titan Text Embeddings v2 / FLOAT32 / 1024]
    Embeddings --> Vector[OpenSearch vector index + text + metadata]
```

`NONE` disables Bedrock's built-in splitting; the custom hook still defines evidence units. One source object remains one source object. The current output contains 42 logical records inside intermediate transport batches, not 40 new source files. Default parsing extracts text; custom chunking identifies records; Titan produces vectors; OpenSearch stores/searches them. No step trains or changes model weights. [Knowledge contracts](knowledge-pipeline.md).

The source bucket stores `internal_courses.md` and versioned deployment ZIPs under `lambda-artifacts/`. Source inclusion is restricted to the catalog prefix. The separate intermediate bucket stores parsed/transformed transport data under `kb-intermediate/`; it is neither the deployment package store nor the vector index. Bedrock requires this bucket to be distinct from the source bucket for this transformation configuration.


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** The parser/NONE/custom transformation, catalog and Titan-1024 index remain unchanged initially. Application skills configuration is not indexed metadata; later filterable skills would require explicit extraction/reprocessing.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart TB
    subgraph Knowledge["Retained knowledge path - no initial migration"]
        Catalog["Existing S3 internal_courses.md"] --> Parser["Default parser"]
        Parser --> None["Built-in NONE"]
        None --> Intermediate["Separate intermediate S3"]
        Intermediate --> Hook["POST_CHUNKING course-aware Lambda"]
        Hook --> Units["40 whole courses and 2 contexts"]
        Units --> Titan["Titan v2 / FLOAT32 / 1024"]
        Titan --> Index["Existing OpenSearch vector index"]
    end
    subgraph Application["NEW application configuration - not ingested"]
        Config["Versioned skill and question definitions"] --> Code["Application Lambda selects relevant definitions"]
        Code --> Prompt["Model context for intake and planning"]
    end
    Worker["Generation worker"] -->|"Bedrock Retrieve: courses and prerequisite evidence"| Index
    Worker --> Search["Serper and bounded page evidence"]
    Search --> Plan["Plan-local external evidence"]
    Prompt --> Plan
    Index --> Plan
```

**Visual difference:** The knowledge path is retained. Application configuration and external-evidence paths are separate; neither is automatically ingested.

<!-- REDESIGN_NOTE_END -->
## Deployment ownership and order

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart TB
    CLI[setup CLI / authenticated deployer] --> Bootstrap[Fresh stack only: two private versioned buckets]
    Bootstrap --> Artifact[Upload verified ZIP key + object version]
    Artifact --> Main[Main CloudFormation stack]
    Main --> KB[Create RAG stack or reuse configured KB]
    KB --> Bind[Bind KB ID and Bedrock-to-Lambda permission]
    Bind --> DS[Create or validate the catalog data source]
    DS --> First[Initial Sync and Retrieve smoke check]
    First --> Schedule[Bind source ID / add main-stack Scheduler resources]
```

`CloudFormation.yaml` owns the application API/Lambda/role/table, source/intermediate buckets, ingestion Lambda/role/log group, invocation permissions and conditional weekly schedule/group/role/DLQ. The bootstrap template is the first revision of the same main stack, not another stack owning the buckets. Never apply its bucket-only template to a complete environment.

`infrastructure/knowledge-base.json` owns a new KB, Bedrock role, S3 source, OpenSearch collection/index and encryption/network/data policies. Source creation is gated by `EnableDataSource`; the setup command creates the KB first, updates the main stack's invoke permission, then enables the source. Already configured external resources are validated and reused without being imported into CloudFormation. Record ownership before cleanup.


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Future main-stack changes add sessions, generation SQS/DLQ, worker, scoped roles and application artifacts. Application packaging/setup must support app-only releases without recreating the KB or needlessly running Sync; present resource counts apply only to the baseline.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart TB
    Inspect["Inspect current account, resources and ownership"] --> Review["Review additive CloudFormation change set"]
    Review --> Artifacts["Build versioned application and worker packages"]
    Review --> Retain["Retain KB, catalog, ingestion and schedule"]
    Artifacts --> Deploy["Future main-stack update"]
    Deploy --> Sessions["Add sessions table and scoped grants"]
    Deploy --> Jobs["Add generation SQS, DLQ and worker"]
    Deploy --> Secret["Configure Serper secret ARN"]
    Deploy --> Routes["Add v2 routes and correct model or profile references"]
    Sessions --> Checks["Contract, session, dispatch and worker checks"]
    Jobs --> Checks
    Secret --> Checks
    Routes --> Checks
    Retain --> Retrieve["Retrieval benchmark before generation acceptance"]
    Checks --> Retrieve
    Retrieve --> Accept["Authorized integration, cost and latency acceptance"]
    Accept --> Cutover["Intentional React and Flask cutover"]
    Cutover --> Legacy["Keep legacy route available during transition"]
    Retain --> AppOnly["App-only releases do not require knowledge Sync"]
```

**Visual difference:** Compare retained baseline components with the new or changed components and transitions. The target is not deployment evidence.

<!-- REDESIGN_NOTE_END -->
## Scheduled refresh

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart LR
    Schedule[Main-stack weekly Scheduler] -->|StartIngestionJob| KB[Existing KB + source]
    Role[Scoped Scheduler execution role] --> Schedule
    Schedule -->|failed target delivery after retries| DLQ[Encrypted SQS DLQ / 14 days]
    KB --> Pipeline[Parse / custom chunk / embed / index]
```

The setup CLI performs first-time provisioning and initial Sync synchronously. Scheduler only submits later ingestion jobs; it does not build infrastructure, upload local files or generate plans. Default frequency is Sunday 03:00 `Africa/Cairo`, configurable by expression/timezone parameters. New schedules default DISABLED; an explicit setup flag enables them. Existing settings are preserved unless overridden.

Delivery retries are limited to two attempts within one hour. The DLQ covers API submission failure, not document failure after a job is accepted. Monitor job statistics separately. Turning off the schedule does not stop search capacity charges or an active ingestion job.


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** The existing weekly knowledge refresh is retained. The proposed generation queue/DLQ handles user plan jobs and is separate from the Scheduler delivery DLQ and ingestion lifecycle.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart LR
    subgraph Knowledge["Retained knowledge refresh"]
        Schedule["Weekly Scheduler"] -->|"StartIngestionJob"| KB["Existing KB and source"]
        Schedule -->|"Submission failure"| SyncDLQ["Existing Scheduler delivery DLQ"]
        KB --> Ingest["Parser / custom chunking / embeddings / index"]
    end
    subgraph Planning["NEW user-driven plan jobs"]
        Approved["Approved profile and plan request"] --> Queue["Generation SQS"]
        Queue --> Worker["Generation Lambda"]
        Queue -->|"Repeated delivery or processing failure"| JobDLQ["Separate generation DLQ"]
        Worker --> Jobs["Persist job stage and outcome"]
        Worker --> Read["Read existing KB evidence"]
    end
```

**Visual difference:** Knowledge refresh and plan generation have independent triggers, processing and DLQs.

<!-- REDESIGN_NOTE_END -->
## Trust boundaries and permissions

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart TB
    Caller[Local IAM user or assumed role] -->|execute-api:Invoke| API[API Gateway AWS_IAM route]
    API -->|Lambda resource permission| App[Application Lambda]
    AppRole[Application execution role] -->|assume at runtime| App
    App -->|InvokeModel + Retrieve + RetrieveAndGenerate| Bedrock[Bedrock]
    App -->|PutItem| DB[DynamoDB]
    App -->|execution logs| Logs[CloudWatch]
    KBRole[KB service role] -->|source / intermediate / hook / Titan / index| Bedrock
    Bedrock -->|KB-scoped Lambda resource permission| Hook[Transformation Lambda]
    HookRole[Ingestion execution role] -->|intermediate Get/Put + logs only| Hook
    SyncRole[Scheduler execution role] -->|StartIngestionJob + DLQ SendMessage| Scheduler[Scheduler]
```

The local caller, application execution role, ingestion execution role, KB service role and optional Scheduler role have separate responsibilities. API Gateway's invoke grant is a Lambda resource permission, not another IAM role. OpenSearch data and network policies are additional authorization layers. [Exact grants and limitations](security.md).


<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Keep SigV4 between Flask and the API. Add server-validated anonymous session proof, scoped session read/write and queue grants, and a separate worker role with evidence/model/secret permissions. Existing PutItem rights do not authorize the new table.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart TB
    Browser["React / anonymous cookie / no AWS credentials"] --> Flask["Flask validates origin and handles cookie"]
    Caller["Local IAM identity"] -->|"execute-api:Invoke"| Flask
    Flask -->|"SigV4 and session proof"| API["AWS_IAM API Gateway"]
    API -->|"Route-scoped Lambda invoke permission"| App["Application Lambda"]
    AppRole["Application runtime role"] --> App
    App -->|"Scoped session reads and conditional writes"| Sessions["Sessions table"]
    App -->|"Analysis model invocation"| Bedrock["Bedrock models"]
    App -->|"SendMessage"| Q["Generation SQS"]
    Q -->|"Event source mapping"| Worker["Generation Lambda"]
    WorkerRole["Separate worker role"] --> Worker
    Worker -->|"Receive, delete and inspect queue messages"| Q
    Worker -->|"Claim job and update stage"| Sessions
    Worker -->|"Scoped final-plan persistence"| Plans["Plans table"]
    Worker -->|"Retrieve on configured KB"| KB["Existing KB"]
    Worker -->|"Planner model invocation"| Bedrock
    Worker -->|"GetSecretValue on configured ARN"| Secret["Serper secret"]
    Worker -->|"Generic queries only"| Search["External Serper API and public pages"]
    KBRole["Existing KB service role"] --> KB
    KB --> Hook["Existing ingestion hook"]
    HookRole["Existing intermediate-prefix and log grants"] --> Hook
    SyncRole["Existing scoped Scheduler role"] --> Sync["Existing knowledge refresh"]
```

**Visual difference:** Compare retained baseline components with the new or changed components and transitions. The target is not deployment evidence.

<!-- REDESIGN_NOTE_END -->
## Persistence and operational limits

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

DynamoDB uses `user_id` as partition key and `timestamp` as sort key with PAY_PER_REQUEST billing. Successful items contain request fields, generated text and citations. The UUID default is not verified employee identity. Streams are enabled without a consumer; there is no history-reading API or TTL policy.

CloudWatch holds execution/error logs, not the business-plan store. S3 source/intermediate/artifacts are private and encrypted with managed encryption; request/response archival to S3 is not implemented. The ingestion log group has seven-day retention; application logging uses the basic execution policy without explicit retention in this template.

API Gateway times out after 30 seconds, the backend Lambda after 60 and Flask's HTTP call after 35. A client timeout can leave generation running; retries can incur duplicate model work or records. DynamoDB citation-number serialization and generation persistence require end-to-end acceptance. There is no request idempotency, employee sign-in, per-user quota or hard spending cutoff. Exact-level, strict-track and per-course/whole-plan duration constraints are not implemented in the current app even though chunk metadata enables filters.


**Diagram A — before redesign: current implementation.**

```mermaid
flowchart LR
    Request["Current role and goal"] --> App["Application Lambda"]
    App --> RAG["Synchronous RetrieveAndGenerate"]
    RAG --> Save["PutItem after model success"]
    Save --> Plans["DynamoDB plans: user_id and timestamp"]
    Save --> Response["Text and citations response"]
    App --> Timeout["API 30s / Lambda 60s / Flask 35s"]
    Timeout --> Risk["Timeout may leave work running"]
    Plans --> Retention["No table TTL or history-read API"]
```

<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Persist authoritative session/turn/job state with seven-day sliding expiry, version checks and request claims. Keep final-plan retention separate. Background jobs avoid waiting for long generation inside the current gateway timeout; immutable snapshots/revisions prevent silent overwrites.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart TB
    Cookie["Browser: opaque cookie and UI draft"] --> App["Application Lambda"]
    App --> Check["Validate session proof, expiry and version"]
    Check --> Claim["Conditionally claim request_id"]
    Claim -->|"New request"| Analyze["One model analysis"]
    Claim -->|"Completed duplicate"| Replay["Replay persisted response"]
    Claim -->|"In-flight duplicate"| Processing["Return processing state"]
    Analyze --> Commit["Save facts, answer, counters and next question"]
    Commit --> State["DynamoDB state and turn records"]
    Commit --> UI["Display saved question or review"]
    State --> Expiry["Seven-day sliding logical expiry"]
    Expiry --> TTL["Asynchronous TTL cleanup"]
    Review["Approved profile"] --> Snapshot["Immutable job snapshot"]
    Snapshot --> Queue["Background queue and worker"]
    Queue --> Valid["Validate plan and save revision"]
    Valid --> Plans["Final plans: separate retention"]
    Valid --> Done["Only then mark job completed"]
    Plans --> Download["Authorized read and download"]
    Edit["Changed answers"] --> NewVersion["New profile version and new job"]
    NewVersion --> Snapshot
    NewVersion --> Stale["Older snapshot result remains identifiable"]
```

**Visual difference:** Compare retained baseline components with the new or changed components and transitions. The target is not deployment evidence.

<!-- REDESIGN_NOTE_END -->
## Region and model configuration

<!-- REDESIGN_NOTE_START -->
**Before redesign — implemented baseline:**
<!-- REDESIGN_NOTE_END -->

The setup command requires an explicit Region and derives the account from STS. Lambda uses its runtime role; local profiles do not transfer into AWS. The generation ARN is built from Region and FoundationModelId with an empty account field; KB/IAM ARNs use the destination account pseudo parameter. Inference-profile models require a deliberate parameter/IAM change, not copying an old account's ARN. [Configuration and migration](security.md#region-and-model-portability).

OpenSearch is billed for search/indexing capacity and storage, including a possible persistent capacity floor. Serverless does not make this architecture wholly per-request. [Cost analysis](costs.md).

**Diagram A — before redesign: current implementation.**

```mermaid
flowchart LR
    Param["FoundationModelId"] --> ARN["Regional foundation-model ARN"]
    ARN --> App["Application Lambda"]
    KB["KnowledgeBaseId"] --> App
    App --> RAG["RetrieveAndGenerate"]
    RAG --> Search["Five results; no explicit search-type override"]
    RAG --> Model["Nova Lite default / output cap 800"]
    Titan["Titan v2 / FLOAT32 / 1024 dimensions"] --> Index["Existing OpenSearch index"]
```

<!-- REDESIGN_NOTE_START -->
**After redesign — agreed target, not implemented (2026-11-26):** Haiku 4.5 is the initial candidate; compare Nova and Sonnet. Start final generation at 2048 tokens and experimental temperature 0.2. Correct model/profile configuration and IAM must be verified; the template currently lists Sonnet 4.5, not 4.6.


**Diagram B — after redesign: agreed target, not implemented.**

```mermaid
flowchart LR
    Config["Versioned model and budget configuration"] --> Identity["Verified model ID or inference-profile ARN"]
    Identity --> IAM["Scoped source and destination model grants"]
    IAM --> Intake["Intake analysis: smaller independent budget"]
    IAM --> Outline["Planning outline: smaller independent budget"]
    IAM --> Final["Final plan: 2048 tokens, temperature 0.2"]
    Final --> Validate["Schema and semantic checks"]
    Validate -->|"Valid"| Save["Persist validated revision"]
    Validate -->|"Invalid or truncated"| Repair["At most one repair, up to 4096 tokens"]
    Repair --> Recheck["Revalidate"]
    Recheck -->|"Valid"| Save
    Recheck -->|"Still invalid"| Fail["Explicit failure"]
    Candidates["Compare Haiku 4.5, Nova and Sonnet"] --> Config
    Embed["Retained Titan v2: 1024-dimensional vectors"] --> KB["Knowledge embeddings"]
```

**Visual difference:** Compare retained baseline components with the new or changed components and transitions. The target is not deployment evidence.

<!-- REDESIGN_NOTE_END -->
