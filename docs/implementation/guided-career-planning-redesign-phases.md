# Guided Career Planning Redesign — Implementation Phases

> **Execution update — 2026-11-28:** This preserved design/plan is not the execution ledger. Phases 1–8 passed local acceptance; a limited phase-9 live journey passed before the reference infrastructure was destroyed on 2026-11-26. External search, React, model comparison and full cost acceptance remain pending. See [version history](version-history.md) and [runtime](guided-runtime.md). Earlier current/future wording below describes the pre-execution snapshot.

[Documentation](../README.md) · [Agreed design](../decisions/guided-career-planning-redesign.md) · [Architecture](../architecture.md) · [API](../api.md) · [Code reference](../code-reference.md)

**Status: execution breakdown only; no implementation phase completed by this document. Date: 2026-11-26.**

This breaks the agreed redesign into nine bounded chat-sized work packages. The redesign is the design authority; this document defines execution order, outputs and handoffs. Existing before/after documentation distinguishes implemented baseline from targets. The sequence does not authorize cloud changes or create new chats automatically.


## Single-session execution mode

Use [the complete orchestrator prompt](guided-career-planning-redesign-orchestrator-prompt.md) to execute all nine phases in one chat with up to three gpt-6.1-terra/medium workers and a gpt-6.1-sol/medium orchestrator. The single-phase prompts below remain optional standalone-task instructions; they do not require stopping a single-session orchestrator after phase 1. In single-session mode, phases 4 and 5 may overlap after stable phase-3 interfaces; phase 8 may overlap phase 7 only with frozen contracts and separate ownership. Acceptance still respects dependencies and explicit live-action authorization.

## How to use this plan

Start a new chat with the phase-specific prompt below. Give that chat access to this same repository and the preceding handoff. Run phases in numerical order by default; do not advance until the predecessor's acceptance is evidenced. Phase 1 starts from the current baseline. Phase N depends on phases 1 through N-1 being accepted, not simply discussed.

Each phase should deliver one coherent reviewable change and evidence, not a whole redesign or a collection of trivial file edits. No fixed hours or completion estimates are claimed. If a real blocker makes a phase too large, report the concrete dependency rather than silently dropping outputs or merging later phases.

## Shared execution rules

- Inspect applicable instructions, actual code, local changes and the previous handoff first; preserve other work. Prefer the current suitable checkout. Do not automatically commit, push, create worktrees or new chats.
- Keep legacy POST /generate-plan available and behavior-compatible until intentional cutover. Keep parser/NONE/custom transformation and existing KB ownership unchanged initially.
- Use fake providers/fixtures for implementation and offline tests. A mock success is not live acceptance. No claim of model access, ranking improvement or cost without evidence.
- Declarative infrastructure and packaging changes can be prepared/validated in earlier phases, but AWS mutation, Sync, paid model/search calls, credentials/account creation and cutover require explicit action-specific authorization.
- Preserve English public docs and the private Arabic archive arrangement. Update affected before/after notes as real implementation progresses; never label the entire redesign implemented because one component passed.
- React production screens remain user-owned. The integration phase supplies contracts/proxy support and a testable journey. Lack of a real React UI must remain visible at final acceptance.
- Record unresolved configuration values before activation. Phase 1 fixes contract-level defaults; provider-specific settings are fixed/tested by their owning phase. Do not hide policy decisions in prompts or leave limits to model discretion.

## Dependency sequence

```text
1 Foundation -> 2 Sessions -> 3 Smart Wizard -> 4 Internal evidence
              -> 5 External evidence -> 6 Planner -> 7 Async jobs
              -> 8 Flask / React handoff -> 9 Authorized live acceptance
```

This is one sequential chain. Internal and external evidence are deliberately separate work packages; both are composed in phase 6. The planner runs in-process with fakes before it is wrapped in durable queue/job handling. The frontend contract work follows stable backend behavior.

## Phase status

All nine phases were **planned** at creation. Execution update (2026-11-26): phases 1–8 passed local acceptance (164 offline tests plus final focused checks). Phase 9 artifacts and an offline change-set request are prepared; deployment, paid trials, live acceptance, React UI acceptance and cutover remain pending. See [the runtime implementation record](guided-runtime.md). Documentation, earlier ingestion tests and archived AWS evidence do not count as completion of any execution phase. Each implementation chat must explicitly record its evidence and pending items.

## Phase 1 — Contracts and application packaging

**Entry:** Inspect the current baseline; no preceding execution phase.

**Outcome:** Create a stable implementation foundation without changing the legacy request behavior.

**Deliverables**

- Extract the inline application handler into a versioned package; preserve POST /generate-plan and its existing budgets and response contract.
- Turn agreed JSON contracts into actual schemas and fixtures; define shared profile, question, evidence, resource, plan and job representations.
- Create versioned configuration boundaries and freeze the remaining policy knobs with explicit documented defaults: question/fact rules, claim recovery, fetch/retrieval budgets, model IDs and analysis/outline limits.
- Add model/provider adapter boundaries and deterministic packaging; update setup artifact handling without inventing already-supported app-only flags. No worker or new endpoint implementation yet.

**Acceptance gate**

- Legacy success/error/persistence and UI/signing regressions pass locally with mocked providers.
- Schemas accept the agreed valid fixtures and reject malformed or unauthorized fields; packaging contents/configuration are verified.
- Infrastructure changes pass local checks; no deployment or paid inference is needed.

**Excluded:** Do not add sessions, search, the wizard or change ingestion/model behavior on the legacy path.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 2.

**New-chat prompt**

```text
Implement phase 1 only: Contracts and application packaging.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 1 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 2 — Anonymous session persistence and access

**Entry:** Accepted handoff from phase 1; verify its actual deliverables.

**Outcome:** Make a session recoverable and isolated across stateless Lambda invocations.

**Deliverables**

- Declare the sessions table, TTL configuration, environment binding and least-privilege grants in infrastructure.
- Implement create/read session and persistence for state/turns/claims; use opaque proof with expiry, state versions and request-ID replay/conflict rules.
- Provide conditional claims and bounded recovery before any future model work; preserve final-plan retention separately.
- Expose the proposed session routes through the packaged handler; test the session-proof boundary independently of browser cookies.

**Acceptance gate**

- A session survives handler re-creation; one session cannot read another with an ID alone.
- Expiry is enforced even while the record still exists; stale/duplicate/concurrent submissions have bounded deterministic outcomes.
- Retries do not double-apply state or counters; no model is invoked.

**Excluded:** No employee login, JWT, Redis, EC2 or UI implementation.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 3.

**New-chat prompt**

```text
Implement phase 2 only: Anonymous session persistence and access.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 2 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 3 — Smart Wizard and approved profile

**Entry:** Accepted handoff from phase 2; verify its actual deliverables.

**Outcome:** Complete the personalized intake journey with a reviewable, versioned profile.

**Deliverables**

- Implement reviewed skill/question definitions, eligibility/dependency rules, skipping and question budgets.
- Connect one bounded model-analysis call per conversational turn; validate proposed facts/provenance and use rule-selected fallback wording.
- Implement answer/review routes, persisted next questions, assumption confirmation and invalidation after edits.
- Cover the Backend-to-RAG fixture and another goal that must not receive backend-specific questions.

**Acceptance gate**

- At most ten core/four follow-up/two-per-axis questions; known slots are skipped.
- An ambiguous goal cannot silently become a specialized roadmap; inferred facts stay distinct from confirmed ones.
- A complete journey runs with a fake model; invalid analysis and in-flight duplicate cases do not trigger uncontrolled extra calls.

**Excluded:** No course search, roadmap generation, background jobs or React screens.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 4.

**New-chat prompt**

```text
Implement phase 3 only: Smart Wizard and approved profile.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 3 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 4 — Internal retrieval and prerequisite closure

**Entry:** Accepted handoff from phase 3; verify its actual deliverables.

**Outcome:** Produce traceable internal candidates before any plan generation.

**Deliverables**

- Implement focused Retrieve with explicit SEMANTIC, 15 results and record_type=course, separate from generation.
- Deduplicate by course/version/hash, retrieve missing prerequisite IDs with explicit bounds, detect cycles/missing evidence and honor explicit constraints.
- Resolve only user-approved equivalence assumptions; compute deduplicated known hours and coverage gaps.
- Build a labelled Arabic/English retrieval harness preserving the real legacy baseline and equal-k comparison.

**Acceptance gate**

- SEC-201 closure yields 68 hours without equivalence; shared prerequisites count once.
- Exact IDs, cross-track prerequisites, impossible constraints, mixed versions and sparse coverage are tested with evidence fixtures.
- The harness can run offline without model generation; live Retrieve measurements remain explicitly pending until authorized.

**Excluded:** No ingestion changes, Hybrid, reranking or unapproved live Sync.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 5.

**New-chat prompt**

```text
Implement phase 4 only: Internal retrieval and prerequisite closure.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 4 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 5 — External search and course-page evidence

**Entry:** Accepted handoff from phase 4; verify its actual deliverables.

**Outcome:** Supply bounded, privacy-conscious external candidates with field-level provenance.

**Deliverables**

- Implement Serper adapter and Secrets Manager ARN configuration; keep key material out of code, logs and browser responses.
- Build generic gap queries, at most three search requests including retries, five candidates per search and five page reads.
- Implement bounded public-page reads with DNS/redirect/destination checks and no JavaScript, login bypass or CAPTCHA circumvention.
- Normalize snippet/page evidence and unknown fields into the same resource/evidence contract used internally.

**Acceptance gate**

- Search budgets hold across errors/retries; private answers never enter query fixtures.
- Private/link-local/metadata/redirect destinations, oversized pages, injection content and provider failure are covered.
- Unavailable pages remain limited-evidence candidates; prices/hours/prerequisites are not invented.

**Excluded:** No new KB ingestion, external catalog archive, account signup or paid searches without explicit authorization.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 6.

**New-chat prompt**

```text
Implement phase 5 only: External search and course-page evidence.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 5 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 6 — Roadmap composition and deterministic validation

**Entry:** Accepted handoff from phase 5; verify its actual deliverables.

**Outcome:** Generate a valid, evidenced roadmap from an approved profile and candidate evidence.

**Deliverables**

- Implement outline/capability drafting, candidate matching and generation with initial 2048-token cap and experimental temperature 0.2.
- Compose internal/external adapters while keeping their budgets and source distinctions intact.
- Validate phase/resource/evidence references, dependencies, explicit constraints, equivalence, course/practice totals and unknown durations.
- Allow one bounded final-output repair, optionally at 4096 tokens, then explicit failure; expose immutable revision data and downloads-ready structure.

**Acceptance gate**

- An end-to-end in-process pipeline passes with fake providers for full, partial and time-infeasible coverage.
- Invented IDs/URLs, cycles, unsupported facts and duplicate hours are rejected or exposed as explicit gaps as specified.
- Valid JSON and arithmetic are reported separately from judged roadmap usefulness; no new schema drift.

**Excluded:** No SQS wiring, browser integration or claims of measured model superiority.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 7.

**New-chat prompt**

```text
Implement phase 6 only: Roadmap composition and deterministic validation.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 6 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 7 — Background jobs and durable plan revisions

**Entry:** Accepted handoff from phase 6; verify its actual deliverables.

**Outcome:** Run the tested planner outside the gateway timeout and expose recoverable job APIs.

**Deliverables**

- Declare generation SQS/DLQ, worker/event mapping and separate IAM; initial timeout 180s, batch one, zero batch window and visibility at least 1080s.
- Implement plan submission/status/read/revision routes, approved snapshots and immutable final-plan persistence.
- Handle dispatch gaps between DynamoDB and SQS, conditional job claims, repeated delivery, lease deadlines and stale-profile outcomes.
- Wire the phase-six planner into the worker; complete jobs only after validation and persistence.

**Acceptance gate**

- Submission returns 202 without doing generation synchronously.
- Dispatch failure/retry, redelivery, parallel worker claims, failed save, bounded recovery and DLQ outcomes are tested.
- Revisions preserve prior results and identify profile_version; infrastructure and offline worker/event tests pass.

**Excluded:** No deployment, intentional UI cutover, KB recreation or automatic deletion of retained plans.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 8.

**New-chat prompt**

```text
Implement phase 7 only: Background jobs and durable plan revisions.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 7 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 8 — Flask integration and React handoff

**Entry:** Accepted handoff from phase 7; verify its actual deliverables.

**Outcome:** Make the backend journey consumable by the user's React UI.

**Deliverables**

- Implement same-origin Flask proxy routes, opaque-cookie lifecycle, Origin checks and server-side SigV4 forwarding.
- Expose structured question/review/job/plan/error responses and Markdown/JSON downloads without the legacy text formatter.
- Document precise frontend actions, state ownership, polling/retry behavior, resume/new session, stale results and revision UX.
- Provide a local conformance journey using test clients/fake cloud responses; actual React production screens remain user-owned.

**Acceptance gate**

- No cookie secret/AWS/search key reaches browser JSON; production/development cookie settings are explicit.
- A full same-browser journey including resume/review/202/poll/read/download/revise works locally.
- Legacy UI/route regressions pass; frontend contract samples match actual backend responses.

**Excluded:** Do not build React screens unless separately requested; do not substitute a mock UI result for live AWS acceptance.

**Next handoff:** Record the implemented interfaces, configuration and fixtures required by phase 9.

**New-chat prompt**

```text
Implement phase 8 only: Flask integration and React handoff.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 8 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Phase 9 — Authorized deployment, evaluation and cutover

**Entry:** Accepted handoff from phase 8; verify its actual deliverables.

**Outcome:** Prove the real system and its cost/latency before intentionally activating the redesigned journey.

**Deliverables**

- Prepare exact-account/Region artifacts, change-set review, retained-resource checks, model/profile invocation and secret configuration.
- Obtain explicit authorization for deployment, paid model/search runs and any cutover; the phase prompt alone does not authorize unspecified cloud changes.
- Run live retrieval before generation, compare models under equal profiles/evidence and measure full-journey costs, time and failure paths.
- Exercise the real React journey when available, finalize operating/rollback instructions and change only verified statuses from planned to implemented.

**Acceptance gate**

- Recorded live evidence meets the agreed contract, isolation, budget, prerequisite and roadmap criteria.
- A measured cost/latency budget is approved before cutover; persistent search and retries are counted.
- Legacy fallback/rollback is reviewable. If React, credentials or authorization is absent, report that acceptance pending rather than declaring completion.

**Excluded:** No destructive cleanup, unapproved production changes, invented measurements or automatic model/KB migrations.

**Next handoff:** Report verified production/lab readiness and any pending UI, authorization, measurement or rollout work; there is no automatic next phase.

**New-chat prompt**

```text
Implement phase 9 only: Authorized deployment, evaluation and cutover.
Read docs/implementation/guided-career-planning-redesign-phases.md and its phase 9 scope, then docs/decisions/guided-career-planning-redesign.md and the relevant current code/documentation. Inspect the latest workspace and previous phase handoff; do not assume another chat completed its work.
Deliver the listed outputs and acceptance checks, preserving the legacy path and ingestion behavior. Respect the exclusions and shared execution rules. Do not expand into later phases or build React screens.
Do not deploy, Sync, create accounts/secrets, run paid provider tests or cut over traffic without explicit authorization for that action and target. For phase 9, prepare the exact proposed changes and obtain that authorization before applying.
Record actual changes/checks, remaining gaps and a precise handoff for the next phase. Stop after this phase.
```

## Required closing handoff for every phase

Use the predictable private path `.lab/redesign/phase-NN-handoff.md`, where NN is the two-digit phase number (01 through 09). Phase N reads the preceding checkpoint before work. Do not create acceptance checkpoints in advance; record actual results when that phase runs.

Save a concise dated checkpoint under the private .lab execution evidence area and include a self-contained summary in the chat. Keep the checkpoint free of credentials and raw user answers. The public docs should describe verified behavior, not private account evidence.

```text
Phase:
Status: accepted / incomplete / awaiting authorized live checks
Workspace/branch and commit if one exists:
Files/modules changed:
Implemented contracts/configuration and versions:
Checks run, commands and actual results:
Mock/offline evidence versus live evidence:
Remaining decisions, failures or prerequisites:
Infrastructure prepared versus actually applied:
Next phase and exact starting point:
```

If there is no commit, identify the workspace and changed files rather than inventing a revision. A new chat must inspect those files; do not rely on cross-chat memory. “Ready for the next phase” is justified only by its predecessor's gate. The checkpoint location is private; do not publish tokens, real account details or personal answers.

## Completion boundary

This plan itself is documentation. Implementation starts only when a phase is explicitly requested. Complete local gates first; phase 9 is the sole scheduled live-qualification stage, subject to explicit scope/authorization. Earlier authorized diagnostic reads or tests, if requested, must be labelled separately and do not replace the final acceptance sequence.

