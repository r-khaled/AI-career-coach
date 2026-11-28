import copy
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from career_coach.retrieval import InternalRetriever, RetrievalConflict
from ingestion.course_chunker import chunk_catalog
from scripts.evaluate_retrieval import legacy_prompt, metrics

ROOT = Path(__file__).resolve().parents[1]


def profile(goal='Application security SEC-201', extra=()):
    return {'schema_version':'1.0','profile_version':1,'approved_profile_version':1,
            'facts':[{'key':k,'value':v,'source_question_id':'review','basis':'user_reported'} for k,v in [('goal',goal), *extra]],
            'assumptions':[],'confirmed_assumption_ids':[],'unresolved':[]}


def entries():
    chunks = chunk_catalog((ROOT / 'internal_courses.md').read_text(encoding='utf-8'))
    return {c['contentMetadata']['course_id']: {'content':{'text':c['contentBody']},
        'metadata':c['contentMetadata'], 'location':{'type':'S3','s3Location':{'uri':'s3://catalog/internal_courses.md'}},
        'score':0.9} for c in chunks if c['contentMetadata']['record_type'] == 'course'}


class FakeClient:
    def __init__(self, catalog, initial):
        self.catalog, self.initial, self.calls = catalog, initial, []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        flt = kwargs['retrievalConfiguration']['vectorSearchConfiguration']['filter']
        if 'andAll' in flt:
            cid = flt['andAll'][1]['equals']['value']
            return {'retrievalResults': [copy.deepcopy(self.catalog[cid])] if cid in self.catalog else []}
        return {'retrievalResults': copy.deepcopy(self.initial)}


class RetrievalTests(unittest.TestCase):
    def test_aws_float_metadata_matches_integer_duration_text(self):
        for record in self.catalog.values():
            record['metadata']['duration_hours'] = float(record['metadata']['duration_hours'])
        self.client.initial = [self.catalog['SEC-201']]
        self.assertEqual(self.retriever.retrieve(profile())['known_course_hours'], 68)

    def setUp(self):
        self.catalog = entries()
        self.client = FakeClient(self.catalog, [self.catalog['SEC-201']])
        self.retriever = InternalRetriever(self.client, 'kb', clock=lambda: datetime(2026,1,1,tzinfo=timezone.utc))

    def test_transitive_closure_and_trace(self):
        result = self.retriever.retrieve(profile())
        self.assertEqual({r['course_id'] for r in result['resources']}, {'SEC-201','SEC-101','BKE-101','SDE-101'})
        self.assertEqual(result['known_course_hours'], 68)
        self.assertTrue(result['complete'])
        config = self.client.calls[0]['retrievalConfiguration']['vectorSearchConfiguration']
        self.assertEqual(config, {'numberOfResults':15,'overrideSearchType':'SEMANTIC','filter':{'equals':{'key':'record_type','value':'course'}}})
        self.assertEqual(result['records'][0]['rank'], 1)
        self.assertEqual(result['records'][0]['score'], 0.9)
        self.assertIn('s3Location', result['records'][0]['location'])
        self.assertEqual(result['prerequisites']['BKE-101'], ['SDE-101'])

    def test_explicit_constraint_does_not_relax_to_include_prerequisite(self):
        track = self.catalog['SEC-201']['metadata']['track']
        result = self.retriever.retrieve(profile(extra=[('allowed_track', track)]))
        self.assertFalse(result['complete'])
        self.assertTrue(any('constraint blocks BKE-101' in x for x in result['gaps']))
        self.assertEqual(next(r for r in result['resources'] if r['course_id']=='SEC-201')['prerequisite_status'], 'unresolved')

    def test_missing_exact_id_and_depth_budget_are_visible(self):
        result = InternalRetriever(self.client, 'kb', max_depth=1).retrieve(profile('SEC-201 and MISSING-999'))
        self.assertFalse(result['complete'])
        self.assertTrue(any('MISSING-999' in gap for gap in result['gaps']))
        self.assertTrue(any('depth limit' in gap for gap in result['gaps']))
        self.assertNotIn('MISSING-999', [r['course_id'] for r in result['resources']])

    def test_conflicting_versions_or_records_fail_closed(self):
        other = copy.deepcopy(self.catalog['SEC-201'])
        other['metadata']['catalog_version'] = '999'
        self.client.initial.append(other)
        with self.assertRaises(RetrievalConflict):
            self.retriever.retrieve(profile())
        other['metadata']['catalog_version'] = self.catalog['SEC-201']['metadata']['catalog_version']
        other['content']['text'] = 'different'
        with self.assertRaises(RetrievalConflict):
            self.retriever.retrieve(profile())

    def test_unapproved_equivalence_never_shortcuts(self):
        p = profile()
        p['assumptions'] = [{'assumption_id':'a','description':'experience','course_ids':['BKE-101','SDE-101']}]
        full = self.retriever.retrieve(p)
        self.assertEqual(full['known_course_hours'], 68)
        p['confirmed_assumption_ids'] = ['a']
        reduced = self.retriever.retrieve(p)
        self.assertEqual({r['course_id'] for r in reduced['resources']}, {'SEC-201','SEC-101'})
        self.assertEqual(next(r for r in reduced['resources'] if r['course_id']=='SEC-201')['prerequisite_status'], 'user_confirmed_equivalence')
        p['approved_profile_version'] = None
        with self.assertRaises(ValueError):
            self.retriever.retrieve(p)

    def test_cycles_and_request_limit_are_reported(self):
        self.catalog['SEC-101']['metadata']['prerequisites'] = ['SEC-201']
        self.catalog['SEC-101']['metadata']['has_prerequisites'] = True
        self.catalog['SEC-101']['content']['text'] = self.catalog['SEC-101']['content']['text'].replace('**Prerequisites:** None; suitable as an entry point.', '**Prerequisites:** SEC-201')
        result = self.retriever.retrieve(profile())
        self.assertTrue(any('cycle' in gap for gap in result['gaps']))
        limited = InternalRetriever(self.client, 'kb', max_requests=1).retrieve(profile())
        self.assertTrue(any('budget' in gap for gap in limited['gaps']))

    def test_bad_prerequisite_metadata_is_not_claimed_as_evidence(self):
        self.client.initial[0]['metadata']['prerequisites'] = ['BKE-101']
        result = self.retriever.retrieve(profile())
        self.assertFalse(result['complete'])
        self.assertNotIn('prerequisites', result['evidence'][0]['supported_fields'])
        self.assertEqual(result['resources'][0]['prerequisite_status'], 'unresolved')

    def test_mismatched_source_heading_is_not_accepted(self):
        self.client.initial[0]['content']['text'] = self.client.initial[0]['content']['text'].replace('### Course ID: SEC-201', '### Course ID: SEC-999')
        result = self.retriever.retrieve(profile())
        self.assertFalse(result['complete'])
        self.assertTrue(any('disagree' in gap for gap in result['gaps']))

    def test_result_limit_and_unknown_duration_are_visible(self):
        self.client.initial = [copy.deepcopy(self.catalog['SEC-201']) for _ in range(16)]
        result = self.retriever.retrieve(profile())
        self.assertTrue(any('result limit' in gap for gap in result['gaps']))
        self.assertEqual(sum(r['query'].startswith('Career goal:') for r in result['records']), 15)
        self.client.initial = [copy.deepcopy(self.catalog['SEC-201'])]
        self.client.initial[0]['metadata'].pop('duration_hours')
        result = self.retriever.retrieve(profile())
        self.assertIsNone(next(r for r in result['resources'] if r['course_id']=='SEC-201')['duration_hours'])
        self.assertTrue(any('Unknown duration' in gap for gap in result['gaps']))


class EvaluationHarnessTests(unittest.TestCase):
    def test_equal_k_duplicate_ranks_and_empty_labels(self):
        cases = [{'id':'one', 'language':'en','goal':'goal','current_role':'role',
                  'relevant':['A','B'], 'legacy':['A','A','B'], 'semantic':['B','A']},
                 {'id':'none', 'language':'ar','goal':'other','current_role':'role',
                  'relevant':[], 'legacy':[], 'semantic':[]}]
        report = metrics(cases, 2)
        self.assertEqual(report['aggregate']['legacy']['recall_at_k'], 0.5)
        self.assertEqual(report['aggregate']['semantic']['recall_at_k'], 1.0)
        self.assertEqual(report['aggregate']['legacy']['mrr_at_k'], 1.0)
        self.assertIsNone(report['cases'][1]['legacy']['recall'])
        with self.assertRaises(ValueError):
            metrics(cases, 10)
        self.assertEqual(report['legacy_settings']['numberOfResults'], 5)
        self.assertIsNone(report['legacy_settings']['filter'])
        self.assertIsNone(report['legacy_settings']['overrideSearchType'])

    def test_baseline_prompt_matches_actual_legacy_handler(self):
        agent = Mock()
        agent.retrieve_and_generate.return_value = {'output': {'text':'plan'}}
        boto = Mock()
        boto.client.return_value = agent
        sys.modules.pop('career_coach.legacy', None)
        with patch.dict(sys.modules, {'boto3':boto}), patch.dict(os.environ, {'DYNAMODB_TABLE':'table','KNOWLEDGE_BASE_ID':'kb','MODEL_ARN':'model'}):
            legacy = importlib.import_module('career_coach.legacy')
            legacy.lambda_handler({'body':json.dumps({'current_role':'role','goal':'goal'})}, None)
        sys.modules.pop('career_coach.legacy', None)
        call = agent.retrieve_and_generate.call_args.kwargs
        self.assertEqual(call['input']['text'], legacy_prompt('role', 'goal'))
        config = call['retrieveAndGenerateConfiguration']['knowledgeBaseConfiguration']
        self.assertEqual(config['retrievalConfiguration'], {'vectorSearchConfiguration':{'numberOfResults':5}})
        self.assertEqual(config['generationConfiguration']['inferenceConfig']['textInferenceConfig']['maxTokens'], 800)
