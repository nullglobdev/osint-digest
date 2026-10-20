"""Offline exact (type, value) candidate scoring; no maliciousness inference."""
import json
from pathlib import Path

from osint_digest.core.collector import extract_iocs

CORPUS = Path(__file__).parent / 'fixtures' / 'extraction' / 'iocs.json'


def benchmark():
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    totals = {'tp': 0, 'fp': 0, 'fn': 0}
    by_type, cases = {}, []
    for case in corpus['cases']:
        actual, capped = extract_iocs(case['text'])
        predicted = {(x['type'], x['value']) for x in actual}
        expected = {tuple(x) for x in case['expected']}
        groups = {'tp': predicted & expected, 'fp': predicted - expected,
                  'fn': expected - predicted}
        for metric, values in groups.items():
            totals[metric] += len(values)
            for kind, _ in values:
                by_type.setdefault(kind, {'tp': 0, 'fp': 0, 'fn': 0})[metric] += 1
        cases.append({'id': case['id'], 'capped': capped,
                      **{k: sorted(v) for k, v in groups.items()}})
    for counts in [totals, *by_type.values()]:
        counts['precision'] = (counts['tp'] / (counts['tp'] + counts['fp'])
                               if counts['tp'] + counts['fp'] else None)
        counts['recall'] = (counts['tp'] / (counts['tp'] + counts['fn'])
                            if counts['tp'] + counts['fn'] else None)
    return {'corpus_version': corpus['version'], 'case_count': len(cases),
            'micro': totals, 'by_type': by_type, 'cases': cases}


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2))
