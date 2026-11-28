"""Bounded internal-catalog retrieval and prerequisite closure; no generation calls."""
import copy
from datetime import datetime, timezone
import math
import re

from .config import DEFAULTS
from .contracts import validate


COURSE_ID = re.compile(r'\b[A-Z][A-Z0-9]*-\d+\b')


class RetrievalConflict(ValueError):
    """Inconsistent catalog evidence must not be combined into a candidate pool."""


class InternalRetriever:
    def __init__(self, client, kb_id, *, clock=None, max_depth=None, max_requests=None):
        if not kb_id:
            raise ValueError('Knowledge Base ID required')
        self.client, self.kb_id = client, kb_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_depth = DEFAULTS.prerequisite_max_depth if max_depth is None else max_depth
        self.max_requests = DEFAULTS.prerequisite_max_requests if max_requests is None else max_requests
        if isinstance(self.max_depth, bool) or isinstance(self.max_requests, bool) or not isinstance(self.max_depth, int) or not isinstance(self.max_requests, int) or self.max_depth < 0 or self.max_requests < 1:
            raise ValueError('Invalid retrieval bounds')

    def retrieve(self, profile, gaps=None):
        validate('profile', profile)
        if profile['approved_profile_version'] != profile['profile_version']:
            raise ValueError('An approved profile is required')
        facts = {f['key']: f['value'] for f in profile['facts'] if f['basis'] == 'user_reported'}
        goal = facts.get('goal')
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError('An explicitly reported goal is required')
        if gaps is None:
            gaps = []
        if not isinstance(gaps, list) or any(not isinstance(g, str) or not g.strip() for g in gaps):
            raise ValueError('Gaps must be nonempty strings')
        requested = set(COURSE_ID.findall(' '.join([goal] + gaps).upper()))
        constraints = {k: facts[k] for k in ('allowed_track', 'allowed_level', 'per_course_max_hours') if facts.get(k) is not None}
        for key in ('allowed_track', 'allowed_level'):
            if key in constraints and (not isinstance(constraints[key], str) or not constraints[key].strip()):
                raise ValueError('Invalid explicit constraint')
        if 'per_course_max_hours' in constraints:
            n = constraints['per_course_max_hours']
            if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n <= 0:
                raise ValueError('Invalid explicit constraint')
        confirmed = set(profile['confirmed_assumption_ids'])
        assumptions = {a['assumption_id']: a for a in profile['assumptions']}
        if not confirmed <= assumptions.keys():
            raise ValueError('Unknown confirmed assumption')
        equivalents = {course for aid in confirmed for course in assumptions[aid]['course_ids']}
        if any(not COURSE_ID.fullmatch(course) for course in equivalents):
            raise ValueError('Invalid confirmed equivalent course ID')
        records, contexts, pool, gap_messages = [], [], {}, []
        identity = None
        requests = 0
        failed = False

        def add_gap(message):
            if message not in gap_messages:
                gap_messages.append(message)

        def fetch(query, exact=None):
            nonlocal requests, identity, failed
            if requests >= self.max_requests:
                add_gap('Retrieval request budget reached')
                return
            query_filter = {'equals': {'key': 'record_type', 'value': 'course'}}
            if exact:
                query_filter = {'andAll': [query_filter, {'equals': {'key': 'course_id', 'value': exact}}]}
            settings = {'vectorSearchConfiguration': {'numberOfResults': DEFAULTS.retrieval_results,
                'overrideSearchType': DEFAULTS.retrieval_search_type, 'filter': query_filter}}
            requests += 1
            try:
                response = self.client.retrieve(knowledgeBaseId=self.kb_id,
                    retrievalQuery={'text': query}, retrievalConfiguration=settings)
            except Exception:
                failed = True
                add_gap('Internal retrieval temporarily unavailable')
                return
            timestamp = self.clock()
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                raise ValueError('Clock must return a timezone-aware datetime')
            timestamp = timestamp.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            results = response.get('retrievalResults', [])
            if len(results) > DEFAULTS.retrieval_results:
                add_gap('Retrieve response exceeded the configured result limit')
            for rank, result in enumerate(results[:DEFAULTS.retrieval_results], 1):
                meta = result.get('metadata', {})
                record = {'text': result.get('content', {}).get('text'), 'metadata': copy.deepcopy(meta),
                    'location': copy.deepcopy(result.get('location')), 'rank': rank,
                    'score': result.get('score'), 'query': query, 'settings': copy.deepcopy(settings),
                    'retrieved_at': timestamp}
                records.append(record)
                if not isinstance(meta, dict):
                    add_gap('A retrieved record has invalid metadata')
                    continue
                if meta.get('record_type') not in {'course', 'catalog_context'}:
                    add_gap('A retrieved record has an unknown record type')
                    continue
                version, digest = meta.get('catalog_version'), meta.get('parsed_source_sha256')
                if not isinstance(version, str) or not version or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                    add_gap('A retrieved record lacks catalog version or source hash')
                    continue
                if identity is not None and identity != (version, digest):
                    raise RetrievalConflict('Mixed catalog versions or source hashes')
                identity = (version, digest)
                if meta['record_type'] == 'catalog_context':
                    contexts.append(record)
                    continue
                cid = meta.get('course_id')
                if not isinstance(cid, str) or not COURSE_ID.fullmatch(cid) or not isinstance(record['text'], str) or not record['text']:
                    add_gap('A retrieved course lacks an ID or text')
                    continue
                if cid in pool and (pool[cid]['text'] != record['text'] or pool[cid]['metadata'] != meta):
                    raise RetrievalConflict(f'Conflicting evidence for course {cid}')
                heading = re.match(r'^### Course ID:\s*([A-Z][A-Z0-9]*-\d+)\s*$', record['text'], re.MULTILINE)
                name = re.search(r'^\*\*Course Name:\*\*\s*(.+)$', record['text'], re.MULTILINE)
                duration = re.search(r'^\*\*Estimated Duration:\*\*\s*(\d+) hours, including practice\.$', record['text'], re.MULTILINE)
                recorded_hours = meta.get('duration_hours')
                if (not heading or heading.group(1) != cid or not name or name.group(1).strip() != meta.get('course_name') or
                    not duration or (recorded_hours is not None and
                    (isinstance(recorded_hours, bool) or not isinstance(recorded_hours, (int, float)) or
                     not math.isfinite(recorded_hours) or recorded_hours != int(duration.group(1))))):
                    add_gap(f'Course text and metadata disagree: {cid}')
                    continue
                if exact and cid != exact:
                    add_gap(f'Exact lookup returned a different course for {exact}')
                    continue
                if cid in pool:
                    continue
                pool[cid] = record

        query = 'Career goal: ' + goal.strip()
        if gaps:
            query += '\nCapability gaps: ' + '; '.join(g.strip() for g in gaps)
        fetch(query)
        roots = set(pool) | requested
        graph, states, incomplete, prerequisites_supported = {}, {}, set(), set()

        def visit(cid, depth):
            if cid in equivalents and cid not in roots:
                return True
            if states.get(cid) == 'visiting':
                add_gap(f'Prerequisite cycle involving {cid}')
                incomplete.add(cid)
                return False
            if states.get(cid) == 'done':
                return cid not in incomplete
            if depth > self.max_depth:
                add_gap(f'Prerequisite depth limit reached at {cid}')
                incomplete.add(cid)
                return False
            if cid not in pool:
                fetch(cid, cid)
            record = pool.get(cid)
            if not record:
                add_gap(f'Missing course evidence: {cid}')
                incomplete.add(cid)
                states[cid] = 'done'
                return False
            meta = record['metadata']
            location = record['location'] or {}
            uri = location.get('s3Location', {}).get('uri') if isinstance(location, dict) else None
            if (not isinstance(uri, str) or not re.fullmatch(r's3://[^/\s]+/[^\s]+', uri) or
                not isinstance(meta.get('course_name'), str) or not meta['course_name'].strip()):
                add_gap(f'Course lacks source URI or title: {cid}')
                incomplete.add(cid)
                return False
            if ('allowed_track' in constraints and str(meta.get('track', '')).casefold() != constraints['allowed_track'].strip().casefold()) or ('allowed_level' in constraints and str(meta.get('level', '')).casefold() != constraints['allowed_level'].strip().casefold()):
                add_gap(f'Explicit track or level constraint blocks {cid}')
                incomplete.add(cid)
                return False
            hours = meta.get('duration_hours')
            valid_hours = isinstance(hours, (int, float)) and not isinstance(hours, bool) and math.isfinite(hours) and hours >= 0
            if 'per_course_max_hours' in constraints and (not valid_hours or hours > constraints['per_course_max_hours']):
                add_gap(f'Explicit per-course duration constraint blocks {cid}')
                incomplete.add(cid)
                return False
            prerequisites = meta.get('prerequisites', [])
            source_prerequisites = re.search(r'^\*\*Prerequisites:\*\*\s*(.+)$', record['text'], re.MULTILINE)
            source_ids = COURSE_ID.findall(source_prerequisites.group(1)) if source_prerequisites else None
            if (not isinstance(prerequisites, list) or any(not isinstance(p, str) or not COURSE_ID.fullmatch(p) for p in prerequisites)
                    or not isinstance(meta.get('has_prerequisites'), bool)
                    or meta['has_prerequisites'] != bool(prerequisites) or source_ids != prerequisites
                    or (not prerequisites and source_prerequisites.group(1).strip() != 'None; suitable as an entry point.')):
                add_gap(f'Incomplete prerequisite metadata: {cid}')
                incomplete.add(cid)
                prerequisites = []
            else:
                prerequisites_supported.add(cid)
            graph[cid] = list(dict.fromkeys(prerequisites))
            states[cid] = 'visiting'
            for dep in graph[cid]:
                if not visit(dep, depth + 1):
                    incomplete.add(cid)
            states[cid] = 'done'
            return cid not in incomplete

        for cid in sorted(roots):
            visit(cid, 0)
        resources, evidence = [], []
        known_hours = 0
        for cid in sorted(graph):
            record = pool[cid]; meta = record['metadata']; location = record['location'] or {}
            uri = location.get('s3Location', {}).get('uri') if isinstance(location, dict) else None
            title = meta.get('course_name'); duration = meta.get('duration_hours')
            if not isinstance(uri, str) or not uri.startswith('s3://') or not isinstance(title, str) or not title.strip():
                add_gap(f'Course lacks source URI or title: {cid}')
                incomplete.add(cid)
                continue
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                duration = None
                add_gap(f'Unknown duration: {cid}')
            else:
                known_hours += duration
            eid = 'internal:' + cid
            prerequisites = graph[cid]
            status = 'unresolved' if cid in incomplete else ('none' if not prerequisites else
                'user_confirmed_equivalence' if any(p in equivalents and p not in roots for p in prerequisites) else 'included')
            resource = {'resource_id': 'internal:' + cid, 'kind': 'internal', 'course_id': cid,
                'title': title, 'url': None, 'duration_hours': duration, 'prerequisite_status': status,
                'reason': 'Retrieved internal candidate or prerequisite', 'evidence_ids': [eid]}
            proof = {'evidence_id': eid, 'source': 'internal_catalog', 'uri': uri, 'retrieved_at': record['retrieved_at'],
                'catalog_version': meta['catalog_version'], 'parsed_source_sha256': meta['parsed_source_sha256'],
                'course_id': cid, 'supported_fields': ['title'] + (['prerequisites'] if cid in prerequisites_supported else []) + (['duration_hours'] if duration is not None else [])}
            validate('resource', resource); validate('evidence', proof)
            resources.append(resource); evidence.append(proof)
        return {'resources': resources, 'evidence': evidence, 'records': records, 'contexts': contexts,
            'prerequisites': graph, 'gaps': gap_messages, 'known_course_hours': known_hours,
            'complete': not gap_messages and not failed,
            'experiment': {'number_of_results': DEFAULTS.retrieval_results, 'search_type': DEFAULTS.retrieval_search_type,
                           'record_type': 'course', 'requests': requests, 'max_requests': self.max_requests,
                           'max_depth': self.max_depth, 'constraints': constraints}}
