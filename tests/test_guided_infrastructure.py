"""Offline declarations, not proof of deployed IAM/service behavior."""
import json
from pathlib import Path
import unittest

from cfnlint.decode import decode


class GuidedInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template, errors = decode(str(Path(__file__).resolve().parents[1] / 'CloudFormation.yaml'))
        if errors:
            raise AssertionError(errors)
        cls.resources = cls.template['Resources']

    def test_guided_activation_is_explicit_and_legacy_remains_available(self):
        self.assertEqual(self.template['Parameters']['GuidedEnabled']['Default'], 'false')
        for name in ('SessionCreateRoute', 'SessionProxyRoute'):
            self.assertEqual(self.resources[name]['Condition'], 'EnableGuided')
            self.assertEqual(self.resources[name]['Properties']['AuthorizationType'], 'AWS_IAM')
        self.assertNotIn('Condition', self.resources['ApiRoute'])
        self.assertEqual(self.resources['ApiRoute']['Properties']['RouteKey'], 'POST /generate-plan')

    def test_queue_visibility_worker_timeout_and_redrive_are_consistent(self):
        worker = self.resources['GenerationWorkerFunction']['Properties']
        queue = self.resources['GenerationQueue']['Properties']
        self.assertEqual(worker['Timeout'], 180)
        self.assertGreaterEqual(queue['VisibilityTimeout'], 6 * worker['Timeout'])
        self.assertEqual(queue['RedrivePolicy']['maxReceiveCount'], 5)
        self.assertEqual(queue['RedrivePolicy']['deadLetterTargetArn'], {'Fn::GetAtt': ['GenerationDeadLetterQueue', 'Arn']})
        mapping = self.resources['GenerationQueueMapping']['Properties']
        self.assertEqual(mapping['BatchSize'], 1)
        self.assertEqual(mapping['MaximumBatchingWindowInSeconds'], 0)
        self.assertEqual(mapping['FunctionResponseTypes'], ['ReportBatchItemFailures'])
        self.assertEqual(mapping['Enabled'], {'Fn::If': ['EnableGuided', True, False]})

    def test_worker_permissions_and_artifact_are_independent(self):
        role = json.dumps(self.resources['GenerationWorkerRole'])
        self.assertIn('dynamodb:ConditionCheckItem', role)
        self.assertIn('secretsmanager:GetSecretValue', role)
        self.assertIn('SerperSecretArn', role)
        self.assertNotIn('sqs:SendMessage', role)
        self.assertNotIn('bedrock:RetrieveAndGenerate', role)
        self.assertNotIn('StartIngestionJob', role)
        self.assertNotIn('secretsmanager', json.dumps(self.resources['LambdaExecutionRole']))
        code = self.resources['GenerationWorkerFunction']['Properties']['Code']
        self.assertEqual(code['S3Key'], {'Ref': 'WorkerCodeS3Key'})
        self.assertEqual(code['S3ObjectVersion'], {'Ref': 'WorkerCodeS3ObjectVersion'})
        invoke = self.resources['GenerationWorkerRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        target = next(s for s in invoke if s.get('Action') == 'bedrock:InvokeModel')
        self.assertEqual(target['Resource']['Fn::If'][1], {'Ref': 'PlannerModelId'})

    def test_outbox_stream_filters_jobs_and_uses_existing_application(self):
        self.assertEqual(self.resources['SessionsTable']['Properties']['StreamSpecification']['StreamViewType'], 'NEW_IMAGE')
        mapping = self.resources['DispatchOutboxMapping']['Properties']
        self.assertEqual(mapping['FunctionName'], {'Ref': 'CareerCoachFunction'})
        self.assertEqual(mapping['BatchSize'], 1)
        pattern = json.loads(mapping['FilterCriteria']['Filters'][0]['Pattern'])
        self.assertEqual(pattern['dynamodb']['NewImage']['sk']['S'], [{'prefix': 'JOB#'}])
        self.assertNotIn('REMOVE', pattern['eventName'])
        self.assertEqual(self.resources['SessionsTable']['Properties']['TimeToLiveSpecification']['AttributeName'], 'expires_at')
        self.assertNotIn('TimeToLiveSpecification', self.resources['CareerPlansTable']['Properties'])
