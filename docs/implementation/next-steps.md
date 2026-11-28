# Stopping point and next steps

## Verified teardown: 2026-11-26

- [x] Destroy the reference project in the reference account, Region `us-east-2`.
- [x] Verify the stack, OpenSearch Serverless collection, Bedrock knowledge base, both project S3 buckets (including object versions), DynamoDB tables, queues, Lambda functions, API, schedules, project log groups and dedicated IAM roles/policies are absent.
- [x] Retain source code, local catalog, backend contracts, local build artifacts and historical acceptance evidence.

A DynamoDB SYSTEM backup of the deleted sessions table remains under AWS management until 2026-12-31. AWS retains this deleted-table backup for 35 days at no additional cost ([AWS reference](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BackupDetails.html)). It is not a running table. Earlier usage charges may still arrive in billing; this teardown does not audit unrelated account resources or establish a zero account balance.

Private verification evidence is in `.lab/redesign/teardown/verification.json` and `additional-verification.json`. The first file checks USER backups; the second records the SYSTEM backup. Cloud deletion was observed, not merely requested.

## Ordered follow-up checklist

1. [x] Review public and private Arabic documentation against code and historical evidence, preserve old/new snapshots and record version anchors.
   - [ ] Prove fresh-account/Region rebuild and prepare the complete guided cost worksheet before future deployment. Current setup uses CloudFormation, not Terraform. Rebuild artifacts and catalog from local sources; old bucket object versions and deployed IDs no longer exist. Cross-account/Region portability still requires validating service availability, models/profiles, IAM, secret configuration and quotas. Version anchors and the authorized publication are recorded in [version history](version-history.md).
2. [ ] Design the lower-cost vector storage replacement. Compare supported alternatives and trade-offs in a separate task, preserve backend contracts where possible, then implement and test offline. No replacement has been selected or deployed.
3. [ ] Design and build React locally using `docs/react-integration.md` and `examples/guided/client.js`, starting with mocks and the conformance journey. Production React screens do not exist yet. Choose hosting separately. Authorize a bounded, short-lived deployment only after the storage/cost decision, then run real integration and remaining live acceptance with a cleanup deadline.

## Acceptance boundary

The historical reference deployment passed the guided API-to-worker plan journey; the latest recorded offline suite passed 166 tests. External Serper search, real React UI, cross-model comparison and full monetary cost acceptance remain incomplete. These tests were not rerun as part of documentation-only teardown bookkeeping. Legacy fallback remains in source, with no live endpoint after teardown. Restart requires redeployment; this is not a paused stack.
