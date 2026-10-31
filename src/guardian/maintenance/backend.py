"""Trusted local Supabase lifecycle. Candidate code/SQL never executes on the host."""
import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
import httpx

if __package__:
    from .sandbox import command
else:
    from sandbox import command

VERSION = '2.119.0'
PROJECT = re.compile(r'guardian-(?:local|[0-9]{1,20})-[a-f0-9]{16}')
EXCLUDE = 'studio,imgproxy,realtime,edge-runtime,logflare,vector,postgres-meta,supavisor'


def startup_diagnostics(output):
    """Fixed startup categories only; CLI output may contain local test credentials."""
    text=output.decode('utf-8',errors='replace').lower()
    patterns={
        'image-download':r'failed to pull|pull access denied|manifest unknown|download.*failed|toomanyrequests',
        'dns-resolution':r'no such host|name resolution|lookup .*:|enotfound',
        'connection-refused':r'connection refused|econnrefused',
        'health-check':r'unhealthy|health check|healthcheck|failed to connect to postgres',
        'config-schema':r'invalid config|failed to parse|cannot unmarshal|has invalid keys|unsupported.*version',
        'port-conflict':r'port is already allocated|address already in use|bind.*failed',
        'service-network':r'network.*not found|no route to host|network is unreachable',
        'startup-timeout':r'timed out|context deadline exceeded',
        'permission-denied':r'permission denied|operation not permitted',
        'local-database-target':r'(?:127\.0\.0\.1|localhost|\[::1\]|::1):54322',
        'public-ecr-target':r'public\.ecr\.aws',
        'github-registry-target':r'ghcr\.io',
        'docker-registry-target':r'(?:registry-1\.)?docker\.io',
        'postgres-connection':r'failed to connect to postgres|dbconnecterror',
        'service-migration':r'migrate job|migration.*(?:failed|error)|dbsetuperror',
        'host-mount-rejected':r'unexpected backend host mount',
        'volume-rejected':r'unowned backend volume',
        'public-binding-rejected':r'public backend port forbidden|public backend binding forbidden',
        'network-attachment-rejected':r'unexpected backend network attachment|isolation transition incomplete',
        'required-service-missing':r'required real service missing|required services missing',
        'egress-probe-failed':r'guardian_network_probe_failed|egress still available',
    }
    return [label for label,pattern in patterns.items() if re.search(pattern,text)]


def migration_files(workspace):
    folder=Path(workspace)/'supabase'/'migrations'
    if folder.is_symlink() or folder.parent.is_symlink():raise ValueError('Unsafe migrations directory')
    files=sorted(folder.glob('*.sql'))
    if not 1<=len(files)<=100:raise ValueError('Missing/budgeted migrations')
    result=[]
    for path in files:
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[0-9]{12,14}_[a-z0-9_]+\.sql',path.name):
            raise ValueError('Unsafe migration identity')
        if not 0<path.stat().st_size<=60000:raise ValueError('Migration input budget')
        raw=path.read_bytes()
        if not 0<len(raw)<=60000 or b'\0' in raw:raise ValueError('Migration input budget')
        text=raw.decode('utf-8')
        if re.search(r'(?m)^\s*\\',text):raise ValueError('psql meta-command forbidden')
        result.append((path.name,text,hashlib.sha256(raw).hexdigest()))
    if sum(len(text.encode()) for _,text,_ in result)>1024*1024:raise ValueError('Migration aggregate budget')
    return result


def run_id():
    value=os.getenv('GITHUB_RUN_ID','local')
    if not re.fullmatch(r'local|[0-9]{1,20}',value):raise ValueError('Invalid backend run identity')
    return value


def owned_containers(project):
    if not PROJECT.fullmatch(project):raise ValueError('Invalid owned project')
    raw=command(['docker','ps','-aq','--filter','label=com.supabase.cli.project='+project]).decode().split()
    if len(raw)>12 or any(not re.fullmatch(r'[a-f0-9]{12,64}',x) for x in raw):raise ValueError('Unexpected service inventory')
    if not raw:return []
    rows=json.loads(command(['docker','inspect',*raw]))
    if any(r.get('Config',{}).get('Labels',{}).get('com.supabase.cli.project')!=project for r in rows):
        raise ValueError('Service ownership mismatch')
    return rows


def cleanup_project(project, network):
    rows=owned_containers(project)
    volumes={m.get('Name') for r in rows for m in r.get('Mounts',[])
             if m.get('Type')=='volume' and m.get('Name','').endswith('_'+project)}
    for row in rows:command(['docker','rm','--force',row['Id']],timeout=60)
    names=set(command(['docker','volume','ls','-q','--filter','label=com.supabase.cli.project='+project]).decode().split()) | volumes
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('Invalid owned volume')
        command(['docker','volume','rm',name],timeout=60)
    if network:
        row=json.loads(command(['docker','network','inspect',network]))[0]
        if row.get('Labels',{}).get('guardian.project')!=project or row.get('Containers'):
            raise ValueError('Network cleanup ownership mismatch')
        command(['docker','network','rm',network],timeout=60)


def isolate_network(project, source, target):
    """Move trusted services off bootstrap networking before any website input."""
    for name,internal in ((source,False),(target,True)):
        row=json.loads(command(['docker','network','inspect',name]))[0]
        if row.get('Labels',{}).get('guardian.project')!=project or row.get('Internal') is not internal:
            raise ValueError('Unexpected network ownership/mode')
    rows=owned_containers(project)
    if not rows:raise ValueError('No services to isolate')
    for row in rows:
        attachments=row['NetworkSettings'].get('Networks',{})
        if set(attachments)!={source}:raise ValueError('Unexpected bootstrap attachments')
        name=row['Name'].lstrip('/')
        if not re.fullmatch(r'supabase_[a-z_]+_'+re.escape(project),name):raise ValueError('Unsafe service alias')
        aliases={name,*filter(None,attachments[source].get('Aliases') or [])}
        if any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',alias) for alias in aliases):raise ValueError('Unsafe network alias')
        args=['docker','network','connect']
        for alias in sorted(aliases):args+=['--alias',alias]
        command([*args,target,row['Id']])
        command(['docker','network','disconnect',source,row['Id']])
    for row in owned_containers(project):
        if set(row['NetworkSettings'].get('Networks',{}))!={target}:raise ValueError('Isolation transition incomplete')


class Backend:
    def __init__(self, sandbox, workspace):
        self.sandbox,self.workspace=sandbox,Path(workspace)
        self.project='guardian-'+run_id()+'-'+uuid.uuid4().hex[:16]
        self.network='guardian-net-'+uuid.uuid4().hex[:16]
        self.bootstrap_network='guardian-bootstrap-'+uuid.uuid4().hex[:16]
        self.root=None;self.network_created=False;self.bootstrap_created=False
        self.gateway='supabase_kong_'+self.project
        self.environment={}
        self.evidence={'mode':'real','cli_version':VERSION,'postgres_major':17,'cleanup':'pending','phase':'preflight'}

    def cli(self,*args,timeout=300):
        # A fresh HOME prevents reading local CLI login credentials or profiles.
        env={k:v for k,v in os.environ.items() if k in {'PATH','SystemRoot','WINDIR','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG'}}
        env['HOME']=str(self.root/'home')
        return command(['supabase',*args,'--workdir',str(self.root),'--network-id',self.bootstrap_network],env=env,timeout=timeout)

    def audit(self):
        network=json.loads(command(['docker','network','inspect',self.network]))[0]
        if not network.get('Internal') or network.get('Labels',{}).get('guardian.project')!=self.project:
            raise ValueError('Backend network is not private/owned')
        rows=owned_containers(self.project)
        roles={};images={}
        for row in rows:
            name=row['Name'].lstrip('/')
            match=re.fullmatch(r'supabase_([a-z_]+)_'+re.escape(self.project),name)
            if not match:raise ValueError('Unexpected backend service identity')
            role=match[1];roles[role]=name
            if row.get('State',{}).get('Status')!='running':raise ValueError('Backend service is not running')
            host=row['HostConfig']
            if host.get('Privileged') or host.get('PidMode')=='host' or host.get('NetworkMode')=='host':
                raise ValueError('Privileged backend service forbidden')
            if set(row['NetworkSettings'].get('Networks',{}))!={self.network}:
                raise ValueError('Unexpected backend network attachment')
            for bindings in (row['NetworkSettings'].get('Ports') or {}).values():
                if any(b.get('HostIp') not in {'127.0.0.1','::1'} for b in bindings or []):
                    raise ValueError('Public backend port forbidden')
            for mount in row.get('Mounts',[]):
                if mount['Type']=='bind':
                    source=Path(mount['Source']).resolve()
                    if not source.is_relative_to(self.root.resolve()):raise ValueError('Unexpected backend host mount')
                elif mount['Type']=='volume':
                    if not mount.get('Name','').endswith('_'+self.project):raise ValueError('Unowned backend volume')
                elif mount['Type']!='tmpfs':raise ValueError('Unexpected backend mount type')
            image=row['Image']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',image):raise ValueError('Missing backend image identity')
            images[role]=image
            memory='1g' if role=='db' else ('384m' if role=='storage' else '256m')
            command(['docker','update','--memory',memory,'--memory-swap',memory,'--cpus','0.5','--pids-limit','192',row['Id']])
        if not {'db','auth','rest','storage','kong'}<=roles.keys():raise ValueError('Required real service missing')
        gateway=next(row for row in rows if row['Name'].lstrip('/')==roles['kong'])
        address=ipaddress.ip_address(gateway['NetworkSettings']['Networks'][self.network]['IPAddress'])
        subnets=[ipaddress.ip_network(item['Subnet']) for item in network.get('IPAM',{}).get('Config',[]) if item.get('Subnet')]
        if address.version!=4 or not address.is_private or address.is_loopback or not any(address in subnet for subnet in subnets):
            raise ValueError('Gateway address is outside owned private network')
        self.api_origin='http://'+str(address)+':8000'
        self.db=roles['db'];self.gateway=roles['kong'];self.rest=roles['rest'];self.evidence['images']=images
        self.evidence['isolation']='passed'

    def sql(self,text):
        if len(text.encode())>64000:raise ValueError('SQL command budget')
        # -c sends this entire BEGIN-prefixed string to PostgreSQL, not psql's
        # stdin meta-command interpreter. Never invoke a shell on candidate SQL.
        return command(['docker','exec',self.db,'psql','-X','-Atq','-U','postgres','-d','postgres',
                        '-v','ON_ERROR_STOP=1','-c','BEGIN;\n'+text+'\n;COMMIT;'],timeout=120)

    def reload_schema(self):
        # Documented PostgREST cache reload, independent of a LISTEN connection
        # that may be reconnecting after the trusted network transition.
        command(['docker','kill','--signal=SIGUSR1',self.rest],timeout=30)

    def request(self,method,path,*,body=None,content=None,service=False,token=None,allowed=(200,201,204)):
        if not re.fullmatch(r'/(?:rest|auth|storage)/v1/[A-Za-z0-9_/?=.,%&-]+',path):
            raise ValueError('Backend API path outside test scope')
        key=self.service if service else self.anon
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=20) as client:
            response=client.request(method,self.api_origin+path,
                headers={'apikey':key,'Authorization':'Bearer '+(token or key),'Prefer':'return=representation',
                         'Content-Type':'application/octet-stream' if content is not None else 'application/json'},json=body,content=content)
        if response.status_code not in allowed:
            self.evidence['api_failure']={'method':method,'service':path.split('/')[1],'status':response.status_code}
            try:
                error=response.json()
                code=error.get('code')
                if isinstance(code,str) and re.fullmatch(r'PGRST[0-9]{3}|42501|42P01|23505|23502|23503|23514',code):
                    self.evidence['api_failure']['code']=code
                auth_code=error.get('error_code',code)
                if auth_code in {'email_provider_disabled','email_address_invalid','signup_disabled','weak_password',
                                 'validation_failed','invalid_credentials','email_not_confirmed','unexpected_failure',
                                 'bad_jwt','user_already_exists'}:
                    self.evidence['api_failure']['auth_code']=auth_code
                message=error.get('message','').lower()
                for label,pattern in {'gateway-no-route':r'no route matched|no route found',
                                      'schema-cache-miss':r'schema cache|could not find the table',
                                      'permission-denied':r'permission denied',
                                      'upstream-unavailable':r'upstream|name resolution'}.items():
                    if re.search(pattern,message):self.evidence['api_failure']['category']=label
            except (ValueError,AttributeError,TypeError):pass
            raise ValueError('Required real backend request failed')
        self.evidence.pop('api_failure',None)
        if len(response.content)>1024*1024:raise ValueError('Backend response budget')
        return response

    def seed(self):
        self.evidence['phase']='migrations'
        migrations=migration_files(self.workspace)
        self.evidence['migrations']={name:sha for name,_,sha in migrations}
        for _,sql,_ in migrations:self.sql(sql)
        probe=json.loads(self.sql("SELECT pg_catalog.json_build_object("
            "'blogs_present',pg_catalog.to_regclass('public.blogs') IS NOT NULL,"
            "'anon_schema_usage',pg_catalog.has_schema_privilege('anon','public','USAGE'),"
            "'anon_blog_select',pg_catalog.has_table_privilege('anon','public.blogs','SELECT'),"
            "'service_blog_select',pg_catalog.has_table_privilege('service_role','public.blogs','SELECT'))::text;"))
        if not isinstance(probe,dict) or set(probe)!={'blogs_present','anon_schema_usage','anon_blog_select','service_blog_select'} or any(type(v)is not bool for v in probe.values()):
            raise ValueError('Invalid schema inspection')
        self.evidence['schema_probe']=probe
        self.sql("NOTIFY pgrst, 'reload schema';")
        self.reload_schema()
        self.evidence['phase']='schema-cache-readiness'
        for attempt in range(120):
            try:
                self.request('GET','/rest/v1/blogs?select=slug&limit=1')
                break
            except ValueError:
                if attempt==119:raise
                if attempt%10==9 and self.evidence.get('api_failure',{}).get('code')=='PGRST205':self.reload_schema()
                time.sleep(.5)
        self.evidence['schema_cache']='passed'
        # Literal content is parsed in a credential-free container, never imported on host.
        self.evidence['phase']='fixture-parser'
        posts=json.loads(self.sandbox.run(self.workspace,['node','/trusted/fixture-data.cjs']))
        self.evidence['phase']='seed'
        if not isinstance(posts,list) or not 1<=len(posts)<=50:raise ValueError('Invalid public seed')
        self.evidence['seed_sha256']=hashlib.sha256(json.dumps(posts,sort_keys=True).encode()).hexdigest()
        categories={}
        for post in posts:
            if not isinstance(post,dict) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',post.get('slug','')):
                raise ValueError('Invalid fixture slug')
            row={'slug':post['slug'],'title':post['title'],'summary':post['summary'],'status':'published',
                 'published_at':post['publishedAt'],'categories':post.get('categories',[]),
                 'featured_image':post.get('featuredImage'),'seo_title':post['seoTitle'],
                 'seo_description':post['seoDescription'],'blocks':post['blocks']}
            saved=self.request('POST','/rest/v1/blogs',body=row,service=True).json()[0]
            for category in post.get('categories',[]):
                if not isinstance(category,str) or not 1<=len(category)<=100:raise ValueError('Invalid fixture category')
                if category not in categories:
                    saved_category=self.request('POST','/rest/v1/categories',body={'name':category,
                         'slug':re.sub(r'[^a-z0-9]+','-',category.lower()).strip('-')},service=True).json()[0]
                    categories[category]=saved_category['id']
                self.request('POST','/rest/v1/blog_categories',body={'blog_id':saved['id'],'category_id':categories[category]},service=True)
        self.request('POST','/rest/v1/blogs',body={'slug':'guardian-private-draft','title':'Synthetic private draft',
                     'summary':'Must not be anonymously readable','status':'draft'},service=True)
        self.sql("UPDATE public.career_job_publications SET closing_date='2099-12-31', paused=false, summary='Synthetic CI job listing', description='Synthetic CI career description.', responsibilities='Synthetic responsibilities.', requirements='Synthetic requirements.'; NOTIFY pgrst, 'reload schema';")
        self.evidence['schema']='passed'
        # Schema/RLS proof uses real PostgREST with its anonymous role, not service bypass.
        public=self.request('GET','/rest/v1/blogs?select=slug&status=eq.published').json()
        private=self.request('GET','/rest/v1/blogs?select=slug&slug=eq.guardian-private-draft').json()
        career=self.request('GET','/rest/v1/career_job_publications?select=slug&slug=eq.admin-assistant').json()
        if len(public)!=len(posts) or private!=[] or len(career)!=1:raise ValueError('Real RLS/seed probe failed')
        self.evidence['rls']='passed'
        self.evidence['phase']='auth-admin-create'
        email='guardian-admin@example.com';password=secrets.token_urlsafe(24)
        user=self.request('POST','/auth/v1/admin/users',service=True,
                          body={'email':email,'password':password,'email_confirm':True}).json()
        identity=user.get('id')
        if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9-]{36}',identity):raise ValueError('Invalid test account')
        self.evidence['phase']='auth-public-signup-denied'
        denied=self.request('POST','/auth/v1/signup',body={'email':'guardian-signup@example.com','password':password},allowed=(400,422)).json()
        if denied.get('error_code',denied.get('code'))!='signup_disabled':raise ValueError('Public registration is not confirmed disabled')
        self.evidence['public_signup']='denied'
        self.evidence['phase']='auth-password'
        auth=self.request('POST','/auth/v1/token?grant_type=password',body={'email':email,'password':password}).json()
        self.evidence['phase']='auth-user-check'
        verified=self.request('GET','/auth/v1/user',token=auth['access_token']).json()
        if verified.get('id')!=identity:raise ValueError('Real Auth token verification failed')
        self.evidence['auth']='passed'
        self.evidence['phase']='storage'
        marker=b'guardian-storage-probe'
        self.request('POST','/storage/v1/object/blog-media/guardian-probe.txt',service=True,content=marker)
        stored=self.request('GET','/storage/v1/object/public/blog-media/guardian-probe.txt').content
        if stored!=marker:raise ValueError('Real Storage round trip failed')
        self.request('DELETE','/storage/v1/object/blog-media',service=True,body={'prefixes':['guardian-probe.txt']})
        self.evidence['storage']='passed'
        self.environment={'E2E_TEST_DATA':'0','ADMIN_SESSION_SECRET':secrets.token_hex(32),
            'NEXT_PUBLIC_SUPABASE_URL':'http://127.0.0.1:8000','NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY':self.anon,
            'SUPABASE_SECRET_KEY':self.service,'ADMIN_USER_ID':identity,'ADMIN_EMAIL':email,
            'NEXT_PUBLIC_SITE_URL':'http://localhost:3100','APP_URL':'http://localhost:3100',
            'GUARDIAN_TEST_ADMIN_EMAIL':email,'GUARDIAN_TEST_ADMIN_PASSWORD':password,'REQUIRE_ADMIN_MFA':'true'}

    def __enter__(self):
        try:
            if platform.system()!='Linux':raise ValueError('Real backend requires isolated Linux runner')
            if command(['supabase','--version']).decode().strip()!=VERSION:raise ValueError('Unreviewed backend CLI')
            memory=re.search(r'MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text())
            if not memory or int(memory[1])<6*1024*1024:raise ValueError('Insufficient disposable runner capacity')
            self.root=Path(tempfile.mkdtemp(prefix='guardian-backend-'))
            (self.root/'supabase').mkdir();(self.root/'home').mkdir()
            config=(self.sandbox.trusted/'backend-config.toml').read_text().replace('GUARDIAN_PROJECT',self.project)
            (self.root/'supabase'/'config.toml').write_text(config)
            # The CLI's own database bootstrap needs its loopback published port.
            # Only trusted service images/configuration exist during this phase.
            command(['docker','network','create','--label','guardian.project='+self.project,
                     '--opt','com.docker.network.bridge.host_binding_ipv4=127.0.0.1',self.bootstrap_network])
            self.bootstrap_created=True
            print(json.dumps({'sandbox_stage':'real-backend','status':'starting'}),flush=True)
            try:
                self.cli('start','--exclude',EXCLUDE,timeout=480)
            except Exception as exc:
                self.evidence['startup_signals']=startup_diagnostics(getattr(exc,'output',b'') or b'')
                services={}
                for row in owned_containers(self.project):
                    name=row.get('Name','').lstrip('/')
                    match=re.fullmatch(r'supabase_([a-z_]+)_'+re.escape(self.project),name)
                    if not match:continue
                    state=row.get('State',{})
                    services[match[1]]={'status':state.get('Status'),'exit_code':state.get('ExitCode'),
                                       'health':state.get('Health',{}).get('Status')}
                self.evidence['startup_services']=services
                raise
            status=json.loads(self.cli('status','--output','json'))
            self.anon=status.get('ANON_KEY');self.service=status.get('SERVICE_ROLE_KEY')
            if not all(isinstance(k,str) and 20<len(k)<2048 for k in (self.anon,self.service)):
                raise ValueError('Missing local API credentials')
            self.evidence['phase']='isolation-transition'
            command(['docker','network','create','--internal','--label','guardian.project='+self.project,
                     '--opt','com.docker.network.bridge.host_binding_ipv4=127.0.0.1',self.network])
            self.network_created=True
            isolate_network(self.project,self.bootstrap_network,self.network)
            self.evidence['phase']='isolation-audit'
            self.audit()
            self.sandbox.backend=self
            try:
                network_probe=json.loads(self.sandbox.run(self.workspace,['node','/trusted/network-probe.cjs'],timeout=15))
                if network_probe!={'tcp_blocked':True,'dns_blocked':True}:raise ValueError('Backend egress probe failed')
                self.evidence['egress_probe']='passed'
            finally:self.sandbox.backend=None
            self.seed()
            self.evidence['phase']='ready'
            return self
        except Exception as exc:
            self.evidence['signals']=startup_diagnostics(getattr(exc,'output',b'') or str(exc).encode())
            self.close()
            raise

    def close(self):
        if self.root is None:return
        try:
            networks=([self.network] if self.network_created else [])+([self.bootstrap_network] if self.bootstrap_created else [])
            for network in networks or [None]:cleanup_project(self.project,network)
            self.evidence['cleanup']='passed'
            root=self.root.resolve()
            if root.parent!=Path(tempfile.gettempdir()).resolve() or not root.name.startswith('guardian-backend-'):
                raise ValueError('Unexpected cleanup directory')
            shutil.rmtree(root)
        except Exception:
            self.evidence['cleanup']='failed'
            raise

    def __exit__(self,*args):self.close()


def cleanup_owned():
    rows=command(['docker','ps','-aq','--filter','label=com.supabase.cli.project']).decode().split()
    inspected=json.loads(command(['docker','inspect',*rows])) if rows else []
    projects={r.get('Config',{}).get('Labels',{}).get('com.supabase.cli.project','') for r in inspected}
    networks=command(['docker','network','ls','-q','--filter','label=guardian.project']).decode().split()
    network_rows=json.loads(command(['docker','network','inspect',*networks])) if networks else []
    projects.update(n.get('Labels',{}).get('guardian.project','') for n in network_rows)
    for project in projects:
        if not re.fullmatch(r'guardian-'+re.escape(run_id())+r'-[a-f0-9]{16}',project):continue
        nets=[n['Name'] for n in network_rows if n.get('Labels',{}).get('guardian.project')==project]
        if len(nets)>2:raise ValueError('Unexpected owned network inventory')
        for network in nets or [None]:cleanup_project(project,network)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cleanup-owned',action='store_true')
    if parser.parse_args().cleanup_owned:cleanup_owned()
