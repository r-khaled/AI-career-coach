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
