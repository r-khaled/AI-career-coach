# Course-aware ingestion

This package provides the Bedrock transformation hook and reproducible setup/Sync tooling.

- `course_chunker.py`: pure schema validation and whole-course evidence/metadata extraction.
- `transform.py`: runtime Bedrock event/S3 adapter; handler `ingestion.transform.lambda_handler`.
- `prepare_lab.py`: deterministic three-file ZIP, manifest, fixtures and configuration examples.
- `setup_lab.py`: read-only preview, guarded provisioning, initial/manual Sync, status and Scheduler binding.

Only `__init__.py`, `course_chunker.py` and `transform.py` enter the Lambda ZIP. Build/setup commands run locally; weekly refresh is an AWS Scheduler target, not a local cron process or another Lambda.

```bash
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2
python -m ingestion.setup_lab setup --profile YOUR_PROFILE --region us-east-2 --apply --enable-schedule
python -m ingestion.setup_lab sync --profile YOUR_PROFILE --region us-east-2 --apply
python -m ingestion.setup_lab status --profile YOUR_PROFILE --region us-east-2
```

[Deployment](../docs/deployment.md) · [Pipeline contract](../docs/knowledge-pipeline.md) · [Code reference](../docs/code-reference.md) · [Operations](../docs/operations.md)

## Before/after redesign boundary (2026-11-26)

**Current implementation:** this package owns source validation, whole-course extraction, the transformation adapter and knowledge setup/Sync. It does not own user dialogue or plan jobs.

**Agreed target, not implemented:** [Guided Career Planning Redesign](../docs/decisions/guided-career-planning-redesign.md) retains this ingestion runtime and source schema initially. Application skill/question configuration, anonymous sessions, Serper evidence, prerequisite closure and structured plan validation belong to separately packaged application/worker code. Do not add them to the three-file transformation ZIP.

Knowledge edits still require deliberate upload/Sync. Application-only releases should gain their own deployment path rather than needlessly running this knowledge setup. That app-only path does not exist in the current CLI.
