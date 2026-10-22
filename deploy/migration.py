"""Scoped state migration; no arbitrary extraction, shell commands or secret output."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from contextlib import closing

KEYS = {'ANTHROPIC_API_KEY','GUARDIAN_MODEL','GUARDIAN_GSC_PROPERTY',
        'GUARDIAN_GSC_CLIENT_ID','GUARDIAN_GSC_CLIENT_SECRET','GUARDIAN_GSC_REFRESH_TOKEN',
        'GUARDIAN_PAGESPEED_API_KEY','GUARDIAN_TELEGRAM_BOT_TOKEN','GUARDIAN_TELEGRAM_CHAT_ID'}
DATABASES = {'data/guardian.sqlite3','data/telegram.sqlite3','data/weekly.sqlite3'}
MAX_BYTES = 64 * 1024 * 1024


def allowed(name):
    if '\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
        return False
    if name in DATABASES | {'guardian.env','data/weekly.json'}:
        return True
    return bool(re.fullmatch(r'reports/[a-f0-9]{32}/(report\.json|report\.md|summary\.md|search-periods\.json)',name) or
                re.fullmatch(r'data/performance/estateplanning/[a-f0-9]{32}\.json',name))


def environment(values):
    selected = {key:values.get(key,'') for key in KEYS}
    required = KEYS - {'GUARDIAN_PAGESPEED_API_KEY'}
    if any(not selected[k] for k in required):
        raise ValueError('Required Guardian configuration missing')
    if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_./:+@=-]*',v) for v in selected.values()):
        raise ValueError('Unsupported credential formatting; review locally')
    return ''.join(f'{k}={v}\n' for k,v in sorted(selected.items())).encode() + b'AGENT_ENABLED=true\nGUARDIAN_TELEGRAM_ENABLED=true\n'


def build(root, output):
    from dotenv import dotenv_values
    root,output=Path(root).resolve(),Path(output).resolve()
    values=dotenv_values(root/'.env',interpolate=False)
    values.update({key:os.environ[key] for key in KEYS if key in os.environ})
    items={'guardian.env':environment(values)}
    schedule=json.loads((root/'data/weekly.json').read_bytes())
    if schedule.get('site_id')!='estateplanning': raise ValueError('Schedule site mismatch')
    schedule['enabled']=True
    items['data/weekly.json']=json.dumps(schedule).encode()
    with tempfile.TemporaryDirectory(dir=output.parent) as folder:
        for name in sorted(DATABASES):
            source=root/name
            if not source.exists(): continue
            if source.is_symlink(): raise ValueError('Symlink database rejected')
            backup=Path(folder)/source.name
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original, closing(sqlite3.connect(backup)) as target:
                original.backup(target)
                if target.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('Invalid SQLite backup')
                if name=='data/telegram.sqlite3':
                    if target.execute('SELECT count(*) FROM telegram_leases WHERE expires_at > ?',(__import__('time').time(),)).fetchone()[0]:
                        raise ValueError('A polling lease is still active; wait for expiry')
            items[name]=backup.read_bytes()
    if 'data/telegram.sqlite3' not in items: raise ValueError('Paired Telegram state required')
    for base in [root/'reports',root/'data/performance/estateplanning']:
        for source in base.rglob('*'):
            if not source.is_file(): continue
            name=source.relative_to(root).as_posix()
            if not allowed(name): continue
            if source.is_symlink() or not source.resolve().is_relative_to(root): raise ValueError('Unsafe artifact path')
            items[name]=source.read_bytes()
    if len(items)>1000 or sum(map(len,items.values()))>MAX_BYTES: raise ValueError('Migration budget exceeded')
    manifest={'version':1,'site_id':'estateplanning','created_at':datetime.now(timezone.utc).isoformat(),
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in items.items()}}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        for name,data in items.items(): archive.writestr(name,data)
    return {'files':len(items),'bytes':sum(map(len,items.values())),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


def validate(path):
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>1001 or len({e.filename for e in entries})!=len(entries) or sum(e.file_size for e in entries)>MAX_BYTES:
            raise ValueError('Invalid archive size/entries')
        if any(stat.S_ISLNK(e.external_attr>>16) or e.is_dir() for e in entries): raise ValueError('Invalid archive mode')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('version')!=1 or manifest.get('site_id')!='estateplanning': raise ValueError('Invalid manifest')
        names=set(manifest['files'])
        if set(archive.namelist())!=names|{'manifest.json'} or not all(allowed(n) for n in names): raise ValueError('Invalid scope')
        items={name:archive.read(name) for name in names}
    if any(hashlib.sha256(data).hexdigest()!=manifest['files'][name] for name,data in items.items()): raise ValueError('Artifact hash mismatch')
    env={}
    for line in items['guardian.env'].decode().splitlines():
        key,sep,value=line.partition('=')
        if not sep or key in env: raise ValueError('Invalid environment')
        env[key]=value
    if set(env)!=KEYS|{'AGENT_ENABLED','GUARDIAN_TELEGRAM_ENABLED'} or env['AGENT_ENABLED']!='true' or env['GUARDIAN_TELEGRAM_ENABLED']!='true':
        raise ValueError('Unexpected environment keys')
    environment(env)
    return items


def install(path, work='/var/lib/guardian/work', env_path='/etc/guardian/guardian.env'):
    if os.getuid()!=0: raise ValueError('Administrator required')
    import pwd
    uid=pwd.getpwnam('websiteguardian').pw_uid
    gid=pwd.getpwnam('websiteguardian').pw_gid
    items=validate(path)
    work=Path(work).resolve()
    # Resume identical partial copies, never replace divergent server history.
    for name in DATABASES:
        existing=work/name
        if existing.exists() and (name not in items or existing.read_bytes()!=items[name]):
            raise ValueError('Existing server history differs; reconcile before overwrite')
    for name,data in items.items():
        if name=='guardian.env': continue
        destination=work/name
        if not destination.resolve().is_relative_to(work): raise ValueError('Unsafe destination')
        destination.parent.mkdir(parents=True,exist_ok=True)
        for parent in [destination.parent,*destination.parent.parents]:
            if parent==work: break
            if not parent.is_relative_to(work): break
            os.chown(parent,uid,gid)
            parent.chmod(0o700)
        if destination.suffix!='.sqlite3' or not destination.exists():
            with destination.open('xb' if destination.suffix=='.sqlite3' else 'wb') as stream: stream.write(data)
        destination.chmod(0o600)
        os.chown(destination,uid,gid)
    temporary=Path(env_path).with_suffix('.pending')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(items['guardian.env'])
    temporary.replace(env_path)
    print(json.dumps({'installed_files':len(items),'credentials':'root-only','github_write_credentials':'excluded'}))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['build','install'])
    parser.add_argument('archive')
    parser.add_argument('--root',default=str(Path(__file__).resolve().parent.parent))
    args=parser.parse_args()
    try:
        if args.mode=='build': print(json.dumps(build(args.root,args.archive)))
        else: install(args.archive)
    except Exception as exc:
        parser.exit(2,f'Migration failed ({type(exc).__name__}); private details omitted.\n')
