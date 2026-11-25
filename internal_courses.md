# Internal Corporate Training Catalog

Catalog version: 2.0 | Updated: 2026-11-25 | Scope: synthetic internal learning data for the AI Career Coach lab.

This catalog contains 40 fictional courses across 10 tracks. Course availability, durations, assessments, and role mappings are demo data, not real enrollment offers, certifications, or guaranteed promotion requirements. Enrolling in a course does not itself provision AWS resources. Practical cloud labs require separately approved accounts, costs, and permissions.

## How to read this catalog

- Foundation: introductory skills; Intermediate: applied delivery skills; Advanced: design, operational judgment, or leadership built on earlier practice.
- Durations are estimated total learning hours, including exercises, not calendar weeks. Learners can combine courses into a three-to-six-month plan based on available study time.
- Prerequisites refer to course IDs in this catalog. Equivalent demonstrated skills can replace completing the named prerequisite; a learner does not need to repeat skills they already have.
- Target roles describe useful preparation, not employment eligibility. Role readiness also requires experience and assessment beyond course completion.
- Delivery for all courses: self-paced lessons and guided practice with a mentor-reviewed assessment. All courses are available in this demo catalog. No dates, seats, fees, or external certification exam entitlements are represented.
- Each course repeats its track and level so retrieved excerpts retain their context. A course may support more than one career path.

## Cloud Architecture Track

### Course ID: CLD-001
**Course Name:** Cloud and AWS Foundations
**Track:** Cloud Architecture
**Level:** Foundation
**Estimated Duration:** 12 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Understand compute, storage, databases, networking, and identity through a small application rather than a service-name checklist.
**Target Audience:** Junior Developers; IT Support Engineers; Cloud Engineer trainees.
**Skills Covered:** AWS service selection, shared responsibility, Regions, IAM basics, cost awareness.
**Learning Outcome and Assessment:** Draw a basic application architecture and explain its access boundaries and recurring cost drivers.

### Course ID: CLD-101
**Course Name:** AWS for Enterprise Architects
**Track:** Cloud Architecture
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** CLD-001
**Description:** Compare architecture choices for a departmental application, including failure recovery, network boundaries, least privilege, and infrastructure as code.
**Target Audience:** Cloud Engineers; Senior Developers; Solutions Architect trainees.
**Skills Covered:** AWS Solutions Architecture, VPC, IAM, reliability, Terraform concepts, cost management.
**Learning Outcome and Assessment:** Produce an architecture decision record with a failure scenario, recovery approach, and cost assumptions.

### Course ID: CLD-201
**Course Name:** Mastering Kubernetes on EKS
**Track:** Cloud Architecture
**Level:** Advanced
**Estimated Duration:** 28 hours, including practice.
**Prerequisites:** CLD-101, DVO-201
**Description:** Build on container fundamentals to understand Kubernetes workloads, service discovery, rollouts, permissions, and observability using an EKS lab.
**Target Audience:** DevOps Engineers; Backend Developers; Platform Engineers.
**Skills Covered:** Kubernetes, Docker, EKS, deployments, services, Prometheus, troubleshooting.
**Learning Outcome and Assessment:** Deploy a sample service, diagnose a failing workload, and demonstrate a controlled rollback.

### Course ID: CLD-301
**Course Name:** Architecture Reviews and Migration Planning
**Track:** Cloud Architecture
**Level:** Advanced
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** CLD-101
**Description:** Assess an existing application and plan an incremental migration with dependency mapping, acceptance criteria, security review, and rollback checkpoints.
**Target Audience:** Senior Cloud Engineers; Solutions Architects; Technical Leads.
**Skills Covered:** architecture reviews, migration sequencing, resilience, trade-offs, stakeholder communication.
**Learning Outcome and Assessment:** Present a migration proposal with alternatives and measurable success criteria.

---

## DevOps and Site Reliability Track

### Course ID: DVO-101
**Course Name:** Linux, Networking, and Git for Delivery
**Track:** DevOps and Site Reliability
**Level:** Foundation
**Estimated Duration:** 16 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Practice the operating-system, networking, and version-control skills needed to understand deployment failures and communicate useful diagnostic evidence.
**Target Audience:** Junior Developers; IT Support Engineers; Junior DevOps Engineers.
**Skills Covered:** Linux, processes, permissions, DNS, HTTP, Git, shell troubleshooting.
**Learning Outcome and Assessment:** Diagnose a sample connection failure and submit a small change through a Git review workflow.

### Course ID: DVO-201
**Course Name:** Containers and Repeatable Local Environments
**Track:** DevOps and Site Reliability
**Level:** Intermediate
**Estimated Duration:** 18 hours, including practice.
**Prerequisites:** DVO-101
**Description:** Package a small web service and its local dependencies, keeping configuration external and understanding image builds, logs, and container lifecycle.
**Target Audience:** Developers; Junior DevOps Engineers; QA Automation Engineers.
**Skills Covered:** Docker, images, containers, environment configuration, health checks.
**Learning Outcome and Assessment:** Build and run a reproducible local environment with a documented health check.

### Course ID: DVO-210
**Course Name:** CI/CD Fundamentals and Safe Releases
**Track:** DevOps and Site Reliability
**Level:** Intermediate
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** DVO-101
**Description:** Create a delivery workflow that validates changes, produces an identifiable artifact, and promotes it through an environment with an explicit rollback procedure.
**Target Audience:** Developers; DevOps Engineers; Release Engineers.
**Skills Covered:** CI/CD, automated checks, artifacts, deployment environments, rollback.
**Learning Outcome and Assessment:** Demonstrate a failed check blocking a release and restore the previous application artifact.

### Course ID: DVO-301
**Course Name:** Service Reliability and Incident Response
**Track:** DevOps and Site Reliability
**Level:** Advanced
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** DVO-210
**Description:** Define useful service indicators and alerts, investigate a simulated outage, and prioritize reliability improvements without introducing unnecessary platform complexity.
**Target Audience:** DevOps Engineers; Site Reliability Engineer trainees; Technical Leads.
**Skills Covered:** SLIs, SLOs, metrics, logs, alerting, incident response, postmortems.
**Learning Outcome and Assessment:** Run a simulated incident and write a blameless postmortem with concrete follow-up actions.

---

## Frontend Web Engineering (FWE) Track

### Course ID: FWE-101
**Course Name:** Accessible Web Foundations
**Track:** Frontend Web Engineering (FWE)
**Level:** Foundation
**Estimated Duration:** 16 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Build semantic, responsive pages and accessible forms while learning keyboard interaction, layout debugging, and browser behavior.
**Target Audience:** Junior Frontend Developers; UI Developers; Web Engineer trainees.
**Skills Covered:** HTML, CSS, responsive layout, accessibility, browser developer tools.
**Learning Outcome and Assessment:** Deliver a responsive form that works with keyboard navigation and clear validation feedback.

### Course ID: FWE-201
**Course Name:** JavaScript, TypeScript, and Browser APIs
**Track:** Frontend Web Engineering (FWE)
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** FWE-101, SDE-101
**Description:** Use typed application models, asynchronous requests, and browser APIs while distinguishing compile-time types from validation of real server responses.
**Target Audience:** Frontend Developers; Full-Stack Developer trainees.
**Skills Covered:** JavaScript, TypeScript, DOM, asynchronous code, fetch, runtime validation.
**Learning Outcome and Assessment:** Build a typed API client and handle loading, failure, empty, and successful UI states.

### Course ID: FWE-210
**Course Name:** React Applications and UI State
**Track:** Frontend Web Engineering (FWE)
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** FWE-201
**Description:** Structure a multi-screen interface around reusable components, predictable state, accessible forms, and clear data-fetching boundaries.
**Target Audience:** Frontend Developers; React Developer trainees; Full-Stack Developers.
**Skills Covered:** React, components, hooks, forms, routing, server state, component testing.
**Learning Outcome and Assessment:** Implement a small dashboard with routed screens, validated forms, and focused component tests.

### Course ID: FWE-301
**Course Name:** Frontend Performance and Architecture
**Track:** Frontend Web Engineering (FWE)
**Level:** Advanced
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** FWE-210
**Description:** Measure rendering and loading bottlenecks, define maintainable feature boundaries, and support accessible interfaces across languages and text directions.
**Target Audience:** Senior Frontend Developer trainees; Frontend Technical Leads.
**Skills Covered:** web performance, profiling, design systems, internationalization, RTL, frontend architecture.
**Learning Outcome and Assessment:** Profile an application, improve a measured bottleneck, and document a reusable UI architecture.

---

## Backend and API Engineering Track

### Course ID: BKE-101
**Course Name:** HTTP, APIs, and SQL Foundations
**Track:** Backend and API Engineering
**Level:** Foundation
**Estimated Duration:** 16 hours, including practice.
**Prerequisites:** SDE-101
**Description:** Model a small domain and expose clear API contracts while understanding request/response behavior and basic relational queries.
**Target Audience:** Junior Backend Developers; Full-Stack Developer trainees.
**Skills Covered:** HTTP methods, JSON, REST, SQL, relational modeling, status codes.
**Learning Outcome and Assessment:** Design a small API contract and relational schema with example queries.

### Course ID: BKE-201
**Course Name:** Node.js and TypeScript Services
**Track:** Backend and API Engineering
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** BKE-101
**Description:** Implement a service with explicit configuration, runtime request validation, structured errors, and testable business logic separated from transport code.
**Target Audience:** Backend Developers; Full-Stack Developers.
**Skills Covered:** Node.js, TypeScript, input validation, configuration, error handling, API testing.
**Learning Outcome and Assessment:** Build and test a CRUD service that returns consistent success and failure responses.

### Course ID: BKE-210
**Course Name:** Data Modeling and Reliable Persistence
**Track:** Backend and API Engineering
**Level:** Intermediate
**Estimated Duration:** 22 hours, including practice.
**Prerequisites:** BKE-101
**Description:** Choose storage and keys from access patterns, understand consistency and indexing, and handle duplicate writes and paginated reads.
**Target Audience:** Backend Developers; Data Engineer trainees; Full-Stack Developers.
**Skills Covered:** SQL, DynamoDB concepts, indexes, transactions, pagination, idempotency.
**Learning Outcome and Assessment:** Compare two storage designs and implement a persistence boundary with a duplicate-request strategy.

### Course ID: BKE-301
**Course Name:** Distributed Service Design
**Track:** Backend and API Engineering
**Level:** Advanced
**Estimated Duration:** 26 hours, including practice.
**Prerequisites:** BKE-201, BKE-210
**Description:** Design service interactions around realistic failure modes, explaining when synchronous APIs, background jobs, caching, and retry controls are appropriate.
**Target Audience:** Senior Backend Developer trainees; Backend Technical Leads.
**Skills Covered:** queues, asynchronous jobs, retries, timeouts, caching, observability.
**Learning Outcome and Assessment:** Document and prototype a workflow with bounded retries, request correlation, and recovery behavior.

---

## Cybersecurity and Application Security Track

### Course ID: SEC-101
**Course Name:** Security Foundations for Engineers
**Track:** Cybersecurity and Application Security
**Level:** Foundation
**Estimated Duration:** 12 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Recognize common application and cloud threats, classify sample data, and practice safe credential handling and reporting of suspicious behavior.
**Target Audience:** All Developers; QA Engineers; IT Support Engineers; Security Analyst trainees.
**Skills Covered:** confidentiality, integrity, availability, threat awareness, secrets, least privilege.
**Learning Outcome and Assessment:** Review a mock application and identify its assets, trust boundaries, and unsafe secret handling.

### Course ID: SEC-201
**Course Name:** Identity, Authentication, and Authorization
**Track:** Cybersecurity and Application Security
**Level:** Intermediate
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** SEC-101, BKE-101
**Description:** Distinguish user login from service authorization and evaluate access decisions across a browser, backend, and AWS service boundary.
**Target Audience:** Developers; Cloud Engineers; Security Engineers.
**Skills Covered:** IAM, RBAC, OAuth concepts, OIDC, JWT, sessions, policy evaluation.
**Learning Outcome and Assessment:** Design an access matrix and test permitted and denied requests for a sample API.

### Course ID: SEC-210
**Course Name:** Secure Application Development
**Track:** Cybersecurity and Application Security
**Level:** Intermediate
**Estimated Duration:** 22 hours, including practice.
**Prerequisites:** SEC-101, BKE-201
**Description:** Find and repair common web application weaknesses using validation, safe rendering, session controls, and focused negative security tests.
**Target Audience:** Backend Developers; Frontend Developers; Application Security Engineer trainees.
**Skills Covered:** input validation, injection prevention, XSS, CSRF, dependency risk, threat modeling.
**Learning Outcome and Assessment:** Threat-model a feature, remediate representative vulnerabilities, and demonstrate regression checks.

### Course ID: SEC-301
**Course Name:** Cloud Security Reviews and Detection
**Track:** Cybersecurity and Application Security
**Level:** Advanced
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** SEC-201, CLD-101
**Description:** Review an AWS application for overly broad access and exposed data, then define useful audit evidence and detection hypotheses for suspicious activity.
**Target Audience:** Security Engineers; Cloud Security Engineer trainees; Senior Cloud Engineers.
**Skills Covered:** cloud posture, IAM review, audit logs, detection, incident investigation.
**Learning Outcome and Assessment:** Produce a prioritized security review and investigate a simulated unauthorized-access event.

---

## Quality Engineering and Test Automation Track

### Course ID: QAE-101
**Course Name:** Software Testing Foundations
**Track:** Quality Engineering and Test Automation
**Level:** Foundation
**Estimated Duration:** 12 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Turn a feature description into testable acceptance criteria and cover normal, boundary, and failure cases with clear reproducible reports.
**Target Audience:** Junior QA Engineers; Developers; Business Analysts.
**Skills Covered:** test design, acceptance criteria, exploratory testing, defect reporting.
**Learning Outcome and Assessment:** Write a test charter and report a defect with reproducible steps and expected behavior.

### Course ID: QAE-201
**Course Name:** API and Integration Testing
**Track:** Quality Engineering and Test Automation
**Level:** Intermediate
**Estimated Duration:** 18 hours, including practice.
**Prerequisites:** QAE-101, BKE-101
**Description:** Test API behavior across success, invalid input, authorization failures, and persistence boundaries without relying only on UI clicks.
**Target Audience:** QA Engineers; Backend Developers; QA Automation Engineer trainees.
**Skills Covered:** HTTP testing, contracts, fixtures, test data, integration boundaries.
**Learning Outcome and Assessment:** Create a repeatable API test suite with isolated test data and meaningful assertions.

### Course ID: QAE-210
**Course Name:** Web UI Automation with TypeScript
**Track:** Quality Engineering and Test Automation
**Level:** Intermediate
**Estimated Duration:** 22 hours, including practice.
**Prerequisites:** QAE-101, FWE-201
**Description:** Automate user journeys with stable locators, explicit assertions, isolated state, and useful failure evidence while avoiding brittle timing assumptions.
**Target Audience:** QA Automation Engineers; Frontend Developers; SDET trainees.
**Skills Covered:** TypeScript, Playwright, locators, browser automation, test isolation.
**Learning Outcome and Assessment:** Automate a critical form journey and diagnose an intentionally failing browser test.

### Course ID: QAE-301
**Course Name:** Quality Strategy and Performance Testing
**Track:** Quality Engineering and Test Automation
**Level:** Advanced
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** QAE-201
**Description:** Build a quality strategy that balances unit, integration, UI, and performance checks against product risk and interprets realistic load-test results.
**Target Audience:** Senior QA Engineers; SDET trainees; Quality Leads.
**Skills Covered:** risk-based testing, load testing, performance baselines, release quality.
**Learning Outcome and Assessment:** Present a release-quality plan and analyze a controlled performance regression.

---

## Data Analytics and Data Engineering Track

### Course ID: DAT-101
**Course Name:** SQL and Data Literacy
**Track:** Data Analytics and Data Engineering
**Level:** Foundation
**Estimated Duration:** 16 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Explore a synthetic business dataset, ask measurable questions, and detect misleading aggregates and missing or inconsistent records.
**Target Audience:** Data Analyst trainees; Business Analysts; Developers.
**Skills Covered:** SQL, joins, aggregation, data quality, basic statistics.
**Learning Outcome and Assessment:** Answer business questions with reproducible SQL queries and documented data-quality caveats.

### Course ID: DAT-201
**Course Name:** Analytics and Business Dashboards
**Track:** Data Analytics and Data Engineering
**Level:** Intermediate
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** DAT-101
**Description:** Translate a business decision into well-defined metrics and a readable dashboard that distinguishes missing data, trends, and uncertainty.
**Target Audience:** Data Analysts; Business Intelligence Developer trainees; Product Analysts.
**Skills Covered:** metrics definitions, dashboards, visualization, reporting, stakeholder questions.
**Learning Outcome and Assessment:** Build a dashboard with explicit metric definitions and explain what decisions it can support.

### Course ID: DAT-210
**Course Name:** Python Data Processing and ETL
**Track:** Data Analytics and Data Engineering
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** DAT-101
**Description:** Transform source records into a validated dataset with explicit schemas, handling missing values, duplicates, and repeatable batch execution.
**Target Audience:** Data Engineer trainees; Data Analysts; ML Engineer trainees.
**Skills Covered:** Python, Pandas, ETL, schemas, data validation, batch processing.
**Learning Outcome and Assessment:** Build an ETL task with quality checks, failure reporting, and a safe rerun strategy.

### Course ID: DAT-301
**Course Name:** Reliable Data Pipelines and Modeling
**Track:** Data Analytics and Data Engineering
**Level:** Advanced
**Estimated Duration:** 26 hours, including practice.
**Prerequisites:** DAT-210
**Description:** Design maintainable data pipelines with incremental processing, ownership, lineage, and clear consumer contracts rather than ad hoc scripts.
**Target Audience:** Data Engineers; Analytics Engineers; Senior Data Analyst trainees.
**Skills Covered:** orchestration concepts, incremental loads, lineage, dimensional modeling, data contracts.
**Learning Outcome and Assessment:** Design a small analytical data model and demonstrate recovery from an interrupted pipeline run.

---

## AI, Machine Learning, and GenAI Applications Track

### Course ID: AIML-001
**Course Name:** AI Literacy and Responsible Evaluation
**Track:** AI, Machine Learning, and GenAI Applications
**Level:** Foundation
**Estimated Duration:** 12 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Distinguish machine learning, generative AI, RAG, and fine-tuning, and evaluate a simple AI feature against accuracy, privacy, and usefulness criteria.
**Target Audience:** All Engineers; Product Managers; Business Analysts; AI Engineer trainees.
**Skills Covered:** AI concepts, evaluation, hallucinations, privacy, human review.
**Learning Outcome and Assessment:** Create an evaluation checklist and analyze examples of unsupported AI-generated claims.

### Course ID: AIML-101
**Course Name:** Applied Machine Learning with SageMaker
**Track:** AI, Machine Learning, and GenAI Applications
**Level:** Intermediate
**Estimated Duration:** 28 hours, including practice.
**Prerequisites:** DAT-210, AIML-001
**Description:** Prepare a dataset, train a baseline model, evaluate leakage and overfitting, and understand the steps required to deploy and monitor it.
**Target Audience:** Software Developers; Data Analysts; ML Engineer trainees.
**Skills Covered:** Python, Scikit-learn, Pandas, Amazon SageMaker, model evaluation, MLOps concepts.
**Learning Outcome and Assessment:** Train a baseline on synthetic data and report meaningful validation metrics and limitations.

### Course ID: AIML-201
**Course Name:** RAG Applications with Bedrock Knowledge Bases
**Track:** AI, Machine Learning, and GenAI Applications
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** AIML-001, BKE-201, CLD-001
**Description:** Build a document-grounded application and understand ingestion, retrieval, prompt construction, citations, and evaluation separately from model training.
**Target Audience:** Backend Developers; Full-Stack Developers; GenAI Application Engineer trainees.
**Skills Covered:** Amazon Bedrock, embeddings, chunking, vector search, citations, retrieval evaluation.
**Learning Outcome and Assessment:** Demonstrate a grounded answer, inspect its retrieved sources, and evaluate one retrieval failure.

### Course ID: AIML-301
**Course Name:** Advanced GenAI: Fine-Tuning Models with Bedrock
**Track:** AI, Machine Learning, and GenAI Applications
**Level:** Advanced
**Estimated Duration:** 28 hours, including practice.
**Prerequisites:** AIML-201, AIML-101
**Description:** Compare prompting, retrieval, and model customization for a specific task; verify model and Region support before choosing any fine-tuning lab.
**Target Audience:** AI/ML Engineers; Senior Cloud Architects; GenAI Technical Leads.
**Skills Covered:** Generative AI, Amazon Bedrock, model customization, dataset curation, evaluation, prompt engineering.
**Learning Outcome and Assessment:** Produce a customization proposal with a curated sample dataset, evaluation baseline, and a justified alternative if fine-tuning is unavailable.

---

## Software Engineering Foundations and Serverless Track

### Course ID: SDE-101
**Course Name:** Programming, Git, and Problem Solving
**Track:** Software Engineering Foundations and Serverless
**Level:** Foundation
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Practice functions, data structures, version control, and systematic debugging through small exercises that prepare learners for typed application code.
**Target Audience:** Junior Developer trainees; QA Automation trainees; Career Switchers.
**Skills Covered:** programming fundamentals, JavaScript, Git, debugging, problem decomposition.
**Learning Outcome and Assessment:** Implement and review a small program with tests and a readable change history.

### Course ID: SDE-201
**Course Name:** Maintainable Code and Automated Tests
**Track:** Software Engineering Foundations and Serverless
**Level:** Intermediate
**Estimated Duration:** 20 hours, including practice.
**Prerequisites:** SDE-101
**Description:** Separate business rules from I/O, write useful tests, and refactor a small codebase without changing its intended behavior.
**Target Audience:** Software Developers; QA Automation Engineers.
**Skills Covered:** modularity, unit testing, dependency boundaries, refactoring, code review.
**Learning Outcome and Assessment:** Refactor a feature with focused regression tests and explain its module boundaries.

### Course ID: SDE-210
**Course Name:** Serverless Development Patterns
**Track:** Software Engineering Foundations and Serverless
**Level:** Intermediate
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** BKE-201, CLD-001
**Description:** Connect a typed application handler to managed cloud services, covering identity boundaries, request validation, event handling, and observable failures.
**Target Audience:** All Software Developers; Cloud Engineer trainees.
**Skills Covered:** AWS Lambda, API Gateway, DynamoDB, EventBridge, serverless deployment concepts.
**Learning Outcome and Assessment:** Implement a small serverless API and trace a request through its storage and logging boundaries.

### Course ID: SDE-301
**Course Name:** System Design and Technical Decisions
**Track:** Software Engineering Foundations and Serverless
**Level:** Advanced
**Estimated Duration:** 24 hours, including practice.
**Prerequisites:** SDE-201, BKE-210
**Description:** Turn product requirements into a simple architecture with explicit assumptions, reliability goals, data boundaries, and alternatives.
**Target Audience:** Senior Developer trainees; Full-Stack Engineers; Technical Leads.
**Skills Covered:** system design, capacity assumptions, trade-offs, API boundaries, architecture documentation.
**Learning Outcome and Assessment:** Present a system design and defend its trade-offs against a changing product requirement.

---

## Product, Delivery, and Engineering Leadership Track

### Course ID: PRD-101
**Course Name:** Product Discovery and Requirements
**Track:** Product, Delivery, and Engineering Leadership
**Level:** Foundation
**Estimated Duration:** 12 hours, including practice.
**Prerequisites:** None; suitable as an entry point.
**Description:** Distinguish user needs from proposed solutions and express a small product opportunity as testable outcomes and bounded requirements.
**Target Audience:** Business Analysts; Product Owner trainees; Developers.
**Skills Covered:** user problems, interviews, requirements, acceptance criteria, prioritization.
**Learning Outcome and Assessment:** Write a problem statement and a prioritized feature brief with acceptance criteria.

### Course ID: PRD-201
**Course Name:** Product Metrics and Experimentation
**Track:** Product, Delivery, and Engineering Leadership
**Level:** Intermediate
**Estimated Duration:** 18 hours, including practice.
**Prerequisites:** PRD-101, DAT-101
**Description:** Define measurable product outcomes, design small experiments, and interpret results without claiming causality from an uncontrolled dashboard.
**Target Audience:** Product Managers; Product Analysts; Business Analysts.
**Skills Covered:** success metrics, hypotheses, experiments, basic statistics, ethical evaluation.
**Learning Outcome and Assessment:** Create an experiment proposal with a primary metric, guardrails, and interpretation limits.

### Course ID: PRD-210
**Course Name:** Agile Delivery and Cross-Team Communication
**Track:** Product, Delivery, and Engineering Leadership
**Level:** Intermediate
**Estimated Duration:** 16 hours, including practice.
**Prerequisites:** PRD-101
**Description:** Plan a small delivery increment with clear ownership, manageable scope, and visible dependencies while communicating uncertainty early.
**Target Audience:** Technical Leads; Product Owners; Delivery Coordinator trainees.
**Skills Covered:** backlog refinement, estimation, dependencies, delivery risks, stakeholder communication.
**Learning Outcome and Assessment:** Create a delivery plan and communicate a scope or dependency change to stakeholders.

### Course ID: PRD-301
**Course Name:** Technical Leadership and Mentoring
**Track:** Product, Delivery, and Engineering Leadership
**Level:** Advanced
**Estimated Duration:** 22 hours, including practice.
**Prerequisites:** PRD-210, SDE-301
**Description:** Develop engineering leadership through mentoring, clear delegation, constructive feedback, and facilitation of decisions across product and engineering.
**Target Audience:** Senior Engineers; Technical Lead trainees; Engineering Manager trainees.
**Skills Covered:** mentoring, feedback, delegation, technical strategy, decision facilitation.
**Learning Outcome and Assessment:** Produce a mentoring plan and facilitate a documented technical decision with competing stakeholder needs.

---

## Example learning paths

These are illustrative sequences, not individualized recommendations or proof of role readiness. Include prerequisites or demonstrate equivalent skills first.

- Junior Frontend Developer to Senior Frontend Developer: FWE-101 → FWE-201 → FWE-210 → FWE-301, with SDE-201 for maintainability and SEC-101 for security awareness.
- Junior Backend Developer to Backend Engineer: SDE-101 → BKE-101 → BKE-201 → BKE-210; then consider BKE-301 for distributed design.
- Developer to QA Automation Engineer: QAE-101 → QAE-201 → QAE-210, with FWE-201 for browser automation prerequisites.
- IT Support Engineer to Cloud Engineer: CLD-001 → DVO-101 → CLD-101, with SEC-101 for security fundamentals.
- Developer to DevOps Engineer: DVO-101 → DVO-201 → DVO-210, then DVO-301 when operational reliability becomes part of the role.
- Backend Developer to Application Security Engineer: SEC-101 → SEC-201 → SEC-210; add SEC-301 for cloud-security responsibilities.
- Business Analyst to Data Analyst: DAT-101 → DAT-201; add DAT-210 when repeatable data preparation is needed.
- Data Analyst to Data Engineer: DAT-101 → DAT-210 → DAT-301.
- Backend Developer to GenAI Application Engineer: AIML-001 → AIML-201, with the backend/cloud prerequisites; fine-tuning is not a mandatory starting point.
- Senior Engineer to Technical Lead: SDE-301 → PRD-101 → PRD-210 → PRD-301, accounting for each course's prerequisites.

## Coverage boundaries

This catalog covers engineering, cloud, security, quality, data, AI application development, product delivery, and introductory technical leadership. It does not represent a complete curriculum for every specialty, a university degree, or regulated professional training. A career goal outside these areas may only be partially supported by these internal courses.
