# Security and configuration

[Documentation](README.md) · [Deployment](deployment.md) · [Operations](operations.md)

## Local caller

Flask uses the local boto3 credential provider chain to sign requests for API Gateway's `execute-api` service in the configured Region. Use an IAM user or temporary role/SSO session, never root for KB creation. Profile names select local configuration; they do not grant permissions. Credentials are not copied into Lambda or browser JavaScript.

The caller needs this identity-policy grant, substituting the exact ApiInvokeArn from main-stack Outputs:

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"execute-api:Invoke","Resource":"API_INVOKE_ARN_FROM_OUTPUTS"}]}
```

`POST /generate-plan` uses AWS_IAM. There is no JWT authorizer or employee identity layer. The current user_id is application input/default UUID, not a verified user identity. A production web identity design would need separate authentication and per-user authorization.

## Application execution role

The application role trusts Lambda and has basic CloudWatch execution logging, PutItem on the plans table, InvokeModel on the selected foundation model, Retrieve on the configured KB and RetrieveAndGenerate on `*` because that action lacks resource-level scoping. Logs record execution/errors; DynamoDB records successful requests/plans. The role does not need deployment/IAM-policy administration or access to ingestion artifacts.

API Gateway invokes the application through a separate Lambda resource-based permission restricted to the API/stage/POST route. This is not the application's execution role and not an extra IAM role for the browser.

## Ingestion execution role

The hook role trusts Lambda and can GetObject/PutObject only under the intermediate bucket's `kb-intermediate/*`, plus writes to its dedicated log group/streams. It cannot read arbitrary source/artifact objects, call Bedrock models, write DynamoDB or access OpenSearch. The group is created by CloudFormation with seven-day retention. The function's additional resource permission trusts Bedrock for the destination account and exact configured KB ARN; bind that ID before source creation/Sync.

## KB service role and vector policies

The companion RAG role trusts Bedrock scoped to this account's KB ARN namespace, avoiding a role→KB circular reference. Source read is limited to the catalog and metadata sidecar, with scoped bucket listing. Intermediate Get/Put/Delete/list is scoped to its prefix. It can invoke the exact hook both unqualified and `$LATEST`, invoke Titan v2 and access the exact collection via aoss:APIAccessAll.

IAM access alone is insufficient: the OpenSearch data policy separately grants the KB principal index DescribeIndex/ReadDocument/WriteDocument. The deployer separately receives index lifecycle rights used by CloudFormation. The provided network policy permits collection endpoint connectivity over the public network; that does not authorize anonymous data access. Private endpoints/operator access are a separate production network design. Existing external KB roles/policies must already satisfy the contract and are not silently rewritten by setup.

## Scheduler execution role

When bound, the main stack adds a dedicated role trusted by scheduler.amazonaws.com with source account and **schedule-group ARN** conditions. It can StartIngestionJob on this KB and SendMessage to this DLQ only. It does not invoke generation, upload data or inherit the deployer's privileges. The encrypted SQS DLQ retains delivery failures for fourteen days; accepted-job document failures require separate monitoring.

## Deployment identity

The provisioner needs scoped CloudFormation, versioned S3, IAM role/policy/tag/pass-role, Lambda, Logs, DynamoDB, API Gateway, Bedrock, OpenSearch, Scheduler and SQS permissions for the chosen stacks/resources. IAM tagging/PassRole failures belong to the caller's permissions, not runtime roles. The script does not attach AdministratorAccess or elevate itself. Account SCPs/boundaries can still deny operations.

For a new index, the current IAM principal needs data-policy access and aoss:APIAccessAll; assumed-role sessions are resolved to IAM-role ARNs using iam:GetRole. A distinct CloudFormation execution role needs its own explicit data-plane setup. Keep privileges separate from application service identities.

## Data protection and controls

Both buckets block public ACLs/policies, use managed encryption and enable versioning. Deployment objects and source reads have separate prefixes/scopes; intermediate content lives in a different bucket. Versioning retains old content until deliberately removed; no lifecycle expiration or customer-managed KMS key is created. Use only synthetic catalog data in this configuration unless adding appropriate privacy/retention controls.

API throttling is one request/second with burst two; CORS is permissive, not an authorization mechanism. CloudWatch access logging, WAF, employee sign-in, alarms, idempotency, per-user quotas and a hard spending cutoff are not included. Application log retention is not explicitly bounded by this template. [Operational controls](operations.md) and [cost controls](costs.md).

## Region and model portability

The setup Region is explicit and the account comes from STS, optionally checked by --expected-account. CloudFormation's AWS::Region/AWS::AccountId resolve for the destination. Local AWS_DEFAULT_REGION must match the API. IAM names can collide across Regions; S3 names are global, so use distinct stack names per account/Region.

The working handler uses `MODEL_ARN = arn:aws:bedrock:${AWS::Region}::foundation-model/${FoundationModelId}` with an empty account field. KB ARNs contain the destination account separately. A literal source-account ID is not embedded in this model ARN. FoundationModelId supports Nova Lite v1 and the listed Sonnet/Haiku 4.5 IDs, but model availability/access and inference mode must be validated in the destination; the alternative model list is not a compatibility test.

A model requiring an inference profile needs a deliberately parameterized destination-account profile ARN plus profile/foundation-model/destination-Region permissions. Do not pass that profile ARN into the current model-ID parameter, which constructs a foundation-model ARN. This documentation does not modify the working generation invocation. [AWS profile invocation](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-use.html).

For an account move, deploy and bind new buckets, functions, KB/source IDs and API Outputs using the destination profile, re-evaluate retrieval, then test generation/citations/persistence before retiring old resources. Private evidence and environment files stay outside Git; never copy credentials into docs/issues.
