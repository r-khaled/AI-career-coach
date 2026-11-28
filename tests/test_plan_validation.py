import copy
import json
from pathlib import Path
import unittest

from career_coach.plan_validation import PlanValidationError, validate_plan

ROOT = Path(__file__).resolve().parents[1] / 'career_coach' / 'fixtures'


def setup():
    plan = json.loads((ROOT / 'career-plan.json').read_text())
    profile = json.loads((ROOT / 'profile.json').read_text())
    profile.update(profile_version=12, approved_profile_version=12,
                   facts=[{'key':'goal', 'value':plan['goal'], 'source_question_id':'goal', 'basis':'user_reported'},
                          {'key':'weekly_hours', 'value':6, 'source_question_id':'hours', 'basis':'user_reported'},
                          {'key':'deadline_weeks', 'value':12, 'source_question_id':'deadline', 'basis':'user_reported'}])
    plan['assumptions'] = []
    internal = {'resources':copy.deepcopy(plan['resources']), 'evidence':copy.deepcopy(plan['evidence']),
                'records':[{'metadata':{'course_id':'AIML-001','track':'AI','level':'beginner'}}],
                'prerequisites':{'AIML-001':[]}, 'gaps':[]}
    external = {'resources':[], 'evidence':[], 'records':[], 'field_provenance':{}, 'gaps':[]}
    return plan, profile, internal, external


def check(p, profile, internal, external):
    return validate_plan(p, profile, internal, external, plan_id='example-plan', revision=1)


class PlanValidationTests(unittest.TestCase):
    def test_normalizes_hours_gaps_and_immutable_inputs(self):
        p, profile, internal, external = setup()
        p['time_budget'].update(known_course_hours=999, estimated_practice_hours=999, fit_status='exceeds')
        internal['gaps'] = ['Source incomplete']
        original = copy.deepcopy(p)
        result = check(p, profile, internal, external)
        self.assertEqual(p, original)
        self.assertEqual(result['time_budget']['known_course_hours'], 12)
        self.assertEqual(result['time_budget']['estimated_practice_hours'], 4)
        self.assertEqual(result['time_budget']['fit_status'], 'estimated_fit')
        self.assertIn('Source incomplete', result['coverage_gaps'])

    def test_rejects_fabricated_sources_and_bindings(self):
        for mutate in (lambda p, f, i: p['resources'][0].update(title='invented'),
                       lambda p, f, i: p['resources'][0].update(url='https://example.com'),
                       lambda p, f, i: p['evidence'][0].update(uri='s3://wrong/source'),
                       lambda p, f, i: p.update(plan_id='other'),
                       lambda p, f, i: f.update(approved_profile_version=None),
                       lambda p, f, i: p['time_budget'].update(weekly_hours=float('nan'))):
            p, f, i, e = setup(); mutate(p, f, i)
            with self.subTest(mutate=mutate), self.assertRaises(PlanValidationError): check(p, f, i, e)

    def test_prerequisite_order_and_shared_hours(self):
        p, f, i, e = setup()
        original = p['resources'][0]; proof = p['evidence'][0]
        for cid, hours in [('PRE-101', 20), ('PRE-102', 36)]:
            r = copy.deepcopy(original); r.update(resource_id='internal:'+cid, course_id=cid, title=cid, duration_hours=hours, evidence_ids=[cid])
            ev = copy.deepcopy(proof); ev.update(evidence_id=cid, course_id=cid)
            p['resources'].append(r); p['evidence'].append(ev)
            i['resources'].append(copy.deepcopy(r)); i['evidence'].append(copy.deepcopy(ev))
            i['prerequisites'][cid] = []
        i['prerequisites']['AIML-001'] = ['PRE-101', 'PRE-102']
        p['resources'][0]['prerequisite_status'] = i['resources'][0]['prerequisite_status'] = 'included'
        p['phases'][0]['resource_ids'] = ['internal:PRE-101', 'internal:PRE-102', 'internal:AIML-001']
        phase = copy.deepcopy(p['phases'][0]); phase.update(phase_id='p2', depends_on=['p1'], resource_ids=['internal:PRE-101'])
        p['phases'].append(phase)
        self.assertEqual(check(p,f,i,e)['time_budget']['known_course_hours'], 68)
        p['phases'][0]['resource_ids'].reverse()
        with self.assertRaises(PlanValidationError): check(p,f,i,e)

    def test_cycles_duplicates_missing_resources_and_unsupported_equivalence(self):
        for mutate in (lambda p,f,i: p['phases'][0].update(depends_on=['p1']),
                       lambda p,f,i: p['phases'][0].update(resource_ids=[]),
                       lambda p,f,i: p['resources'].append(copy.deepcopy(p['resources'][0])),
                       lambda p,f,i: p.update(assumptions=['invented']),
                       lambda p,f,i: i['prerequisites'].update({'AIML-001':['AIML-001']})):
            p,f,i,e = setup(); mutate(p,f,i)
            with self.subTest(mutate=mutate), self.assertRaises(PlanValidationError): check(p,f,i,e)

    def test_unknown_durations_unresolved_and_exceeds(self):
        p,f,i,e = setup()
        p['resources'][0]['duration_hours'] = i['resources'][0]['duration_hours'] = None
        p['resources'][0]['prerequisite_status'] = i['resources'][0]['prerequisite_status'] = 'unresolved'
        result = check(p,f,i,e)
        self.assertEqual(result['time_budget']['fit_status'], 'unknown')
        self.assertEqual(result['time_budget']['unestimated_resource_ids'], ['internal:AIML-001'])
        self.assertTrue(any('Prerequisites unresolved' in g for g in result['coverage_gaps']))
        f['facts'][1]['value'] = .1
        self.assertEqual(check(p,f,i,e)['time_budget']['fit_status'], 'exceeds')

    def test_explicit_track_and_approved_equivalence(self):
        p,f,i,e = setup()
        f['facts'].append({'key':'allowed_track','value':'Security','source_question_id':'review','basis':'user_reported'})
        with self.assertRaises(PlanValidationError): check(p,f,i,e)
        f['facts'][-1]['value'] = 'AI'
        i['prerequisites']['AIML-001'] = ['PRE-101']
        p['resources'][0]['prerequisite_status'] = i['resources'][0]['prerequisite_status'] = 'user_confirmed_equivalence'
        with self.assertRaises(PlanValidationError): check(p,f,i,e)
        f['assumptions'] = [{'assumption_id':'a','description':'equivalent','course_ids':['PRE-101']}]
        f['confirmed_assumption_ids'] = ['a']
        i['resources'][0]['prerequisite_status'] = 'included'
        p['assumptions'] = []
        result = check(p,f,i,e)
        self.assertEqual(result['assumptions'], ['equivalent'])
        self.assertEqual(result['resources'][0]['prerequisite_status'], 'user_confirmed_equivalence')

    def test_external_field_provenance_and_hard_constraints(self):
        p,f,i,e = setup()
        r = copy.deepcopy(p['resources'][0])
        r.update(resource_id='external:x', kind='external', course_id=None, title='Course',
                 url='https://example.com/course', duration_hours=2, prerequisite_status='unresolved', evidence_ids=['external-proof'])
        ev = copy.deepcopy(p['evidence'][0])
        ev.update(evidence_id='external-proof', source='course_page', uri=r['url'], catalog_version=None,
                  parsed_source_sha256=None, course_id=None, supported_fields=['title','url','duration_hours','price','language'])
        p['resources'] = [r]; p['evidence'] = [ev]; p['phases'][0]['resource_ids'] = ['external:x']
        e['resources'] = [copy.deepcopy(r)]; e['evidence'] = [copy.deepcopy(ev)]
        fields = {'title':r['title'], 'url':r['url'], 'duration_hours':2, 'price':{'amount':'0', 'currency':'USD'}, 'language':'en'}
        e['records'] = [{'evidence_id':'external-proof', 'field_values':fields}]
        e['field_provenance'] = {'external:x':{key:['external-proof'] for key in fields}}
        f['facts'].extend([{'key':'budget','value':'free only','basis':'user_reported','source_question_id':'review'},
                           {'key':'language','value':'English only','basis':'user_reported','source_question_id':'review'}])
        self.assertEqual(check(p,f,i,e)['time_budget']['fit_status'], 'unknown')
        e['records'][0]['field_values']['url'] = 'https://wrong.example'
        with self.assertRaises(PlanValidationError): check(p,f,i,e)
        e['records'][0]['field_values']['url'] = r['url']
        e['records'][0]['field_values']['price']['amount'] = '20'
        with self.assertRaises(PlanValidationError): check(p,f,i,e)


if __name__ == '__main__': unittest.main()
