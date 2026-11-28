import importlib
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.agent, self.table = Mock(), Mock()
        boto = Mock()
        boto.client.return_value = self.agent
        boto.resource.return_value.Table.return_value = self.table
        self.env = patch.dict(os.environ, {'DYNAMODB_TABLE': 'plans', 'KNOWLEDGE_BASE_ID': 'kb', 'MODEL_ARN': 'model'})
        self.env.start()
        sys.modules.pop('career_coach.legacy', None)
        with patch.dict(sys.modules, {'boto3': boto}):
            self.legacy = importlib.import_module('career_coach.legacy')

    def tearDown(self):
        self.env.stop()
        sys.modules.pop('career_coach.legacy', None)

    def test_success_preserves_prompt_budgets_and_save(self):
        self.agent.retrieve_and_generate.return_value = {'output': {'text': 'plan'}, 'citations': []}
        result = self.legacy.lambda_handler({'body': json.dumps({'current_role': 'Dev', 'goal': 'RAG', 'user_id': 'u'})}, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(json.loads(result['body'])['career_plan'], 'plan')
        call = self.agent.retrieve_and_generate.call_args.kwargs
        self.assertIn('Current Role: Dev\nCareer Goal: RAG', call['input']['text'])
        config = call['retrieveAndGenerateConfiguration']['knowledgeBaseConfiguration']
        self.assertEqual(config['generationConfiguration']['inferenceConfig']['textInferenceConfig']['maxTokens'], 800)
        self.assertEqual(config['retrievalConfiguration']['vectorSearchConfiguration']['numberOfResults'], 5)
        self.assertEqual(self.table.put_item.call_args.kwargs['Item']['user_id'], 'u')

    def test_missing_input_provider_and_save_errors(self):
        self.assertEqual(self.legacy.lambda_handler({'body': '{}'}, None)['statusCode'], 400)
        event = {'body': '{"current_role":"Dev","goal":"RAG"}'}
        self.agent.retrieve_and_generate.side_effect = RuntimeError('provider failure')
        self.assertEqual(self.legacy.lambda_handler(event, None)['statusCode'], 500)
        self.agent.retrieve_and_generate.side_effect = None
        self.agent.retrieve_and_generate.return_value = {'output': {'text': 'plan'}}
        self.table.put_item.side_effect = RuntimeError('save failure')
        self.assertEqual(self.legacy.lambda_handler(event, None)['statusCode'], 500)
