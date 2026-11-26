# Single-session execution prompt — all nine redesign phases

Copy the entire execution prompt below into the new chat. Select gpt-6.1-sol with medium effort for that chat. The prompt requests worker overrides; it cannot itself change the already selected orchestrator model.

## Execution prompt

You are the orchestrator for implementing the complete AI Career Coach redesign in this one chat. Implement all nine phases, with verified gates, rather than stopping after phase 1 or asking the user to open nine chats.

Model and team configuration:
- Orchestrator: gpt-6.1-sol, medium reasoning effort.
- At most THREE active worker subagents, in addition to the orchestrator.
- Every worker must use model=gpt-6.1-terra and reasoning_effort=medium.
- For collaboration.spawn_agent use agent_type=worker and fork_turns=none when overriding the model. Supply a concise, complete task specification.
- Workers must not spawn further agents. Reuse idle workers where useful. Never silently substitute another model if the requested override is unavailable; report that limitation and continue feasible work.
- These model names identify Codex implementation agents, not the application's Bedrock models.

Read first:
1. Applicable AGENTS.md instructions and actual workspace changes.
2. docs/implementation/guided-career-planning-redesign-phases.md
3. docs/decisions/guided-career-planning-redesign.md
4. docs/architecture.md, docs/api.md, docs/code-reference.md, docs/security.md, docs/deployment.md, docs/operations.md and docs/costs.md.
5. Existing .lab/redesign/phase-NN-handoff.md checkpoints, if any; verify their claims against files and tests.

This instruction explicitly authorizes all nine implementation phases in one session. References that say “one phase per chat” or “stop after this phase” describe the optional standalone-chat mode. Here, those boundaries limit each worker's assignment; the orchestrator continues through the entire dependency graph. Do not reinterpret this task as another planning-only exercise.

Scope:
- Implement backend/application logic, declarative AWS infrastructure and packaging/setup changes, Flask integration and the React-facing contracts.
- React production screens and new frontend hosting are not requested. Do not add EC2, Redis, employee login/JWT, AgentCore or an agent loop.
- Keep the legacy endpoint behavior and existing knowledge ingestion compatible during migration.
- Do not discard other changes, rewrite history, automatically create worktrees/chats or publish code.
- Prepare cloud changes and local tests autonomously. Live deployment, Sync, paid provider tests, account/secret creation and traffic cutover still require explicit authorization for the concrete action/account/Region/budget. Git push authorization from the preparation chat is not AWS authorization.
- If a live action is awaiting authorization, finish all independent authorized work and record exactly what remains pending. Do not claim all nine phases accepted when live evidence or the real React UI is absent.

Execution and parallelism:
1. Inspect and freeze shared contracts/configuration boundaries first. Start from observed implementation, not future-design prose.
2. Phase 1: orchestrator owns shared decisions, CloudFormation/setup integration and review. After interfaces are fixed, split legacy extraction/packaging and schema/configuration fixtures into separate file ownership when useful.
3. Phase 2 follows the foundation; phase 3 consumes tested session interfaces. Do not parallelize dependent state semantics prematurely.
4. Phases 4 and 5 may run in parallel after phase 3 and evidence/resource contracts are stable. They must not edit each other's modules or shared schemas.
5. Phase 6 composes accepted internal/external evidence and produces a tested in-process planner.
6. Phase 7 wraps that planner in durable asynchronous jobs. Phase 8 proxy/download work may overlap only after route/response contracts are frozen, with separate file ownership; its full acceptance waits for phase 7.
7. Phase 9 follows integrated local gates and explicit live authorization. Keep retrieval evaluation before generation evaluation and cutover.
8. Use the third worker for a truly separate bounded task such as independent integration review/fixtures, not a competing edit of the same implementation. Otherwise use fewer workers.
9. The orchestrator owns shared files and final integration unless a single worker is explicitly assigned them. No worker may revert another's work.

Every worker assignment must contain:
- Phase/task ID and exact objective.
- Required source files, current interfaces and relevant approved schema/configuration excerpts.
- Owned files/modules and shared files they may not edit.
- Input/output shapes, error behavior and invariants.
- Concrete deliverables, edge cases, acceptance tests and exclusions.
- Dependency readiness and fake-versus-live provider rules.
- Required return summary: files changed, exact checks/results, unresolved assumptions and integration instructions.
Tell each worker it is not alone in the codebase, must preserve others' edits and must not delegate further.

Quality and resource control:
- Use meaningful subsystem tests and appropriate regressions; do not run paid/live calls as a substitute for fixtures.
- Preserve precise limits from the agreed redesign and version all additional defaults explicitly.
- Reuse compact state summaries rather than forwarding the full conversation to workers.
- Give workers one bounded assignment at a time. Avoid redundant exploration, repeated whole-suite runs without a new reason, and unlimited review/fix loops.
- A detailed specification reduces ambiguity but does not guarantee model correctness. Review and test every worker result before accepting it.
- Routine reversible decisions may be resolved from the repository and agreed design. Ask only for material unresolved requirements or action-specific live authorization.

The complete phase specifications follow. Their deliverables, acceptance gates and exclusions remain binding; proceed automatically to the next ready phase after accepting the current gate.

## Phase 1 — Contracts and application packaging

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 2 — Anonymous session persistence and access

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 3 — Smart Wizard and approved profile

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 4 — Internal retrieval and prerequisite closure

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 5 — External search and course-page evidence

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 6 — Roadmap composition and deterministic validation

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 7 — Background jobs and durable plan revisions

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 8 — Flask integration and React handoff

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

## Phase 9 — Authorized deployment, evaluation and cutover

**Entry:** Respect the dependency graph in the orchestration instructions above.

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

Documentation and persistence:
- Update public English before/after documentation only for behavior actually implemented and verified; preserve the private Arabic archive arrangement.
- After each phase write .lab/redesign/phase-NN-handoff.md with actual state, changes, contracts/configuration versions, commands/results, fake-versus-live evidence and pending items.
- Maintain .lab/redesign/execution-status.md with all nine phase states, dependency readiness, worker ownership and the next exact action.
- Checkpoint before context becomes tight; keep work resumable from files. Do not silently drop later phases or mark a pending gate accepted.
- Report concise progress at meaningful milestones and when a blocker changes what can proceed.

Final delivery:
- Summarize actual outcomes for each of the nine phases.
- List checks passed, failures and authorization/UI/provider dependencies still pending.
- Distinguish infrastructure prepared from infrastructure applied, and offline acceptance from live acceptance.
- Provide the React integration contract, operational/rollback notes and checkpoint locations.
- No claim of deployed success, measured cost or model superiority without recorded evidence.
