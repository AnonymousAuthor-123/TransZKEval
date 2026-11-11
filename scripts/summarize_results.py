"""Summarize saved functional outcomes without executing models or circuits."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def summarize(rows, tasks):
    counts = {int(r['id']): len(r['inputs']) for r in tasks}
    keys = {(int(r['id']), r['lang']) for r in rows}
    if len(keys) != len(rows):
        raise ValueError('Duplicate task-language key')
    n = len(rows)
    tests = sum(counts[int(r['id'])] for r in rows)
    compiled = sum(bool(r['compile_success']) if 'compile_success' in r else
                   r['status'] in {'SUCCESS', 'LOGIC_FAIL', 'SETUP_FAIL'} for r in rows)
    passed = sum(sum(c['status'] == 'PASS' for c in r.get('test_cases', [])) for r in rows)
    correct = sum(r['status'] == 'SUCCESS' for r in rows)
    return {'programs': n, 'tests': tests, 'compiled': compiled,
            'passed_tests': passed, 'correct': correct,
            'CSR': 100 * compiled / n, 'PR': 100 * passed / tests, 'CA': 100 * correct / n}

def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8-sig').splitlines() if s.strip()]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset/source_ipls.jsonl')
    args = parser.parse_args()
    print(json.dumps(summarize(read_jsonl(args.results), read_jsonl(args.dataset)), indent=2))
