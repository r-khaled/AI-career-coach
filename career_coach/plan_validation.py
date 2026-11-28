"""Strict, source-bound validation of a generated career plan."""
import copy
import math

from .contracts import ContractError, validate


class PlanValidationError(ValueError):
    """Safe validation error without user input or provider details."""


def _fail():
    raise PlanValidationError('Plan validation failed')


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        _fail()
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _unique(items, key):
    result = {}
    for item in items:
        value = item[key]
        if value in result:
            _fail()
        result[value] = item
    return result


def _dag(graph):
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            _fail()
        if node in done:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                _fail()
            visit(dep)
        visiting.remove(node)
        done.add(node)
    for node in graph:
        visit(node)


def validate_plan(candidate, profile, internal_bundle, external_bundle, *, plan_id, revision):
    """Return a normalized plan, or raise a value-free PlanValidationError.

    Provider bundles are authoritative for structural fields, not for whether
    a course is suitable. Descriptive reason and practice text remain advice.
    """
    try:
        _finite(candidate)
        _finite(profile)
        validate('career-plan', candidate)
        validate('profile', profile)
        if (not isinstance(plan_id, str) or not plan_id or isinstance(revision, bool) or
                not isinstance(revision, int) or revision < 1 or
                profile['approved_profile_version'] != profile['profile_version'] or
                candidate['plan_id'] != plan_id or candidate['revision'] != revision or
                candidate['profile_version'] != profile['profile_version']):
            _fail()
        facts = _unique(profile['facts'], 'key')
        goal = facts.get('goal', {})
        if goal.get('basis') != 'user_reported' or not goal.get('value') or candidate['goal'] != goal['value']:
            _fail()
        assumptions = _unique(profile['assumptions'], 'assumption_id')
        confirmed = profile['confirmed_assumption_ids']
        if len(set(confirmed)) != len(confirmed) or not set(confirmed) <= assumptions.keys():
            _fail()
        allowed_assumptions = {assumptions[x]['description'] for x in confirmed}
        if any(x not in allowed_assumptions for x in candidate['assumptions']):
            _fail()
        equivalents = {cid for aid in confirmed for cid in assumptions[aid]['course_ids']}
        bundles = (internal_bundle, external_bundle)
        source_resources = _unique([x for b in bundles for x in b['resources']], 'resource_id')
        source_evidence = _unique([x for b in bundles for x in b['evidence']], 'evidence_id')
        resources = _unique(candidate['resources'], 'resource_id')
        evidence = _unique(candidate['evidence'], 'evidence_id')
        phases = _unique(candidate['phases'], 'phase_id')
        for eid, item in evidence.items():
            if eid not in source_evidence or item != source_evidence[eid]:
                _fail()
        identity = None
        source_records = external_bundle.get('records', [])
        records = _unique(source_records, 'evidence_id')
        field_provenance = external_bundle.get('field_provenance', {})
        for rid, resource in resources.items():
            source = source_resources.get(rid)
            if source is None:
                _fail()
            for key in ('resource_id', 'kind', 'course_id', 'title', 'url', 'duration_hours'):
                if resource[key] != source[key]:
                    _fail()
            ids = resource['evidence_ids']
            if len(set(ids)) != len(ids) or not set(ids) <= set(source['evidence_ids']) or not set(ids) <= evidence.keys():
                _fail()
            if resource['kind'] == 'internal':
                if not resource['course_id'] or resource['url'] is not None:
                    _fail()
                for eid in ids:
                    ev = evidence[eid]
                    if ev['source'] != 'internal_catalog' or ev['course_id'] != resource['course_id'] or not ev['catalog_version'] or not ev['parsed_source_sha256']:
                        _fail()
                    current = (ev['catalog_version'], ev['parsed_source_sha256'])
                    if identity is not None and current != identity:
                        _fail()
                    identity = current
                supported = {field for eid in ids for field in evidence[eid]['supported_fields']}
                if 'title' not in supported or (resource['duration_hours'] is not None and 'duration_hours' not in supported):
                    _fail()
            else:
                if resource['course_id'] is not None or resource['prerequisite_status'] != source['prerequisite_status']:
                    _fail()
                for field in ('title', 'url', 'duration_hours'):
                    if resource[field] is None:
                        continue
                    supported = set(field_provenance.get(rid, {}).get(field, [])) & set(ids)
                    if not any(eid in records and records[eid].get('field_values', {}).get(field) == resource[field] and
                               field in evidence[eid]['supported_fields'] for eid in supported):
                        _fail()

        # Enforce explicit user-reported hard constraints, not inferred preferences.
        constraints = {key: facts[key]['value'] for key in ('allowed_track', 'allowed_level', 'per_course_max_hours')
                       if key in facts and facts[key]['basis'] == 'user_reported' and facts[key]['value'] is not None}
        budget_fact = facts.get('budget', {})
        budget_text = budget_fact.get('value') if budget_fact.get('basis') == 'user_reported' else None
        free_only = isinstance(budget_text, str) and budget_text.strip().casefold() in {
            'free only', 'free courses only', 'no paid courses', 'no cost', 'zero budget'}
        language_fact = facts.get('language', {})
        language_text = language_fact.get('value') if language_fact.get('basis') == 'user_reported' else None
        strict_language = None
        if isinstance(language_text, str) and language_text.strip().casefold() in {'english only', 'arabic only'}:
            strict_language = language_text.strip().split()[0].casefold()
        internal_records = {r.get('metadata', {}).get('course_id'): r for r in internal_bundle.get('records', [])
                            if isinstance(r.get('metadata'), dict)}
        for resource in resources.values():
            if resource['kind'] == 'external':
                if constraints.get('allowed_track') or constraints.get('allowed_level'):
                    _fail()
                def supported_values(field):
                    ids = set(field_provenance.get(resource['resource_id'], {}).get(field, [])) & set(resource['evidence_ids'])
                    return [records[eid].get('field_values', {}).get(field) for eid in ids
                            if eid in records and field in evidence[eid]['supported_fields']]
                if free_only:
                    prices = supported_values('price')
                    if not prices or not any(isinstance(p, dict) and p.get('amount') in ('0', '0.0', '0.00') for p in prices):
                        _fail()
                if strict_language:
                    languages = supported_values('language')
                    aliases = {'english': {'english', 'en', 'en-us', 'en-gb'}, 'arabic': {'arabic', 'ar'}}
                    if not any(isinstance(v, str) and v.casefold() in aliases[strict_language] for v in languages):
                        _fail()
            else:
                meta = internal_records.get(resource['course_id'], {}).get('metadata', {})
                for key, meta_key in (('allowed_track', 'track'), ('allowed_level', 'level')):
                    if key in constraints and (not isinstance(meta.get(meta_key), str) or
                            meta[meta_key].casefold() != str(constraints[key]).strip().casefold()):
                        _fail()
                # No supported internal pricing or language field is currently supplied.
                if free_only or strict_language:
                    _fail()
            if 'per_course_max_hours' in constraints:
                hours = resource['duration_hours']
                if (isinstance(constraints['per_course_max_hours'], bool) or
                    not isinstance(constraints['per_course_max_hours'], (int, float)) or
                    hours is None or hours > constraints['per_course_max_hours']):
                    _fail()

        graph = {pid: phase['depends_on'] for pid, phase in phases.items()}
        for phase in phases.values():
            if len(set(phase['depends_on'])) != len(phase['depends_on']) or len(set(phase['resource_ids'])) != len(phase['resource_ids']):
                _fail()
        _dag(graph)
        def ancestors(pid):
            seen, todo = set(), list(graph[pid])
            while todo:
                dep = todo.pop()
                if dep not in seen:
                    seen.add(dep); todo.extend(graph[dep])
            return seen
        placements = {}
        for pid, phase in phases.items():
            for index, rid in enumerate(phase['resource_ids']):
                if rid not in resources:
                    _fail()
                placements.setdefault(rid, []).append((pid, index))
        if set(placements) != set(resources):
            _fail()
        prereqs = internal_bundle.get('prerequisites', {})
        _dag({cid: [dep for dep in deps if dep in prereqs] for cid, deps in prereqs.items()})
        selected_course_ids = [r['course_id'] for r in resources.values() if r['kind'] == 'internal']
        if len(set(selected_course_ids)) != len(selected_course_ids):
            _fail()
        gaps = list(candidate['coverage_gaps'])
        for bundle in bundles:
            for gap in bundle.get('gaps', []):
                if gap not in gaps:
                    gaps.append(gap)
        unresolved = False
        statuses = {}
        for rid, resource in resources.items():
            if resource['kind'] != 'internal':
                statuses[rid] = resource['prerequisite_status']
                if statuses[rid] == 'unresolved':
                    unresolved = True
                    gaps.append('Prerequisites unresolved for ' + rid)
                continue
            cid = resource['course_id']
            if cid not in prereqs:
                _fail()
            source_incomplete = source_resources[rid]['prerequisite_status'] == 'unresolved'
            if not source_incomplete and not any('prerequisites' in evidence[eid]['supported_fields'] for eid in resource['evidence_ids']):
                _fail()
            used_equivalence = False
            for dep in prereqs[cid]:
                dep_id = 'internal:' + dep
                if dep_id not in resources:
                    if dep in equivalents:
                        used_equivalence = True
                        continue
                    if source_incomplete:
                        continue
                    _fail()
                for pid, index in placements[rid]:
                    if not any((dp == pid and di < index) or dp in ancestors(pid)
                               for dp, di in placements[dep_id]):
                        _fail()
            statuses[rid] = ('unresolved' if source_incomplete else
                             'user_confirmed_equivalence' if used_equivalence else
                             'included' if prereqs[cid] else 'none')
            if source_incomplete:
                unresolved = True
                gaps.append('Prerequisites unresolved for ' + rid)
        if not resources and 'No sourced learning resources selected' not in gaps:
            gaps.append('No sourced learning resources selected')
        result = copy.deepcopy(candidate)
        result['assumptions'] = [assumptions[aid]['description'] for aid in confirmed]
        for resource in result['resources']:
            resource['prerequisite_status'] = statuses[resource['resource_id']]
        result['coverage_gaps'] = list(dict.fromkeys(gaps))
        budget = result['time_budget']
        def user_number(key):
            item = facts.get(key, {})
            value = item.get('value') if item.get('basis') == 'user_reported' else None
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                _fail()
            return value
        weekly, weeks = user_number('weekly_hours'), user_number('deadline_weeks')
        known = sum(r['duration_hours'] for r in resources.values() if r['duration_hours'] is not None)
        practice = sum(p['practice']['estimated_hours'] for p in phases.values())
        if not math.isfinite(known) or not math.isfinite(practice):
            _fail()
        missing = sorted(rid for rid, r in resources.items() if r['duration_hours'] is None)
        capacity = weekly * weeks if weekly is not None and weeks is not None else None
        if capacity is not None and not math.isfinite(capacity):
            _fail()
        fit = ('exceeds' if capacity is not None and known + practice > capacity else
               'unknown' if capacity is None or missing or unresolved or not resources else 'estimated_fit')
        budget.update(weekly_hours=weekly, target_weeks=weeks, known_course_hours=known,
                      estimated_practice_hours=practice, unestimated_resource_ids=missing, fit_status=fit)
        validate('career-plan', result)
        return result
    except (ContractError, KeyError, TypeError, ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, PlanValidationError):
            raise
        raise PlanValidationError('Plan validation failed') from None
