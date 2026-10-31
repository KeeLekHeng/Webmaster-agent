import hashlib
import json
import pytest
from guardian.maintenance import fixtures
from guardian.maintenance.sandbox import CheckFailure, CheckTimeout, IntegrityFailure, Sandbox, command, browser_summary


def test_diagnostics_persist_labels_not_raw_source_or_secrets():
    failure=CheckFailure(b'Turbopack build failed: Module not found, next/font error. sk-ant-private-value','build')
    result=failure.diagnostics()
    assert result['stage']=='build'
    assert {'turbopack-error','missing-module','font-error'}<=set(result['signals'])
    assert 'private-value' not in json.dumps(result)
    assert CheckFailure(b'arbitrary website output').diagnostics()['signals']==[]


def test_timeout_keeps_bounded_private_diagnostics_without_raw_error_prose():
    import sys
    with pytest.raises(CheckTimeout) as caught:
        command([sys.executable,'-c','import time; print("next/font error sk-ant-private-value", flush=True); time.sleep(10)'],timeout=.5)
    result=caught.value.diagnostics()
    assert result['timed_out'] is True and 'font-error' in result['signals']
    assert 'private-value' not in str(caught.value) + json.dumps(result)


def test_integrity_fails_at_first_changed_stage_and_identifies_only_paths(tmp_path,monkeypatch,capsys):
    source=tmp_path/'tsconfig.json';source.write_text('original')
    sandbox=Sandbox('sha256:'+'a'*64,tmp_path,tmp_path)
    calls=[]
    def mutate(path,argv,**kwargs):
        calls.append(argv[-1]);source.write_text('private synthetic value')
        return b''
    monkeypatch.setattr(sandbox,'run',mutate)
    with pytest.raises(IntegrityFailure) as caught:sandbox._checks(tmp_path,{})
    assert calls==['lint']
    diagnostic=caught.value.diagnostics()
    assert diagnostic['stage']=='lint' and diagnostic['changed_paths']==['tsconfig.json']
    assert 'private synthetic value' not in json.dumps(diagnostic)+capsys.readouterr().out


def test_browser_summary_keeps_failure_location_and_counts_without_page_data(tmp_path):
    path=tmp_path/'test-results'/'e2e-report.json';path.parent.mkdir()
    data={'stats':{'expected':3,'unexpected':1,'skipped':4,'private':'sk-ant-private-value'},
          'suites':[{'specs':[{'file':'tests/e2e/example.spec.ts','line':7,'title':'private title',
              'tests':[{'status':'unexpected','projectName':'desktop-chromium',
                        'results':[{'errors':[{'message':'expect(page).toHaveURL sk-ant-private-value private page',
                                              'stack':'private stack at /work/tests/e2e/example.spec.ts:14:2'}]}]}]}]}]}
    path.write_text(json.dumps(data))
    result=browser_summary(tmp_path)
    assert result['counts']=={'expected':3,'unexpected':1,'skipped':4}
    assert result['failures'][0]['file']=='tests/e2e/example.spec.ts'
    assert result['failures'][0]['assertion_locations']==['tests/e2e/example.spec.ts:14:2']
    assert 'assertion-url' in result['failures'][0]['signals']
    assert 'private' not in json.dumps(result)
    path.write_text('invalid JSON')
    assert browser_summary(tmp_path)=={'status':'unavailable'}


def test_browser_summary_retains_structured_location_and_allowlisted_matcher(tmp_path):
    path=tmp_path/'test-results'/'e2e-report.json';path.parent.mkdir()
    error={'message':'expect private-token toBeFocused',
           'location':{'file':'/work/tests/e2e/video.spec.ts','line':114,'column':20}}
    data={'stats':{'unexpected':1},'suites':[{'specs':[{'file':'video.spec.ts','line':97,
        'tests':[{'status':'unexpected','results':[{'errors':[error]}]}]}]}]}
    path.write_text(json.dumps(data))
    result=browser_summary(tmp_path)
    assert result['failures'][0]['assertion_locations']==['tests/e2e/video.spec.ts:114:20']
    assert result['failures'][0]['matchers']==['toBeFocused']
    assert 'private-token' not in json.dumps(result)


@pytest.mark.parametrize('passed',[0,2])
def test_browser_gate_rejects_all_skipped_coverage(tmp_path,monkeypatch,passed):
    from types import SimpleNamespace
    import guardian.maintenance.sandbox as module
    sandbox=Sandbox('sha256:'+'a'*64,tmp_path,tmp_path)
    sandbox.backend=SimpleNamespace(evidence={})
    monkeypatch.setattr(module,'STAGES',('install','browser'))
    monkeypatch.setattr(sandbox,'run',lambda *args,**kwargs:json.dumps({'real_password_mfa_browser':'passed','uat_admin_browser':'passed'}).encode())
    monkeypatch.setattr(module,'browser_summary',lambda workspace:{'counts':{'expected':passed,'unexpected':0,'skipped':10}})
    result={}
    if passed:
        sandbox._checks(tmp_path,result)
        assert result=={'browser':'passed'}
        assert sandbox.backend.evidence['browser_summary']['counts']['skipped']==10
    else:
        with pytest.raises(ValueError,match='coverage'):sandbox._checks(tmp_path,result)
        assert result=={}


def test_real_auth_failure_phase_is_fixed_and_redacted():
    result=CheckFailure(b'GUARDIAN_REAL_AUTH_PROBE_FAILED:mfa-enrollment private-value','browser').diagnostics()
    assert result['auth_probe_phase']=='mfa-enrollment'
    assert 'private-value' not in json.dumps(result)


@pytest.mark.parametrize('proof',[{}, {'real_password_mfa_browser':'passed'},
    {'real_password_mfa_browser':'passed','uat_admin_browser':'skipped'},
    {'real_password_mfa_browser':'passed','uat_admin_browser':'passed','extra':'private-value'}])
def test_browser_gate_requires_both_real_admin_profiles(tmp_path,monkeypatch,proof):
    from types import SimpleNamespace
    import guardian.maintenance.sandbox as module
    sandbox=Sandbox('sha256:'+'a'*64,tmp_path,tmp_path)
    sandbox.backend=SimpleNamespace(evidence={})
    monkeypatch.setattr(module,'STAGES',('install','browser'))
    monkeypatch.setattr(sandbox,'run',lambda *args,**kwargs:json.dumps(proof).encode())
    with pytest.raises(ValueError,match='Both real admin profiles'):sandbox._checks(tmp_path,{})
    assert 'mfa_browser' not in sandbox.backend.evidence and 'uat_admin_browser' not in sandbox.backend.evidence


def test_uat_failure_phase_does_not_expose_account_or_draft_contents():
    result=CheckFailure(b'GUARDIAN_REAL_AUTH_PROBE_FAILED:uat-draft-update private-value','browser').diagnostics()
    assert result['auth_probe_phase']=='uat-draft-update'
    assert 'private-value' not in json.dumps(result)


def test_node_failure_keeps_source_location_without_test_prose():
    result=CheckFailure(b'private-value file:///work/tests/unit/example.test.mjs:12:4','unit').diagnostics()
    assert result['test_locations']==['tests/unit/example.test.mjs:12:4']
    assert 'private-value' not in json.dumps(result)


def test_font_fixture_is_serializable_and_uses_only_cached_loopback_bytes(tmp_path,monkeypatch):
    font=b'synthetic-font-bytes'
    font_url='https://fonts.gstatic.com/s/overpass/font.woff2'
    class Response:
        def __init__(self,raw): self.content=raw;self.text=raw.decode()
        def raise_for_status(self): pass
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            if url==fixtures.CSS_URL:return Response(f'@font-face {{src: url({font_url})}}'.encode())
            assert url==font_url
            return Response(font)
    monkeypatch.setattr(fixtures.httpx,'Client',Client)
    result=fixtures.font_fixture(tmp_path)
    text=(tmp_path/'fonts.cjs').read_text()
    mapping=json.loads(text.removeprefix('module.exports=').strip().removesuffix(';'))
    assert set(mapping)=={fixtures.CSS_URL}
    name=hashlib.sha256(font).hexdigest()+'.woff2'
    assert 'http://127.0.0.1:37913/'+name in mapping[fixtures.CSS_URL]
    assert font_url not in mapping[fixtures.CSS_URL]
    assert (tmp_path/name).read_bytes()==font
    assert result[name]==hashlib.sha256(font).hexdigest()
