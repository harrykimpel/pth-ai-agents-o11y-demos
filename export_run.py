"""Extract a downloaded Demo 2 bundle for the independent release gate."""
import argparse
import json
from pathlib import Path
from quality import parse_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--out', type=Path, default=Path('reports/from-web'))
    args = parser.parse_args()
    try:
        bundle = parse_candidate(args.bundle.read_text(encoding='utf-8'))
        if not isinstance(bundle.get('candidate'), dict) or not isinstance(bundle.get('contract'), dict):
            raise ValueError('The bundle needs a parsed candidate and its recorded contract.')
        args.out.mkdir(parents=True, exist_ok=True)
        for key in ('candidate', 'contract'):
            (args.out / f'{key}.json').write_text(json.dumps(bundle[key], indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError) as error:
        parser.exit(2, f'ERROR: {error}\n')
    print(f'Wrote {args.out / "candidate.json"} and {args.out / "contract.json"}')


if __name__ == '__main__':
    main()
