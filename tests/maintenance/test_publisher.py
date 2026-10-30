import json
import pytest
from guardian.maintenance.policy import STAGES, changes, digest
from guardian.maintenance.publisher import publish, GitHub
from tests.maintenance.backend_helpers import backend_proof


class API:
    def __init__(self, original):
        self.original = original
        self.calls = []
        self.current = 'a'*40
        self.existing = []
    def base(self): return self.current
    def originals(self, revision): return {**self.original, 'tree_sha':'b'*40}
    def request(self, method, path, data=None, params=None, missing=False):
        self.calls.append((method,path,data))
        if path == '/pulls' and method == 'GET': return self.existing
        if method == 'GET': return None
        if path == '/pulls': return {'number':42}
        return {'sha':'c'*40}


@pytest.fixture
def artifact(tmp_path):
    old = {'packageManager':'pnpm@10.18.2','dependencies':{'example':'1.0.0'},'scripts':{'build':'next build'}}
    new = {**old, 'dependencies':{'example':'1.0.1'}}
    original = {'package.json':json.dumps(old).encode(), 'pnpm-lock.yaml':b'old lock\n'}
    candidate = {'package.json':json.dumps(new).encode(),'pnpm-lock.yaml':b'new lock\n'}
    report = {'version':2,'backend':{k:backend_proof() for k in ('baseline','candidate')},'base_sha':'a'*40,'status':'verified','security_not_worsened':True,
              'advisories_before':[],'advisories_after':[],
              'baseline':{s:'passed' for s in STAGES},'candidate':{s:'passed' for s in STAGES},
              'updates':changes(original['package.json'],candidate['package.json']),
              'files':{n:{'before_sha256':digest(original[n]),'after_sha256':digest(v)} for n,v in candidate.items()}}
    for name,data in candidate.items(): (tmp_path/name).write_bytes(data)
    (tmp_path/'verification.json').write_text(json.dumps(report))
    return tmp_path, API(original), report


def fingerprint(path): return digest((path/'verification.json').read_bytes())


def test_valid_artifact_creates_only_dependency_branch_and_pr(artifact):
    path, api, _ = artifact
    assert publish(path, fingerprint(path), api, enabled=True) == {'status':'published','number':42}
    tree = next(data for method,p,data in api.calls if p == '/git/trees')
    assert {e['path'] for e in tree['tree']} == {'package.json','pnpm-lock.yaml'}
    assert tree['base_tree'] == 'b'*40
    assert not any('merge' in p or method in {'PUT','PATCH','DELETE'} for method,p,_ in api.calls)


def test_default_off_and_duplicate_suppression(artifact):
    path, api, _ = artifact
    assert publish(path, '', api)['status'] == 'disabled'
    assert not api.calls
    api.existing = [{'number':7}]
    assert publish(path, fingerprint(path), api, enabled=True)['status'] == 'already-published'
    assert not any(method == 'POST' for method,_,_ in api.calls)


@pytest.mark.parametrize('kind', ['base','hash','stage','extra','scripts','security','fingerprint'])
def test_tampering_and_unverified_results_never_write(artifact, kind):
    path, api, report = artifact
    expected = fingerprint(path)
    if kind == 'base': api.current = 'd'*40
    if kind == 'hash': (path/'pnpm-lock.yaml').write_text('tampered')
    if kind == 'stage': del report['candidate']['build']
    if kind == 'extra': (path/'evil.sh').write_text('evil')
    if kind == 'scripts':
        package=json.loads((path/'package.json').read_bytes()); package['scripts']['build']='evil'
        raw=json.dumps(package).encode(); (path/'package.json').write_bytes(raw)
        report['files']['package.json']['after_sha256']=digest(raw)
    if kind == 'security': report['advisories_after']=[{'id':'1','package':'example','severity':'high'}]
    if kind in {'stage','scripts','security'}:
        (path/'verification.json').write_text(json.dumps(report)); expected=fingerprint(path)
    if kind == 'fingerprint': expected='f'*64
    with pytest.raises(ValueError): publish(path, expected, api, enabled=True)
    assert not any(method == 'POST' for method,_,_ in api.calls)


def test_routes_cannot_merge_or_write_default_branch():
    api=GitHub('synthetic')
    with pytest.raises(ValueError): api.request('PUT','/pulls/1/merge')
    with pytest.raises(ValueError): api.request('PATCH','/git/refs/heads/main',{})


def test_base_moves_during_publication_no_branch_is_created(artifact):
    path,api,_=artifact
    values=iter(['a'*40,'d'*40])
    api.base=lambda:next(values)
    with pytest.raises(ValueError,match='Base changed'):
        publish(path,fingerprint(path),api,enabled=True)
    assert not any(p in {'/git/refs','/pulls'} and method=='POST' for method,p,_ in api.calls)


@pytest.mark.parametrize('kind',['old-version','missing-backend','cleanup-failed','input-mismatch'])
def test_incomplete_real_backend_evidence_never_writes(artifact,kind):
    path,api,report=artifact
    if kind=='old-version':report['version']=1
    if kind=='missing-backend':report.pop('backend')
    if kind=='cleanup-failed':report['backend']['candidate']['cleanup']='failed'
    if kind=='input-mismatch':report['backend']['candidate']['seed_sha256']='d'*64
    (path/'verification.json').write_text(json.dumps(report))
    with pytest.raises(ValueError):publish(path,fingerprint(path),api,enabled=True)
    assert not any(method=='POST' for method,_,_ in api.calls)
