import copy
import threading
import unittest
from career_coach.store import MemoryStore
from career_coach.sessions import SessionService
from career_coach.errors import APIError


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.time = 1000
        self.store = MemoryStore()
        self.a = SessionService(self.store, clock=lambda: self.time)
        self.b = SessionService(self.store, clock=lambda: self.time)
        self.state, self.token = self.a.create()
        self.sid = self.state['session_id']

    def claim(self, request='r', value='answer', version=1, service=None):
        return (service or self.a).claim(self.sid, self.token, request, {'answer': value}, version)

    def test_auth_expiry_and_sliding_across_instances(self):
        with self.assertRaises(APIError) as e:
            self.b.read(self.sid, 'wrong')
        self.assertEqual(e.exception.status, 403)
        self.time += 600000
        self.assertEqual(self.b.read(self.sid, self.token), self.state)
        self.time += 604800
        with self.assertRaises(APIError) as e:
            self.a.read(self.sid, self.token)
        self.assertEqual(e.exception.status, 410)
        self.assertIsNotNone(self.store.get('SESSION#'+self.sid, 'STATE'))

    def test_replay_content_conflict_and_stale(self):
        c = self.claim(); new = copy.deepcopy(self.state); new['state_version'] = 2
        self.a.complete(self.sid, self.token, 'r', c['claim_token'], new, {'ok': True}, {'answer': 'answer'})
        self.assertEqual(self.claim(service=self.b), {'status': 'replay', 'response': {'ok': True}})
        with self.assertRaises(APIError) as e:
            self.claim(value='different')
        self.assertEqual(e.exception.code, 'request_conflict')
        with self.assertRaises(APIError) as e:
            self.claim(request='new')
        self.assertEqual(e.exception.code, 'stale_version')

    def test_concurrent_same_and_different_requests(self):
        barrier = threading.Barrier(2); results = []
        def run(service):
            barrier.wait(); results.append(self.claim(service=service)['status'])
        threads = [threading.Thread(target=run, args=(x,)) for x in (self.a,self.b)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertCountEqual(results, ['claimed','processing'])
        with self.assertRaises(APIError) as e:
            self.claim(request='other')
        self.assertEqual(e.exception.code, 'processing')

    def test_fencing_and_bounded_recovery(self):
        first = self.claim(); self.time += 60
        second = self.claim(); self.time += 60
        third = self.claim(); new = copy.deepcopy(self.state); new['state_version'] = 2
        with self.assertRaises(APIError) as e:
            self.a.complete(self.sid,self.token,'r',first['claim_token'],new,{}, {})
        self.assertEqual(e.exception.code, 'claim_lost')
        self.time += 60
        with self.assertRaises(APIError) as e:
            self.claim()
        self.assertEqual(e.exception.code, 'recovery_exhausted')
        self.assertNotEqual(second['claim_token'], third['claim_token'])

    def test_lost_completion_response_is_replayed(self):
        first = self.claim(); new = copy.deepcopy(self.state); new['state_version'] = 2
        self.a.complete(self.sid,self.token,'r',first['claim_token'],new,{'saved': True}, {})
        self.assertEqual(self.claim()['response'], {'saved': True})
        self.assertEqual(self.b.read(self.sid,self.token)['state_version'], 2)


    def test_large_valid_response_replay_and_renewal(self):
        c = self.claim(); new = copy.deepcopy(self.state); new['state_version'] = 2
        response = {'data': 'x' * 40000}
        self.a.complete(self.sid, self.token, 'r', c['claim_token'], new, response, {})
        self.time += 600000
        self.b.read(self.sid, self.token)
        self.time += 10000
        self.assertEqual(self.claim()['response'], response)

    def test_receipts_survive_sliding_expiry_and_simulated_ttl(self):
        c = self.claim(); new = copy.deepcopy(self.state); new['state_version'] = 2
        self.a.complete(self.sid, self.token, 'r', c['claim_token'], new, {'ok': True}, {})
        self.time += 600000
        self.b.read(self.sid, self.token)
        self.time += 10000
        with self.store._lock:
            self.store._items = {k:v for k,v in self.store._items.items() if v.get('expires_at', self.time+1) > self.time}
        self.assertEqual(self.claim()['status'], 'replay')

    def test_failure_releases_lock_and_preserves_question(self):
        c = self.claim()
        response = self.a.fail(self.sid, self.token, 'r', c['claim_token'])
        self.assertEqual(response['code'], 'temporary_failure')
        self.assertEqual(self.b.read(self.sid, self.token)['state_version'], 1)
        self.assertEqual(self.claim()['status'], 'failed')
        self.assertEqual(self.claim(request='new')['status'], 'claimed')

    def test_abandoned_request_can_be_replaced_after_lease(self):
        first = self.claim()
        self.time += 60
        self.assertEqual(self.claim(request='new')['status'], 'claimed')
        self.assertEqual(self.claim(request='r')['status'], 'failed')
        new = copy.deepcopy(self.state); new['state_version'] = 2
        with self.assertRaises(APIError) as e:
            self.a.complete(self.sid, self.token, 'r', first['claim_token'], new, {}, {})
        self.assertEqual(e.exception.code, 'claim_lost')

    def test_exhaustion_releases_lock(self):
        self.claim()
        for _ in range(2):
            self.time += 60; self.claim()
        self.time += 60
        with self.assertRaises(APIError): self.claim()
        self.assertEqual(self.claim(request='fresh')['status'], 'claimed')


if __name__ == '__main__': unittest.main()
