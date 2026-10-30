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
            'browser-timeout': r'test timeout|timeout .*exceeded|timed out',
            'browser-launch-error': r'browser.*closed|browser.*launch|executable doesn.t exist|pthread_create',
            'test-assertion': r'expect\(|assertionerror|expect.*received',
            'assertion-url': r'tohaveurl',
            'assertion-visibility': r'tobevisible|tobehidden',
            'assertion-text': r'tohavetext|tocontaintext',
            'test-collection-error': r'did not expect test|more than one version of @playwright/test',
        }
        locations = sorted(set(re.findall(r'tests/(?:e2e|unit|integration)/[a-z0-9_/-]+\.(?:spec|test)\.(?:tsx?|mjs):\d+(?::\d+)?', text)))[:10]
        result = {'stage': self.stage, 'signals': [label for label, pattern in patterns.items() if re.search(pattern, text)],
                  'test_locations': locations}
        if hasattr(self, 'browser_summary'):
            result['browser_summary'] = self.browser_summary
        auth = re.search(r'guardian_real_auth_probe_failed:([a-z-]+)', text)
        if auth and auth[1] in {'start','anonymous-redirect','password-login','mfa-enrollment','mfa-management-access','logout'}:
            result['auth_probe_phase'] = auth[1]
        return result


class CheckTimeout(subprocess.TimeoutExpired):
    stage = None

    def diagnostics(self):
        return {**CheckFailure(self.output or b'', self.stage).diagnostics(), 'timed_out': True}


class IntegrityFailure(ValueError):
    def __init__(self, paths, stage):
        super().__init__('Verification changed website source; publication blocked')
        self.paths, self.stage = paths, stage

    def diagnostics(self):
        safe = [p for p in sorted(self.paths) if len(p)<200 and re.fullmatch(r'[A-Za-z0-9_./-]+',p)
                and not any(part.startswith('.env') for part in p.split('/'))]
        result = {'stage': self.stage, 'signals': ['source-integrity'], 'changed_paths': safe[:20], 'changed_count': len(self.paths)}
        if isinstance(self.__context__, (CheckFailure, CheckTimeout)):
            result['underlying'] = self.__context__.diagnostics()
        return result


class OutputBudgetFailure(CheckFailure):
    def diagnostics(self):
        result = super().diagnostics()
        result['signals'].append('output-budget-exceeded')
        return result


def browser_summary(workspace):
    """Extract only bounded counts/source locations and fixed error categories."""
    try:
        path = workspace/'test-results'/'e2e-report.json'
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>4*1024*1024:
            raise ValueError('Unsafe report')
        report = json.loads(path.read_bytes())
        stats = {k:v for k,v in report.get('stats',{}).items()
                 if k in {'expected','unexpected','flaky','skipped'} and type(v) is int and 0<=v<=100000}
        failures = []
        visited = 0
        def visit(suites, depth=0):
            nonlocal visited
            if depth>10: raise ValueError('Report nesting limit')
            for suite in suites:
                visited+=1
                if visited>10000: raise ValueError('Report suite limit')
                for spec in suite.get('specs',[]):
                    visited+=1
                    if visited>10000: raise ValueError('Report test limit')
                    for test in spec.get('tests',[])[:10]:
                        if test.get('status')!='unexpected': continue
                        file=spec.get('file','').removeprefix('/work/')
                        if '/' not in file: file='tests/e2e/'+file
                        if not re.fullmatch(r'tests/e2e/[A-Za-z0-9_/-]+\.spec\.tsx?',file): continue
                        line=spec.get('line')
                        if type(line) is not int or not 1<=line<=100000:continue
                        messages=[]
                        assertions=[]
                        matchers=set()
                        for result in test.get('results',[])[:5]:
                            for error in result.get('errors',[])[:5]:
                                value=error.get('message','')
                                if isinstance(value,str):
                                    messages.append(value[:10000])
                                    matchers.update(name for name in ('toBeFocused','toBeVisible','toHaveCount','toHaveAttribute','toHaveScreenshot','toHaveURL') if name in value[:10000])
                                location=error.get('location',{})
                                if isinstance(location,dict):
                                    source=location.get('file','')
                                    row=location.get('line')
                                    column=location.get('column')
                                    if isinstance(source,str):source=source.removeprefix('/work/')
                                    if isinstance(source,str) and re.fullmatch(r'tests/e2e/[A-Za-z0-9_/-]+\.spec\.tsx?',source) and type(row) is int and 1<=row<=100000 and type(column) is int and 1<=column<=100000:
                                        assertions.append(f'{source}:{row}:{column}')
                                stack=error.get('stack','')
                                if isinstance(stack,str):
                                    assertions.extend(re.findall(r'tests/e2e/[A-Za-z0-9_/-]+\.spec\.tsx?:\d+(?::\d+)?',stack[:20000]))
                        failure={'file':file,'line':line,'signals':CheckFailure('\n'.join(messages).encode()).diagnostics()['signals']}
                        if assertions:failure['assertion_locations']=sorted(set(assertions))[:5]
                        if matchers:failure['matchers']=sorted(matchers)
                        if test.get('projectName') in {'desktop-chromium','mobile-chromium','reduced-motion'}:
                            failure['project']=test['projectName']
                        if len(failures)<10:failures.append(failure)
                visit(suite.get('suites',[]),depth+1)
        visit(report.get('suites',[]))
        return {'counts':stats,'failures':failures}
    except Exception:
        return {'status':'unavailable'}

def command(args, cwd=None, timeout=180, allowed=(0,), env=None):
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        def bounded_tail():
            result = b''
            for stream in (output, errors):
                stream.seek(max(0, os.fstat(stream.fileno()).st_size-32768))
                result += stream.read(32768)
            return result
        child = subprocess.Popen(args, cwd=cwd, stdout=output, stderr=errors, shell=False, env=env)
        deadline = time.monotonic() + timeout
        try:
            while child.poll() is None:
                if time.monotonic() > deadline:
                    raise CheckTimeout('maintenance command', timeout)
                if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > 8 * 1024 * 1024:
                    raise OutputBudgetFailure(bounded_tail())
                time.sleep(.05)
            if os.fstat(output.fileno()).st_size + os.fstat(errors.fileno()).st_size > 8 * 1024 * 1024:
                raise OutputBudgetFailure(bounded_tail())
            output.seek(0)
            if child.returncode not in allowed:
                errors.seek(0)
                raise CheckFailure(output.read() + b'\n' + errors.read())
            return output.read()
        except CheckTimeout as exc:
            output.seek(0)
            errors.seek(0)
            raw = output.read(8 * 1024 * 1024)
            exc.output = raw + errors.read(8 * 1024 * 1024 - len(raw))
            raise
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
        self.backend = None
        self.backend_evidence = {}

    def run(self, workspace, argv, *, network=False, allowed=(0,), timeout=900):
        # No inherited environment, token, home, Docker socket, host PID or ports.
        name = 'guardian-' + uuid.uuid4().hex
        mode = 'bridge' if network else ('container:'+self.backend.gateway if self.backend else 'none')
        args = ['docker', 'run', '--name', name, '--rm', '--init', '--network', mode,
                '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--pids-limit=256', '--memory=3g', '--memory-swap=3g', '--cpus=2', '--read-only',
                '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777,size=1g', '--shm-size=256m',
                '--mount', f'type=bind,src={Path(workspace).resolve()},dst=/work',
                '--mount', f'type=bind,src={self.fixtures},dst=/fixtures,readonly',
                '--mount', f'type=bind,src={self.trusted},dst=/trusted,readonly', '-w', '/work']
        environment = {'CI': 'true', 'HOME': '/tmp', 'NEXT_TELEMETRY_DISABLED': '1',
                       'PLAYWRIGHT_BROWSERS_PATH': '/ms-playwright', 'E2E_TEST_DATA': '1',
                       'ADMIN_SESSION_SECRET': 'guardian-synthetic-session-key-not-for-production',
                       'NEXT_PUBLIC_SUPABASE_URL': 'http://127.0.0.1:54321',
                       'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY': 'synthetic-public-key',
                       'NEXT_PUBLIC_SITE_URL': 'https://estateplanning.com.my',
                       'NEXT_FONT_GOOGLE_MOCKED_RESPONSES': '/fixtures/fonts.cjs',
                       'npm_config_ignore_pnpmfile': 'true', 'npm_config_registry': 'https://registry.npmjs.org'}
        if self.backend and not network:
            environment.update(self.backend.environment)
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
        if __package__:
            from .backend import Backend
        else:
            from backend import Backend
        backend = Backend(self, Path(workspace))
        try:
            with backend:
                self.backend = backend
                self._checks(workspace, result)
        finally:
            self.backend = None
            self.backend_evidence = backend.evidence

    def _checks(self, workspace, result):
        def snapshot():
            result = {}
            for p in workspace.rglob('*'):
                if any(part in {'node_modules', '.next', 'test-results', 'playwright-report'} for part in p.relative_to(workspace).parts):
                    continue
                if p.is_symlink():
                    raise ValueError('Verification introduced a source symlink')
                if p.is_file() and p.name not in {'next-env.d.ts', 'tsconfig.tsbuildinfo'}:
                    result[p.relative_to(workspace).as_posix()] = digest(p.read_bytes())
            return result
        before = snapshot()
        try:
            for stage in STAGES[1:]:
                print(json.dumps({'sandbox_stage': stage, 'status': 'running'}), flush=True)
                try:
                    if stage == 'browser' and self.backend:
                        self.backend.evidence['phase']='mfa-browser'
                        self.run(workspace, ['node', '/trusted/real-backend.cjs'], timeout=180)
                        self.backend.evidence['mfa_browser'] = 'passed'
                        self.backend.evidence['phase']='browser-suite'
                    self.run(workspace, ['bash', '/trusted/check.sh', stage], timeout=1200)
                    if stage == 'browser' and self.backend:
                        summary = browser_summary(workspace)
                        if summary.get('counts',{}).get('expected',0)<1 or summary.get('counts',{}).get('unexpected',0)!=0:
                            raise ValueError('Browser execution coverage is missing or failed')
                        self.backend.evidence['browser_summary'] = summary
                except (CheckFailure, CheckTimeout) as exc:
                    exc.stage = stage
                    if stage == 'browser':
                        exc.browser_summary = browser_summary(workspace)
                    raise
                result[stage] = 'passed'
                print(json.dumps({'sandbox_stage': stage, 'status': 'passed'}), flush=True)
                after = snapshot()
                changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
                if changed:
                    raise IntegrityFailure(changed, stage)
        finally:
            after = snapshot()
            changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
            if changed:
                raise IntegrityFailure(changed, stage)


