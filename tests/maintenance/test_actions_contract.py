"""Check privilege and activation boundaries in the actual workflow, not a fixture."""
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return yaml.load((ROOT/'.github/workflows/dependency-maintenance.yml').read_text(),Loader=yaml.BaseLoader)


def test_workflow_defaults_and_publisher_separation():
    data=workflow()
    assert set(data['on'])=={'workflow_dispatch','schedule'}
    assert data['permissions']=={'contents':'read'}
    assert 'GUARDIAN_MAINTENANCE_ENABLED' in data['jobs']['verify']['if']
    publish=data['jobs']['publish']
    assert publish['needs']=='verify'
    assert 'GUARDIAN_DEPENDENCY_PRS_ENABLED' in publish['if']
    for step in publish['steps']:
        assert 'docker ' not in step.get('run','')
        if 'GUARDIAN_SIS_WRITE_TOKEN' in step.get('env',{}):
            assert 'guardian.maintenance.publisher' in step['run']
        if 'checkout@' in step.get('uses',''):
            assert step['with']['persist-credentials']=='false'


def test_actions_are_pinned_and_install_inputs_exist():
    for job in workflow()['jobs'].values():
        for step in job['steps']:
            if 'uses' in step:
                assert re.fullmatch(r'actions/[a-z-]+@[a-f0-9]{40}',step['uses'])
            for filename in re.findall(r'pip install -r ([A-Za-z0-9_.-]+)',step.get('run','')):
                assert (ROOT/filename).is_file()
