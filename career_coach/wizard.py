"""Deterministic intake policy; the model proposes facts, never controls routing."""
import copy
import json
import math
from pathlib import Path
import re

from .config import DEFAULTS
from .contracts import ContractError, validate
from .errors import APIError

_DEFINITIONS = Path(__file__).parent / 'definitions'
QUESTIONS = json.loads((_DEFINITIONS / 'questions.json').read_text(encoding='utf-8'))
SKILLS = json.loads((_DEFINITIONS / 'skills.json').read_text(encoding='utf-8'))
FIELDS = QUESTIONS['fields']
BY_ID = {question['id']: question for question in QUESTIONS['questions']}


def _error(status, code, message):
    raise APIError(status, code, message)


def _valid_value(key, value):
    field = FIELDS.get(key)
    if field is None:
        return False
    if value is None:
        return True
    if field['type'] == 'text':
        return isinstance(value, str) and 0 < len(value.strip()) <= 2000
    if field['type'] == 'choice':
        return value in field['values'] if isinstance(value, str) else False
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and field['minimum'] <= value <= field['maximum'])


def _facts(profile):
    return {fact['key']: fact for fact in profile['facts']}


def _question(definition):
    return {'question_id': definition['id'], 'text': definition['fallback'],
            'answer_type': definition['type'], 'options': definition['options'],
            'allow_unknown': True, 'optional': False}


def _issue(state, definition):
    counters = state['counters']
    if definition['id'] == 'direction_followup':
        counters['followups'] += 1
        counters['per_axis'][definition['axis']] = counters['per_axis'].get(definition['axis'], 0) + 1
    else:
        counters['core'] += 1
    state.update(stage=definition['stage'], status='awaiting_answer', current_question=_question(definition))
    state.pop('review', None)


def initial_state():
    state = {'stage': 'direction', 'status': 'awaiting_answer', 'current_question': None,
             'profile': {'schema_version': '1.0', 'profile_version': 1, 'facts': [],
                         'assumptions': [], 'confirmed_assumption_ids': [],
                         'approved_profile_version': None, 'unresolved': []},
             'counters': {'core': 0, 'followups': 0, 'per_axis': {}, 'definitions_version': QUESTIONS['schema_version']}}
    _issue(state, BY_ID['current_work'])
    return state


def _technical(facts):
    # Direction and outcome must both be user-reported; inference cannot select specialization.
    goal, outcome, direction = (facts.get(k) for k in ('goal', 'outcome', 'direction'))
    if not all(f and f['basis'] == 'user_reported' and f['value'] for f in (goal, outcome, direction)):
        return False
    combined = (str(goal['value']) + ' ' + str(outcome['value'])).lower()
    return direction['value'] == 'applications' and bool(re.search(r'\b(?:rag|ai|models?|documents?|software|apis?)\b', combined))


def _review_view(profile):
    facts = _facts(profile)
    summary = '; '.join(f"{key}: {fact['value'] if fact['value'] is not None else 'unknown'} ({fact['basis']})"
                        for key, fact in facts.items())
    hours, weeks = facts.get('weekly_hours'), facts.get('deadline_weeks')
    if hours and weeks and hours['value'] is not None and weeks['value'] is not None:
        summary += f"; available capacity: {hours['value'] * weeks['value']} hours"
    return {'summary': summary or 'No information provided',
            'assumptions': [a['assumption_id'] + ': ' + a['description'] for a in profile['assumptions']],
            'unresolved': list(profile['unresolved'])}


def _select(state):
    profile, counters = state['profile'], state['counters']
    facts = _facts(profile)
    followup = BY_ID['direction_followup']
    direction = facts.get('direction')
    if (facts.get('goal') and not (direction and direction['basis'] == 'user_reported' and direction['value']) and
        not (direction and direction['source_question_id'] == 'direction_followup') and
        counters['followups'] < DEFAULTS.max_followups and
        counters['per_axis'].get('direction', 0) < DEFAULTS.max_followups_per_axis):
        if 'direction' not in profile['unresolved']:
            profile['unresolved'].append('direction')
        _issue(state, followup)
        return
    technical = _technical(facts)
    for definition in QUESTIONS['questions']:
        existing = facts.get(definition['slot'])
        if definition['id'] == 'direction_followup' or (existing and
                (existing['basis'] == 'user_reported' or existing['source_question_id'] == definition['id'])):
            continue
        if any(dependency not in facts for dependency in definition['dependencies']):
            continue
        if definition['eligibility'] == 'technical' and not technical:
            continue
        if definition['eligibility'] == 'generic' and technical:
            continue
        if counters['core'] < DEFAULTS.max_core_questions:
            _issue(state, definition)
            return
        break
    practice = facts.get('practice', {})
    practice_text = str(practice.get('value') or '').lower()
    if (technical and practice.get('basis') == 'user_reported' and
        re.search(r'\bapis?\b', practice_text) and re.search(r'\bsql\b', practice_text) and
        not re.search(r"\b(?:no|never|not|without|lack|limited)\b|\b(?:haven't|don't|didn't)\b", practice_text)):
        profile['assumptions'] = [{'assumption_id': 'backend-foundation-equivalence',
            'description': 'My self-reported API and SQL experience may substitute for the listed backend foundation courses; this is not a certification.',
            'course_ids': ['BKE-201', 'BKE-101', 'SDE-101']}]
    state.update(stage='review', status='review_required', current_question=None, review=_review_view(profile))


def answer(state, request, model):
    try:
        validate('answer-request', request)
    except ContractError:
        _error(400, 'invalid_request', 'Invalid answer')
    question = state.get('current_question')
    if state.get('status') != 'awaiting_answer' or not question or question['question_id'] != request['question_id']:
        _error(409, 'invalid_question', 'Question is no longer current')
    if request['state_version'] != state['state_version']:
        _error(409, 'stale_version', 'Session version is stale')
    definition = BY_ID[question['question_id']]
    text = request['answer'].strip()
    unknown = text.lower() in {'not sure', 'unknown', 'unsure', 'i do not know', "i don't know"}
    if not text or (definition['type'] == 'single_choice' and not unknown and text.lower() not in definition['options']):
        _error(400, 'invalid_request', 'Invalid answer')
    if definition['type'] == 'number' and not unknown:
        try:
            number = float(text)
        except ValueError:
            _error(400, 'invalid_request', 'Invalid answer')
        if not _valid_value(definition['slot'], number):
            _error(400, 'invalid_request', 'Invalid answer')
    # All reviewed slots may be provided in a multi-slot answer; arbitrary fields are rejected.
    allowed_fields = {key: FIELDS[key] for key in definition['allowed_fields']}
    data = {'question': copy.deepcopy(question), 'answer': text, 'profile': copy.deepcopy(state['profile']),
            'allowed_fields': allowed_fields, 'definitions': {'question': definition, 'skills': SKILLS}}
    data['schema'] = json.loads((Path(__file__).parent / 'schemas' / 'answer-analysis.json').read_text(encoding='utf-8'))
    data['analysis_rules'] = {
        'fact_keys': list(allowed_fields),
        'source_question_id': question['question_id'],
        'instructions': 'Use only the listed fact_keys; do not create fields such as experience_years. '
                        'Extract only information in this answer. Do not fill absent slots. '
                        'Every source_question_id must equal the supplied source_question_id. '
                        'unresolved may contain only listed fact_keys. Return every required schema field.'}
    analysis = model.generate('answer-analysis', data, max_tokens=DEFAULTS.intake_max_tokens, temperature=DEFAULTS.temperature)
    try:
        validate('answer-analysis', analysis)
        seen = set()
        for fact in analysis['facts']:
            if (fact['key'] not in allowed_fields or fact['key'] in seen or fact['source_question_id'] != question['question_id'] or
                    not _valid_value(fact['key'], fact['value'])):
                raise ValueError()
            seen.add(fact['key'])
        if any(item not in FIELDS for item in analysis['unresolved']):
            raise ValueError()
    except (ContractError, ValueError, TypeError):
        _error(503, 'invalid_analysis', 'Answer analysis unavailable')
    result = copy.deepcopy(state)
    profile = result['profile']
    facts = _facts(profile)
    for fact in ([] if unknown else analysis['facts']):
        prior = facts.get(fact['key'])
        if prior and prior['basis'] == 'user_reported' and fact['basis'] == 'inferred':
            continue
        facts[fact['key']] = copy.deepcopy(fact)
    slot = definition['slot']
    if definition['type'] == 'single_choice':
        facts[slot] = {'key': slot, 'value': None if unknown else text.lower(),
                       'source_question_id': question['question_id'], 'basis': 'user_reported'}
    elif definition['type'] == 'number':
        facts[slot] = {'key': slot, 'value': None if unknown else number,
                       'source_question_id': question['question_id'], 'basis': 'user_reported'}
    elif slot not in facts or (facts[slot]['basis'] == 'inferred' and facts[slot]['source_question_id'] != question['question_id']):
        facts[slot] = {'key': slot, 'value': None, 'source_question_id': question['question_id'], 'basis': 'user_reported'}
    if unknown:
        facts[slot] = {'key': slot, 'value': None, 'source_question_id': question['question_id'], 'basis': 'user_reported'}
    unresolved = set(profile['unresolved']) | (set() if unknown else set(analysis['unresolved']))
    for fact in ([] if unknown else analysis['facts']):
        if fact['value'] is not None and (fact['key'] != 'direction' or fact['basis'] == 'user_reported'):
            unresolved.discard(fact['key'])
    if facts[slot]['value'] is None:
        unresolved.add(slot)
    else:
        unresolved.discard(slot)
    if question['question_id'] == 'goal' and text.lower().strip(' .!') in {'ai', 'move into ai', 'move to ai', 'work in ai'}:
        facts.pop('direction', None)
        unresolved.add('direction')
    profile.update(facts=list(facts.values()), unresolved=sorted(unresolved),
                   profile_version=profile['profile_version'] + 1, approved_profile_version=None,
                   confirmed_assumption_ids=[])
    result['state_version'] += 1
    _select(result)
    selected = result.get('current_question')
    if selected and analysis['suggested_followup_id'] == selected['question_id']:
        suggested = analysis['suggested_question_text']
        if suggested in BY_ID[selected['question_id']]['wording_variants']:
            selected['text'] = suggested
    validate('profile', profile)
    return result


def review(state, request):
    try:
        validate('review-request', request)
    except ContractError:
        _error(400, 'invalid_request', 'Invalid review')
    if request['state_version'] != state['state_version']:
        _error(409, 'stale_version', 'Session version is stale')
    corrections = request.get('corrections', [])
    if state.get('status') != 'review_required' and not (corrections and state.get('status') in {'ready_to_generate', 'planning', 'complete'}):
        _error(409, 'invalid_review', 'Review is not available')
    result = copy.deepcopy(state)
    profile = result['profile']
    if corrections:
        if request['confirmed_assumption_ids'] or len({c['key'] for c in corrections}) != len(corrections):
            _error(400, 'invalid_request', 'Invalid corrections')
        facts = _facts(profile)
        unresolved = set(profile['unresolved'])
        for correction in sorted(corrections, key=lambda c: (c['key'] != 'goal', c['key'] != 'direction')):
            key, value = correction['key'], correction['value']
            if not _valid_value(key, value):
                _error(400, 'invalid_request', 'Invalid correction')
            if key in {'goal', 'direction', 'outcome'}:
                dependents = ('practice', 'capability_two', 'capability_three')
                if key == 'goal':
                    dependents += ('outcome',)
                for dependent in dependents:
                    facts.pop(dependent, None)
                    unresolved.add(dependent)
                if key == 'goal':
                    facts.pop('direction', None)
                    unresolved.add('direction')
            facts[key] = {'key': key, 'value': value, 'source_question_id': 'review', 'basis': 'user_reported'}
            if value is None:
                unresolved.add(key)
            else:
                unresolved.discard(key)
        # Corrections invalidate model-derived facts and any dependent equivalence decisions.
        unresolved.update(key for key, fact in facts.items() if fact['basis'] == 'inferred')
        facts = {key: fact for key, fact in facts.items() if fact['basis'] != 'inferred'}
        profile.update(facts=list(facts.values()), unresolved=sorted(unresolved), assumptions=[],
                       confirmed_assumption_ids=[], approved_profile_version=None,
                       profile_version=profile['profile_version'] + 1)
        result.update(stage='review', status='review_required', current_question=None)
        result['review'] = _review_view(profile)
    else:
        allowed = {a['assumption_id'] for a in profile['assumptions']}
        selected = request['confirmed_assumption_ids']
        if len(set(selected)) != len(selected) or not set(selected) <= allowed:
            _error(400, 'invalid_request', 'Invalid assumption selection')
        facts = _facts(profile)
        if ('direction' in profile['unresolved'] or 'goal' in profile['unresolved'] or
                any(not facts.get(key) or facts[key]['basis'] != 'user_reported' or not facts[key]['value']
                    for key in ('goal', 'direction'))):
            _error(409, 'unresolved_goal', 'Choose a direction before approval')
        profile['confirmed_assumption_ids'] = list(selected)
        profile['approved_profile_version'] = profile['profile_version']
        result['status'] = 'ready_to_generate'
        result['review'] = _review_view(profile)
    result['state_version'] += 1
    validate('profile', profile)
    return result
