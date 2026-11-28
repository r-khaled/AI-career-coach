# Project documentation

AI Career Coach generates career-development plans from an internal course catalog using Amazon Bedrock retrieval-augmented generation. This reference describes the implemented application, its infrastructure, data contracts and operating procedures.

## Documentation map

1. [Architecture](architecture.md): AWS components, trust boundaries, deployment ownership, ingestion and request-time flows.
2. [Code reference](code-reference.md): every runtime/build/setup module, generated Lambda handler, UI and tests.
3. [API and persistence contract](api.md): signed requests, fields, responses, DynamoDB and errors.
4. [Deployment](deployment.md): prerequisites, first-time provisioning, configuration, local startup and acceptance checks.
5. [Knowledge pipeline](knowledge-pipeline.md): catalog schema, custom chunking, metadata, embeddings and retrieval.
6. [Security and configuration](security.md): IAM identities, policies, Region/model selection and account portability.
7. [Operations](operations.md): updates, manual/weekly Sync, troubleshooting, rollback and cleanup.
8. [Cost model and controls](costs.md): Ohio unit prices, traffic scenarios, persistent search capacity and operating controls.
9. [Course-aware chunking decision](decisions/course-aware-chunking.md): measured source structure, alternatives and trade-offs.

The repository contains code for the full setup path, including Scheduler resources. A deployed environment can be at an earlier revision. Verify stack resources and schedule state before relying on automatic refresh; [operations](operations.md#verify-scheduling) provides the checks.

## Implementation status — reviewed 2026-11-28

[Implementation phases](implementation/guided-career-planning-redesign-phases.md) breaks the redesign into nine bounded, ordered work packages with deliverables, acceptance gates and ready-to-copy new-chat prompts. Phases 1–8 passed local gates. Phase 9 passed a limited reference live journey; full live acceptance and React remain pending. The reference infrastructure was subsequently destroyed.

[Guided Career Planning Redesign](decisions/guided-career-planning-redesign.md) records the agreed Smart Wizard journey, anonymous sessions, skills configuration, retrieval and external search, asynchronous generation, JSON contracts and implementation/acceptance plan. It remains the design authority. The implementation is recorded separately; the reference deployment is now historical.

## Historical before/after comparison coverage

The comparison sections preserve the pre-implementation proposals. Current sections above them document actual code; partial live results do not establish full acceptance.

- [Architecture](architecture.md): paired A/B diagrams in all eight sections.
- [API](api.md): current request/response alongside v2 routes, answer/review/job/plan/error examples and persistence flow.
- [Code reference](code-reference.md): current tree alongside proposed packages, proxy/handler/worker pseudocode, artifact separation and acceptance groups.
- [Knowledge pipeline](knowledge-pipeline.md): retained ingestion versus application configuration, metadata consumption, retrieval settings and generation/evidence flow.
- [Deployment](deployment.md): current commands alongside target release gates, migration checklists and configuration responsibilities.
- [Operations](operations.md): separate knowledge/job lifecycles, telemetry examples, diagnosis and rollback/retention paths.
- [Security](security.md): caller flows, role separation, session access, fetching controls and model/profile verification.
- [Costs](costs.md): preserved baseline estimates alongside new workload formulas, an unmeasured scenario worksheet and work-budget controls.
- [Chunking decision](decisions/course-aware-chunking.md): retained ingestion versus new application-level closure and evidence validation.
- [Canonical redesign](decisions/guided-career-planning-redesign.md): agreed design and schemas against which the examples are checked.

The existing JSON cost inputs and calculator remain baseline-only. The redesigned workload worksheet is documentation, not an implemented calculator or a measured estimate.

[Single-session orchestrator prompt](implementation/guided-career-planning-redesign-orchestrator-prompt.md) executes all nine phases with bounded worker parallelism and explicit dependency gates.

## Current implementation and release references

- [Runtime implementation](implementation/guided-runtime.md): modules, limits and local acceptance.
- [React integration](react-integration.md): delivered Flask contracts and client examples.
- [Historical live results and deployed diagram](implementation/live-deployment.md): measured samples and unresolved gates.
- [Version history](implementation/version-history.md): old and new version anchors and nine-phase results.
- [Stopping point and next steps](implementation/next-steps.md): verified teardown and future work.
