"""Compose one bounded in-process plan from a frozen approved profile."""
import copy
import json
from pathlib import Path
import re

from .config import DEFAULTS
from .contracts import ContractError, validate
from .external import TOPICS
from .models import ModelError
from .plan_validation import PlanValidationError, validate_plan
from jsonschema import Draft202012Validator

_PLAN_SCHEMA = json.loads((Path(__file__).parent / 'schemas' / 'career-plan.json').read_text(encoding='utf-8'))
_DRAFT_SCHEMA = copy.deepcopy(_PLAN_SCHEMA)
_DRAFT_SCHEMA['required'].remove('evidence')
_DRAFT_SCHEMA['properties'].pop('evidence')
for _bound in ('plan_id', 'revision', 'profile_version', 'goal'):
    _DRAFT_SCHEMA['required'].remove(_bound)
    _DRAFT_SCHEMA['properties'].pop(_bound)
_DRAFT_SCHEMA['properties']['resources'] = {'type': 'array', 'items': {
    'type': 'object', 'additionalProperties': False, 'required': ['resource_id', 'reason'],
    'properties': {'resource_id': {'type': 'string', 'minLength': 1}, 'reason': {'type': 'string', 'minLength': 1}}}}


class PlanningError(Exception):
    """Safe failure without provider output or private profile content."""


def _text(value, limit=2000):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def _outline(value):
    if not isinstance(value, dict) or set(value) != {'capabilities', 'gaps', 'external_topic_ids'}:
        raise PlanningError('Invalid outline')
    capabilities, gaps, topics = value['capabilities'], value['gaps'], value['external_topic_ids']
    if (not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 8 or
            not isinstance(gaps, list) or len(gaps) > 8 or any(not _text(x, 500) for x in gaps) or
            not isinstance(topics, list) or len(topics) > 3 or
            any(not isinstance(t, str) or t not in TOPICS for t in topics) or len(set(topics)) != len(topics)):
        raise PlanningError('Invalid outline')
    skill_ids = set()
    for capability in capabilities:
        if not isinstance(capability, dict) or set(capability) != {'skill_id', 'purpose', 'outcomes', 'practice', 'completion_criteria'}:
            raise PlanningError('Invalid outline')
        skill_id = capability['skill_id']
        if (not isinstance(skill_id, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,99}', skill_id) or
                skill_id in skill_ids or not _text(capability['purpose'], 500) or not _text(capability['practice'], 1000)):
            raise PlanningError('Invalid outline')
        skill_ids.add(skill_id)
        for field in ('outcomes', 'completion_criteria'):
            values = capability[field]
            if not isinstance(values, list) or not 1 <= len(values) <= 8 or any(not _text(x, 500) for x in values):
                raise PlanningError('Invalid outline')
    return copy.deepcopy(value)


def _language(profile):
    for fact in profile['facts']:
        if fact['key'] == 'language' and fact['basis'] == 'user_reported' and isinstance(fact['value'], str):
            if fact['value'].strip().casefold() in {'ar', 'arabic', 'العربية', 'عربي'}:
                return 'ar'
    return 'en'


def _empty_external(message):
    return {'resources': [], 'evidence': [], 'records': [], 'field_provenance': {}, 'gaps': [message],
            'budget': {'search_attempts': 0, 'page_reads': 0,
                       'max_search_attempts': DEFAULTS.search_max_requests,
                       'max_page_reads': DEFAULTS.search_max_page_reads}}


def _close_selected_dependencies(candidate, profile, internal):
    """Attach known prerequisite entities before validating the composed plan."""
    validate('career-plan', candidate)
    result = copy.deepcopy(candidate)
    sources = {r['resource_id']: r for r in internal['resources']}
    proofs = {e['evidence_id']: e for e in internal['evidence']}
    selected = {r['resource_id']: r for r in result['resources']}
    evidence = {e['evidence_id'] for e in result['evidence']}
    equivalent = {cid for a in profile['assumptions'] if a['assumption_id'] in profile['confirmed_assumption_ids'] for cid in a['course_ids']}
    graph = internal.get('prerequisites', {})
    def expand(rid, visiting):
        if rid in visiting:
            raise PlanValidationError('Plan validation failed')
        resource = selected.get(rid)
        if not resource or resource['kind'] != 'internal': return []
        added = []
        for cid in graph.get(resource['course_id'], []):
            dep = 'internal:' + cid
            if cid in equivalent and dep not in selected: continue
            if dep not in selected:
                source = sources.get(dep)
                if source is None: continue
                selected[dep] = copy.deepcopy(source)
                result['resources'].append(selected[dep])
                for eid in source['evidence_ids']:
                    if eid not in evidence:
                        result['evidence'].append(copy.deepcopy(proofs[eid])); evidence.add(eid)
            added.extend(expand(dep, visiting | {rid})); added.append(dep)
        return added
    for phase in result['phases']:
        ordered = []
        for rid in phase['resource_ids']:
            ordered.extend(expand(rid, set())); ordered.append(rid)
        phase['resource_ids'] = list(dict.fromkeys(ordered))
    return result


def _materialize(candidate, internal, external, *, profile, plan_id, revision):
    if not isinstance(candidate, dict) or 'evidence' in candidate:
        return candidate  # Existing full-plan providers remain strictly validated.
    if not Draft202012Validator(_DRAFT_SCHEMA).is_valid(candidate):
        raise PlanValidationError('Invalid plan draft')
    result = copy.deepcopy(candidate)
    result.update(plan_id=plan_id, revision=revision, profile_version=profile['profile_version'],
                  goal=next(f['value'] for f in profile['facts'] if f['key']=='goal'))
    resources = {r['resource_id']: r for bundle in (internal, external) for r in bundle['resources']}
    evidence = {e['evidence_id']: e for bundle in (internal, external) for e in bundle['evidence']}
    result['resources'] = []
    ids = set()
    for ref in candidate['resources']:
        if ref['resource_id'] not in resources:
            raise PlanValidationError('Unknown resource reference')
        resource = copy.deepcopy(resources[ref['resource_id']]); resource['reason'] = ref['reason']
        result['resources'].append(resource); ids.update(resource['evidence_ids'])
    result['evidence'] = [copy.deepcopy(evidence[eid]) for eid in sorted(ids)]
    return result


class PlanningPipeline:
    def __init__(self, model, internal_retriever, external_factory):
        self.model, self.internal_retriever, self.external_factory = model, internal_retriever, external_factory

    def generate(self, profile, *, plan_id, revision, change_request=None, stage_callback=None):
        usage = getattr(self.model, 'usage', None)
        if isinstance(usage, list):
            usage.clear()
        try:
            validate('profile', profile)
        except (ContractError, TypeError, ValueError):
            raise PlanningError('Invalid profile') from None
        if (profile['approved_profile_version'] != profile['profile_version'] or
                not isinstance(plan_id, str) or not 1 <= len(plan_id) <= 128 or
                isinstance(revision, bool) or not isinstance(revision, int) or revision < 1 or
                (change_request is not None and not _text(change_request, 4000))):
            raise PlanningError('Invalid planning request')
        facts = [f for f in profile['facts'] if f['key'] == 'goal']
        if len(facts) != 1 or facts[0]['basis'] != 'user_reported' or not _text(facts[0]['value']):
            raise PlanningError('Invalid planning request')
        frozen = copy.deepcopy(profile)

        def stage(name):
            if stage_callback is not None:
                stage_callback(name)

        stage('outline')
        try:
            proposed = self.model.generate('outline', {'profile': copy.deepcopy(frozen),
                'change_request': change_request, 'allowed_external_topic_ids': list(TOPICS),
                'limits': {'capabilities': 8, 'gaps': 8, 'external_topic_ids': 3},
                'instructions': 'Produce a concise outline, preferably three capabilities. '
                                'Never exceed the supplied array limits. Select at most THREE external_topic_ids.',
                'outline_contract': {'capabilities': [{'skill_id':'string', 'purpose':'string',
                    'outcomes':['string'], 'practice':'string', 'completion_criteria':['string']}],
                    'gaps':['string'], 'external_topic_ids':['allowed topic ID']}},
                max_tokens=DEFAULTS.outline_max_tokens, temperature=DEFAULTS.temperature)
            outline = _outline(proposed)
        except Exception:
            raise PlanningError('Unable to produce a valid outline') from None

        stage('retrieval')
        try:
            internal = copy.deepcopy(self.internal_retriever.retrieve(copy.deepcopy(frozen), gaps=copy.deepcopy(outline['gaps'])))
        except Exception:
            raise PlanningError('Internal evidence unavailable') from None
        stage('external_search')
        if self.external_factory is None:
            external = _empty_external('External search is unavailable')
        elif not outline['external_topic_ids']:
            external = _empty_external('No approved external search topic identified')
        else:
            try:
                provider = self.external_factory()
                external = copy.deepcopy(provider.search(copy.deepcopy(outline['external_topic_ids']), language=_language(frozen)))
            except Exception:
                external = _empty_external('External search is unavailable')
        inputs = {'profile': copy.deepcopy(frozen), 'outline': copy.deepcopy(outline),
                  'internal': copy.deepcopy(internal), 'external': copy.deepcopy(external),
                  'plan_id': plan_id, 'revision': revision, 'change_request': change_request,
                  'schema': copy.deepcopy(_DRAFT_SCHEMA),
                  'draft_instructions': 'Output the supplied draft schema. Resources contain resource_id and reason ONLY. '
                      'Do NOT output evidence, plan_id, revision, profile_version or goal; code binds these '
                      'from the approved snapshot and attaches authoritative entities.'}
        approved = [a for a in frozen['assumptions'] if a['assumption_id'] in frozen['confirmed_assumption_ids']]
        inputs['validation_rules'] = {
            'allowed_assumptions': [a['description'] for a in approved],
            'allowed_equivalent_course_ids': [cid for a in approved for cid in a['course_ids']],
            'instructions': 'assumptions must contain ONLY exact allowed_assumptions strings, otherwise use []. '
                'Unconfirmed profile assumptions and work experience NEVER waive prerequisites. '
                'Include every prerequisite resource recursively unless its ID is explicitly allowed as equivalent. '
                'Use the exact supplied resource and evidence fields and IDs; do not invent or paraphrase them. '
                'Order prerequisite courses before dependent courses. Prefer a small relevant closed subset of '
                'courses and concise phases, not every search result. Expose remaining coverage gaps. '
                'Keep the JSON concise enough for the token cap. Code will recompute time totals and fit.'}

        def generate(task, cap, data):
            return self.model.generate(task, copy.deepcopy(data), max_tokens=cap, temperature=DEFAULTS.temperature)

        stage('generation')
        invalid = False
        candidate = None
        try:
            candidate = generate('career-plan', DEFAULTS.final_max_tokens, inputs)
        except ModelError as error:
            if isinstance(error.__cause__, json.JSONDecodeError):
                invalid = True
            else:
                raise PlanningError('Plan generation unavailable') from None
        except Exception:
            raise PlanningError('Plan generation unavailable') from None
        stage('validation')
        if not invalid:
            try:
                candidate = _materialize(candidate, internal, external, profile=frozen, plan_id=plan_id, revision=revision)
                candidate = _close_selected_dependencies(candidate, frozen, internal)
                plan = validate_plan(copy.deepcopy(candidate), copy.deepcopy(frozen), copy.deepcopy(internal),
                                     copy.deepcopy(external), plan_id=plan_id, revision=revision)
            except (PlanValidationError, ContractError):
                invalid = True
            except Exception:
                raise PlanningError('Plan validation unavailable') from None
        if invalid:
            try:
                repaired = generate('career-plan-repair', DEFAULTS.repair_max_tokens,
                                    {**inputs, 'invalid_candidate': copy.deepcopy(candidate)})
                repaired = _materialize(repaired, internal, external, profile=frozen, plan_id=plan_id, revision=revision)
                repaired = _close_selected_dependencies(repaired, frozen, internal)
                plan = validate_plan(copy.deepcopy(repaired), copy.deepcopy(frozen), copy.deepcopy(internal),
                                     copy.deepcopy(external), plan_id=plan_id, revision=revision)
            except Exception:
                raise PlanningError('Plan validation failed after repair') from None
        usage = getattr(self.model, 'usage', None)
        usage = copy.deepcopy(usage) if isinstance(usage, list) else []
        return {'plan': plan, 'trace': {'outline': copy.deepcopy(outline), 'internal': internal,
                                      'external': external, 'model_usage': usage}}
