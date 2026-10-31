"""Controller safety tests; these do not claim a live Supabase pass."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from guardian.maintenance import backend
from guardian.maintenance.policy import STAGES, backend_verification, verification
from tests.maintenance.backend_helpers import backend_proof


@pytest.mark.parametrize('sql', ['\\! whoami', 'SELECT 1;\n  \\include file', '\0', 'x'*60001, ''],
                         ids=['shell-meta','include-meta','nul','oversized','empty'])
def test_rejects_unsafe_migration_input(tmp_path, sql):
    folder=tmp_path/'supabase'/'migrations'
    folder.mkdir(parents=True)
    (folder/'202610010001_test.sql').write_text(sql)
    with pytest.raises(ValueError):backend.migration_files(tmp_path)


def test_migrations_are_data_and_hashes(tmp_path):
    folder=tmp_path/'supabase'/'migrations'
    folder.mkdir(parents=True)
    (folder/'202610010001_test.sql').write_text('SELECT 1;')
    result=backend.migration_files(tmp_path)
    assert result[0][:2]==('202610010001_test.sql','SELECT 1;')
    assert len(result[0][2])==64


@pytest.mark.parametrize('field', ['schema','rls','auth','storage','mfa_browser','uat_admin_browser','isolation','egress_probe','cleanup'])
def test_every_real_gate_is_required(field):
    proof=backend_proof()
    proof[field]='failed'
    with pytest.raises(ValueError):backend_verification(proof)


@pytest.mark.parametrize('field,value', [('seed_sha256',None),('images',{1:'a'}),('migrations',{1:None})])
def test_malformed_proof_is_rejected(field,value):
    proof=backend_proof();proof[field]=value
    with pytest.raises(ValueError):backend_verification(proof)


def report():
    return {'version':2,'base_sha':'a'*40,'updates':[{}],'security_not_worsened':True,
            'baseline':{s:'passed' for s in STAGES},'candidate':{s:'passed' for s in STAGES},
            'backend':{k:backend_proof() for k in ('baseline','candidate')}}


def test_old_evidence_remains_readable_but_cannot_publish():
    value=report();value['version']=1;value.pop('backend')
    assert verification(value)
    with pytest.raises(ValueError,match='Old mock-only'):verification(value,require_backend=True)


@pytest.mark.parametrize('field', ['images','migrations','seed_sha256'])
def test_paired_backend_inputs_must_match(field):
    value=report()
    proof=value['backend']['candidate']
    if field=='images':proof[field]['db']='sha256:'+'d'*64
    elif field=='migrations':proof[field]['202610010001_example.sql']='d'*64
    else:proof[field]='d'*64
    with pytest.raises(ValueError,match='inputs differ'):verification(value,require_backend=True)


def test_cli_does_not_inherit_provider_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv('SUPABASE_ACCESS_TOKEN','never-copy')
    monkeypatch.setenv('ANTHROPIC_API_KEY','never-copy')
    monkeypatch.setenv('GITHUB_TOKEN','never-copy')
    calls=[]
    monkeypatch.setattr(backend,'command',lambda args,**kwargs:calls.append((args,kwargs)) or b'')
    instance=backend.Backend(SimpleNamespace(),tmp_path);instance.root=tmp_path
    instance.cli('status')
    environment=calls[0][1]['env']
    assert not {'SUPABASE_ACCESS_TOKEN','ANTHROPIC_API_KEY','GITHUB_TOKEN'} & environment.keys()
    assert environment['HOME']==str(tmp_path/'home')


def service(instance,role):
    return {'Id':'a'*64,'Name':'/supabase_'+role+'_'+instance.project,'Image':'sha256:'+'b'*64,
            'HostConfig':{},'Mounts':[],'State':{'Status':'running'},
            'NetworkSettings':{'Networks':{instance.network:{}},'Ports':{'8000/tcp':[{'HostIp':'127.0.0.1'}]}}}


@pytest.mark.parametrize('unsafe', ['public-port','host-network','host-mount','privileged','foreign-volume','extra-network'])
def test_audit_blocks_unsafe_services(tmp_path,monkeypatch,unsafe):
    instance=backend.Backend(SimpleNamespace(),tmp_path);instance.root=tmp_path
    row=service(instance,'kong')
    if unsafe=='public-port':row['NetworkSettings']['Ports']['8000/tcp'][0]['HostIp']='0.0.0.0'
    if unsafe=='host-network':row['HostConfig']['NetworkMode']='host'
    if unsafe=='host-mount':row['Mounts']=[{'Type':'bind','Source':str(tmp_path.parent)}]
    if unsafe=='privileged':row['HostConfig']['Privileged']=True
    if unsafe=='foreign-volume':row['Mounts']=[{'Type':'volume','Name':'production'}]
    if unsafe=='extra-network':row['NetworkSettings']['Networks']['bridge']={}
    monkeypatch.setattr(backend,'owned_containers',lambda project:[row])
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        return json.dumps([{'Internal':True,'Labels':{'guardian.project':instance.project}}]).encode()
    monkeypatch.setattr(backend,'command',command)
    with pytest.raises(ValueError):instance.audit()
    assert not any(args[:2]==['docker','update'] for args in calls)


def test_cleanup_refuses_unowned_network(monkeypatch):
    monkeypatch.setattr(backend,'owned_containers',lambda project:[])
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        return b'' if args[1:3]==['volume','ls'] else b'[{"Labels":{},"Containers":{}}]'
    monkeypatch.setattr(backend,'command',command)
    with pytest.raises(ValueError,match='ownership'):backend.cleanup_project('guardian-local-'+'a'*16,'network')
    assert not any(args[1:3]==['network','rm'] for args in calls)


def test_cleanup_failure_cannot_claim_pass(tmp_path,monkeypatch):
    instance=backend.Backend(SimpleNamespace(),tmp_path);instance.root=tmp_path
    def fail(*args):raise ValueError('cleanup failed')
    monkeypatch.setattr(backend,'cleanup_project',fail)
    with pytest.raises(ValueError):instance.close()
    assert instance.evidence['cleanup']=='failed'


def test_totp_matches_rfc6238_vectors():
    script=Path('maintenance/real-backend.cjs').resolve()
    code='const {totp}=require(process.argv[1]);console.log(JSON.stringify([59000,1111111109000,1234567890000].map(t=>totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",t))))'
    result=subprocess.run(['node','-e',code,str(script)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==['287082','081804','005924']


def test_startup_diagnostics_never_copy_secrets():
    output=b'local-key=secret-value failed to connect to postgres: connection refused'
    assert backend.startup_diagnostics(output)==['connection-refused','health-check','postgres-connection']


def test_network_transition_preserves_aliases_and_removes_bootstrap(monkeypatch):
    project='guardian-local-'+'a'*16
    row={'Id':'b'*64,'Name':'/supabase_db_'+project,
         'NetworkSettings':{'Networks':{'bootstrap':{'Aliases':['database']}}}}
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        if args[:3]==['docker','network','inspect']:
            return json.dumps([{'Internal':args[3]=='private','Labels':{'guardian.project':project}}]).encode()
        if args[:3]==['docker','network','connect']:row['NetworkSettings']['Networks']['private']={}
        if args[:3]==['docker','network','disconnect']:row['NetworkSettings']['Networks'].pop('bootstrap')
        return b''
    monkeypatch.setattr(backend,'command',command)
    monkeypatch.setattr(backend,'owned_containers',lambda project:[row])
    backend.isolate_network(project,'bootstrap','private')
    assert set(row['NetworkSettings']['Networks'])=={'private'}
    connect=next(args for args in calls if args[:3]==['docker','network','connect'])
    assert 'database' in connect and row['Name'].lstrip('/') in connect


def test_network_transition_refuses_foreign_target(monkeypatch):
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        return json.dumps([{'Internal':args[3]=='private','Labels':{'guardian.project':'another-owner'}}]).encode()
    monkeypatch.setattr(backend,'command',command)
    with pytest.raises(ValueError,match='ownership'):
        backend.isolate_network('guardian-local-'+'a'*16,'bootstrap','private')
    assert all(args[:3]==['docker','network','inspect'] for args in calls)


@pytest.mark.parametrize('outside',[False,True])
def test_gateway_origin_is_discovered_only_from_owned_subnet(tmp_path,monkeypatch,outside):
    instance=backend.Backend(SimpleNamespace(),tmp_path);instance.root=tmp_path
    rows=[service(instance,role) for role in ('db','auth','rest','storage','kong')]
    for i,row in enumerate(rows,2):row['NetworkSettings']['Networks'][instance.network]['IPAddress']='172.19.0.'+str(i)
    if outside:rows[-1]['NetworkSettings']['Networks'][instance.network]['IPAddress']='8.8.8.8'
    monkeypatch.setattr(backend,'owned_containers',lambda project:rows)
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        if args[:3]==['docker','network','inspect']:
            return json.dumps([{'Internal':True,'Labels':{'guardian.project':instance.project},
                               'IPAM':{'Config':[{'Subnet':'172.19.0.0/16'}]}}]).encode()
        return b''
    monkeypatch.setattr(backend,'command',command)
    if outside:
        with pytest.raises(ValueError,match='outside owned'):instance.audit()
    else:
        instance.audit()
        assert instance.api_origin=='http://172.19.0.6:8000'
        assert instance.evidence['isolation']=='passed'
    assert len([args for args in calls if args[:2]==['docker','update']])==5


def test_api_failure_records_code_without_response_body(tmp_path,monkeypatch):
    import httpx
    instance=backend.Backend(SimpleNamespace(),tmp_path)
    instance.api_origin='http://172.19.0.6:8000';instance.anon='test-only-key'
    original=httpx.Client
    transport=httpx.MockTransport(lambda request:httpx.Response(404,json={
        'code':'PGRST205','message':'Could not find the table in schema cache private-test-value'}))
    monkeypatch.setattr(backend.httpx,'Client',lambda **kwargs:original(transport=transport,**kwargs))
    with pytest.raises(ValueError,match='backend request'):instance.request('GET','/rest/v1/blogs')
    assert instance.evidence['api_failure']=={'method':'GET','service':'rest','status':404,
                                            'code':'PGRST205','category':'schema-cache-miss'}
    assert 'private-test-value' not in json.dumps(instance.evidence)


def test_schema_reload_targets_the_audited_rest_service(tmp_path,monkeypatch):
    instance=backend.Backend(SimpleNamespace(),tmp_path)
    instance.rest='supabase_rest_'+instance.project
    calls=[]
    monkeypatch.setattr(backend,'command',lambda args,**kwargs:calls.append(args) or b'')
    instance.reload_schema()
    assert calls==[['docker','kill','--signal=SIGUSR1',instance.rest]]


def test_email_provider_does_not_enable_public_registration():
    import tomllib
    config=tomllib.loads(Path('maintenance/backend-config.toml').read_text())['auth']
    assert config['enable_signup'] is False and config['email']['enable_signup'] is True
    assert config['mfa']['totp']=={'enroll_enabled':True,'verify_enabled':True}
    proof=backend_proof();proof.pop('public_signup')
    with pytest.raises(ValueError,match='signup denial'):backend_verification(proof)
