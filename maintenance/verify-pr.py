"""SIS PR checks: trusted base scripts verify an exported disposable merge checkout."""
import argparse
import json
import tempfile
from pathlib import Path
from sandbox import Sandbox, export
from font_fixtures import font_fixture
from policy import STAGES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = {'status': 'blocked', 'stages': {}}
    try:
        with tempfile.TemporaryDirectory(prefix='sis-pr-') as temporary:
            root = Path(temporary)
            source = root/'source'
            source.mkdir()
            report['tested_sha'] = export(args.repository, source)
            fixtures = root/'fixtures'
            report['font_fixtures'] = font_fixture(fixtures)
            sandbox = Sandbox(args.image, fixtures, Path(__file__).resolve().parent)
            sandbox.install(source, True)
            report['stages']['install'] = 'passed'
            sandbox.checks(source, report['stages'])
            if report['stages'] != {s: 'passed' for s in STAGES}:
                raise ValueError('Incomplete checks')
            report['status'] = 'verified'
    except Exception as exc:
        report['failure_kind'] = type(exc).__name__
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'stages': report['stages']}))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
