# Guided runtime implementation

> **Current cloud status (2026-11-26):** The reference project infrastructure was destroyed at the user's request. Earlier live results and resource diagrams below are historical. Code, contracts and local artifacts remain available; no reference API is running. See [stopping point and next steps](next-steps.md).

> **Historical live deployment (2026-11-26, subsequently destroyed):** The reference stack reached UPDATE_COMPLETE with 31 resources and a successful live API-to-worker plan journey. External search, real React UI, cross-model and full cost acceptance remain pending. See [recorded live results](live-deployment.md). Earlier statements below are dated implementation/design snapshots.


Recorded 2026-11-26. This is the implementation record for the guided redesign.
It distinguishes local evidence from deployment and live acceptance. Earlier
before/after notes remain historical design snapshots. The design authority is
[the decision](../decisions/guided-career-planning-redesign.md).

## Accepted local foundations

The application runtime is `career_coach`, independent of `ingestion`. The
legacy handler was extracted without changing its prompt, five-result retrieval,
800-token limit, response, errors or successful-plan persistence. Flask's legacy
form and text formatter remain available.

JSON contracts and examples live in `career_coach/schemas` and
`career_coach/fixtures`. They use schema version 1.0; structural validation is
separate from provenance, prerequisite, ownership and arithmetic checks.
`config.PolicyV1` declares the initial limits. They are experimental operating
settings, not measured quality or monetary guarantees. Haiku 4.5 is a candidate.
The Converse adapter passes model IDs and full inference-profile ARNs unchanged,
performs one SDK attempt and records available token usage without raw answers.

Build a Linux Python 3.12 application artifact locally:

```bash
python -m scripts.package_application .lab/redesign/application.zip
# Repeat offline after the pinned wheelhouse has been populated:
python -m scripts.package_application .lab/redesign/application.zip \
  --dependency-dir .lab/application-wheels
```

The builder checks committed wheel filenames/SHA-256 hashes and exact version
pins, normalizes ZIP entries and embeds a manifest. The Lambda runtime supplies
boto3/botocore. The ingestion ZIP remains its existing independent artifact.
Setup binds content-addressed keys and exact S3 object versions. `app-release`
refuses CloudFormation resource changes outside the application function; it
cannot apply an initial additive infrastructure migration. It does not Sync or
recreate the KB. Previewing setup still performs account reads; it is not a
fully offline deployment command.

## Anonymous persistence

Sessions use random opaque proof with only its hash stored. IDs alone do not
authorize access. Logical expiry is seven days after activity; DynamoDB TTL
cleanup timing does not authorize a read. Final-plan retention is independent.
The API consumes proof in the signed `X-Session-Token` header. Session creation
returns it only in a server response header for Flask to consume.

State, request receipts and turns are separate bounded records. State versions
and transactional record revisions are distinct. Request content hashes detect
ID reuse; completed results replay before stale-version rejection. A session
lock and a fenced 60-second lease protect future model work. At most two lease
recoveries are allowed. Expired abandoned work is terminalized before another
request proceeds. Failure releases the lock and preserves the current question.
External provider billing cannot be exactly once after a lost provider reply.

There are at most 32 dialogue requests per session. Each activity transaction
renews the state and all retained receipts/turns (at most 65 items), preserving
replay while the session slides forward. This has read/write cost proportional
to retained requests and requires live cost/latency acceptance. State is capped
at 96 KiB, responses at 64 KiB, turns at 16 KiB; the store also enforces 100
unique operations, a 300 KiB item and a conservative 3.5 MB transaction limit.
Missing indexed receipts fail closed. Exhausting the dialogue request budget
requires a new session; this is a deliberate bounded lifetime work limit.

Offline tests use a shared conditional in-memory store and mocked DynamoDB
request validation. They establish local behavior, not actual DynamoDB service
semantics, IAM correctness or deployment acceptance.

## Intake

The Smart Wizard is implemented and tested offline. Reviewed question/skill
definitions are versioned in the package. Rules select and persist questions,
skip reported slots and enforce the 10 core / 4 follow-up / 2 per-axis limits.
One bounded analysis proposal is validated per answer. Explicit uncertainty
cannot populate unrelated reported facts. Model wording is accepted only when
it matches a reviewed variant for the rule-selected question; otherwise the
fallback is used. Broader goals use generic capability objectives.

Approval requires a nonempty user-reported goal and direction. Review exposes
fact provenance, unknowns and identified optional assumptions. Equivalence is
opt-in and bound to the approved profile version; it is not a certified skills
assessment. Corrections invalidate approval and dependent decisions, including
after approval, and require another confirmation. The local Backend-to-RAG
fixture reaches review after ten core questions and one direction follow-up.
An expert multi-slot fixture skips questions. These are behavioral fixtures,
not measured model interpretation accuracy or evaluated career usefulness.

## Evidence sources

`InternalRetriever` calls Retrieve separately with explicit SEMANTIC, 15 results
and `record_type=course`. It retains text, metadata, source, score, rank, settings
and retrieval time. Exact-ID prerequisite expansion has a visited set, depth 10
and 30 SDK-call budget; production clients must disable hidden SDK retries.
Catalog versions/hashes/content cannot be mixed silently. Constraints are
explicit; no default strict track/level restriction is added. Course metadata is
checked against source text. Missing, cyclic or blocked prerequisites remain
visible; only approved profile-bound assumptions permit equivalence. The
SEC-201 fixture closes to 68 deduplicated course hours without equivalence.

The offline `scripts.evaluate_retrieval` harness preserves the actual legacy
prompt and settings and compares Recall/MRR at the same k (1–5 against Top-5).
The included English/Arabic ranks are labelled synthetic, not real measurements
or evidence of ranking improvement. Live mode refuses execution; a real original
baseline still needs separately authorized capture. No ingestion/index change
has been made.

`ExternalSearch` accepts only reviewed topic IDs and en/ar, never raw answers or
profile text. Its initial five topics cover RAG retrieval, AI fundamentals,
cloud deployment, backend APIs and data analysis; other subjects expose a
coverage gap. Serper receives at most three requests including failed attempts
and retries, five candidates per search. Up to five selected page attempts use
HTTPS, three redirects, a 10-second absolute deadline and a 1 MB aggregate body
limit. Every destination is validated and the TCP connection is pinned to a
public DNS address with the original TLS hostname/SNI. DNS workers are bounded;
timeouts, unsupported encoding, login/CAPTCHA and private destinations fail
closed. Authenticated provider POST requests cannot redirect.

Configure a Secrets Manager ARN only. SecretString may contain a raw API key or
JSON `{"api_key":"..."}`. The worker alone will receive scoped read access.
There is no external catalog ingestion or permanent page archive. Snippets and
pages have distinct evidence with exact field values and provenance. Matching
nonexecuting JSON-LD Course declarations may supply duration, provider,
language, price, skills and prerequisites. Unknowns stay unknown. These are
provider declarations, not independently verified quality/readiness evidence;
unreadable pages remain limited-evidence candidates.

Local source acceptance comprises 11 retrieval tests and 17 external tests,
including adversarial DNS/redirect/deadline/budget/provenance cases. The first
three phases passed 82 integrated tests. Planning, jobs and Flask integration subsequently passed their local acceptance gates. No actual DNS, TLS, Serper or Bedrock behavior is established
by fake-provider tests.

## Deployment and acceptance status — reviewed 2026-11-28

The reference stack was updated and the guided journey ran live before complete user-authorized teardown. No reference API, KB or OpenSearch collection is running now. [Historical live results](live-deployment.md) record the successful journey, corrective releases and measurements. External Serper, real React, cross-model comparison and full cost acceptance remain pending. Private checkpoints and teardown evidence are under `.lab/redesign/` and do not ship in Git.

## Local acceptance and retained runtime

Phases 1–8 now pass local acceptance. The full offline suite passed 166 tests on 2026-11-28. The earlier pre-live snapshot passed 164 tests and 17 focused checks; the final count includes subsequent live-driven fixes. All three
CloudFormation templates passed cfn-lint and the diff check is clean.
The async worker uses 180 seconds, SQS visibility 1080 seconds and independent
queue/DLQ/IAM/artifact versions. A filtered DynamoDB stream dispatches the outbox
through the existing application Lambda. GuidedEnabled defaults false.
Sessions retain at most 32 dialogue requests and eight jobs; renewal includes
job receipts. Final plans and bounded private compressed evidence traces are
immutable and retained separately. Saved-plan acknowledgement loss reconciles
without another generation, including the last allowed attempt.

Flask and structured downloads are implemented; see [React integration](../react-integration.md).
No production React screens were built. Historical before/after notes remain
historical snapshots, not current deployment claims.

Phase 9 artifacts, change sets and a reference update were applied under user authorization. The limited live journey passed; the environment was then destroyed at the user's request. No Sync/reindex or UI cutover was performed. Current source includes numeric metadata normalization, explicit analysis/outline prompts, compact model drafts materialized with original evidence, and selected prerequisite closure before deterministic validation. Historical live usage is not a complete monetary estimate. Rebuild and new paid trials require fresh authorization. See [version history](version-history.md) for remaining acceptance.
