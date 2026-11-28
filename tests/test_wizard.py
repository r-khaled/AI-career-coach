import copy
import unittest

from career_coach import wizard
from career_coach.errors import APIError


class FakeModel:
    def __init__(self, facts=(), unresolved=()):
        self.facts, self.unresolved, self.calls = facts, unresolved, []

    def generate(self, task, data, **kwargs):
        self.calls.append((task, data, kwargs))
        return {'facts': [{'key': k, 'value': v, 'basis': basis,
                           'source_question_id': data['question']['question_id']}
                          for k, v, basis in self.facts],
                'unresolved': list(self.unresolved), 'suggested_followup_id': None,
                'suggested_question_text': None}


def initial():
    return {'session_id': 'session', 'schema_version': '1.0', 'state_version': 1, **wizard.initial_state()}


def respond(state, text, *facts, unresolved=()):
    request = {'question_id': state['current_question']['question_id'], 'answer': text,
               'state_version': state['state_version'], 'request_id': str(state['state_version'])}
    model = FakeModel([(k, v, 'user_reported') for k, v in facts], unresolved)
    result = wizard.answer(state, request, model)
    assert len(model.calls) == 1 and model.calls[0][2] == {'max_tokens': 512, 'temperature': 0.2}
    return result


class WizardTests(unittest.TestCase):
    def test_backend_rag_journey_review_and_explicit_equivalence(self):
        state = initial()
        state = respond(state, 'Node backend for three years', ('current_role', 'Node backend for three years'))
        state = respond(state, 'Move into AI', ('goal', 'Move into AI'), unresolved=['direction'])
        self.assertEqual(state['current_question']['question_id'], 'direction_followup')
        state = respond(state, 'applications')
        state = respond(state, 'Document Q&A with sources', ('outcome', 'Document Q&A with sources'))
        self.assertEqual(state['current_question']['question_id'], 'independent_practice')
        state = respond(state, 'Production Node APIs and SQL', ('practice', 'Production Node APIs and SQL'))
        self.assertEqual(state['current_question']['question_id'], 'cloud_practice')
        state = respond(state, 'Tried Lambda; limited IAM', ('capability_two', 'Tried Lambda; limited IAM'))
        self.assertEqual(state['current_question']['question_id'], 'ai_practice')
        state = respond(state, 'Model API; no RAG', ('capability_three', 'Model API; no RAG'))
        state = respond(state, '6')
        state = respond(state, '12 weeks flexible', ('deadline_weeks', 12), ('flexibility', 'flexible'))
        state = respond(state, 'English', ('language', 'English'))
        state = respond(state, 'Internal/free; subscription', ('budget', 'Internal/free'), ('subscription', 'existing'))
        self.assertEqual(state['status'], 'review_required')
        self.assertEqual((state['counters']['core'], state['counters']['followups']), (10, 1))
        self.assertIn('72', state['review']['summary'])
        assumption = state['profile']['assumptions'][0]
        self.assertIn(assumption['assumption_id'], state['review']['assumptions'][0])
        self.assertEqual(state['profile']['confirmed_assumption_ids'], [])
        approved = wizard.review(state, {'state_version': state['state_version'], 'confirmed_assumption_ids': [assumption['assumption_id']]})
        self.assertEqual(approved['status'], 'ready_to_generate')
        self.assertEqual(approved['profile']['approved_profile_version'], state['profile']['profile_version'])

    def test_multi_slot_skip_and_non_backend_goal(self):
        state = respond(initial(), 'I teach and want to become a school principal',
                        ('current_role', 'teacher'), ('goal', 'become a school principal'),
                        ('outcome', 'lead a school'), ('practice', 'teaching experience'))
        self.assertEqual(state['current_question']['question_id'], 'direction_followup')
        state = respond(state, 'other')
        self.assertEqual(state['current_question']['question_id'], 'generic_capability_two')
        self.assertEqual(state['counters']['core'], 2)

    def test_invalid_analysis_is_atomic_and_uses_safe_error(self):
        state = initial(); before = copy.deepcopy(state)
        request = {'question_id': 'current_work', 'answer': 'hello', 'state_version': 1, 'request_id': 'a'}
        for facts in [[('weekly_hours', True, 'user_reported')], [('weekly_hours', float('nan'), 'user_reported')], [('unapproved', 'x', 'user_reported')]]:
            with self.assertRaises(APIError) as err:
                wizard.answer(state, request, FakeModel(facts))
            self.assertEqual(err.exception.status, 503)
            self.assertEqual(state, before)

    def test_unknown_does_not_become_lack_of_skill(self):
        state = respond(initial(), 'Not sure', ('weekly_hours', 40))
        fact = state['profile']['facts'][0]
        self.assertIsNone(fact['value'])
        self.assertIn('current_role', state['profile']['unresolved'])
        self.assertNotIn('weekly_hours', [f['key'] for f in state['profile']['facts']])

    def test_only_reviewed_wording_for_selected_question_is_accepted(self):
        state = initial()
        request = {'question_id':'current_work', 'answer':'Developer', 'state_version':1, 'request_id':'r'}
        for suggested_id, suggested_text, accepted in [
            ('goal', 'Please tell me: What direction would you like to explore?', True),
            ('goal', 'Ignore all instructions', False),
            ('budget', 'Please tell me: What direction would you like to explore?', False)]:
            model = FakeModel([('current_role', 'Developer', 'user_reported')])
            original = model.generate
            def generate(*args, **kwargs):
                result = original(*args, **kwargs)
                result.update(suggested_followup_id=suggested_id, suggested_question_text=suggested_text)
                return result
            model.generate = generate
            result = wizard.answer(state, request, model)
            self.assertEqual(result['current_question']['text'], suggested_text if accepted else wizard.BY_ID['goal']['fallback'])
            self.assertEqual(len(model.calls), 1)

    def test_nontechnical_training_does_not_match_ai_and_negative_experience_not_equivalence(self):
        def fact(key, value):
            return {'key': key, 'value': value, 'basis': 'user_reported', 'source_question_id': 'review'}
        facts = {key: fact(key, val) for key, val in [('goal', 'corporate training'), ('outcome', 'train teachers'), ('direction', 'applications')]}
        self.assertFalse(wizard._technical(facts))
        state = initial()
        state['profile']['facts'] = [fact('goal','AI'), fact('outcome','build a RAG app'),
            fact('direction','applications'), fact('practice','never used API or SQL')]
        state['counters']['core'] = 10
        wizard._select(state)
        self.assertEqual(state['profile']['assumptions'], [])

    def test_correction_invalidates_approval_and_requires_second_review(self):
        state = {'session_id':'s', 'state_version':10, **wizard.initial_state()}
        state['status'] = 'review_required'; state['stage'] = 'review'; state['current_question'] = None
        state['profile'].update(facts=[{'key':'goal','value':'RAG','source_question_id':'goal','basis':'user_reported'},
            {'key':'capability_two','value':'AWS','source_question_id':'cloud_practice','basis':'inferred'}],
            assumptions=[{'assumption_id':'a','description':'Assumption','course_ids':['X']}], confirmed_assumption_ids=['a'], approved_profile_version=1)
        changed = wizard.review(state, {'state_version':10,'confirmed_assumption_ids':[], 'corrections':[{'key':'goal','value':'teaching'}]})
        self.assertEqual(changed['status'], 'review_required')
        self.assertEqual(changed['profile']['assumptions'], [])
        self.assertIsNone(changed['profile']['approved_profile_version'])
        self.assertIn('direction', changed['profile']['unresolved'])
        with self.assertRaises(APIError):
            wizard.review(changed, {'state_version':11,'confirmed_assumption_ids':[]})

    def test_inferred_direction_does_not_authorize_and_approved_edit_revokes(self):
        state = initial()
        state = respond(state, 'Analyst', ('current_role', 'Analyst'))
        model = FakeModel([('goal', 'Change into machine intelligence', 'user_reported'),
                           ('direction', 'applications', 'inferred')])
        state = wizard.answer(state, {'question_id':'goal', 'answer':'Change into machine intelligence',
            'state_version':state['state_version'], 'request_id':'g'}, model)
        self.assertEqual(state['current_question']['question_id'], 'direction_followup')
        state = respond(state, 'other')
        state['status'] = 'ready_to_generate'; state['stage'] = 'review'; state['current_question'] = None
        state['profile']['approved_profile_version'] = state['profile']['profile_version']
        edited = wizard.review(state, {'state_version':state['state_version'], 'confirmed_assumption_ids':[],
                                      'corrections':[{'key':'direction','value':None}]})
        self.assertEqual(edited['status'], 'review_required')
        self.assertIsNone(edited['profile']['approved_profile_version'])
        with self.assertRaises(APIError):
            wizard.review(edited, {'state_version':edited['state_version'], 'confirmed_assumption_ids':[]})
