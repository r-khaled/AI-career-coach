# Cost model and operating controls

[Documentation](README.md) · [Architecture](architecture.md) · [Operations](operations.md)

**Pricing basis:** USD, on-demand, US East (Ohio), checked 2026-11-26. This is an engineering estimate of the implemented topology, not an invoice or a claim of production measurements. The generation model is Nova Lite v1; embeddings are Titan Text Embeddings v2. Model and OpenSearch unit rates were cross-checked against AWS Price List API entries for us-east-2; other service rates use the linked AWS pricing references. Reprice when changing Region/model/service generation.

The reproducible inputs/rates are in [cost-model.json](cost-model.json), with an [offline calculator](../scripts/estimate_cost.py). No AWS calls or credentials are used by the calculator. Gross estimates exclude free tiers, credits, tax and discounts so account eligibility does not conceal persistent costs. Optional GPU acceleration, capacity growth, data transfer and external Flask hosting are explicitly outside the totals.

## Cost structure of this deployment

Most request-path costs scale with successful/attempted calls, tokens or duration. OpenSearch is different: the VECTORSEARCH collection uses indexing/search OCUs and managed storage, not a fixed price per search request. The reference collection was verified ACTIVE with standby disabled. For the small, nonredundant capacity case, assume 0.5 indexing OCU plus 0.5 search OCU; actual data/memory/shard demand may require more. There is no basis to assume scale-to-zero for this configuration. Same-key vector collections can share capacity; do not charge a separate floor to each shared collection blindly. [Capacity and billing](https://aws.amazon.com/opensearch-service/pricing/).

At $0.24 per OCU-hour for each compute category, this illustrative floor costs `730 × (0.5 + 0.5) × $0.24 = $175.20/month`, even with no user messages. Two hours cost $0.48 for this component; 24 hours cost $5.76. Redundant minimum capacity of 1 indexing plus 1 search OCU doubles that illustration to $350.40/month. These are capacity scenarios, not measured OCU-hours or hard bounds on a busy collection. Storage is additionally $0.024/GB-month in the Ohio price entry; the model reserves 0.1 GB as an allowance rather than reporting measured index size.

The live reference collection also reports vector acceleration enabled. That feature can incur separate accelerated-index-build compute when used; an enabled setting is not proof of a charge or of zero usage. The new RAG template does not explicitly configure this option, so inspect each deployed collection. GPU acceleration is not Titan embedding or the normal Search/Indexing OCU charge. Its actual usage is not measured here and is excluded from totals. [AWS acceleration contract](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/gpu-acceleration-vector-index.html).

## Per-service rates and formulas

### Bedrock generation and embeddings

Nova Lite on-demand input is $0.06/million tokens and output $0.24/million tokens. With assumed 3,000 input and 600 output tokens, each generation is `(3000 × 0.06 + 600 × 0.24) / 1,000,000 = $0.000324`. Input includes the generated prompt, retrieved evidence and service context, not just the two form fields. The 800-token output cap is implemented; 600 average output tokens is an assumption. [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/).

Titan v2 text embeddings use $0.02/million input tokens. A 150-token query costs $0.000003; five full ingestion passes of an assumed 12,000 source tokens cost $0.0012. These token counts were not measured. Scheduled Sync detects changes, so five weekly checks do not automatically imply five full re-embeddings; the model intentionally budgets full passes. No reranker, multimodal parser or extra LLM parser call is configured. KB orchestration has no separate base KB fee in this text-RAG use case; underlying model/search/storage charges remain. [Titan price](https://aws.amazon.com/blogs/machine-learning/get-started-with-amazon-titan-text-embeddings-v2-a-new-state-of-the-art-embeddings-model-on-amazon-bedrock/), [AWS KB cost example](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/cost.html).

### Application and ingestion Lambda

Use x86 on-demand request charges of $0.20/million and duration of $0.0000166667/GB-second. The application has 512 MB; at assumed 10 seconds it consumes 5 GB-seconds per call, approximately $0.0000835335 including the request. Waiting for Bedrock still counts toward Lambda duration. No provisioned concurrency is configured.

The hook has 256 MB; five assumed one-second transformations cost about $0.00002183 including requests. Actual invocation counts depend on processed inputs/retries, not user-message count. The model assumes one hook invocation per source per Sync. Lambda free allowances may reduce the invoice when available; they are not subtracted from these gross numbers. [Lambda pricing](https://aws.amazon.com/lambda/pricing/).

### HTTP API Gateway

This is an HTTP API, not a REST API/WebSocket/API destination. The initial pricing tier is $1.00/million billable calls, so 1,000 small requests cost $0.001. HTTP API size metering uses 512-KB request increments; the calculator assumes one unit per submitted plan. Larger requests/retries/unauthorized traffic need separate accounting. Response transfer is not included. [API pricing](https://aws.amazon.com/api-gateway/pricing/).

### DynamoDB

PAY_PER_REQUEST writes use $0.625/million write request units; a normal write is rounded up per 1 KB item size. At assumed 8 KiB per saved plan, 1,000 successful writes cost `1000 × 8 × 0.625 / 1,000,000 = $0.005`. The app has no table-read API; do not budget one read for vector retrieval, which uses OpenSearch instead.

Storage uses $0.25/GB-month; 1,000 assumed 8-KiB records retained for a full month cost about $0.00191. The calculator conservatively charges the whole month's new records for the full month. Prior retained records accumulate because no TTL is configured; index/citation growth can also increase item sizes. Streams have no configured consumer in this project. [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/).

### S3 and CloudWatch

S3 Standard reference rates are $0.023/GB-month, $0.005/1,000 PUT-class requests and $0.0004/1,000 GET-class requests. A combined 0.1-GB source/artifact/intermediate allowance plus 100 PUTs and 100 GETs costs $0.00284/month. Bucket creation is not charged as a reserved server. Versioning retains old objects and intermediate batches; growth is not capped by the small current catalog. Source S3 reads occur for ingestion, not as one direct source read for every question. [S3 pricing](https://aws.amazon.com/s3/pricing/).

CloudWatch log references are $0.50/GB ingestion and $0.03/GB-month archived storage. At 4 KiB assumed application logs/request, 1,000 requests cost about $0.00202 including a full month's archive. Ingestion logs have seven-day retention; the application log group does not have explicit template retention. Extra ingestion logs, Logs Insights scans, custom metrics and alarms are not covered by that per-request assumption. [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/).

### Scheduler and SQS

Scheduler is charged per invocation, with a published 14-million/month free allowance and $1/million above it. Five weekly invocations have a gross rate equivalent of $0.000005 and generally cost zero when allowance is available; no event-bus event or API Destination fee is added for this direct Scheduler SDK target. Starting a Sync still incurs any underlying ingestion work. Scheduler was deployed and enabled in the reference stack by the authorized setup run on 2026-11-26. [Scheduler pricing](https://aws.amazon.com/eventbridge/pricing/).

The standard SQS DLQ has no compute server charge; requests use $0.40/million after applicable allowance. A healthy schedule sends no DLQ messages. Reads/deletes/polling/retries and request-size units add usage if operated; an empty queue is not assumed to perform periodic polls by itself. The reference scenario assumes no DLQ activity. [SQS pricing](https://aws.amazon.com/sqs/pricing/).

IAM and native AWS CloudFormation resource management add no request-path server fee. No EC2, NAT Gateway, load balancer, CloudFront distribution, custom KMS key or deployed frontend is provisioned by this topology.

## Workload assumptions and scenarios

A message here means one plan request, one RetrieveAndGenerate, one successful DynamoDB write and one HTTP API/Lambda request. The scenarios assume no retries/failures, 10-second application duration, 3,000/600 generation input/output tokens, 150 query-embedding tokens, 8-KiB items, 4-KiB app logs, five full source Syncs and one hook call per Sync. Source token count is assumed 12,000; words/characters are not substituted as measured tokens. Each monthly scenario reserves 0.1 GB in S3 and 0.1 GB in OpenSearch and keeps the collection at one combined OCU for 730 hours. These are inputs to adjust, not load-test observations.

Generated totals from the calculator, including the modeled storage/Sync overhead:

- No plan requests: **$175.21/month**; search capacity dominates.
- 1,000 plan requests/month: **$175.63/month**; Nova is $0.324 and application Lambda about $0.0835.
- 10,000 plan requests/month: **$179.41/month**; Nova is $3.24 and application Lambda about $0.8353.
- 100,000 plan requests/month: **$217.25/month**; Nova is $32.40 and application Lambda about $8.3534.

These totals hold average search capacity fixed for comparison; higher traffic/data could force scaling, so the 100,000-message scenario is not a performance/capacity guarantee. A 2-hour run with 100 requests and one full Sync is approximately **$0.53** with the same conservative storage allowances, if resources are actually retired afterward. Leaving search running for days changes that result substantially.

Reproduce or vary the assumptions:

```bash
python scripts/estimate_cost.py --requests 1000
python scripts/estimate_cost.py --requests 10000 --duration-seconds 20 --input-tokens 5000
python scripts/estimate_cost.py --requests 100 --hours 2 --syncs 1
python scripts/estimate_cost.py --requests 1000 --indexing-ocus 1 --search-ocus 1
```

All output is JSON with the complete assumptions, service breakdown and exclusions. Fractional item sizes round upward for write units. Negative/nonfinite assumptions fail. Storage allowances are full-month charges even for the short-run example, making that comparison conservative; they are not duration-prorated automatically.

## Measured configuration versus actual invoice

A read-only check established the reference collection's type/redundancy and the absence of Scheduler on 2026-11-26. The billing query available during this review was still marked Estimated and did not contain settled OpenSearch/Bedrock line items. It does not establish a zero-cost deployment. Account-wide or Region-wide service totals also cannot be attributed precisely to this stack without allocation evidence.

Use Cost Explorer/CUR by service and usage type, hourly OCU metrics, model input/output tokens, Lambda billed duration, table size/consumed units, log bytes and versioned-object storage to reconcile estimates. Keep account invoices/IDs/credit balances in private evidence; they are not included in this public documentation. A reusable project's expected cost is not the original account's net post-credit bill.

## Controls implemented and operator actions

Implemented: API throttle one request/second with burst two; 800 generated-output-token cap; 60-second Lambda timeouts; fixed memory sizes; scoped IAM; seven-day ingestion-log retention; hash/version reuse of unchanged code/data; default-parser/custom-boundary ingestion without a paid LLM parser. These reduce particular costs but are not an account spending limit. The API throttle does not bound direct Bedrock calls or persistent OCU cost.

Operational controls: set account/Region service budgets and anomaly notifications; inspect account-level OpenSearch maximum indexing/search capacity before setting a shared limit; explicitly bound application-log retention and old S3 versions/intermediate data according to policy; validate duration/token inputs against actual usage; disable unnecessary refresh and remove owned search infrastructure after short runs. Budgets are alerts/actions configured separately, not an automatic universal hard cap. No budget/alarm/account-level OCU limit/object lifecycle/teardown timer is created by these templates. Avoid changing account-wide limits without assessing other workloads.

A model switch requires new unit prices and IAM/inference compatibility checks. Choosing another vector-store architecture is a separate design change; this document prices the implemented OpenSearch stack rather than silently assuming a cheaper store. See [cleanup ownership](operations.md#cleanup).
