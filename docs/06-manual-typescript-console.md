<div dir="ltr" lang="en">

# 06. Rebuild by hand: TypeScript code and AWS Console

[README](../README.md) | [Previous: original run](05-run-original-demo.md) | [Next: Terraform](07-terraform-rebuild.md)

## Goal and boundary

After understanding and testing the reference application, rebuild it yourself with TypeScript. We will explain and write each piece together, then configure its AWS resources manually in the Console. This guide is the implementation plan; no TypeScript app or new AWS resources have been created by writing it.

Keep a separate implementation directory or repository, to be chosen with the user. Keep the Python reference available for comparison. Use distinct names for manually managed resources so CloudFormation cannot accidentally own them.

## 1. Design the smallest equivalent system

Preserve the same business task and JSON contract. Initially keep the UI local, use an HTTP API with IAM authorization, run the TypeScript backend as compiled JavaScript on Lambda, and keep a vector-store-based Bedrock Knowledge Base with S3/OpenSearch and DynamoDB storage.

Do not add employee login, a React migration, agents/tools, or a CI/CD system while translating the baseline. Those are independent design decisions. A local Node server can play Flask's current role and sign requests on the server; the browser must not contain long-lived AWS credentials.

Before writing infrastructure, agree on these decisions:

- Is the initial goal behavior parity, or should we also improve the response contract?
- Which parts of the previous knowledge setup will be recreated, and which are deliberately shared?
- How will successful and failed requests be identified in logs and persistence?
- Do we keep synchronous generation for the first pass, given the HTTP API timeout?

## 2. Write the contract and validation first

A starting request type mirrors the reference:

```typescript
type GeneratePlanRequest = {
  current_role: string;
  goal: string;
};
```

A TypeScript type disappears at runtime. We must also validate parsed input: object shape, string types, trimmed non-empty fields, and agreed maximum lengths. Handle malformed JSON and base64-encoded API bodies deliberately. Do not use an unchecked `JSON.parse(...) as GeneratePlanRequest` as the entire validation strategy.

Define the response fields and error shape. Decide how to expose citations. If choosing structured model output later, select a model/API capability that supports the chosen method or explicitly parse and validate the output; do not assume all models support a strict JSON schema mode.

**Checkpoint:** invalid inputs are rejected locally without calling Bedrock or DynamoDB.

## 3. Create a small file structure, then implement one function at a time

A proposed structure, not files already present:

```text
career-coach-typescript/
  src/
    handler.ts
    config.ts
    contracts.ts
    prompt.ts
    knowledge-base.ts
    plan-store.ts
  local/
    server.ts
  tests/
  package.json
  tsconfig.json
```

- `contracts.ts`: request validation and response definitions.
- `config.ts`: validate KB ID, model ARN, table name, and runtime Region configuration.
- `prompt.ts`: build the task clearly; distinguish company courses from optional external learning. Decide what to say when the catalog lacks relevant courses.
- `knowledge-base.ts`: use `BedrockAgentRuntimeClient` and `RetrieveAndGenerateCommand` from `@aws-sdk/client-bedrock-agent-runtime`.
- `plan-store.ts`: use the DynamoDB client/document client and a write command; choose keys and serialization deliberately.
- `handler.ts`: parse the HTTP API event, validate, call the application functions, and format the proxy response.
- `local/server.ts`: serve a simple local form and sign its request to the IAM-protected API. We will choose its minimal dependencies when implementing it.

The conceptual orchestration remains:

```text
parse -> validate -> build prompt -> retrieve and generate
      -> persist successful result -> return response
```

See the official [Bedrock JavaScript command reference](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/client/bedrock-agent-runtime/command/RetrieveAndGenerateCommand/) and [DynamoDB document client](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/Package/-aws-sdk-lib-dynamodb/). Pin the selected application dependencies when creating the actual package rather than depending on an unspecified runtime SDK version.

**Checkpoint:** test the handler with mocked model/storage boundaries. Check error behavior without incurring model requests.

## 4. Understand the Lambda build artifact

Lambda's Node runtime executes JavaScript. A local build compiles/bundles TypeScript and its chosen dependencies into a deployment artifact. We will choose ESM or CommonJS deliberately, set the package metadata consistently, and make the handler filename/export agree with the Console handler setting.

For example, an `index.js` file at the ZIP root exporting `handler` would use `index.handler`. A differently named output must use its corresponding handler setting. Uploading a ZIP with an unintended extra parent directory can break resolution.

This is a build step, not an infrastructure pipeline. We can run it locally and upload the ZIP from the Console. [AWS documents TypeScript Lambda packaging](https://docs.aws.amazon.com/lambda/latest/dg/typescript-package.html).

## 5. Configure the knowledge path in the Console

The user performs these operations with explanations at each boundary:

1. **S3:** create the manual lab's private source bucket in the agreed Region. Discuss encryption/versioning, then upload the mock catalog.
2. **Vector store:** select the agreed OpenSearch Serverless configuration and understand the collection versus index, vector dimension, and text/metadata/vector fields.
3. **Policies:** understand encryption, network access, IAM identity policies, and OpenSearch data access as different controls. Give the selected KB role access to the relevant collection/index, not every collection.
4. **KB role:** trust the Bedrock service and scope document-reading, embedding-model access, and required vector-store actions. Narrow trust/source conditions appropriately for the created KB.
5. **Knowledge Base/data source:** connect the bucket, embedding model, vector mapping, parser, and chunking settings. Record all identifiers. If the Console creates resources for you, inspect those resources explicitly rather than treating them as invisible defaults.
6. **Ingestion:** start Sync, inspect document counts/failures, and retrieve relevant chunks before testing generation.

If we intentionally reuse the previous catalog/index to avoid another paid store, record the shared owner and pass its KB ID to this application. That is different from claiming we recreated the whole knowledge pipeline. The learning objective is to understand every required resource either way.

**Checkpoint:** explain how the index's numeric dimensions relate to the embedding model, and why a new S3 object is not searchable until ingestion completes.

## 6. Create result storage and the Lambda role

Create the DynamoDB table with the agreed key design. For parity, use a string `user_id` partition key and string `timestamp` sort key. Discuss whether future stable identity, expiry, or query requirements should change that design. Do not enable Streams without an understood consumer requirement merely because the reference enabled them.

Create the Lambda execution role with Lambda service trust, basic logging permission, the intended model/retrieval permissions, and `PutItem` on this table. This is separate from the KB role and your local caller identity.

## 7. Create and test the Lambda

Choose a supported Node.js runtime at implementation time. Set the handler, execution role, memory, timeout, and environment configuration. Upload the built ZIP. Create a saved test event with the expected HTTP API body format and inspect the response plus logs.

Validate environment variables at startup. Use execution-role credentials inside Lambda; do not set laptop AWS keys or `AWS_PROFILE=devops` there. Avoid printing complete user prompts, credentials, or document content to logs.

**Checkpoint:** a direct Lambda test can generate and persist one appropriate plan, and expected failures are intelligible.

## 8. Create and connect the HTTP API

Create the HTTP API, Lambda proxy integration, `POST /generate-plan` route, IAM authorization, and chosen stage. Understand the integration payload version, invocation permission, route ARN, and deployed URL.

Review API timeout, request throttling, CORS needs, and logging. CORS matters for browser-origin cross-site requests; it is not the authentication control for the local server's signed call.

The local caller needs invoke permission for this route. Confirm an unsigned request fails and a properly signed request reaches Lambda.

## 9. Run the TypeScript application end to end

Open the local preview, submit the reference scenario, and inspect the plan, citations, stored item, and logs. Then test invalid input, an unauthorized call, a model/configuration error, and the agreed timeout behavior.

Check token usage and actual charges where the APIs/billing tools expose them; do not assume `RetrieveAndGenerate` returns the same usage fields as every model-invocation API.

Improve observability with a request ID and safe structured logs. Decide on retry/idempotency before allowing a timed-out generation to be retried automatically. Keep any changes from Python behavior explicit in our learning notes.

## 10. Record the manual architecture before Terraform

Write down names/IDs, Region, model ARN, KB ID, index settings, role trust/policies, environment variables, API route/stage/integration settings, build artifact details, and ownership/cleanup choices. Record no credentials.

For each setting ask: is it a fixed design decision, a deploy-time input, a reference to another resource, or a generated output? That classification is the bridge from Console work to Terraform.

> **Checkpoint:** the manual application works, you can explain each Console setting, and the resource inventory is sufficient to reproduce it without relying on memory.

[Previous: original run](05-run-original-demo.md) | [Next: Terraform](07-terraform-rebuild.md)

</div>
