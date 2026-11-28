"""Conditional, bounded JSON records for anonymous sessions and future jobs."""
import copy
import json
import threading

MAX_ITEM_BYTES = 300 * 1024


class StoreConflict(Exception):
    pass


def encode_item(item):
    data = json.dumps(item, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))
    if len(data.encode("utf-8")) > MAX_ITEM_BYTES:
        raise ValueError("Record exceeds size limit")
    return data


def _validate_operations(operations):
    if not operations or len(operations) > 100:
        raise ValueError("Invalid transaction size")
    keys = [(op['pk'], op['sk']) for op in operations]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate transaction item")
    # Leave room for DynamoDB attribute names, keys and protocol overhead.
    total = sum(len(encode_item(op['item']).encode('utf-8')) +
                len(op['pk'].encode('utf-8')) + len(op['sk'].encode('utf-8')) + 128
                for op in operations)
    if total > 3_500_000:
        raise ValueError("Transaction exceeds size limit")


class MemoryStore:
    def __init__(self):
        self._items = {}
        self._lock = threading.RLock()

    def get(self, pk, sk):
        with self._lock:
            return copy.deepcopy(self._items.get((pk, sk)))

    def transact(self, operations):
        _validate_operations(operations)
        with self._lock:
            for op in operations:
                current = self._items.get((op['pk'], op['sk']))
                expected = op['expected_revision']
                if (current is None if expected is not None else current is not None):
                    raise StoreConflict()
                if current is not None and current['revision'] != expected:
                    raise StoreConflict()
                encode_item(op['item'])
            for op in operations:
                self._items[(op['pk'], op['sk'])] = copy.deepcopy(op['item'])


class DynamoStore:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def get(self, pk, sk):
        response = self.client.get_item(TableName=self.table_name,
            Key={'pk': {'S': pk}, 'sk': {'S': sk}}, ConsistentRead=True)
        item = response.get('Item')
        return json.loads(item['payload']['S']) if item else None

    def transact(self, operations):
        _validate_operations(operations)
        changes = []
        for op in operations:
            item, expected = op['item'], op['expected_revision']
            data = encode_item(item)
            record = {'pk': {'S': op['pk']}, 'sk': {'S': op['sk']},
                      'revision': {'N': str(item['revision'])}, 'payload': {'S': data}}
            if 'expires_at' in item:
                record['expires_at'] = {'N': str(int(item['expires_at']))}
            put = {'TableName': self.table_name, 'Item': record}
            if expected is None:
                put['ConditionExpression'] = 'attribute_not_exists(pk)'
            else:
                put['ConditionExpression'] = '#rev = :expected'
                put['ExpressionAttributeNames'] = {'#rev': 'revision'}
                put['ExpressionAttributeValues'] = {':expected': {'N': str(expected)}}
            changes.append({'Put': put})
        try:
            self.client.transact_write_items(TransactItems=changes)
        except Exception as exc:
            # Only conditional cancellation is a conflict; service/network errors
            # must remain failures, never be retried as successful CAS.
            response = getattr(exc, 'response', {})
            if response.get('Error', {}).get('Code') == 'TransactionCanceledException':
                reasons = response.get('CancellationReasons', [])
                if any(r.get('Code') == 'ConditionalCheckFailed' for r in reasons):
                    raise StoreConflict() from exc
            raise
