import hashlib
import json
import pytest
from guardian.maintenance import fixtures
from guardian.maintenance.sandbox import CheckFailure, CheckTimeout, IntegrityFailure, Sandbox, command


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
    with pytest.raises(IntegrityFailure) as caught:sandbox.checks(tmp_path,{})
    assert calls==['lint']
    diagnostic=caught.value.diagnostics()
    assert diagnostic['stage']=='lint' and diagnostic['changed_paths']==['tsconfig.json']
    assert 'private synthetic value' not in json.dumps(diagnostic)+capsys.readouterr().out


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
