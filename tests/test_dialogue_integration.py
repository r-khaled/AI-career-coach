"""Offline API journey against the real wizard and session persistence."""
import json
import unittest

from career_coach import handler, wizard
from career_coach.contracts import validate
from career_coach.sessions import SessionService
from career_coach.store import MemoryStore


def event(method, path, body=None, token=''):
    return {'rawPath': path, 'requestContext': {'http': {'method': method}, 'requestId': 'http-test'},
            'headers': {'x-session-token': token}, 'body': json.dumps(body or {})}


class FakeModel:
    def __init__(self):
        self.calls = 0
        self.result = None

    def generate(self, task, data, *, max_tokens, temperature=0.2):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def analysis(question_id, key, value):
    return {'facts': [{'key': key, 'value': value, 'source_question_id': question_id,
                       'basis': 'user_reported'}], 'unresolved': [],
            'suggested_followup_id': None, 'suggested_question_text': None}


class DialogueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.sessions = SessionService(self.store)
        self.model = FakeModel()
        self.app = handler.Application(self.sessions, wizard=wizard, model=self.model)
        response = self.app.handle(event('POST', '/v2/sessions'))
        self.assertEqual(response['statusCode'], 201)
        self.token = response['headers']['X-Session-Token']
        self.data = json.loads(response['body'])
        self.sid = self.data['session_id']
        self.path = '/v2/sessions/' + self.sid
        self.check_envelope(self.data)

    def check_envelope(self, data):
        validate('dialogue-response', data['state'])
        validate('profile', data['profile'])
        self.assertNotIn('proof_hash', json.dumps(data))
        self.assertNotIn(self.token, json.dumps(data))

    def send(self, action, body):
        return self.app.handle(event('POST', self.path + '/' + action, body, self.token))

    def answer_body(self, req='r1'):
        state = self.data['state']
        return {'question_id': state['next_question']['question_id'], 'answer': 'An answer',
                'state_version': state['state_version'], 'request_id': req}

    def test_create_resume_answer_replay_and_request_conflict(self):
        self.assertIsNotNone(self.data['state']['next_question'])
        resumed = self.app.handle(event('GET', self.path, token=self.token))
        self.assertEqual(json.loads(resumed['body']), self.data)
        body = self.answer_body()
        self.model.result = analysis(body['question_id'], 'current_role', 'Backend developer')
        first = self.send('answers', body)
        self.assertEqual(first['statusCode'], 200, first['body'])
        self.assertEqual(self.model.calls, 1)
        updated = json.loads(first['body']); self.check_envelope(updated)
        self.assertGreater(updated['state']['state_version'], self.data['state']['state_version'])
        self.assertEqual(self.send('answers', body), first)
        self.assertEqual(self.model.calls, 1)
        body['answer'] = 'A different answer'
        self.assertEqual(self.send('answers', body)['statusCode'], 409)
        self.assertEqual(self.model.calls, 1)

    def test_processing_duplicate_does_not_call_model(self):
        body = self.answer_body()
        claim = self.sessions.claim(self.sid, self.token, body['request_id'],
                                    {'action': 'answers', **body}, body['state_version'])
        self.assertEqual(claim['status'], 'claimed')
        response = self.send('answers', body)
        self.assertEqual(response['statusCode'], 202)
        self.assertEqual(self.model.calls, 0)

    def test_invalid_analysis_does_not_advance_or_leave_session_locked(self):
        body = self.answer_body()
        self.model.result = {'facts': 'invalid'}
        self.assertEqual(self.send('answers', body)['statusCode'], 503)
        resumed = json.loads(self.app.handle(event('GET', self.path, token=self.token))['body'])
        self.assertEqual(resumed, self.data)
        self.assertEqual(self.send('answers', body)['statusCode'], 503)
        self.assertEqual(self.model.calls, 1)
        self.model.result = analysis(body['question_id'], 'current_role', 'Backend developer')
        body['request_id'] = 'fresh'
        self.assertEqual(self.send('answers', body)['statusCode'], 200)
        self.assertEqual(self.model.calls, 2)

    def test_wrong_question_and_stale_version_do_not_call_model(self):
        body = self.answer_body(); body['question_id'] = 'not-the-current-question'
        self.assertIn(self.send('answers', body)['statusCode'], (400, 409))
        self.assertEqual(self.model.calls, 0)
        body = self.answer_body('stale'); body['state_version'] += 1
        self.assertEqual(self.send('answers', body)['statusCode'], 409)
        self.assertEqual(self.model.calls, 0)

    def test_review_correction_requires_a_separate_confirmation(self):
        values = {'current_work': ('current_role', 'Backend developer'),
                  'goal': ('goal', 'Build RAG applications'),
                  'direction_followup': ('direction', 'applications'),
                  'outcome': ('outcome', 'Build document Q&A'),
                  'independent_practice': ('practice', 'Build APIs'),
                  'cloud_practice': ('capability_two', 'Tried Lambda'),
                  'generic_capability_two': ('capability_two', 'Tools'),
                  'ai_practice': ('capability_three', 'Model APIs'),
                  'generic_capability_three': ('capability_three', 'Research'),
                  'weekly_hours': ('weekly_hours', 6),
                  'deadline': ('deadline_weeks', 12),
                  'language': ('language', 'English'), 'budget': ('budget', 'Free')}
        for i in range(16):
            if self.data['state']['status'] == 'review_required':
                break
            body = self.answer_body('journey-' + str(i))
            key, value = values[body['question_id']]
            body['answer'] = str(value)
            self.model.result = analysis(body['question_id'], key, value)
            result = self.send('answers', body)
            self.assertEqual(result['statusCode'], 200, result['body'])
            self.data = json.loads(result['body']); self.check_envelope(self.data)
        self.assertEqual(self.data['state']['status'], 'review_required')
        review = {'state_version': self.data['state']['state_version'], 'confirmed_assumption_ids': [],
                  'corrections': [{'key': 'weekly_hours', 'value': 4}]}
        result = self.send('review', review)
        self.assertEqual(result['statusCode'], 200, result['body'])
        self.data = json.loads(result['body']); self.check_envelope(self.data)
        self.assertIsNone(self.data['profile']['approved_profile_version'])
        self.assertEqual(self.data['state']['status'], 'review_required')
        result = self.send('review', {'state_version': self.data['state']['state_version'],
                                      'confirmed_assumption_ids': []})
        self.assertEqual(result['statusCode'], 200, result['body'])
        approved = json.loads(result['body']); self.check_envelope(approved)
        self.assertEqual(approved['profile']['approved_profile_version'], approved['profile']['profile_version'])
        self.assertEqual(approved['state']['status'], 'ready_to_generate')


if __name__ == '__main__':
    unittest.main()
