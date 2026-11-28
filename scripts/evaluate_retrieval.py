"""Compare saved retrieval ranks at equal k; default fixtures are synthetic, not measurements."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / 'tests/fixtures/retrieval/ranking-cases.json'


def legacy_prompt(current_role, goal):
    return f"""You are an expert career coach. Create a personalized career development plan.

Current Role: {current_role}
Career Goal: {goal}

Provide a comprehensive career development plan that includes:
1. Recommended internal training courses (from the knowledge base)
2. Key skills to develop
3. Suggested timeline (3-6 months)
4. Additional certifications or learning resources

Be specific and actionable."""


def metrics(cases, k):
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 5:
        raise ValueError('Equal-k comparison against the legacy Top-5 requires k between 1 and 5')
    observations = []
    for case in cases:
        relevant = set(case['relevant'])
        row = {'id': case['id'], 'language': case['language'], 'goal': case['goal'], 'relevant': sorted(relevant),
               'legacy_prompt': legacy_prompt(case['current_role'], case['goal'])}
        for side in ('legacy', 'semantic'):
            ranks = case[side][:k]
            # Duplicate IDs do not increase recall or create multiple reciprocal ranks.
            hits = set(ranks) & relevant
            first = next((i for i, cid in enumerate(ranks, 1) if cid in relevant), None)
            row[side] = {'ranked_ids': ranks, 'recall': len(hits) / len(relevant) if relevant else None,
                         'reciprocal_rank': 1 / first if first else (0.0 if relevant else None)}
        observations.append(row)
    aggregates = {}
    for side in ('legacy', 'semantic'):
        measured = [row[side] for row in observations if row[side]['recall'] is not None]
        aggregates[side] = {'recall_at_k': sum(v['recall'] for v in measured) / len(measured) if measured else None,
                            'mrr_at_k': sum(v['reciprocal_rank'] for v in measured) / len(measured) if measured else None}
    return {'k': k, 'cases': observations, 'aggregate': aggregates,
            'legacy_settings': {'operation': 'RetrieveAndGenerate', 'numberOfResults': 5,
                'overrideSearchType': None, 'filter': None, 'maxTokens': 800},
            'semantic_settings': {'operation': 'Retrieve', 'numberOfResults': 15,
                'overrideSearchType': 'SEMANTIC', 'filter': {'equals': {'key': 'record_type', 'value': 'course'}}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--k', type=int, default=5)
    parser.add_argument('--live', action='store_true', help='Reserved for separately authorized live experiments')
    args = parser.parse_args()
    if args.live:
        parser.error('Live execution is not implemented; supply saved evidence with --input')
    data = json.loads(args.input.read_text(encoding='utf-8'))
    result = metrics(data['cases'], args.k)
    result['evidence_kind'] = data['evidence_kind']
    result['catalog'] = data.get('catalog')
    result['model'] = data.get('model')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
