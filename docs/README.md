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

## Agreed future design — not implemented

[Implementation phases](implementation/guided-career-planning-redesign-phases.md) breaks the redesign into nine bounded, ordered work packages with deliverables, acceptance gates and ready-to-copy new-chat prompts. All phases start as planned; this document does not execute them.

[Guided Career Planning Redesign](decisions/guided-career-planning-redesign.md) records the agreed Smart Wizard journey, anonymous sessions, skills configuration, retrieval and external search, asynchronous generation, JSON contracts and implementation/acceptance plan. It is a future design, not a description of deployed behavior. The references above continue to describe the current implementation.

## Before/after comparison coverage

Target examples are design-only; implementation and live acceptance remain pending.

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
