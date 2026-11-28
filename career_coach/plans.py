"""Immutable final plan revisions in the existing retained plans table."""
import copy
import base64
import gzip
import json
import threading

from .store import encode_item


class PlanConflict(Exception):
    pass


def _item(job_id, plan, trace):
    raw = json.dumps(trace, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    if len(raw) > 3 * 1024 * 1024:
        raise ValueError('Trace exceeds size limit')
    item = {'job_id':job_id, 'plan':copy.deepcopy(plan),
            'trace_gzip_b64':base64.b64encode(gzip.compress(raw, mtime=0)).decode('ascii'),
            'trace_raw_size':len(raw)}
    encode_item(item)
    return item


def _key(plan_id, revision):
    if not isinstance(plan_id, str) or not plan_id or '#' in plan_id or isinstance(revision, bool) or not isinstance(revision, int) or not 1 <= revision <= 999999:
        raise ValueError('Invalid plan key')
    return f'PLAN#{plan_id}#REV#{revision:06d}'


class MemoryPlanStore:
    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def save(self, sid, plan_id, revision, job_id, plan, trace=None):
        key = (sid, _key(plan_id, revision))
        item = _item(job_id, plan, trace if trace is not None else {})
        with self._lock:
            existing = self._items.get(key)
            if existing is not None and existing != item:
                raise PlanConflict('Plan revision already exists')
            self._items[key] = copy.deepcopy(item)

    def load(self, sid, plan_id, revision):
        with self._lock:
            return copy.deepcopy(self._items.get((sid, _key(plan_id, revision))))

    def save_fenced(self, sid, plan_id, revision, job_id, plan, store, job_revision, trace=None):
        # Share the session store lock so another claimant cannot race this save.
        with store._lock:
            job = store._items.get(('SESSION#' + sid, 'JOB#' + job_id))
            if not job or job['revision'] != job_revision:
                from .store import StoreConflict
                raise StoreConflict()
            self.save(sid, plan_id, revision, job_id, plan, trace)


class DynamoPlanStore:
    def __init__(self, client, table):
        self.client, self.table = client, table

    def load(self, sid, plan_id, revision):
        key = {'user_id': {'S': sid}, 'timestamp': {'S': _key(plan_id, revision)}}
        item = self.client.get_item(TableName=self.table, Key=key, ConsistentRead=True).get('Item')
        return json.loads(item['payload']['S']) if item else None

    def save(self, sid, plan_id, revision, job_id, plan, trace=None):
        item = _item(job_id, plan, trace if trace is not None else {})
        payload = encode_item(item)
        try:
            self.client.put_item(TableName=self.table, Item={'user_id': {'S': sid},
                'timestamp': {'S': _key(plan_id, revision)}, 'payload': {'S': payload}},
                ConditionExpression='attribute_not_exists(user_id)')
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
                raise
            if self.load(sid, plan_id, revision) != item:
                raise PlanConflict('Plan revision already exists') from None

    def save_fenced(self, sid, plan_id, revision, job_id, plan, store, job_revision, trace=None):
        item = _item(job_id, plan, trace if trace is not None else {})
        payload = encode_item(item)
        check = {'TableName':store.table_name, 'Key':{'pk':{'S':'SESSION#'+sid}, 'sk':{'S':'JOB#'+job_id}},
                 'ConditionExpression':'#rev = :rev', 'ExpressionAttributeNames':{'#rev':'revision'},
                 'ExpressionAttributeValues':{':rev':{'N':str(job_revision)}}}
        put = {'TableName':self.table, 'Item':{'user_id':{'S':sid}, 'timestamp':{'S':_key(plan_id, revision)},
                'payload':{'S':payload}}, 'ConditionExpression':'attribute_not_exists(user_id)'}
        try:
            self.client.transact_write_items(TransactItems=[{'ConditionCheck':check}, {'Put':put}])
        except Exception as exc:
            response = getattr(exc, 'response', {})
            if response.get('Error', {}).get('Code') == 'TransactionCanceledException':
                reasons = response.get('CancellationReasons', [])
                if len(reasons) > 1 and reasons[1].get('Code') == 'ConditionalCheckFailed':
                    if self.load(sid, plan_id, revision) == item:
                        return
                    raise PlanConflict('Plan revision already exists') from None
                if reasons and reasons[0].get('Code') == 'ConditionalCheckFailed':
                    from .store import StoreConflict
                    raise StoreConflict() from None
            raise
