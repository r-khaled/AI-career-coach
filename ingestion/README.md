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
