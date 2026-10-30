import json
import subprocess
from pathlib import Path
import pytest
from guardian.maintenance import runner, sandbox as sandbox_module
from guardian.maintenance.policy import STAGES
from tests.maintenance.backend_helpers import backend_proof


class Sandbox:
    fail = False
    def __init__(self, *args): pass
    def install(self, path, frozen):
        if not frozen: (path/'pnpm-lock.yaml').write_text('generated lock\n')
    def audit(self, path): return []
    def inventory(self, path, package):
        from guardian.maintenance.policy import declared
        return {name: '.'.join(map(str,declared(spec)[1])) for name,spec in package['dependencies'].items()}
    def checks(self, path, result):
        self.backend_evidence=backend_proof()
        for stage in STAGES[1:]:
            if self.fail and stage == 'build': raise ValueError('synthetic private error')
            result[stage]='passed'


@pytest.fixture
def setup(monkeypatch):
    def export(repository, path):
        (path/'package.json').write_text(json.dumps({'packageManager':'pnpm@10.18.2','dependencies':{'example':'1.0.0'}}))
        (path/'pnpm-lock.yaml').write_text('old lock\n')
        return 'a'*40
    monkeypatch.setattr(runner,'export',export)
    monkeypatch.setattr(Sandbox,'fail',False)


def registry(name):
    return {'versions':{'1.0.1':{}},'time':{'1.0.1':'2020-01-01T00:00:00Z'}}


def test_paired_success_and_failure_are_bound_to_artifacts(setup,tmp_path,monkeypatch):
    report=runner.run('unused',tmp_path/'good','sha256:'+'a'*64,sandbox_factory=Sandbox,registry=registry,fixtures=lambda p:{})
    assert report['status']=='verified'
    assert report['baseline']==report['candidate']=={s:'passed' for s in STAGES}
    assert (tmp_path/'good'/'package.json').is_file()
    monkeypatch.setattr(Sandbox,'fail',True)
    failed=runner.run('unused',tmp_path/'bad','sha256:'+'a'*64,sandbox_factory=Sandbox,registry=registry,fixtures=lambda p:{})
    assert failed['status']=='blocked'
    assert 'build' not in failed['baseline']
    assert not (tmp_path/'bad'/'package.json').exists()
    assert 'synthetic private error' not in (tmp_path/'bad'/'verification.json').read_text()


def test_sandbox_does_not_inherit_credentials_or_expose_host_network(tmp_path,monkeypatch):
    captured=[]
    monkeypatch.setenv('GUARDIAN_SIS_WRITE_TOKEN','synthetic-secret')
    monkeypatch.setattr(sandbox_module,'command',lambda args,**kw: captured.append(args) or b'')
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw: None)
    sandbox=runner.Sandbox('sha256:'+'a'*64,tmp_path,tmp_path)
    monkeypatch.setattr(runner.os,'getuid',lambda:1001,raising=False)
    monkeypatch.setattr(runner.os,'getgid',lambda:1001,raising=False)
    sandbox.run(tmp_path,['bash','/trusted/check.sh','build'])
    args=captured[0]
    assert args[args.index('--network')+1]=='none'
    assert '--cap-drop=ALL' in args and '--read-only' in args
    assert 'synthetic-secret' not in ' '.join(args)
    assert 'ADMIN_SESSION_SECRET=guardian-synthetic-session-key-not-for-production' in args
    assert 'docker.sock' not in ' '.join(args)


def test_timeout_forces_container_cleanup(tmp_path,monkeypatch):
    cleaned=[]
    monkeypatch.setattr(runner.os,'getuid',lambda:1001,raising=False)
    monkeypatch.setattr(runner.os,'getgid',lambda:1001,raising=False)
    def timeout(*a,**kw): raise subprocess.TimeoutExpired('docker',1)
    monkeypatch.setattr(sandbox_module,'command',timeout)
    monkeypatch.setattr(subprocess,'run',lambda args,**kw: cleaned.append(args))
    with pytest.raises(subprocess.TimeoutExpired): runner.Sandbox('sha256:'+'a'*64,tmp_path,tmp_path).run(tmp_path,['false'])
    assert cleaned[0][:3]==['docker','rm','--force']


def test_process_output_is_separate_bounded_and_timeout_controlled():
    import sys
    result=runner.command([sys.executable,'-c','import sys;sys.stderr.write("diagnostic");print("json")'])
    assert result.strip()==b'json'
    with pytest.raises(subprocess.TimeoutExpired):
        runner.command([sys.executable,'-c','import time;time.sleep(10)'],timeout=.1)
    with pytest.raises(ValueError,match='output'):
        runner.command([sys.executable,'-c','import sys;sys.stdout.write("x"*(9*1024*1024))'])


def test_candidate_failure_never_emits_publishable_files(setup,tmp_path):
    class FailingCandidate(Sandbox):
        def checks(self,path,result):
            if path.name=='candidate':
                result['lint']='passed'
                raise ValueError('candidate failed')
            super().checks(path,result)
    report=runner.run('unused',tmp_path/'result','sha256:'+'a'*64,
                      sandbox_factory=FailingCandidate,registry=registry,fixtures=lambda p:{})
    assert report['baseline']=={s:'passed' for s in STAGES}
    assert report['status']=='blocked' and report['phase']=='candidate-checks'
    assert not (tmp_path/'result'/'package.json').exists()
