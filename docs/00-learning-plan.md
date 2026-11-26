<div dir="ltr" lang="en">

# 00. Learning plan: understand, run, rebuild

[README](../README.md) | [Next: architecture](01-architecture.md)

## Working agreement

We are reading and discussing now. The user will decide when to deploy. No remaining command in this curriculum is an instruction for the assistant to execute automatically. Region selection, cost controls, and resource creation are separate decisions.

The user writes TypeScript. Python is only the existing reference implementation; learning enough Python to follow this small handler is sufficient for phase one.

## Phase 1: understand and run the reference application

### Step 1: explain the system before creating it

Read guides 01 through 04. Follow one request from the form to the response. Identify what CloudFormation creates and what still needs manual setup. Explain why there are separate embedding and generation models.

**Checkpoint:** you can describe where the courses live, how they become searchable, who calls Bedrock, what DynamoDB stores, and which identity authorizes each service call.

### Step 2: settle the environment

Choose the AWS account/profile, the final Region, the generation model, the embedding model, the vector-store configuration, the cost-alert scope, and the cleanup approach. `us-east-1` is a previously checked candidate; it is not locked in. A prepared change set in that Region does not force that choice.

**Checkpoint:** we have written down the chosen settings and understood their costs. We do not infer SSO, permissions, or model availability from a profile name.

### Step 3: deploy only after the user says to proceed

Use the existing CloudFormation stack for the baseline resources. Inspect its Events, Resources, and Outputs. Upload the course catalog, configure the vector-store-based Bedrock Knowledge Base in the Console, synchronize it, and connect its ID through the stack parameter.

**Checkpoint:** the stack and ingestion are successful, and a direct knowledge-base test returns relevant material.

### Step 4: open the preview and trace a real request

Run Flask locally with the deployed endpoint and the correct AWS profile/Region. Submit a role/goal pair. Inspect the returned plan and citations, the DynamoDB item, and Lambda's CloudWatch logs. Confirm an unsigned API request is rejected without reaching the model.

**Checkpoint:** evidence links input, retrieval, generation, persistence, and the displayed output. A local form or a mocked test alone does not satisfy this checkpoint.

## Phase 2: rebuild by hand with TypeScript and the Console

### Step 5: design and write the replacement together

Agree on the same request/response contract first. Create a separate TypeScript implementation. Write validation, the prompt, the Bedrock call, persistence, and error handling in understandable steps. Keep AWS operations behind small functions so the code can be tested without a billable request.

### Step 6: configure AWS resources yourself

Use a distinct resource-name prefix to identify this manual lab. Create and explain S3, the vector store and its access policies, the Knowledge Base and its role, DynamoDB, the Lambda role/function, and the HTTP API. Upload compiled JavaScript, not raw TypeScript.

The user performs Console actions while we explain what each field changes. No Terraform apply or CloudFormation deployment creates this manual lab.

### Step 7: verify the rebuilt application

Repeat the baseline scenario and the error checks. Compare behavior rather than exact generated sentences. Record the dependencies and settings discovered in the Console; those notes become the requirements for Terraform.

**Checkpoint:** the TypeScript implementation works, and you can explain every resource connection without relying on an opaque deployment command.

## Phase 3: reproduce the understood architecture with Terraform

### Step 8: start with explicit resources

Learn provider configuration, variables, resource references, outputs, plan, apply, and state. Build the smallest working pieces first. Keep the application build artifact separate from infrastructure configuration.

### Step 9: complete the knowledge path and request path

Add the vector index, service roles/policies, Knowledge Base and data source, Lambda packaging, API integration/route/stage, invocation permissions, and required settings. Check actual provider coverage before selecting resource types.

### Step 10: extract modules after one complete working version

Group by useful responsibilities: knowledge ingestion/search, API/runtime, and result storage, with clear inputs and outputs. Do not create a module for every AWS resource just to have more folders.

**Checkpoint:** Terraform can create the lab, expose the API output, pass the same scenario, and remove its owned resources without touching the previous experiments.

## A realistic same-day route

The goal is to complete all three phases today if account access, quotas, ingestion, and understanding allow it. These are planning ranges, not completion promises:

- Reading and discussion: about 45-75 minutes.
- First deployment and end-to-end inspection: about 60-90 minutes, plus service provisioning time.
- Manual TypeScript/Console rebuild: about 2-3 hours.
- Terraform implementation and verification: about 1.5-2.5 hours.
- Cleanup, recording evidence, and remaining questions: about 30 minutes.

Move on when each checkpoint is understood. If time runs short, retain a working, explained checkpoint rather than marking an unfinished phase complete. Avoid running several paid vector-store labs in parallel just to follow this schedule.

## What comes after this lab

For the real estate application, RAG can help with descriptions, policies, and property documents. Current price, availability, permissions, and bookings should come from authoritative application APIs/data. An agent that executes actions adds tool permissions, action validation, and auditability beyond this read-and-recommend demo.

> **Discussion checkpoint:** explain the three phases back in your own words. Decide which concepts need clarification before choosing a Region or deploying.

[Previous: README](../README.md) | [Next: architecture](01-architecture.md)

</div>

## Reproducible setup and scheduled refresh

The [automation guide](automation.md) documents first-time CLI setup, guarded CloudFormation updates and weekly EventBridge Scheduler resources in the main stack. The initial setup creates/reuses the KB and performs Sync; Scheduler subsequently calls StartIngestionJob, independently of your machine. Its state/expression/timezone are configurable stack parameters; it is not active in the published live lab yet. A future TypeScript/Terraform rebuild should preserve that ownership and distinguish first-time provisioning, document refresh, and question-time generation. See the same guide for model ARN/account migration, permissions, cost and cleanup. The working application invocation is unchanged.
