import unittest
from career_coach.store import MemoryStore, DynamoStore, StoreConflict, encode_item


class StoreTests(unittest.TestCase):
    def test_memory_atomic_cas_and_copy(self):
        s = MemoryStore(); a = {'pk':'p','sk':'a','item':{'revision':1},'expected_revision':None}
        s.transact([a]); a['item']['revision'] = 9
        self.assertEqual(s.get('p','a')['revision'], 1)
        with self.assertRaises(StoreConflict):
            s.transact([{'pk':'p','sk':'b','item':{'revision':1},'expected_revision':None},a])
        self.assertIsNone(s.get('p','b'))

    def test_dynamo_json_and_conditions(self):
        class Client:
            def transact_write_items(self, **kwargs): self.kwargs = kwargs
            def get_item(self, **kwargs): return {'Item': {'payload': {'S': '{"revision":1,"value":0.1}'}}}
        c = Client(); s = DynamoStore(c,'table')
        self.assertEqual(s.get('p','s')['value'], 0.1)
        s.transact([{'pk':'p','sk':'s','item':{'revision':2,'value':0.1,'expires_at':4},'expected_revision':1}])
        put = c.kwargs['TransactItems'][0]['Put']
        self.assertEqual(put['Item']['expires_at'], {'N':'4'})
        self.assertIn('0.1', put['Item']['payload']['S'])
        self.assertEqual(put['ExpressionAttributeValues'][':expected'], {'N':'1'})

    def test_size_bound(self):
        with self.assertRaises(ValueError): encode_item({'x':'a' * (301*1024)})

    def test_transaction_bounds(self):
        s = MemoryStore()
        op = {'pk':'p','sk':'s','item':{'revision':1},'expected_revision':None}
        with self.assertRaises(ValueError): s.transact([op, op])
        with self.assertRaises(ValueError): s.transact([dict(op, sk=str(i)) for i in range(101)])
        with self.assertRaises(ValueError):
            s.transact([dict(op, sk=str(i), item={'revision':1, 'data':'x'*300000}) for i in range(12)])

    def test_dynamo_requests_match_botocore_shapes(self):
        import botocore.session
        from botocore.validate import validate_parameters
        model = botocore.session.get_session().get_service_model('dynamodb')
        class Client:
            def transact_write_items(self, **kwargs):
                validate_parameters(kwargs, model.operation_model('TransactWriteItems').input_shape)
            def get_item(self, **kwargs):
                validate_parameters(kwargs, model.operation_model('GetItem').input_shape)
                return {}
        s = DynamoStore(Client(), 'table')
        self.assertIsNone(s.get('p', 's'))
        s.transact([{'pk':'p','sk':'s','item':{'revision':1,'expires_at':100},'expected_revision':None}])
        s.transact([{'pk':'p','sk':'s','item':{'revision':2},'expected_revision':1}])


if __name__ == '__main__': unittest.main()
