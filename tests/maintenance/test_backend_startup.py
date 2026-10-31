"""Startup-control boundaries; successful fakes are not live database evidence."""
import importlib.util
import json
import re
from pathlib import Path

import pytest


@pytest.fixture
def control(monkeypatch):
    spec=importlib.util.spec_from_file_location('backend_startup',Path('maintenance/backend-startup.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    calls=[];state={}
    monkeypatch.setattr(module.platform,'system',lambda:'Linux')
    def command(args,**kwargs):
        calls.append((args,kwargs))
        if args==['supabase','--version']:return module.VERSION.encode()
        if args[:3]==['docker','network','create']:
            state['network']=args[-1]
            state['project']=args[args.index('--label')+1].split('=',1)[1]
        if args[:2]==['docker','exec']:
            nonce=re.search(r"VALUES \('([a-f0-9]{32})'\)",args[-1])[1]
            return (nonce+':170006\n').encode()
        return b''
    def inventory(project):
        assert project==state['project']
        return [{'Id':format(i,'064x'),'Name':'/supabase_'+role+'_'+project,'Image':'sha256:'+'a'*64,
                 'State':{'Status':'running'},'HostConfig':{},
                 'NetworkSettings':{'Networks':{state['network']:{}},
                                   'Ports':{'5432/tcp':[{'HostIp':'127.0.0.1'}]}}}
                for i,role in enumerate(('db','auth','rest','storage','kong'),1)]
    monkeypatch.setattr(module,'command',command)
    monkeypatch.setattr(module,'owned_containers',inventory)
    monkeypatch.setattr(module,'cleanup_project',lambda project,network:state.update(cleaned=True))
    return module,calls,state


def test_real_round_trip_required_and_control_cannot_publish(control,monkeypatch):
    module,calls,state=control
    monkeypatch.setenv('SUPABASE_ACCESS_TOKEN','do-not-copy')
    report=module.run()
    assert report['status']=='passed' and report['database_query']=='passed' and state['cleaned']
    assert report['publishing_authority'] is False and report['website_input'] is False
    start=next(kwargs for args,kwargs in calls if args[:2]==['supabase','start'])
    assert 'SUPABASE_ACCESS_TOKEN' not in start['env']
    from guardian.maintenance.policy import backend_verification
    with pytest.raises(ValueError):backend_verification(report)


def test_query_failure_blocks_control_and_still_cleans(control,monkeypatch):
    module,calls,state=control
    original=module.command
    monkeypatch.setattr(module,'command',lambda args,**kw:b'wrong:170006' if args[:2]==['docker','exec'] else original(args,**kw))
    report=module.run()
    assert report['status']=='blocked' and state['cleaned']
    assert report['phase']=='database-query'


def test_cleanup_failure_blocks_even_a_successful_query(control,monkeypatch):
    module,_,_=control
    def fail(*args):raise ValueError('failed')
    monkeypatch.setattr(module,'cleanup_project',fail)
    report=module.run()
    assert report['database_query']=='passed' and report['cleanup']=='failed' and report['status']=='blocked'


def test_public_bindings_are_rejected(control,monkeypatch):
    module,_,state=control
    original=module.owned_containers
    def inventory(project):
        rows=original(project)
        rows[0]['NetworkSettings']['Ports']['5432/tcp'][0]['HostIp']='0.0.0.0'
        return rows
    monkeypatch.setattr(module,'owned_containers',inventory)
    report=module.run()
    assert report['status']=='blocked' and report['phase']=='service-inspection' and state['cleaned']


def test_cli_failure_is_redacted_and_cleaned(control,monkeypatch):
    module,_,state=control
    original=module.command
    from guardian.maintenance.sandbox import CheckFailure
    def command(args,**kwargs):
        if args[:2]==['supabase','start']:raise CheckFailure(b'private-password failed to connect to postgres')
        return original(args,**kwargs)
    monkeypatch.setattr(module,'command',command)
    report=module.run()
    assert report['status']=='blocked' and state['cleaned']
    assert 'private-password' not in json.dumps(report)
