"""Step 1 control: trusted Supabase startup only, with no website input or publishing."""
import argparse
import json
import os
import platform
import re
import secrets
import tempfile
from pathlib import Path

try:
    from guardian.maintenance.backend import Backend, VERSION, EXCLUDE, run_id, owned_containers, cleanup_project, startup_diagnostics, isolate_network
    from guardian.maintenance.sandbox import command
except ModuleNotFoundError:
    from backend import Backend, VERSION, EXCLUDE, run_id, owned_containers, cleanup_project, startup_diagnostics, isolate_network
    from sandbox import command


def run(network_mode='bridge'):
    if network_mode not in {'bridge','internal','transition'}:raise ValueError('Unknown control network mode')
    report={'purpose':'startup-control-only','status':'blocked','phase':'preflight',
            'cli_version':VERSION,'network_mode':network_mode,
            'website_input':False,'publishing_authority':False,'cleanup':'pending'}
    project='guardian-'+run_id()+'-'+secrets.token_hex(8)
    network='guardian-startup-'+secrets.token_hex(8)
    created=[]
    with tempfile.TemporaryDirectory(prefix='guardian-startup-') as directory:
        root=Path(directory)
        try:
            if platform.system()!='Linux':raise ValueError('Disposable Linux runner required')
            if command(['supabase','--version']).decode().strip()!=VERSION:
                raise ValueError('Unreviewed CLI version')
            (root/'home').mkdir();(root/'supabase').mkdir()
            config=Path(__file__).with_name('backend-config.toml').read_text().replace('GUARDIAN_PROJECT',project)
            (root/'supabase'/'config.toml').write_text(config)
            env={k:v for k,v in os.environ.items() if k in {'PATH','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG'}}
            env['HOME']=str(root/'home')
            # Standard networking is the control variable. Only trusted service images
            # run here; the production candidate verifier's internal network is unchanged.
            command(['docker','network','create',*(['--internal'] if network_mode=='internal' else []),'--label','guardian.project='+project,
                     '--opt','com.docker.network.bridge.host_binding_ipv4=127.0.0.1',network])
            created.append(network)
            report['phase']='supabase-start'
            command(['supabase','start','--exclude',EXCLUDE,'--workdir',str(root),
                     '--network-id',network],env=env,timeout=600)
            report['startup']='passed'
            if network_mode=='transition':
                report['phase']='isolation-transition'
                private='guardian-net-'+secrets.token_hex(8)
                command(['docker','network','create','--internal','--label','guardian.project='+project,
                         '--opt','com.docker.network.bridge.host_binding_ipv4=127.0.0.1',private])
                created.append(private)
                isolate_network(project,network,private)
                network=private
                audit=Backend(None,root)
                audit.project=project;audit.network=private;audit.root=root
                audit.audit()  # Same mount/network/port checks and quotas as the candidate verifier.
                report['isolation']=audit.evidence['isolation'];report['resource_limits']='applied'
                report['phase']='egress-probe'
                storage=next(row['Image'] for row in owned_containers(project) if row['Name']=='/supabase_storage_'+project)
                probe_name='guardian-probe-'+secrets.token_hex(8)
                try:
                    probe=command(['docker','run','--rm','--name',probe_name,'--network','container:'+audit.gateway,
                        '--cap-drop=ALL','--security-opt=no-new-privileges','--read-only','--user','65534:65534',
                        '--memory=128m','--pids-limit=64','--entrypoint','node',storage,'-e',
                        Path(__file__).with_name('network-probe.cjs').read_text()],timeout=15)
                    if json.loads(probe)!={'tcp_blocked':True,'dns_blocked':True}:raise ValueError('Egress still available')
                    report['egress_probe']='passed'
                finally:command(['docker','rm','--force',probe_name],allowed=(0,1),timeout=30)
            report['phase']='service-inspection'
            images={};database=None
            for row in owned_containers(project):
                match=re.fullmatch(r'/supabase_([a-z_]+)_'+re.escape(project),row.get('Name',''))
                if not match:raise ValueError('Unexpected service identity')
                role=match[1]
                if row.get('State',{}).get('Status')!='running':raise ValueError('Service not running')
                if row.get('HostConfig',{}).get('Privileged'):raise ValueError('Unexpected service privilege')
                if set(row['NetworkSettings'].get('Networks',{}))!={network}:raise ValueError('Unexpected network')
                for bindings in (row['NetworkSettings'].get('Ports') or {}).values():
                    if any(b.get('HostIp') not in {'127.0.0.1','::1'} for b in bindings or []):
                        raise ValueError('Public backend binding forbidden')
                image=row.get('Image','')
                if not re.fullmatch(r'sha256:[a-f0-9]{64}',image):raise ValueError('Missing image identity')
                images[role]=image
                if role=='db':database=row['Id']
            if not {'db','auth','rest','storage','kong'}<=images.keys():raise ValueError('Required services missing')
            report['images']=images
            report['phase']='database-query'
            nonce=secrets.token_hex(16)
            sql=("BEGIN; CREATE TEMP TABLE guardian_startup_probe (value text); "
                 "INSERT INTO guardian_startup_probe VALUES ('"+nonce+"'); "
                 "SELECT value || ':' || current_setting('server_version_num') FROM guardian_startup_probe; ROLLBACK;")
            result=command(['docker','exec',database,'psql','-X','-Atq','-U','postgres','-d','postgres',
                            '-v','ON_ERROR_STOP=1','-c',sql],timeout=30).decode().strip()
            value,separator,version=result.partition(':')
            if value!=nonce or separator!=':' or not version.isdigit() or not 170000<=int(version)<180000:
                raise ValueError('Real database round trip failed')
            report['database_query']='passed';report['postgres_major']=17
            report['phase']='complete'
        except Exception as exc:
            report['failure_kind']=type(exc).__name__
            report['signals']=startup_diagnostics(getattr(exc,'output',b'') or str(exc).encode())
        finally:
            try:
                for owned_network in reversed(created):cleanup_project(project,owned_network)
                report['cleanup']='passed'
            except Exception:
                report['cleanup']='failed'
    if report.get('database_query')=='passed' and report['cleanup']=='passed':report['status']='passed'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--network-mode',choices=['bridge','internal','transition'],default='bridge')
    args=parser.parse_args()
    report=run(args.network_mode)
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    raise SystemExit(0 if report['status']=='passed' else 1)
