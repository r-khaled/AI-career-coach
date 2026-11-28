import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import app as app_module
from career_coach import handler, wizard
from career_coach.sessions import SessionService
from career_coach.store import MemoryStore
from career_coach.downloads import export_plan
from career_coach.contracts import validate


class Model:
    def __init__(self): self.calls = 0; self.value = None
    def generate(self, task, data, *, max_tokens, temperature=0.2):
        self.calls += 1
        return self.value


class BackendResponse:
    def __init__(self, response):
        self.status_code = response['statusCode']; self.headers = response['headers']; self.body = response['body']
    def json(self): return json.loads(self.body)


class GuidedProxyTests(unittest.TestCase):
    def setUp(self):
        self.model = Model()
        self.sessions = SessionService(MemoryStore())
        self.backend = handler.Application(self.sessions, wizard=wizard, model=self.model)
        self.calls = []
        def transport(method, url, body, proof):
            self.calls.append((method, url, body, proof))
            u = urlsplit(url)
            event = {'rawPath': u.path.removeprefix('/prod'), 'rawQueryString':u.query,
                     'requestContext': {'http': {'method':method}, 'requestId':'test'},
                     'headers': {'x-session-token':proof or ''}, 'body':body.decode() if body else None,
                     'queryStringParameters': {k:v[0] for k,v in parse_qs(u.query).items()}}
            return BackendResponse(self.backend.handle(event))
        app_module.app.config.update(TESTING=True, GUIDED_ENV='production', PUBLIC_ORIGIN='https://frontend.example',
                                     API_BASE_URL='https://api.example/prod', GUIDED_TRANSPORT=transport)
        self.client = app_module.app.test_client()
        self.origin = {'Origin':'https://frontend.example'}

    def create(self):
        result = self.client.post('/api/v2/sessions', json={}, headers=self.origin)
        self.assertEqual(result.status_code, 201, result.text)
        return result

    def test_create_cookie_resume_and_answer_replay(self):
        result = self.create(); cookie = result.headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie); self.assertIn('Secure', cookie); self.assertIn('SameSite=Lax', cookie)
        body = result.get_json(); validate('dialogue-response', body['state']); validate('profile', body['profile'])
        self.assertNotIn('X-Session-Token', result.headers); self.assertNotIn(self.calls[-1][3] or 'proof_hash', result.text)
        sid = body['session_id']; self.assertEqual(self.client.get('/api/v2/session').get_json(), body)
        q = body['state']['next_question']['question_id']
        self.model.value = {'facts':[{'key':'current_role','value':'Backend developer','source_question_id':q,'basis':'user_reported'}],
                            'unresolved':[],'suggested_followup_id':None,'suggested_question_text':None}
        answer = {'question_id':q,'answer':'Backend developer','state_version':body['state']['state_version'],'request_id':'test-answer'}
        first = self.client.post('/api/v2/sessions/'+sid+'/answers', json=answer, headers=self.origin)
        self.assertEqual(first.status_code, 200, first.text)
        again = self.client.post('/api/v2/sessions/'+sid+'/answers', json=answer, headers=self.origin)
        self.assertEqual(again.get_json(), first.get_json()); self.assertEqual(self.model.calls, 1)

    def test_origin_cookie_isolation_and_forged_header(self):
        self.assertEqual(self.client.post('/api/v2/sessions', json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/v2/sessions', json={}, headers={'Origin':'null'}).status_code, 403)
        result = self.create(); sid = result.get_json()['session_id']
        calls = len(self.calls)
        self.assertEqual(self.client.get('/api/v2/sessions/other', headers={'x-session-token':'forged'}).status_code, 403)
        self.assertEqual(len(self.calls), calls)
        result = self.create(); sid = result.get_json()['session_id']
        self.client.get('/api/v2/sessions/'+sid, headers={'x-session-token':'forged'})
        self.assertNotEqual(self.calls[-1][3], 'forged')

    def test_local_development_only_and_expiry_clears_cookie(self):
        app_module.app.config.update(GUIDED_ENV='development', PUBLIC_ORIGIN='http://localhost:5001', API_BASE_URL='http://localhost:9000')
        result = self.client.post('/api/v2/sessions', json={}, headers={'Origin':'http://localhost:5001'})
        self.assertEqual(result.status_code, 201)
        self.assertNotIn('Secure', result.headers['Set-Cookie'])
        sid = result.get_json()['session_id']
        pk = 'SESSION#' + sid
        self.sessions.store._items[(pk,'STATE')]['expires_at'] = 0
        result = self.client.get('/api/v2/session')
        self.assertEqual(result.status_code, 410); self.assertIn('Max-Age=0', result.headers['Set-Cookie'])
        app_module.app.config['GUIDED_ENV'] = 'production'
        self.assertEqual(self.client.post('/api/v2/sessions', json={}, headers={'Origin':'http://localhost:5001'}).status_code, 503)

    def test_sigv4_signs_exact_query_with_server_proof_and_no_redirects(self):
        import web_guided
        from botocore.credentials import Credentials
        class Session:
            region_name = 'us-east-1'
            def get_credentials(self): return Credentials('access', 'secret', 'session')
        with patch('web_guided.boto3.Session', return_value=Session()), patch('web_guided.requests.request') as request_call:
            web_guided.signed_call('GET', 'https://api.example/prod/v2/sessions/a/plans/b?revision=2', b'', 'proof-token')
        args, kwargs = request_call.call_args
        self.assertEqual(args, ('GET', 'https://api.example/prod/v2/sessions/a/plans/b?revision=2'))
        self.assertEqual(kwargs['headers']['x-session-token'], 'proof-token')
        self.assertIn('Authorization', kwargs['headers'])
        self.assertFalse(kwargs['allow_redirects']); self.assertEqual(kwargs['timeout'],35)

    def test_oversized_stream_without_content_length_and_safe_error_id(self):
        import io
        # Werkzeug reads input without Content-Length only when the WSGI server
        # indicates that it has safely terminated the input stream.
        response = self.client.open('/api/v2/sessions', method='POST',
            input_stream=io.BytesIO(b'{"x":"' + b'a' * 20000 + b'"}'),
            content_type='application/json', headers=self.origin,
            environ_overrides={'CONTENT_LENGTH':'', 'wsgi.input_terminated':True})
        self.assertEqual(response.status_code, 400)
        error = response.get_json()['error']
        self.assertEqual(set(error), {'code', 'message', 'request_id'})
        self.assertTrue(error['request_id'])
        self.assertEqual(self.calls, [])

    def test_revision_limits_match_backend(self):
        sid = self.create().get_json()['session_id']
        path = '/api/v2/sessions/' + sid + '/plans/example'
        count = len(self.calls)
        self.assertEqual(self.client.get(path+'?revision=1000000').status_code, 400)
        self.assertEqual(self.client.get(path+'/download?revision=1000000&format=json').status_code, 400)
        self.assertEqual(len(self.calls), count)

    def test_bad_backend_and_safe_error(self):
        def broken(*args): raise RuntimeError('SECRET')
        app_module.app.config['GUIDED_TRANSPORT'] = broken
        r = self.client.post('/api/v2/sessions', json={}, headers=self.origin)
        self.assertEqual(r.status_code, 503); self.assertNotIn('SECRET', r.text)

    def test_full_worker_journey_download_and_revision(self):
        from career_coach.jobs import JobService
        from career_coach.plans import MemoryPlanStore
        from career_coach.planning import PlanningPipeline
        from career_coach.worker import JobWorker
        from tests.test_planning import FakeModel as PlanModel, FakeInternal, FakeExternal
        class Queue:
            def __init__(self): self.messages = []
            def send(self, sid, jid): self.messages.append((sid,jid))
        queue = Queue()
        jobs = JobService(self.sessions, MemoryPlanStore(), queue)
        self.backend.jobs = jobs
        class JourneyPlanModel(PlanModel):
            def generate(self, task, data, **kwargs):
                result = super().generate(task, data, **kwargs)
                if task in ('career-plan', 'career-plan-repair'):
                    result['goal'] = next(f['value'] for f in data['profile']['facts'] if f['key'] == 'goal')
                return result
        pipeline = PlanningPipeline(JourneyPlanModel(), FakeInternal(), lambda: FakeExternal())
        worker = JobWorker(jobs, pipeline)
        state = self.create().get_json(); sid = state['session_id']
        values = {'current_work': ('current_role', 'Backend developer'), 'goal': ('goal', 'Build RAG applications'),
                  'direction_followup': ('direction', 'applications'), 'outcome': ('outcome', 'Build document Q&A'),
                  'independent_practice': ('practice', 'Build APIs'), 'cloud_practice': ('capability_two', 'Tried Lambda'),
                  'generic_capability_two': ('capability_two', 'Tools'), 'ai_practice': ('capability_three', 'Model APIs'),
                  'generic_capability_three': ('capability_three', 'Research'), 'weekly_hours': ('weekly_hours', 6),
                  'deadline': ('deadline_weeks', 12), 'language': ('language', 'English'), 'budget': ('budget', 'Free')}
        for i in range(16):
            if state['state']['status'] == 'review_required': break
            q = state['state']['next_question']['question_id']; key, value = values[q]
            self.model.value = {'facts':[{'key':key,'value':value,'source_question_id':q,'basis':'user_reported'}],
                                'unresolved':[],'suggested_followup_id':None,'suggested_question_text':None}
            body = {'question_id':q,'answer':str(value),'state_version':state['state']['state_version'],'request_id':'q'+str(i)}
            response = self.client.post('/api/v2/sessions/'+sid+'/answers',json=body,headers=self.origin)
            self.assertEqual(response.status_code, 200, response.text); state = response.get_json()
        self.assertEqual(state['state']['status'], 'review_required')
        self.assertEqual(self.client.get('/api/v2/session').get_json(), state)
        review = {'state_version':state['state']['state_version'],'confirmed_assumption_ids':[]}
        response = self.client.post('/api/v2/sessions/'+sid+'/review',json=review,headers=self.origin)
        self.assertEqual(response.status_code, 200, response.text); state = response.get_json()
        self.assertEqual(state['state']['status'], 'ready_to_generate')
        version = state['profile']['profile_version']
        response = self.client.post('/api/v2/sessions/'+sid+'/plans',json={'request_id':'plan-one','profile_version':version},headers=self.origin)
        self.assertEqual(response.status_code, 202, response.text); job = response.get_json(); validate('job',job)
        self.assertEqual(job['status'],'queued'); self.assertEqual(queue.messages[-1], (sid,job['job_id']))
        self.assertEqual(self.client.get('/api/v2/sessions/'+sid+'/jobs/'+job['job_id']).get_json()['status'],'queued')
        worker.process(sid,job['job_id'])
        job = self.client.get('/api/v2/sessions/'+sid+'/jobs/'+job['job_id']).get_json()
        self.assertEqual(job['status'],'completed'); pid = job['plan_id']
        path = '/api/v2/sessions/'+sid+'/plans/'+pid
        response = self.client.get(path+'?revision=1'); self.assertEqual(response.status_code,200,response.text)
        plan = response.get_json(); validate('career-plan',plan); self.assertEqual(plan['revision'],1)
        self.assertEqual(self.client.get(path+'/download?revision=1&format=json').get_json(),plan)
        markdown = self.client.get(path+'/download?revision=1&format=markdown')
        self.assertEqual(markdown.status_code,200); self.assertIn('Evidence',markdown.text)
        self.assertTrue(self.calls[-1][1].endswith('?revision=1'))
        rev = {'request_id':'rev-one','profile_version':version,'base_revision':1,'change_request':'Add practice'}
        response = self.client.post(path+'/revisions',json=rev,headers=self.origin)
        self.assertEqual(response.status_code,202,response.text); job2 = response.get_json()
        worker.process(sid,job2['job_id'])
        latest = self.client.get(path+'?revision=2'); self.assertEqual(latest.status_code,200,latest.text)
        self.assertEqual(latest.get_json()['revision'],2)
        self.assertEqual(self.client.get(path+'?revision=1').get_json(),plan)

    def test_download_export_escapes_untrusted_markdown(self):
        with open('career_coach/fixtures/career-plan.json', encoding='utf-8') as f: plan = json.load(f)
        plan['goal'] = '<script>alert(1)</script>\n# forged'
        plan['resources'][0]['title'] = '[bad](https://evil.example)'
        markdown, content_type, _ = export_plan(plan, 'markdown')
        self.assertNotIn('<script>', markdown); self.assertNotIn('\n# forged', markdown)
        self.assertIn('Evidence', markdown); self.assertIn('Assumptions', markdown)
        exported, _, _ = export_plan(plan, 'json'); self.assertEqual(json.loads(exported), plan)


if __name__ == '__main__': unittest.main()
