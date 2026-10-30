"""SIS PR checks: trusted base scripts verify an exported disposable merge checkout."""
import argparse
import json
import tempfile
from pathlib import Path
from sandbox import Sandbox, CheckFailure, CheckTimeout, IntegrityFailure, export
from font_fixtures import font_fixture
from policy import STAGES, backend_verification


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = {'version': 2, 'status': 'blocked', 'stages': {},
              'limits': ['Synthetic records and credentials; production integrations and delivery are unverified.',
                         'Legacy password-only admin suites remain skipped; the separate real MFA probe is required.']}
    sandbox = None
    try:
        with tempfile.TemporaryDirectory(prefix='sis-pr-') as temporary:
            root = Path(temporary)
            source = root/'source'
            source.mkdir()
            report['tested_sha'] = export(args.repository, source)
            fixtures = root/'fixtures'
            report['font_fixtures'] = font_fixture(fixtures)
            sandbox = Sandbox(args.image, fixtures, Path(__file__).resolve().parent)
            print(json.dumps({'sandbox_stage': 'install', 'status': 'running'}), flush=True)
            sandbox.install(source, True)
            report['stages']['install'] = 'passed'
            print(json.dumps({'sandbox_stage': 'install', 'status': 'passed'}), flush=True)
            sandbox.checks(source, report['stages'])
            report['backend'] = sandbox.backend_evidence
            backend_verification(report['backend'])
            if report['stages'] != {s: 'passed' for s in STAGES}:
                raise ValueError('Incomplete checks')
            report['status'] = 'verified'
    except Exception as exc:
        report['failure_kind'] = type(exc).__name__
        if isinstance(exc, (CheckFailure, CheckTimeout, IntegrityFailure)):
            report['diagnostics'] = exc.diagnostics()
    finally:
        if sandbox is not None:report['backend'] = sandbox.backend_evidence
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'stages': report['stages']}))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
