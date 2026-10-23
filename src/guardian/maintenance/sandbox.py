"""Credential-free Docker verification; usable as a vendored standalone module."""
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

if __package__:
    from .policy import STAGES, SECTIONS, audit, digest, version
else:
    from policy import STAGES, SECTIONS, audit, digest, version

class CheckFailure(ValueError):
    """Private bounded diagnostics; never include raw output in str/reports."""
    def __init__(self, output, stage=None):
        super().__init__('Verification command failed; raw output withheld')
        self.output, self.stage = output, stage

    def diagnostics(self):
        """Fixed labels only; no raw compiler/source/environment text is persisted."""
        text = self.output.decode('utf-8', errors='replace').lower()
        patterns = {
            'permission-denied': r'permission denied|eacces|operation not permitted|eperm',
            'memory-or-process-limit': r'out of memory|heap limit|eagain|resource temporarily unavailable|sigkill|killed',
            'missing-module': r'module not found|cannot find module|cannot resolve|can.t resolve',
            'font-error': r'font.*(?:error|failed|unable)|(?:error|failed|unable).*font|next/font',
            'network-error': r'enotfound|econnrefused|network is unreachable|failed to fetch|error while requesting resource',
            'turbopack-error': r'turbopack.*(?:error|failed)|turbopackinternalerror',
            'typescript-error': r'type error|error ts\d+',
            'prerender-error': r'prerender|error occurred prerendering|failed to collect page data',
            'missing-test-data': r'missing.*(?:supabase|environment)|supabase.*required',
            'missing-file': r'enoent|no such file or directory',
            'invalid-font-response': r'mocked.*response|missing mocked response|font.*response',
        }
        return {'stage': self.stage, 'signals': [label for label, pattern in patterns.items() if re.search(pattern, text)]}

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
            if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > 8 * 1024 * 1024:
                raise ValueError('Maintenance command failed; raw output withheld')
            output.seek(0)
            if child.returncode not in allowed:
                errors.seek(0)
                raise CheckFailure(output.read() + b'\n' + errors.read())
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
        try:
            for stage in STAGES[1:]:
                try:
                    self.run(workspace, ['bash', '/trusted/check.sh', stage], timeout=1200)
                except CheckFailure as exc:
                    exc.stage = stage
                    raise
                result[stage] = 'passed'
        finally:
            if snapshot() != before:
                raise ValueError('Verification changed website source; publication blocked')


