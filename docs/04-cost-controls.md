<div dir="ltr" lang="en">

# 04. Cost targets, AWS Budgets, alerts, and spending controls

[README](../README.md) | [Previous: access and Region](03-aws-access-and-region.md) | [Next: running the demo](05-run-original-demo.md)

## 1. What did USD 5 mean?

The earlier choice of a two-hour session and a USD 5 target was a planning preference. It did not create an AWS Budget, set a Bedrock spending limit, reserve credits, or establish automatic shutdown.

No budget or budget action was created by this work. Existing account budgets were not inspected. The target can be discussed before deployment; no cost estimate for the complete lab has been verified yet.

Your recollection is consistent with AWS Budgets: you can configure a cost budget scoped to Bedrock and receive an alert when a threshold is crossed. That is a useful control and is separate from choosing a target in chat.

## 2. Ordinary AWS Budgets: track and notify

A cost budget defines an amount, period, and cost scope. Filters can select a service or Region; current Bedrock-specific product attributes also support finer selection where available. For a straightforward first control, use the Bedrock service filter and confirm its actual billed scope in your account. See [AWS budget filters](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create-filters.html).

An illustrative alert setup for a USD 5 budget could notify at 50%, 80%, and 100% of actual spend. These correspond to USD 2.50, USD 4, and USD 5. This is an explanation, not a setting we have applied.

Ordinary alerts rely on billing updates. AWS documents delayed updates/notifications, so the amount can be exceeded before an alert arrives. A two-hour lab can finish before updated billing data reaches an alert. See [AWS Budgets considerations](https://docs.aws.amazon.com/cost-management/latest/userguide/bcm-lite-use-budget.html) and [standard AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).

## 3. Budget Actions: do something when a threshold is met

An action can apply an IAM policy or SCP, or perform certain supported instance controls. It can run automatically or require approval. That is different from an email-only budget.

For example, a carefully scoped deny policy could restrict a lab identity's future model invocations. It needs explicit action permissions and testing. It would not delete an OpenSearch collection or stop every independently billed resource. Because the trigger still depends on budget evaluation, it is not a precise per-request USD 5 cutoff. See [Configuring budget actions](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html).

## 4. A separate feature: project Spend Limits

Current AWS documentation also describes project-level Spend Limits in the new AWS experience. These can pause a project at its limit. Their account/plan availability and scope are different from an ordinary service-filtered budget. The documented minimum is the greater of USD 20 or a conservative expected-spend estimate.

We have not inspected whether your account supports this experience. It should not be confused with a USD 5 Bedrock-only alert. See [Create a spend limit in AWS Settings](https://docs.aws.amazon.com/accounts/latest/reference/create-spend-limit.html).

## 5. Bedrock charges are only part of this lab

The lab can incur costs from:

- Generation-model input/output tokens.
- Embedding during ingestion and retrieval.
- Vector-store compute and storage.
- S3 storage, requests, and retained object versions.
- API Gateway requests, Lambda execution, and DynamoDB operations/storage.
- CloudWatch log ingestion/storage and any monitoring added later.

A Bedrock-only budget does not cover the other services. For the first lab, discuss both a Bedrock alert and a broader lab/account cost view. Tags help identify resources, but this template's tags do not automatically create a complete cost allocation policy for model invocations or manually created resources.

An application inference profile can help attribute model costs when requests actually use it and the relevant cost-allocation tags are activated. The current handler uses a foundation-model ARN directly, not an application inference profile. Adopting one requires explicit configuration/code-policy review. See [Inference profile cost tracking](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-application-inference-profiles.html).

## 6. OpenSearch can change the cost picture

Classic OpenSearch Serverless collections can retain a minimum compute charge while idle; standby configuration affects that baseline. NextGen collections in collection groups have a separate scale-to-zero capability. Storage charges remain a separate consideration.

Do not infer the billing mode from the word Serverless. Check the exact collection generation, redundancy, capacity, Region, and Knowledge Base compatibility before creating it. The newer cold-start behavior can also matter for a synchronous API's timeout.

Use [OpenSearch pricing](https://aws.amazon.com/opensearch-service/pricing/) and [scale-to-zero requirements](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scale-to-zero.html). We have not validated which generation/configuration the chosen Console Knowledge Base flow will create in this account.

A simple estimating formula is:

```text
vector compute estimate = indexing OCU-hours * indexing rate
                        + search OCU-hours * search rate
model estimate          = input tokens * input rate
                        + output tokens * output rate
lab total               = vector compute + storage + models + other services
```

Use the selected model/Region's actual published rates and units, such as price per million tokens. Do not treat the formula as a verified dollar estimate.

## 7. Future Console setup, after agreement

1. Open Billing and Cost Management, then Budgets.
2. Check existing budgets first; do not create duplicates or edit another workload's controls.
3. Choose a cost budget, its period, and agreed amount.
4. Configure the Bedrock service filter; inspect exactly what costs it includes.
5. Add actual-cost thresholds and the notification destination the user chooses.
6. If using SNS, verify topic permissions and subscription confirmation.
7. Decide separately whether broader cost coverage or a budget action is needed.
8. Record what is configured and its scope. Do not describe an alert as an instant hard cutoff.

Do not execute these steps during the documentation stage. No email address or new budget setting is needed to read and understand the project.

## 8. Immediate controls and cleanup

The current template limits output length and uses IAM authorization plus best-effort request throttling. These reduce some risks but do not enforce a total dollar ceiling. Lambda is still synchronous; duplicate retries can generate extra work. Stopping Flask stops this local client, not all costs of existing cloud resources.

For an effective lab limit, keep a small agreed number of test requests, inspect the vector-store choice before creation, track the session duration, and clean up owned paid resources when finished. Avoid keeping the original, manual, and Terraform vector stores running in parallel unless their cost is explicitly accepted.

> **Checkpoint:** explain the difference between a target, an alert, a budget action, and a project spend limit. Explain why a Bedrock-only budget cannot cover an idle vector store.

[Previous: access and Region](03-aws-access-and-region.md) | [Next: running the demo](05-run-original-demo.md)

</div>

## Reproducible setup and scheduled refresh

The [automation guide](automation.md) documents first-time CLI setup, guarded CloudFormation updates and weekly EventBridge Scheduler resources in the main stack. The initial setup creates/reuses the KB and performs Sync; Scheduler subsequently calls StartIngestionJob, independently of your machine. Its state/expression/timezone are configurable stack parameters; it is not active in the published live lab yet. A future TypeScript/Terraform rebuild should preserve that ownership and distinguish first-time provisioning, document refresh, and question-time generation. See the same guide for model ARN/account migration, permissions, cost and cleanup. The working application invocation is unchanged.
