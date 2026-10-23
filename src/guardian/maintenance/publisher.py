"""Trusted Actions publisher; never checks out or executes candidate code."""
import argparse
import base64
import json
import os
import re
from pathlib import Path
import httpx

from guardian.maintenance.policy import FILES, changes, digest, security_gate, verification

REPOSITORY = 'KeeLekHeng/sisweb'


class GitHub:
    def __init__(self, token, client=None):
        if not token:
            raise ValueError('Missing scoped SIS publishing token')
        self.token, self.client = token, client

    def request(self, method, path, data=None, params=None, missing=False):
        allowed = bool(method == 'GET' and (path == '/git/ref/heads/main' or path == '/pulls' or
                  re.fullmatch(r'/git/(?:trees|blobs|commits)/[a-f0-9]{40}', path) or
                  re.fullmatch(r'/git/ref/heads/guardian/dependencies-[a-f0-9]{20}', path)))
        allowed |= method == 'POST' and path in {'/git/blobs', '/git/trees', '/git/commits', '/git/refs', '/pulls'}
        if not allowed:
            raise ValueError('GitHub route outside dependency PR authority')
        if method == 'POST' and path == '/git/refs' and (not isinstance(data, dict) or
                set(data) != {'ref', 'sha'} or not re.fullmatch(r'refs/heads/guardian/dependencies-[a-f0-9]{20}', data.get('ref', ''))):
            raise ValueError('Only new Guardian dependency branches are permitted')
        if method == 'POST' and path == '/pulls' and (not isinstance(data, dict) or data.get('base') != 'main' or
                not re.fullmatch(r'guardian/dependencies-[a-f0-9]{20}', data.get('head', ''))):
            raise ValueError('Pull request scope mismatch')
        own = self.client is None
        client = self.client or httpx.Client(trust_env=False, follow_redirects=False, timeout=30)
        try:
            with client.stream(method, 'https://api.github.com/repos/' + REPOSITORY + path,
                               headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                                        'X-GitHub-Api-Version': '2022-11-28'}, json=data, params=params) as response:
                if missing and response.status_code == 404:
                    return None
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 6 * 1024 * 1024:
                        raise ValueError('GitHub response exceeds publisher budget')
            return json.loads(raw)
        finally:
            if own:
                client.close()

    def base(self):
        sha = self.request('GET', '/git/ref/heads/main')['object']['sha']
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise ValueError('Invalid base SHA')
        return sha

    def originals(self, revision):
        tree_id = self.request('GET', '/git/commits/' + revision)['tree']['sha']
        if not re.fullmatch(r'[a-f0-9]{40}', tree_id):
            raise ValueError('Invalid commit tree identity')
        tree = self.request('GET', '/git/trees/' + tree_id)
        if tree.get('truncated'):
            raise ValueError('Incomplete root tree')
        result = {'tree_sha': tree['sha']}
        if not re.fullmatch(r'[a-f0-9]{40}', result['tree_sha']):
            raise ValueError('Invalid tree identity')
        for name in FILES:
            entries = [entry for entry in tree['tree'] if entry.get('path') == name]
            if len(entries) != 1 or entries[0].get('mode') != '100644' or entries[0].get('type') != 'blob':
                raise ValueError('Expected regular dependency file')
            blob_id = entries[0]['sha']
            if not re.fullmatch(r'[a-f0-9]{40}', blob_id):
                raise ValueError('Invalid blob identity')
            blob = self.request('GET', '/git/blobs/' + blob_id)
            if blob.get('encoding') != 'base64':
                raise ValueError('Unsupported blob encoding')
            result[name] = base64.b64decode(''.join(blob['content'].split()), validate=True)
        return result


def publish(directory, expected, api, *, enabled=False, run_url=''):
    if not enabled:
        return {'status': 'disabled'}
    directory = Path(directory)
    if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Symlink artifact forbidden')
    if {p.name for p in directory.iterdir()} != {*FILES, 'verification.json'}:
        raise ValueError('Only exact dependency artifact files are allowed')
    raw = (directory / 'verification.json').read_bytes()
    if len(raw) > 2 * 1024 * 1024 or digest(raw) != expected:
        raise ValueError('Verification does not match the trusted job output')
    report = json.loads(raw)
    verification(report)
    if report.get('status') != 'verified' or set(report.get('files', {})) != set(FILES):
        raise ValueError('Missing verified artifact')
    if not security_gate(report['advisories_before'], report['advisories_after']):
        raise ValueError('Security evidence contradicts outcome')
    base = api.base()
    if base != report['base_sha']:
        raise ValueError('Base changed; rerun verification')
    originals = api.originals(base)
    candidate = {}
    for name in FILES:
        data = (directory / name).read_bytes()
        if not data or len(data) > 4 * 1024 * 1024 or b'\0' in data:
            raise ValueError('Invalid candidate file')
        data.decode('utf-8')
        if digest(data) != report['files'][name]['after_sha256'] or digest(originals[name]) != report['files'][name]['before_sha256']:
            raise ValueError('Artifact/source hash mismatch')
        candidate[name] = data
    updates = changes(originals['package.json'], candidate['package.json'])
    if updates != report['updates']:
        raise ValueError('Dependency delta does not match verified policy')
    identity = digest(base.encode() + b''.join(candidate[n] for n in FILES))[:20]
    branch = 'guardian/dependencies-' + identity
    existing = api.request('GET', '/pulls', params={'state': 'all', 'head': 'KeeLekHeng:' + branch})
    if existing:
        return {'status': 'already-published', 'number': existing[0]['number']}
    opened = api.request('GET', '/pulls', params={'state': 'open', 'base': 'main', 'per_page': 100})
    if len(opened) >= 100:
        raise ValueError('Open pull request inventory exceeds review budget')
    pending = [pr for pr in opened if pr.get('head', {}).get('ref', '').startswith('guardian/dependencies-')
               and pr.get('head', {}).get('repo', {}).get('full_name') == REPOSITORY]
    if pending:
        return {'status': 'existing-maintenance-pr', 'number': pending[0]['number']}
    if api.request('GET', '/git/ref/heads/' + branch, missing=True) is not None:
        raise ValueError('Partial publication branch exists; reconcile manually')
    tree = []
    for name in FILES:
        blob = api.request('POST', '/git/blobs', {'content': base64.b64encode(candidate[name]).decode(), 'encoding': 'base64'})
        tree.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    new_tree = api.request('POST', '/git/trees', {'base_tree': originals['tree_sha'], 'tree': tree})
    commit = api.request('POST', '/git/commits', {'message': 'chore: verified compatible dependency maintenance',
                                               'tree': new_tree['sha'], 'parents': [base]})
    if api.base() != base:
        raise ValueError('Base changed before branch publication')
    api.request('POST', '/git/refs', {'ref': 'refs/heads/' + branch, 'sha': commit['sha']})
    if api.base() != base:
        raise ValueError('Base changed; preserve branch and rerun verification')
    lines = ['Updates existing dependencies within the approved stable same-major policy.', '',
             '| Package | Before | After |', '| --- | --- | --- |']
    lines += [f"| {u['package']} | {u['before']} | {u['after']} |" for u in updates]
    lines += ['', 'Validation: frozen install, lint, TypeScript, unit tests, production build, integration tests and Playwright passed for both baseline and candidate.',
              'Tested base: ' + base,
              f"Reported advisory inventory: {len(report['advisories_before'])} before, {len(report['advisories_after'])} after.",
              'Known reported advisories were not introduced or increased in severity. Existing advisories may remain.',
              'Tests ran with synthetic data, mocked external services and cached Google Fonts; live provider behavior is not verified.',
              'Owner review, merge and deployment are required. If main changes after this run, rerun verification before merge. No auto-merge or production action was requested.']
    if re.fullmatch(r'https://github.com/KeeLekHeng/Webmaster-agent/actions/runs/\d+', run_url):
        lines += ['', 'Verification run: ' + run_url]
    pr = api.request('POST', '/pulls', {'title': 'chore: verified compatible dependency maintenance',
                                     'head': branch, 'base': 'main', 'body': '\n'.join(lines), 'draft': False})
    return {'status': 'published', 'number': pr['number']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--expected', required=True)
    args = parser.parse_args()
    if os.getenv('GUARDIAN_DEPENDENCY_PRS_ENABLED') != 'true':
        print(json.dumps({'status': 'disabled'}))
        return 0
    try:
        result = publish(args.artifact, args.expected, GitHub(os.getenv('GUARDIAN_SIS_WRITE_TOKEN')),
                         enabled=os.getenv('GUARDIAN_DEPENDENCY_PRS_ENABLED') == 'true',
                         run_url=os.getenv('GUARDIAN_VERIFICATION_URL', ''))
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'failure_kind': type(exc).__name__,
                          'notice': 'Preserve any created branch; do not blindly retry partial publication.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
