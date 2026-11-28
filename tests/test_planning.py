import copy
import json
import unittest

from career_coach.models import ModelError
from career_coach.planning import PlanningError, PlanningPipeline


def profile(hours=6, weeks=12):
    facts = [{'key':k, 'value':v, 'basis':'user_reported', 'source_question_id':'review'}
             for k,v in [('goal','Learn security'), ('weekly_hours',hours), ('deadline_weeks',weeks), ('language','English')]]
    return {'schema_version':'1.0','profile_version':1,'facts':facts,'assumptions':[],
            'confirmed_assumption_ids':[],'approved_profile_version':1,'unresolved':[]}


def source():
    evidence = {'evidence_id':'internal:SEC-101', 'source':'internal_catalog', 'uri':'s3://catalog/courses.md',
                'retrieved_at':'2026-01-01T00:00:00Z','catalog_version':'2.0','parsed_source_sha256':'a'*64,
                'course_id':'SEC-101','supported_fields':['title','duration_hours','prerequisites']}
    resource = {'resource_id':'internal:SEC-101','kind':'internal','course_id':'SEC-101','title':'Security basics',
                'url':None,'duration_hours':16,'prerequisite_status':'none','reason':'Foundation','evidence_ids':[evidence['evidence_id']]}
    return {'resources':[resource], 'evidence':[evidence], 'records':[], 'contexts':[],
            'prerequisites':{'SEC-101':[]},'gaps':[], 'known_course_hours':16, 'complete':True, 'experiment':{}}


def outline():
    return {'capabilities':[{'skill_id':'security_basics','purpose':'Security foundations',
        'outcomes':['Understand authentication'], 'practice':'Review an access policy',
        'completion_criteria':['Explain an access policy']}], 'gaps':['authentication'], 'external_topic_ids':['backend_apis']}


def candidate(data):
    resources = copy.deepcopy(data['internal']['resources'])
    evidence = copy.deepcopy(data['internal']['evidence'])
    return {'schema_version':'1.0','plan_id':data['plan_id'],'revision':data['revision'],
        'profile_version':data['profile']['profile_version'],'goal':'Learn security','starting_point':'Starting point',
        'assumptions':[],'phases':[{'phase_id':'p1','title':'Foundations','depends_on':[],
        'skills':['security_basics'],'outcomes':['Understand authentication'],
        'resource_ids':[r['resource_id'] for r in resources],
        'practice':{'description':'Review access policy','estimated_hours':4},
        'completion_criteria':['Explain an access policy']}], 'resources':resources, 'evidence':evidence,
        'time_budget':{'weekly_hours':None,'target_weeks':None,'known_course_hours':0,
            'estimated_practice_hours':0,'unestimated_resource_ids':[],'fit_status':'unknown'}, 'coverage_gaps':[]}


class FakeModel:
    def __init__(self, *, bad_first=None, bad_outline=False, mutate=False):
        self.calls, self.usage, self.bad_first, self.bad_outline, self.mutate = [], [], bad_first, bad_outline, mutate

    def generate(self, task, data, **kwargs):
        self.calls.append((task, copy.deepcopy(data), kwargs))
        self.usage.append({'task':task,'usage':{'outputTokens':1}})
        if task == 'outline':
            if self.mutate:
                data['profile']['facts'][0]['value'] = 'tampered'
            return {'capabilities':[]} if self.bad_outline else outline()
        if task == 'career-plan' and self.bad_first == 'json':
            try:
                json.loads('{')
            except json.JSONDecodeError as exc:
                raise ModelError('invalid') from exc
        if task == 'career-plan' and self.bad_first == 'provider':
            raise ModelError('provider unavailable') from RuntimeError('secret')
        result = candidate(data)
        if task == 'career-plan' and self.bad_first == 'identity':
            result['plan_id'] = 'fabricated'
        return result


class FakeInternal:
    def __init__(self, bundle=None):
        self.bundle, self.calls = source() if bundle is None else bundle, []

    def retrieve(self, profile, gaps=None):
        self.calls.append((copy.deepcopy(profile), copy.deepcopy(gaps)))
        return copy.deepcopy(self.bundle)


class FakeExternal:
    def __init__(self):
        self.calls = []

    def search(self, topics, language):
        self.calls.append((topics,language))
        return {'resources':[],'evidence':[],'records':[],'field_provenance':{},'gaps':[], 'budget':{}}


class PlanningTests(unittest.TestCase):
    def test_compact_draft_uses_authoritative_source_entities(self):
        from career_coach.planning import _materialize, _close_selected_dependencies
        bundle = source()
        p = profile()
        draft = candidate({'profile': p, 'plan_id': 'p', 'revision': 1, 'internal': bundle})
        draft.pop('evidence')
        for key in ('plan_id','revision','profile_version','goal'): draft.pop(key)
        draft['resources'] = [{'resource_id': 'internal:SEC-101', 'reason': 'Relevant foundation'}]
        result = _materialize(draft, bundle, {'resources': [], 'evidence': []}, profile=p, plan_id='p', revision=1)
        self.assertEqual(result['evidence'], bundle['evidence'])
        self.assertEqual(result['resources'][0]['duration_hours'], 16)
        base = copy.deepcopy(bundle['resources'][0])
        base.update(resource_id='internal:SDE-101', course_id='SDE-101', evidence_ids=['internal:SDE-101'])
        proof = copy.deepcopy(bundle['evidence'][0])
        proof.update(evidence_id='internal:SDE-101', course_id='SDE-101')
        bundle['resources'].append(base); bundle['evidence'].append(proof)
        bundle['prerequisites'].update({'SEC-101':['SDE-101'], 'SDE-101':[]})
        result['resources'].append(base)
        result['evidence'].append(proof)
        result['phases'][0]['resource_ids'].append('internal:SDE-101')
        closed = _close_selected_dependencies(result, p, bundle)
        self.assertEqual(closed['phases'][0]['resource_ids'], ['internal:SDE-101', 'internal:SEC-101'])
        draft['resources'][0]['resource_id'] = 'internal:INVENTED-999'
        with self.assertRaises(Exception):
            _materialize(draft, bundle, {'resources': [], 'evidence': []}, profile=p, plan_id='p', revision=1)

    def test_full_pipeline_and_immutable_snapshots(self):
        model, internal, external = FakeModel(mutate=True), FakeInternal(), FakeExternal()
        calls, original = [], profile()
        pipeline = PlanningPipeline(model, internal, lambda: external)
        result = pipeline.generate(original, plan_id='p', revision=1, stage_callback=calls.append)
        self.assertEqual(calls, ['outline','retrieval','external_search','generation','validation'])
        self.assertEqual(external.calls, [(['backend_apis'],'en')])
        self.assertEqual(result['plan']['goal'], 'Learn security')
        self.assertEqual(result['plan']['time_budget']['known_course_hours'], 16)
        self.assertEqual(result['plan']['time_budget']['fit_status'], 'estimated_fit')
        self.assertEqual(original, profile())
        self.assertEqual([c[2]['max_tokens'] for c in model.calls], [1024,2048])

    def test_partial_and_time_infeasible(self):
        empty = {'resources':[],'evidence':[],'records':[],'prerequisites':{},'gaps':['Sparse catalog']}
        partial = PlanningPipeline(FakeModel(), FakeInternal(empty), None).generate(profile(), plan_id='p', revision=1)
        self.assertIn('Sparse catalog', partial['plan']['coverage_gaps'])
        self.assertIn('External search is unavailable', partial['plan']['coverage_gaps'])
        full = PlanningPipeline(FakeModel(), FakeInternal(), lambda: FakeExternal()).generate(profile(1,1), plan_id='p', revision=1)
        self.assertEqual(full['plan']['time_budget']['fit_status'], 'exceeds')

    def test_one_repair_no_repeat_retrieval_or_search(self):
        for failure in ('identity','json'):
            model, internal, external = FakeModel(bad_first=failure), FakeInternal(), FakeExternal()
            result = PlanningPipeline(model, internal, lambda: external).generate(profile(), plan_id='p', revision=2)
            self.assertEqual(result['plan']['revision'], 2)
            self.assertEqual([c[0] for c in model.calls], ['outline','career-plan','career-plan-repair'])
            self.assertEqual(model.calls[-1][2]['max_tokens'], 4096)
            self.assertEqual(len(internal.calls), 1)
            self.assertEqual(len(external.calls), 1)

    def test_provider_failure_is_not_repaired_and_invalid_outline_stops(self):
        model, internal = FakeModel(bad_first='provider'), FakeInternal()
        with self.assertRaises(PlanningError):
            PlanningPipeline(model, internal, None).generate(profile(), plan_id='p', revision=1)
        self.assertEqual([c[0] for c in model.calls], ['outline','career-plan'])
        model, internal = FakeModel(bad_outline=True), FakeInternal()
        with self.assertRaises(PlanningError):
            PlanningPipeline(model, internal, None).generate(profile(), plan_id='p', revision=1)
        self.assertFalse(internal.calls)

    def test_unapproved_profile_never_invokes_model(self):
        p = profile(); p['approved_profile_version'] = None
        model = FakeModel()
        with self.assertRaises(PlanningError):
            PlanningPipeline(model, FakeInternal(), None).generate(p, plan_id='p', revision=1)
        self.assertFalse(model.calls)

    def test_each_revision_uses_fresh_external_budget(self):
        providers = []
        def factory():
            provider = FakeExternal()
            providers.append(provider)
            return provider
        pipeline = PlanningPipeline(FakeModel(), FakeInternal(), factory)
        first = pipeline.generate(profile(), plan_id='p', revision=1)
        second = pipeline.generate(profile(), plan_id='p', revision=2, change_request='Add practice')
        self.assertEqual([p.calls for p in providers], [[(['backend_apis'],'en')], [(['backend_apis'],'en')]])
        self.assertEqual((first['plan']['revision'], second['plan']['revision']), (1, 2))
        self.assertEqual([len(first['trace']['model_usage']), len(second['trace']['model_usage'])], [2, 2])

    def test_model_cannot_send_arbitrary_external_topics(self):
        class TopicModel(FakeModel):
            def generate(self, task, data, **kwargs):
                if task == 'outline':
                    result = outline()
                    result['external_topic_ids'] = ['private answer to be sent']
                    return result
                return super().generate(task, data, **kwargs)
        internal, external = FakeInternal(), FakeExternal()
        with self.assertRaises(PlanningError):
            PlanningPipeline(TopicModel(), internal, lambda: external).generate(profile(), plan_id='p', revision=1)
        self.assertFalse(internal.calls)
        self.assertFalse(external.calls)
