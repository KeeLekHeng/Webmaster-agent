"""GitHub-hosted controller; website code only executes in isolated containers."""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from guardian.maintenance.policy import FILES, SECTIONS, STAGES, changes, declared, digest, manifest, security_gate, select, version
from guardian.maintenance.registry import metadata
from guardian.maintenance.fixtures import font_fixture
from guardian.maintenance.sandbox import Sandbox, CheckFailure, command, export
from guardian.maintenance import repairs

MAX_FILE = 4 * 1024 * 1024

def run(repository, output, image, *, sandbox_factory=Sandbox, registry=metadata, fixtures=font_fixture,
        repair_model=None, planner=repairs.propose, replayer=repairs.replay):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': 1, 'status': 'blocked', 'started_at': datetime.now(timezone.utc).isoformat(),
              'phase': 'export', 'baseline': {}, 'candidate': {}, 'updates': [],
              'image_id': image, 'security_not_worsened': False,
              'coverage': ['synthetic-data', 'mock-auth', 'mock-email', 'cached-google-font', 'no-production-access'],
              'limits': ['Tests are evidence for covered behavior, not a guarantee of all live integrations.',
                         'Nonsecurity releases require seven days of age; 0.x minor changes require manual review.',
                         'Package scripts/hooks are disabled during install; blocked native builds require human review.']}
    try:
        with tempfile.TemporaryDirectory(prefix='guardian-maintenance-') as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            report['base_sha'] = export(repository, source)
            original = {name: (source / name).read_bytes() for name in FILES}
            current = manifest(original['package.json'])
            if current['packageManager'] != 'pnpm@10.18.2':
                raise ValueError('Pinned package manager differs from sandbox')
            fixture_path = root / 'fixtures'
            report['phase'] = 'prepare-font-fixture'
            report['font_fixtures'] = fixtures(fixture_path)
            sandbox = sandbox_factory(image, fixture_path, Path(__file__).resolve().parents[3] / 'maintenance')
            baseline, candidate = root / 'baseline', root / 'candidate'
            shutil.copytree(source, baseline)
            shutil.copytree(source, candidate)
            report['phase'] = 'baseline-install'
            sandbox.install(baseline, True)
            report['baseline']['install'] = 'passed'
            report['phase'] = 'baseline-audit-inventory'
            before = sandbox.audit(baseline)
            installed = sandbox.inventory(baseline, current)
            report['resolved_before'] = installed
            report['advisories_before'] = before
            # Analyze declared stable bounds; frozen baseline and dependency inventories
            # remain distinct from release availability.
            urgent = {a['package'] for a in before}
            report['phase'] = 'select-registry-updates'
            report['releases'] = []
            for section in SECTIONS:
                for name, specification in current.get(section, {}).items():
                    info = registry(name)
                    target = select(specification, info, name in urgent, installed=installed[name])
                    report['releases'].append({'package': name, 'section': section, 'declared': specification,
                                               'installed': installed[name], 'eligible': target,
                                               'latest': info.get('dist-tags', {}).get('latest', '')})
                    current[section][name] = target
            proposed = (json.dumps(current, indent=2) + '\n').encode()
            report['updates'] = changes(original['package.json'], proposed)
            report['phase'] = 'baseline-checks'
            sandbox.checks(baseline, report['baseline'])
            if not report['updates']:
                report['status'] = 'no-compatible-updates'
                report['phase'] = 'complete'
                return report
            (candidate / 'package.json').write_bytes(proposed)
            report['phase'] = 'candidate-install'
            sandbox.install(candidate, False)
            # A second frozen install proves the generated manifest/lock agree.
            sandbox.install(candidate, True)
            report['candidate']['install'] = 'passed'
            report['phase'] = 'candidate-audit-inventory'
            after = sandbox.audit(candidate)
            resolved_after = sandbox.inventory(candidate, current)
            report['resolved_after'] = resolved_after
            if any(version(resolved_after[u['package']]) != declared(u['after'])[1] for u in report['updates']):
                raise ValueError('Resolved candidate differs from selected exact upgrade')
            report['advisories_after'] = after
            report['security_not_worsened'] = security_gate(before, after)
            if not report['security_not_worsened']:
                raise ValueError('Candidate introduces or worsens a known advisory')
            if any((candidate / name).is_symlink() for name in FILES):
                raise ValueError('Dependency artifact became a symlink')
            tested = {name: (candidate / name).read_bytes() for name in FILES}
            if changes(original['package.json'], tested['package.json']) != report['updates']:
                raise ValueError('Package manager changed unapproved manifest fields')
            report['phase'] = 'candidate-checks'
            try:
                sandbox.checks(candidate, report['candidate'])
            except CheckFailure as exc:
                if not repair_model or exc.stage != 'typecheck':
                    raise
                report['phase'] = 'candidate-compatibility-repair'
                problems = repairs.diagnostics(exc.output)
                plan = planner(source, problems, report['updates'], repair_model)
                plan = repairs.validate(plan, report['updates'], problems)
                source_originals = {e.path: (source/e.path).read_bytes() for e in plan.edits}
                repaired = replayer(plan, source_originals, report['updates'])
                # Discard everything touched by the failed tests/install before retrying.
                shutil.rmtree(candidate)
                shutil.copytree(source, candidate)
                for name, data in {**tested, **repaired}.items():
                    (candidate/name).write_bytes(data)
                report['candidate'] = {}
                sandbox.install(candidate, True)
                report['candidate']['install'] = 'passed'
                after = sandbox.audit(candidate)
                if (sandbox.inventory(candidate, current) != resolved_after or not security_gate(before, after)):
                    raise ValueError('Repair retry changed dependency/security evidence')
                report['advisories_after'] = after
                report['repair_plan'] = plan.model_dump()
                report['repair_changed_lines'] = repairs.diff_budget(source_originals, repaired)
                original.update(source_originals)
                tested.update(repaired)
                report['phase'] = 'repaired-candidate-checks'
                sandbox.checks(candidate, report['candidate'])
            if any((candidate / name).read_bytes() != data for name, data in tested.items()):
                raise ValueError('Tests changed dependency artifacts')
            report['files'] = {}
            for name, data in tested.items():
                if not data or len(data) > MAX_FILE or b'\0' in data:
                    raise ValueError('Invalid dependency artifact')
                (output / name).parent.mkdir(parents=True, exist_ok=True)
                (output / name).write_bytes(data)
                report['files'][name] = {'before_sha256': digest(original[name]), 'after_sha256': digest(data)}
            report['status'] = 'verified'
            report['phase'] = 'complete'
    except Exception as exc:
        # Do not publish arbitrary registry/package/test output or credentials.
        report['status'] = 'blocked'
        report['failure_kind'] = type(exc).__name__
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    model = (os.getenv('GUARDIAN_MAINTENANCE_MODEL') or 'claude-haiku-4-5') if os.getenv('GUARDIAN_COMPAT_REPAIRS_ENABLED') == 'true' else None
    report = run(args.repository, args.output, args.image, repair_model=model)
    print(json.dumps({'status': report['status'], 'updates': len(report['updates']), 'failure_kind': report.get('failure_kind')}))
    return 0 if report['status'] in {'verified', 'no-compatible-updates'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
