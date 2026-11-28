"""Safe exports for schema-validated career plans."""
import json
import re
from urllib.parse import quote, urlsplit

from .contracts import validate


def _md(value):
    value = str(value).replace('\r', ' ').replace('\n', ' ')
    value = ''.join(c for c in value if ord(c) >= 32)
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~>-])', r'\\\1', value)


def _url(value):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return None
        return quote(value, safe=':/?#[]@!$&*+,;=%~-._')
    except ValueError:
        return None


def export_plan(plan, fmt):
    validate('career-plan', plan)
    if fmt == 'json':
        return json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'application/json; charset=utf-8', 'career-plan.json'
    if fmt != 'markdown':
        raise ValueError('Invalid export format')
    lines = ['# Career plan', '', '**Goal:** ' + _md(plan['goal']),
             '**Plan:** ' + _md(plan['plan_id']), '**Revision:** ' + str(plan['revision']),
             '**Profile version:** ' + str(plan['profile_version']), '',
             '## Starting point', _md(plan['starting_point']), '', '## Assumptions']
    lines += ['- ' + _md(x) for x in plan['assumptions']] or ['- None recorded']
    for phase in plan['phases']:
        lines += ['', '## ' + _md(phase['title']), '**Phase ID:** ' + _md(phase['phase_id']),
                  '**Depends on:** ' + _md(', '.join(phase['depends_on']) or 'None'),
                  '**Skills:** ' + _md(', '.join(phase['skills'])), '**Outcomes:**']
        lines += ['- ' + _md(x) for x in phase['outcomes']]
        lines += ['**Practice:** ' + _md(phase['practice']['description']),
                  '**Practice hours:** ' + str(phase['practice']['estimated_hours']), '**Completion criteria:**']
        lines += ['- ' + _md(x) for x in phase['completion_criteria']]
        lines += ['**Resource IDs:** ' + _md(', '.join(phase['resource_ids']) or 'None')]
    lines += ['', '## Resources']
    for resource in plan['resources']:
        url = _url(resource['url'])
        title = '[' + _md(resource['title']) + '](' + url + ')' if url else _md(resource['title'])
        lines += ['- ' + title + ' — ' + _md(resource['reason']),
                  '  - ID: ' + _md(resource['resource_id']) + '; kind: ' + _md(resource['kind']) +
                  '; course ID: ' + _md(resource['course_id'] or 'none') +
                  '; hours: ' + _md(resource['duration_hours'] if resource['duration_hours'] is not None else 'unknown') +
                  '; prerequisites: ' + _md(resource['prerequisite_status']),
                  '  - Evidence: ' + _md(', '.join(resource['evidence_ids']))]
    lines += ['', '## Evidence']
    for ev in plan['evidence']:
        lines += ['- ' + _md(ev['evidence_id']) + ': ' + _md(ev['source']) + '; URI: ' + _md(ev['uri']) +
                  '; retrieved: ' + _md(ev['retrieved_at']) + '; fields: ' + _md(', '.join(ev['supported_fields'])) +
                  '; course ID: ' + _md(ev['course_id'] or 'none') +
                  '; catalog version: ' + _md(ev['catalog_version'] or 'unknown') +
                  '; source hash: ' + _md(ev['parsed_source_sha256'] or 'unknown')]
    budget = plan['time_budget']
    lines += ['', '## Time budget', '- Weekly hours: ' + _md(budget['weekly_hours'] if budget['weekly_hours'] is not None else 'unknown'),
              '- Target weeks: ' + _md(budget['target_weeks'] if budget['target_weeks'] is not None else 'unknown'),
              '- Known course hours: ' + _md(budget['known_course_hours']),
              '- Estimated practice hours: ' + _md(budget['estimated_practice_hours']),
              '- Unestimated resources: ' + _md(', '.join(budget['unestimated_resource_ids']) or 'None'),
              '- Fit status: ' + _md(budget['fit_status']), '', '## Coverage gaps']
    lines += ['- ' + _md(x) for x in plan['coverage_gaps']] or ['- None recorded']
    return '\n'.join(lines) + '\n', 'text/markdown; charset=utf-8', 'career-plan.md'
