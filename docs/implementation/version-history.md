# Version history and acceptance

Reviewed 2026-11-28. Version anchors preserve source and documentation; they do not recreate deleted cloud data or establish production readiness.

## Legacy baseline

`old-architecture` is an annotated tag at `b7f5a2df5dc915ec4c4e520483f5f1be5eb16b04`, the existing `origin/main` tip verified before publication. It contains the old inline application and ingestion implementation, plus the design documents already present at that time. The planned redesign in those documents was not yet implemented in that revision. Restore or inspect this tag without overwriting uncommitted work.

## Guided redesign and frontend contract

`guided-redesign-v1` and `react-contract-v1` mark the same final reviewed revision of this release. The former identifies the implemented backend/infrastructure redesign; the latter identifies the schema version 1.0 backend handoff to the future React client. Two tags do not imply two different APIs or a completed UI.

The first two commits are `4d1d6ed` (runtime) and `2ea4ccd` (infrastructure/Flask). Changes are published in three ordered commits: (1) packaged runtime, strict contracts, wizard/evidence/planning/jobs and subsystem tests; (2) declarative infrastructure, setup/release tooling, Flask proxy and integration/conformance tests; (3) documentation, historical comparisons, acceptance and version anchors. This is a logical split of the existing working changes, not an invented reconstruction of phase-by-phase historical commits.

## Nine-phase result

1. Contracts and packaging: implemented; extracted compatible legacy handler, strict schemas/fixtures, locked deterministic application/worker artifacts independent of ingestion.
2. Anonymous persistence: implemented; proof isolation, logical expiry, conditional versions, claims/replay and bounded records passed offline gates.
3. Smart Wizard and approval: implemented; reviewed definitions, budgets, provenance, fallback and version-bound review passed offline gates. Model intake also participated in the limited live journey.
4. Internal evidence: implemented; explicit SEMANTIC/15/course retrieval, ID prerequisite closure and deterministic hours. SEC-201 was 68 hours offline and in a historical live check. The ranking harness uses synthetic ranks; live comparative ranking acceptance remains pending.
5. External evidence: implemented and checked offline for request/page budgets, SSRF, provenance and provider failure. No configured Serper secret was available for live acceptance.
6. Planning and validation: implemented and checked offline with fake providers; a historical live plan passed schema, evidence, dependency and arithmetic validation. This does not prove career usefulness or model superiority.
7. Background jobs and revisions: implemented; queue/DLQ, separate worker/IAM/artifact, outbox, claims, bounded recovery and immutable revisions. A historical SQS worker completed and saved a readable plan. Not every injected failure case was reproduced live.
8. Flask and React handoff: implemented; cookie/Origin/SigV4 routes, structured downloads, client example and offline start/answer/resume/review/202/poll/read/download/revise conformance. Production React and its real end-to-end acceptance remain absent.
9. Live qualification and transition: partial; reference deployment and limited live journey passed, then all dedicated reference infrastructure was destroyed at the user's request. Cross-model comparison, external search, real React, complete invoiced cost acceptance and cutover remain pending. The project is not declared fully accepted.

## Recorded checks and measurements

On 2026-11-28, `python -m unittest discover -s tests -v` passed 166 tests. `cfn-lint CloudFormation.yaml infrastructure/*.json` and `git diff --check` passed. These are local checks; no cloud redeployment, Sync or paid trial was performed for this publication. Static documentation link checks cover public local file targets; private Arabic HTML was regenerated or its current-status banner refreshed while preserving existing diagrams.

The historical live reference had 31 stack resources (13 added/imported and 18 baseline); dedicated external KB/OpenSearch ownership was separate. One successful synthetic journey recorded 13 model calls, 38,712 input / 4,021 output tokens and a 16-second generation job. Separate SEC-201 retrieval took 6.09 seconds. Total bill, diagnostic/failed-attempt cost and production latency were not measured completely. [Historical live results and deployed diagram](live-deployment.md) retain the details.

## Stopping point and recovery

The old/new architecture and code explanations remain side by side in the main references. Pre-execution proposals, old names such as `backend/`, and original phase prompts are explicitly historical. Current code uses `career_coach/`. [Runtime](guided-runtime.md) is the implementation record; [React integration](../react-integration.md), `career_coach/schemas/`, `career_coach/fixtures/` and `examples/guided/client.js` are the frontend handoff.

Reference stack, external KB/OpenSearch, versioned project buckets, retained tables, functions, queues, API, schedules, dedicated IAM and project logs were removed on 2026-11-26. A provider-managed DynamoDB SYSTEM backup expires 2026-12-31 at no additional cost. Private evidence/checkpoints and Arabic documentation remain ignored by Git; credentials and raw user answers are not release artifacts. Local source and catalog remain, but deleted AWS identifiers/object versions cannot restore the environment by themselves. Legacy fallback remains in source, with no live endpoint. Rebuild needs reviewed target configuration and new cloud/spend authorization.

Next: cost/vector-store redesign and offline React work, followed by an explicitly bounded deployment. Fresh-account/Region bootstrap, final cost worksheet and full live acceptance remain future gates. See [next steps](next-steps.md).
