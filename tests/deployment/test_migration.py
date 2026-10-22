import hashlib
import json
from pathlib import Path
import runpy
import zipfile
import sqlite3
import types
import sys

import pytest

module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'deploy/migration.py'))


def values():
    return {k:'synthetic-value' for k in module['KEYS']}


@pytest.mark.parametrize('name',['../.env','/etc/passwd','data/approvals.sqlite3','data/repositories.local.json','data\\telegram.sqlite3'])
def test_rejects_out_of_scope_records(name):
    assert not module['allowed'](name)


def test_only_selected_credentials_exported():
    config=values()
    config['GUARDIAN_GITHUB_WRITE_TOKEN']='DO_NOT_EXPORT'
    result=module['environment'](config)
    assert b'DO_NOT_EXPORT' not in result and b'GITHUB' not in result
    config['ANTHROPIC_API_KEY']='secret\nINJECTED=true'
    with pytest.raises(ValueError): module['environment'](config)


def test_validates_archive_scope_and_hashes(tmp_path):
    path=tmp_path/'bundle.zip'
    env=module['environment'](values())
    manifest={'version':1,'site_id':'estateplanning','files':{'guardian.env':hashlib.sha256(env).hexdigest()}}
    with zipfile.ZipFile(path,'w') as out:
        out.writestr('manifest.json',json.dumps(manifest))
        out.writestr('guardian.env',env)
    assert module['validate'](path)['guardian.env']==env
    with zipfile.ZipFile(path,'a') as out: out.writestr('../escape',b'no')
    with pytest.raises(ValueError): module['validate'](path)


def test_build_closes_online_backups_before_cleanup(tmp_path,monkeypatch):
    for key,value in values().items(): monkeypatch.setenv(key,value)
    (tmp_path/'data').mkdir()
    (tmp_path/'.env').write_text(''.join(f'{k}={v}\n' for k,v in values().items()))
    (tmp_path/'data/weekly.json').write_text(json.dumps({'site_id':'estateplanning','enabled':False}))
    db=sqlite3.connect(tmp_path/'data/telegram.sqlite3')
    db.execute('CREATE TABLE telegram_leases(expires_at REAL)')
    db.close()
    archive=tmp_path/'transfer.zip'
    result=module['build'](tmp_path,archive)
    assert result['files']==3
    assert 'data/telegram.sqlite3' in module['validate'](archive)
    assert not list(tmp_path.glob('tmp*'))


def test_private_install_resumes_identical_db_and_rejects_changed_history(tmp_path,monkeypatch):
    monkeypatch.setattr(module['os'],'getuid',lambda:0,raising=False)
    monkeypatch.setattr(module['os'],'chown',lambda *args:None,raising=False)
    monkeypatch.setitem(sys.modules,'pwd',types.SimpleNamespace(getpwnam=lambda _:types.SimpleNamespace(pw_uid=1,pw_gid=1)))
    archive=tmp_path/'payload.zip'
    env=module['environment'](values())
    items={'guardian.env':env,'data/telegram.sqlite3':b'synthetic state'}
    with zipfile.ZipFile(archive,'w') as out:
        out.writestr('manifest.json',json.dumps({'version':1,'site_id':'estateplanning','files':{n:hashlib.sha256(v).hexdigest() for n,v in items.items()}}))
        for name,data in items.items(): out.writestr(name,data)
    work=tmp_path/'work'
    work.mkdir()
    target=tmp_path/'guardian.env'
    module['install'](archive,work,target)
    assert target.read_bytes()==env
    module['install'](archive,work,target)
    (work/'data/telegram.sqlite3').write_bytes(b'changed state')
    with pytest.raises(ValueError): module['install'](archive,work,target)
