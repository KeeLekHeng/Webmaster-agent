import json
from datetime import datetime, timezone
import pytest
from guardian.maintenance.policy import audit, changes, select, security_gate, verification, STAGES


def package(version='1.0.0', **extra):
    return json.dumps({'name': 'test', 'packageManager': 'pnpm@10.18.2',
                       'dependencies': {'example': version}, 'scripts': {'build': 'next build'}, **extra}).encode()


@pytest.mark.parametrize('old,new', [('1.0.0','1.1.0'),('^1.0.0','^1.0.2'),('0.2.0','0.2.1')])
def test_compatible_upgrades(old, new):
    assert len(changes(package(old), package(new))) == 1


@pytest.mark.parametrize('old,new', [('1.0.0','2.0.0'),('0.2.0','0.3.0'),('1.0.0','1.0.0-beta'),
                                    ('1.0.0','https://example.com'),('1.0.0','^1.0.1'),('1.0.1','1.0.0')])
def test_incompatible_changes_blocked(old, new):
    with pytest.raises(ValueError): changes(package(old), package(new))


def test_script_and_dependency_set_cannot_change():
    with pytest.raises(ValueError): changes(package(), package('1.0.1', scripts={'build': 'evil'}))
    with pytest.raises(ValueError): changes(package(), package(dependencies={'other': '1.0.1'}))


def test_release_cooldown_and_stable_policy():
    now = datetime(2026,10,23,tzinfo=timezone.utc)
    value = {'versions': {'1.0.1': {}, '1.1.0': {}, '2.0.0': {}, '1.2.0-beta': {}},
             'time': {'1.0.1': '2026-10-01T00:00:00Z','1.1.0':'2026-10-22T00:00:00Z','2.0.0':'2026-10-01T00:00:00Z'}}
    assert select('1.0.0', value, now=now) == '1.0.1'
    assert select('1.0.0', value, urgent=True, now=now) == '1.1.0'
    value['versions']['1.1.0']['deprecated'] = 'unsafe'
    assert select('1.0.0', value, urgent=True, now=now) == '1.0.1'
    assert select('^1.0.0', value, now=now, installed='1.0.1') == '^1.0.0'


def test_registry_failure_is_not_clean_audit():
    with pytest.raises(ValueError): audit({'error': {'message': 'failed'}})
    with pytest.raises(ValueError): audit({'advisories': {}, 'metadata': {'vulnerabilities': {'high': 1}}})
    assert audit({'advisories': {}, 'metadata': {'vulnerabilities': {'high': 0}}}) == []


def test_advisory_delta_gate():
    old = [{'id':'1','package':'example','severity':'moderate'}]
    assert security_gate(old, [])
    assert security_gate(old, old)
    assert not security_gate(old, [{'id':'1','package':'example','severity':'high'}])
    assert not security_gate([], old)


def test_missing_stage_cannot_be_verified():
    report = {'version':1,'base_sha':'a'*40,'updates':[{}], 'security_not_worsened':True,
              'baseline':{s:'passed' for s in STAGES}, 'candidate':{s:'passed' for s in STAGES}}
    assert verification(report)
    del report['candidate']['browser']
    with pytest.raises(ValueError): verification(report)
