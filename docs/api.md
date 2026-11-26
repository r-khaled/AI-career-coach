# API and persistence contract

[Documentation](README.md) · [Code reference](code-reference.md) · [Security](security.md)

## Endpoint and authorization

The main stack's ApiEndpoint resolves to `https://<api-id>.execute-api.<region>.amazonaws.com/prod/generate-plan`. The only business route is POST `/generate-plan` under stage `prod`, with HTTP API payload v2 and AWS_IAM authorization. Use the output for the destination deployment; do not copy another account's URL. A GET to this endpoint is not a health route.

Sign calls with SigV4 for execute-api in the API's Region. The caller requires execute-api:Invoke on the route's ApiInvokeArn. Local Flask performs signing server-side using the standard boto3 provider chain. CORS does not replace this authorization. The API's permission to invoke Lambda is a separate resource-based grant scoped to this route.

## Request

```json
{"current_role":"Cloud Engineer","goal":"Security Engineer"}
```

Both fields are required. `user_id` is optional in the cloud handler; absent values generate a UUID. This field is not authenticated employee identity. The UI currently sends only current_role and goal. Level, track, per-course hours, total-plan hours and prerequisite restrictions are not supported request parameters in the current handler.

The integration wraps the request JSON in the Lambda event's `body` string. The handler does not support every alternate proxy format, such as base64-encoded bodies. It constructs a career-development prompt, invokes RetrieveAndGenerate with top five evidence records and up to 800 output tokens, and persists success before returning.

## Successful result

```json
{
  "user_id":"generated-or-supplied-id",
  "current_role":"Cloud Engineer",
  "goal":"Security Engineer",
  "career_plan":"Generated plan text",
  "citations":[],
  "timestamp":"UTC-ISO-format"
}
```

Status is 200 and Content-Type is application/json. Citations carry Bedrock's returned structure; this example's empty list is only a shape illustration. Plan text is not a strict JSON curriculum schema. Flask converts numbered text sections into template data and renders the result; it does not validate course IDs, duration totals or citation completeness.

## Persistence

DynamoDB table name comes from DynamoDBTable output. The key is `(user_id, timestamp)` and items contain the request fields, career_plan and citations. UTC timestamps currently omit a timezone suffix. PAY_PER_REQUEST billing and DynamoDB Streams are enabled, with no configured stream consumer, TTL or read/history API. A successful model call followed by a PutItem failure returns an error after generation may already be billed. Citation numeric serialization must be checked end to end.

## Error behavior

Missing required fields return 400. Missing KB configuration, Bedrock failures, persistence failures and other caught handler exceptions return 500 with an error body. A 403 at API Gateway can be a missing/invalid signature or missing route permission. Unmatched methods/routes fail at the API rather than generating a plan. Flask surfaces upstream/configuration errors in the page.

The gateway integration timeout is 30 seconds, application Lambda is 60 and Flask's HTTP timeout is 35. A timeout does not guarantee cloud work stopped. There is no idempotency key/duplicate-suppression mechanism, so inspect logs/records before retrying a costly request. API throttling is one request/second with burst two; this does not establish per-user quotas or an account cost cap.

For acceptance, verify a signed success, missing-field failure and unsigned denial, then inspect the stored record and citations. These checks are separate from ingestion/Retrieve tests and are not implied by a successful infrastructure update.
