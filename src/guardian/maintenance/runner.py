"""GitHub-hosted controller. Website code only executes inside Docker, never here."""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone

from guardian.maintenance.policy import FILES, SECTIONS, STAGES, audit, changes, declared, digest, manifest, security_gate, select, version
from guardian.maintenance.registry import metadata
from guardian.maintenance.fixtures import font_fixture

MAX_FILE = 4 * 1024 * 1024


def command(args, cwd=None, timeout=180, allowed=(0,)):
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(args, cwd=cwd, stdout=output, stderr=errors, shell=False)
        deadline = time.monotonic() + timeout
        try:
            while child.poll() is None:
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired('maintenance command', timeout)
                if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > 8 * 1024 * 1024:
                    raise ValueError('Maintenance output budget exceeded')
                time.sleep(.05)
            if child.returncode not in allowed or os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > 8 * 1024 * 1024:
                raise ValueError('Maintenance command failed; raw output withheld')
            output.seek(0)
            return output.read()
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()


def export(repository, destination):
    """Export committed regular files only; no worktree .env/git credentials/hooks."""
    base = command(['git', '-C', str(repository), 'rev-parse', 'HEAD']).decode().strip()
    if not re.fullmatch(r'[a-f0-9]{40}', base):
        raise ValueError('Invalid base revision')
    with tempfile.TemporaryFile() as temporary:
        subprocess.run(['git', '-C', str(repository), 'archive', '--format=zip', base], stdout=temporary,
                       stderr=subprocess.DEVNULL, timeout=60, check=True, shell=False)
        temporary.seek(0)
        with zipfile.ZipFile(temporary) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 512 * 1024 * 1024:
                raise ValueError('Website export exceeds budget')
            for entry in entries:
                parts = entry.filename.split('/')
                if entry.is_dir():
                    continue
                if ('..' in parts or entry.filename.startswith('/') or '\\' in entry.filename or
                        stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('Unsafe export path')
                if any(p.startswith('.env') or p in {'.git', '.github', '.npmrc', '.pnpmfile.cjs', 'pnpmfile.cjs', 'node_modules'} for p in parts):
                    continue
                path = destination / entry.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(entry))
    if (destination / 'pnpm-workspace.yaml').exists():
        raise ValueError('Workspace/hook policy requires separate review')
    return base


class Sandbox:
    def __init__(self, image, fixtures, trusted):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('Use a locally built image ID, not a mutable name')
        self.image, self.fixtures, self.trusted = image, Path(fixtures).resolve(), Path(trusted).resolve()

    def run(self, workspace, argv, *, network=False, allowed=(0,), timeout=900):
        # No inherited environment, token, home, Docker socket, host PID or ports.
        name = 'guardian-' + uuid.uuid4().hex
        args = ['docker', 'run', '--name', name, '--rm', '--init', '--network', 'bridge' if network else 'none',
                '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--pids-limit=256', '--memory=4g', '--memory-swap=4g', '--cpus=2', '--read-only',
                '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777,size=1g', '--shm-size=256m',
                '--mount', f'type=bind,src={Path(workspace).resolve()},dst=/work',
                '--mount', f'type=bind,src={self.fixtures},dst=/fixtures,readonly',
                '--mount', f'type=bind,src={self.trusted},dst=/trusted,readonly', '-w', '/work']
        environment = {'CI': 'true', 'HOME': '/tmp', 'NEXT_TELEMETRY_DISABLED': '1',
                       'PLAYWRIGHT_BROWSERS_PATH': '/ms-playwright', 'E2E_TEST_DATA': '1',
                       'NEXT_PUBLIC_SUPABASE_URL': 'http://127.0.0.1:54321',
                       'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY': 'synthetic-public-key',
                       'NEXT_PUBLIC_SITE_URL': 'https://estateplanning.com.my',
                       'NEXT_FONT_GOOGLE_MOCKED_RESPONSES': '/fixtures/fonts.cjs',
                       'npm_config_ignore_pnpmfile': 'true', 'npm_config_registry': 'https://registry.npmjs.org'}
        for key, value in environment.items():
            args += ['-e', key + '=' + value]
        args += [self.image, *argv]
        try:
            return command(args, timeout=timeout, allowed=allowed)
        finally:
            subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=30, shell=False)

    def install(self, workspace, frozen):
        return self.run(workspace, ['pnpm', 'install', '--ignore-scripts', '--ignore-pnpmfile',
                                    '--strict-peer-dependencies',
                                    '--frozen-lockfile' if frozen else '--no-frozen-lockfile'], network=True)

    def audit(self, workspace):
        return audit(json.loads(self.run(workspace, ['pnpm', 'audit', '--json'], network=True, allowed=(0, 1))))

    def inventory(self, workspace, package):
        rows = json.loads(self.run(workspace, ['pnpm', 'list', '--json', '--depth', '0']))
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError('Resolved inventory unavailable')
        resolved = {}
        for section in SECTIONS:
            for name in package.get(section, {}):
                value = rows[0].get(section, {}).get(name, {}).get('version')
                version(value)
                resolved[name] = value
        return resolved

    def checks(self, workspace, result):
        def snapshot():
            result = {}
            for p in workspace.rglob('*'):
                if any(part in {'node_modules', '.next', 'test-results', 'playwright-report'} for part in p.relative_to(workspace).parts):
                    continue
                if p.is_symlink():
                    raise ValueError('Verification introduced a source symlink')
                if p.is_file() and p.name not in {'next-env.d.ts', 'tsconfig.tsbuildinfo'}:
                    result[str(p.relative_to(workspace))] = digest(p.read_bytes())
            return result
        before = snapshot()
        for stage in STAGES[1:]:
            self.run(workspace, ['bash', '/trusted/check.sh', stage], timeout=1200)
            result[stage] = 'passed'
        if snapshot() != before:
            raise ValueError('Verification changed website source; publication blocked')


def run(repository, output, image, *, sandbox_factory=Sandbox, registry=metadata, fixtures=font_fixture):
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
            sandbox.checks(candidate, report['candidate'])
            if any((candidate / name).read_bytes() != data for name, data in tested.items()):
                raise ValueError('Tests changed dependency artifacts')
            report['files'] = {}
            for name, data in tested.items():
                if not data or len(data) > MAX_FILE or b'\0' in data:
                    raise ValueError('Invalid dependency artifact')
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
    report = run(args.repository, args.output, args.image)
    print(json.dumps({'status': report['status'], 'updates': len(report['updates']), 'failure_kind': report.get('failure_kind')}))
    return 0 if report['status'] in {'verified', 'no-compatible-updates'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
