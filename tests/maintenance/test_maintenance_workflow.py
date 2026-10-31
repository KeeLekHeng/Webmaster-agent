"""Exercise maintenance output-binding scripts and preview secret boundaries."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import pytest
import yaml


def workflow():
    return yaml.load(Path('.github/workflows/dependency-maintenance.yml').read_text(),Loader=yaml.BaseLoader)


@pytest.mark.parametrize('ref',['refs/heads/main','refs/heads/feature','refs/heads/Main','refs/pull/2/merge'])
@pytest.mark.parametrize('status',['verified','blocked','no-compatible-updates'])
def test_preview_never_emits_publication_authority(tmp_path,ref,status):
    steps=workflow()['jobs']['verify']['steps']
    mode=next(s for s in steps if s.get('id')=='mode')['run']
    binding=next(s for s in steps if s.get('id')=='result')['run'].splitlines()
    output=tmp_path/'output';folder=tmp_path/'maintenance-artifact';folder.mkdir()
    (folder/'verification.json').write_text(json.dumps({'status':status}))
    env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','WINDIR','TEMP','TMP')}
    env.update(GITHUB_REF=ref,GITHUB_OUTPUT=str(output))
    for script in (mode,'\n'.join(binding[1:-1])):
        subprocess.run([sys.executable,'-c',script],cwd=tmp_path,env=env,check=True,capture_output=True,timeout=10)
    fields=dict(line.split('=',1) for line in output.read_text().splitlines())
    assert fields['trusted_main']==str(ref=='refs/heads/main').lower()
    assert fields['eligible']==str(ref=='refs/heads/main' and status=='verified').lower()


def test_writer_and_model_jobs_require_exact_trusted_main_output():
    data=workflow();jobs=data['jobs']
    assert data['permissions']=={'contents':'read'}
    assert 'GUARDIAN_SIS_WRITE_TOKEN' not in json.dumps(jobs['verify'])
    for name in ('publish','interpret'):
        assert jobs[name]['if'].find("needs.verify.outputs.trusted_main == 'true'")>=0
        assert '||' not in jobs[name]['if']
    run=next(s for s in jobs['verify']['steps'] if s.get('name')=='Verify baseline and candidate')
    assert "steps.mode.outputs.trusted_main == 'true'" in run['env']['ANTHROPIC_API_KEY']
    assert "steps.mode.outputs.trusted_main == 'true'" in run['env']['GUARDIAN_COMPAT_REPAIRS_ENABLED']
    for job in jobs.values():
        for step in job['steps']:
            if 'uses' in step:assert re.fullmatch(r'actions/[a-z-]+@[a-f0-9]{40}',step['uses'])
            if step.get('uses','').startswith('actions/checkout@'):
                assert step['with']['persist-credentials']=='false'


@pytest.mark.parametrize('ref,event,sha,allowed',[
    ('refs/heads/feature','workflow_dispatch','a'*40,True),
    ('refs/heads/main','workflow_dispatch','a'*40,False),
    ('refs/heads/feature','schedule','a'*40,False),
    ('refs/heads/feature','workflow_dispatch','main',False),
    ('refs/heads/feature','workflow_dispatch','a'*40+'\nextra=unsafe',False),
])
def test_sis_commit_override_is_confined_to_manual_read_only_preview(tmp_path,ref,event,sha,allowed):
    steps=workflow()['jobs']['verify']['steps']
    mode=next(s for s in steps if s.get('id')=='mode')
    checkout=next(s for s in steps if s.get('with',{}).get('repository')=='KeeLekHeng/sisweb')
    assert steps.index(mode)<steps.index(checkout)
    assert checkout['with']['ref']=='${{ steps.mode.outputs.sis_ref }}'
    output=tmp_path/'output'
    env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','WINDIR','TEMP','TMP')}
    env.update(GITHUB_REF=ref,GITHUB_EVENT_NAME=event,PREVIEW_SIS_SHA=sha,GITHUB_OUTPUT=str(output))
    result=subprocess.run([sys.executable,'-c',mode['run']],env=env,capture_output=True,timeout=10)
    assert (result.returncode==0)==allowed
    if allowed:
        assert dict(line.split('=',1) for line in output.read_text().splitlines())=={'trusted_main':'false','sis_ref':sha}
    else:assert not output.exists()
