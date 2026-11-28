import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cfnlint.decode import decode
from botocore.session import get_session
from botocore.validate import validate_parameters
from ingestion import setup_lab as lab


def resource(action="Modify", replacement="False", name="Example"):
    return {"ResourceChange": {"Action": action, "Replacement": replacement, "LogicalResourceId": name}}


def stack(parameters=None, outputs=None, status="UPDATE_COMPLETE"):
    return {"StackStatus": status,
        "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in (parameters or {}).items()],
        "Outputs": [{"OutputKey": k, "OutputValue": v} for k, v in (outputs or {}).items()]}


class ChangeSetTests(unittest.TestCase):
    def test_delete_and_replacements_are_rejected_except_explicit_permission(self):
        for change in [resource("Remove"), resource(replacement="True"), resource(replacement="Conditional")]:
            with self.assertRaises(RuntimeError):
                lab.review_changes([change])
        lab.review_changes([resource(replacement="True", name="IngestionBedrockPermission")], {"IngestionBedrockPermission"})
        with self.assertRaises(RuntimeError):
            lab.review_changes([resource("Remove", name="IngestionBedrockPermission")], {"IngestionBedrockPermission"})

    def test_noop_preserves_parameters_and_never_executes(self):
        cfn = Mock()
        current = stack({"FoundationModelId": "existing-model", "KnowledgeBaseId": "EXISTING01"})
        cfn.describe_stacks.return_value = {"Stacks": [current]}
        cfn.create_change_set.return_value = {"Id": "changeset"}
        cfn.describe_change_set.return_value = {"Status": "FAILED", "StatusReason": "The submitted information didn't contain changes."}
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lab.deploy(cfn, "example", "{}", {}, Path(temp)), current)
        self.assertTrue(all(p["UsePreviousValue"] for p in cfn.create_change_set.call_args.kwargs["Parameters"]))
        cfn.execute_change_set.assert_not_called()

    def test_paginated_delete_is_detected_before_execution(self):
        cfn = Mock()
        cfn.describe_stacks.return_value = {"Stacks": [stack()]}
        cfn.create_change_set.return_value = {"Id": "changeset"}
        cfn.describe_change_set.side_effect = [{"Status": "CREATE_COMPLETE", "Changes": [resource()], "NextToken": "next"}, {"Changes": [resource("Remove")]}]
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(RuntimeError):
            lab.deploy(cfn, "example", "{}", {}, Path(temp))
        cfn.execute_change_set.assert_not_called()

    def test_rollback_is_failure_not_success(self):
        cfn = Mock()
        cfn.describe_stacks.side_effect = [{"Stacks": [stack()]}, {"Stacks": [stack(status="UPDATE_ROLLBACK_COMPLETE")]}]
        cfn.create_change_set.return_value = {"Id": "changeset"}
        cfn.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "Changes": [resource()]}
        cfn.describe_stack_events.side_effect = lambda **kw: {"StackEvents": [{
            "ClientRequestToken": cfn.execute_change_set.call_args.kwargs["ClientRequestToken"],
            "ResourceType": "AWS::CloudFormation::Stack", "LogicalResourceId": kw["StackName"],
            "ResourceStatus": "UPDATE_ROLLBACK_COMPLETE"}]}
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            lab.deploy(cfn, "example", "{}", {}, Path(temp))
        cfn.delete_stack.assert_not_called()

    def test_previous_success_does_not_finish_a_new_deployment(self):
        cfn = Mock()
        cfn.describe_stacks.return_value = {"Stacks": [stack()]}
        cfn.create_change_set.return_value = {"Id": "changeset"}
        cfn.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "Changes": [resource()]}
        polls = []
        def events(**kw):
            polls.append(1)
            return {"StackEvents": [] if len(polls) == 1 else [{
                "ClientRequestToken": cfn.execute_change_set.call_args.kwargs["ClientRequestToken"],
                "ResourceType": "AWS::CloudFormation::Stack", "LogicalResourceId": kw["StackName"],
                "ResourceStatus": "UPDATE_COMPLETE"}]}
        cfn.describe_stack_events.side_effect = events
        with tempfile.TemporaryDirectory() as temp, patch.object(lab.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            lab.deploy(cfn, "example", "{}", {}, Path(temp))
        self.assertEqual(len(polls), 2)


class SyncTests(unittest.TestCase):
    def test_complete_with_failed_documents_is_failure(self):
        with self.assertRaises(RuntimeError):
            lab.check_job({"status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 1}})
        with self.assertRaises(RuntimeError):
            lab.check_job({"status": "COMPLETE"})
        lab.check_job({"status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 0}})

    def test_active_job_is_reused_without_another_start(self):
        agent = Mock()
        agent.get_paginator.return_value.paginate.return_value = [{"ingestionJobSummaries": [{"status": "IN_PROGRESS", "ingestionJobId": "existing"}]}]
        agent.get_ingestion_job.return_value = {"ingestionJob": {"status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 0}}}
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            lab.sync(agent, "KB", "DS", Path(temp))
        agent.start_ingestion_job.assert_not_called()
        self.assertEqual(agent.get_ingestion_job.call_args.kwargs["ingestionJobId"], "existing")

    def test_retrieval_waits_for_index_refresh_without_starting_ingestion(self):
        runtime = Mock()
        # Pick the actual first course ID from the repository, rather than mirror a fixed mock ID.
        chunks = lab.chunk_catalog((lab.ROOT / "internal_courses.md").read_text())
        expected = next(c["contentMetadata"]["course_id"] for c in chunks if c["contentMetadata"]["record_type"] == "course")
        runtime.retrieve.side_effect = [{"retrievalResults": []}, {"retrievalResults": [{"metadata": {"course_id": expected}}]}]
        with tempfile.TemporaryDirectory() as temp, patch.object(lab.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            lab.retrieval_smoke(runtime, "KB", Path(temp))
        self.assertEqual(runtime.retrieve.call_count, 2)
        runtime.retrieve_and_generate.assert_not_called()

    def test_unchanged_upload_reuses_verified_version(self):
        s3 = Mock()
        import hashlib
        body = b"catalog"
        s3.head_object.return_value = {"VersionId": "v1", "Metadata": {"sha256": hashlib.sha256(body).hexdigest()}}
        s3.get_object.return_value = {"Body": io.BytesIO(body)}
        self.assertEqual(lab.upload_if_changed(s3, "bucket", "key", body), "v1")
        s3.put_object.assert_not_called()


@patch.object(lab, 'build_application', return_value=('lambda-artifacts/application/test.zip', b'zip'))
class SetupFlowTests(unittest.TestCase):
    def session(self):
        session = Mock()
        session.get_partition_for_region.return_value = "aws"
        clients = {name: Mock() for name in ["sts", "cloudformation", "s3", "bedrock", "bedrock-agent", "bedrock-agent-runtime"]}
        session.client.side_effect = clients.__getitem__
        clients["sts"].get_caller_identity.return_value = {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/example"}
        clients["bedrock"].get_foundation_model.return_value = {"modelDetails": {"modelLifecycle": {"status": "ACTIVE"}}}
        clients["s3"].get_bucket_location.return_value = {"LocationConstraint": "us-east-2"}
        clients["s3"].get_bucket_versioning.return_value = {"Status": "Enabled"}
        clients["bedrock-agent"].get_paginator.return_value.paginate.return_value = [{"knowledgeBaseSummaries": []}]
        return session, clients

    def test_preview_does_not_deploy_upload_or_sync(self, build):
        session, clients = self.session()
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, "ROOT", Path(temp)), patch.object(lab, "chunk_catalog"), patch.object(Path, "read_text", return_value="catalog"), patch.object(lab.boto3, "Session", return_value=session), patch.object(lab, "stack_or_none", return_value=None), patch.object(lab, "deploy") as deploy, patch.object(lab, "sync") as sync, contextlib.redirect_stdout(io.StringIO()):
            lab.main(["setup", "--region", "us-east-2"])
        deploy.assert_not_called()
        sync.assert_not_called()
        clients["s3"].put_object.assert_not_called()

    def test_account_guard_stops_before_cloudformation(self, build):
        session, clients = self.session()
        with patch.object(lab.boto3, "Session", return_value=session), self.assertRaises(RuntimeError):
            lab.main(["setup", "--region", "us-east-2", "--expected-account", "000000000000", "--apply"])
        clients["cloudformation"].create_change_set.assert_not_called()

    def test_existing_kb_is_reused_and_model_parameters_preserved(self, build):
        session, clients = self.session()
        outputs = {"S3BucketName": "source", "IngestionIntermediateBucketName": "middle", "IngestionFunctionArn": "arn:aws:lambda:us-east-2:123456789012:function:example"}
        current = stack({"KnowledgeBaseId": "EXISTING01", "FoundationModelId": "existing-model", "SyncScheduleState": "ENABLED", "SyncScheduleTimezone": "UTC"}, outputs)
        def find(cfn, name):
            return current if name == "career-coach-lab" else None
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, "ROOT", Path(temp)), patch.object(Path, "read_text", return_value="catalog"), patch.object(lab, "chunk_catalog"), patch.object(lab.boto3, "Session", return_value=session), patch.object(lab, "stack_or_none", side_effect=find), patch.object(lab, "validate_kb", return_value="SOURCE0001"), patch.object(lab, "prepare", return_value={"artifact_s3_key": "lambda-artifacts/hash.zip"}), patch.object(Path, "read_bytes", return_value=b"zip"), patch.object(lab, "upload_if_changed", return_value="version"), patch.object(lab, "deploy", return_value=current) as deploy, patch.object(lab, "sync") as sync, patch.object(lab, "retrieval_smoke"), contextlib.redirect_stdout(io.StringIO()):
            lab.main(["setup", "--region", "us-east-2", "--apply"])
        self.assertNotIn("career-coach-lab-rag", [call.args[1] for call in deploy.call_args_list])
        self.assertEqual(deploy.call_args_list[-1].args[3]["SyncScheduleState"], "ENABLED")
        self.assertEqual(deploy.call_args_list[-1].args[3]["SyncScheduleTimezone"], "UTC")
        self.assertNotIn("FoundationModelId", deploy.call_args_list[0].args[3])
        sync.assert_called_once()
        clients["bedrock-agent"].create_knowledge_base.assert_not_called()

    def test_fresh_setup_binds_permission_before_creating_source_and_sync(self, build):
        session, clients = self.session()
        outputs = {"S3BucketName": "source", "IngestionIntermediateBucketName": "middle", "IngestionFunctionArn": "function"}
        order = []
        def deploy(cfn, name, template, parameters, evidence, **kwargs):
            order.append((name, parameters))
            return stack(outputs={"KnowledgeBaseId": "NEWKB00001"}) if name.endswith("-rag") else stack(outputs=outputs)
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, "ROOT", Path(temp)), patch.object(Path, "read_text", return_value="catalog"), patch.object(lab, "chunk_catalog"), patch.object(lab.boto3, "Session", return_value=session), patch.object(lab, "stack_or_none", return_value=None), patch.object(lab, "validate_kb", return_value="SOURCE0001"), patch.object(lab, "prepare", return_value={"artifact_s3_key": "lambda-artifacts/hash.zip"}), patch.object(Path, "read_bytes", return_value=b"zip"), patch.object(lab, "upload_if_changed", return_value="version"), patch.object(lab, "deploy", side_effect=deploy), patch.object(lab, "sync", side_effect=lambda *a: order.append(("sync", {}))), patch.object(lab, "retrieval_smoke"), contextlib.redirect_stdout(io.StringIO()):
            lab.main(["setup", "--region", "us-east-2", "--apply", "--enable-schedule"])
        binding = next(i for i, (name, params) in enumerate(order) if params.get("KnowledgeBaseId") == "NEWKB00001")
        source = next(i for i, (name, params) in enumerate(order) if params.get("EnableDataSource") == "true")
        syncing = next(i for i, (name, params) in enumerate(order) if name == "sync")
        self.assertLess(binding, source)
        self.assertLess(source, syncing)
        self.assertEqual(order[-1][0], "career-coach-lab")
        self.assertEqual(order[-1][1]["SyncScheduleState"], "ENABLED")
        self.assertEqual(order[-1][1]["KnowledgeBaseDataSourceId"], "SOURCE0001")

    def test_root_is_not_accepted(self, build):
        with self.assertRaises(RuntimeError):
            lab.deployment_principal(Mock(), {"Arn": "arn:aws:iam::123456789012:root"})

    def test_app_release_only_binds_application_artifact(self, build):
        session, clients = self.session()
        current = stack({'KnowledgeBaseId': 'EXISTING01'}, {'S3BucketName': 'source'})
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, 'ROOT', Path(temp)), patch.object(lab.boto3, 'Session', return_value=session), patch.object(lab, 'stack_or_none', return_value=current), patch.object(Path, 'read_text', return_value='template'), patch.object(lab, 'upload_if_changed', return_value='v1') as upload, patch.object(lab, 'deploy', return_value=current) as deploy, patch.object(lab, 'sync') as sync, patch.object(lab, 'validate_kb') as validate, contextlib.redirect_stdout(io.StringIO()):
            lab.main(['app-release', '--region', 'us-east-2', '--apply'])
        self.assertEqual(deploy.call_args.args[3], {'ApplicationCodeS3Key': 'lambda-artifacts/application/test.zip', 'ApplicationCodeS3ObjectVersion': 'v1'})
        self.assertEqual(deploy.call_args.kwargs['allowed_resources'], {'CareerCoachFunction'})
        upload.assert_called_once()
        sync.assert_not_called()
        validate.assert_not_called()

    def test_worker_release_does_not_touch_knowledge_or_application(self, build):
        session, clients = self.session()
        current = stack({'KnowledgeBaseId': 'EXISTING01'}, {'S3BucketName': 'source'})
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, 'ROOT', Path(temp)), \
                patch.object(lab.boto3, 'Session', return_value=session), \
                patch.object(lab, 'stack_or_none', return_value=current), \
                patch.object(Path, 'read_text', return_value='template'), \
                patch.object(lab, 'upload_if_changed', return_value='v2'), \
                patch.object(lab, 'deploy', return_value=current) as deploy, \
                patch.object(lab, 'sync') as sync, patch.object(lab, 'validate_kb') as validate, \
                contextlib.redirect_stdout(io.StringIO()):
            lab.main(['worker-release', '--region', 'us-east-2', '--apply'])
        build.assert_called_once_with(artifact_kind='worker')
        self.assertEqual(set(deploy.call_args.args[3]), {'WorkerCodeS3Key', 'WorkerCodeS3ObjectVersion'})
        self.assertEqual(deploy.call_args.kwargs['allowed_resources'], {'GenerationWorkerFunction'})
        sync.assert_not_called()
        validate.assert_not_called()

    def test_app_release_preview_does_not_upload(self, build):
        session, clients = self.session()
        current = stack(outputs={'S3BucketName': 'source'})
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, 'ROOT', Path(temp)), patch.object(lab.boto3, 'Session', return_value=session), patch.object(lab, 'stack_or_none', return_value=current), patch.object(lab, 'deploy') as deploy, contextlib.redirect_stdout(io.StringIO()):
            lab.main(['app-release', '--region', 'us-east-2'])
        deploy.assert_not_called()
        clients['s3'].put_object.assert_not_called()


class InfrastructureTests(unittest.TestCase):
    def test_scheduler_calls_only_start_ingestion_and_has_no_fixed_idempotency_token(self):
        template, errors = decode(str(lab.ROOT / "CloudFormation.yaml"))
        self.assertFalse(errors)
        props = template["Resources"]["WeeklyKnowledgeBaseSync"]["Properties"]
        self.assertEqual(props["ScheduleExpression"], {"Ref": "SyncScheduleExpression"})
        self.assertEqual(template["Parameters"]["SyncScheduleExpression"]["Default"], "cron(0 3 ? * SUN *)")
        self.assertEqual(template["Resources"]["WeeklyKnowledgeBaseSync"]["Condition"], "HasSyncBinding")
        target = props["Target"]
        self.assertTrue(target["Arn"]["Fn::Sub"].endswith(":bedrockagent:startIngestionJob"))
        self.assertNotIn("clientToken", target["Input"]["Fn::Sub"])
        payload = json.loads(target["Input"]["Fn::Sub"].replace("${KnowledgeBaseId}", "ABCDEFGHIJ").replace("${KnowledgeBaseDataSourceId}", "1234567890"))
        shape = get_session().get_service_model("bedrock-agent").operation_model("StartIngestionJob").input_shape
        # Scheduler universal targets require PascalCase, unlike boto3's Bedrock request.
        # Live CreateSchedule validation rejects the lower-camel-case payload.
        self.assertEqual(set(payload), {"KnowledgeBaseId", "DataSourceId"})
        validate_parameters({"knowledgeBaseId": payload["KnowledgeBaseId"], "dataSourceId": payload["DataSourceId"]}, shape)
        role = template["Resources"]["WeeklySyncExecutionRole"]["Properties"]
        statements = role["Policies"][0]["PolicyDocument"]["Statement"]
        self.assertEqual({s["Action"] for s in statements}, {"bedrock:StartIngestionJob", "sqs:SendMessage"})
        self.assertIn("SyncGroup", json.dumps(role["AssumeRolePolicyDocument"]))
        self.assertEqual(template["Parameters"]["SyncScheduleState"]["Default"], "DISABLED")

    def test_new_source_is_gated_until_kb_binding_and_has_exact_ingestion_contract(self):
        template = json.loads((lab.ROOT / "infrastructure/knowledge-base.json").read_text())
        source = template["Resources"]["CoursesDataSource"]
        self.assertEqual(source["Condition"], "CreateDataSource")
        self.assertEqual(template["Parameters"]["EnableDataSource"]["Default"], "false")
        config = source["Properties"]["VectorIngestionConfiguration"]
        self.assertEqual(config["ChunkingConfiguration"]["ChunkingStrategy"], "NONE")
        self.assertNotIn("ParsingConfiguration", config)
        self.assertIn("IntermediateBucket", json.dumps(config))
        self.assertEqual(config["CustomTransformationConfiguration"]["Transformations"][0]["StepToApply"], "POST_CHUNKING")


if __name__ == "__main__":
    unittest.main()
