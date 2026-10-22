import json
from datetime import datetime, timezone

import pytest

from guardian.core.models import Report
from guardian.scheduling.weekly import WeeklyConfig,run_weekly,weekly_slot


def test_malaysia_monday_boundary():
    assert weekly_slot(datetime(2026,10,26,0,59,tzinfo=timezone.utc)).startswith('2026-10-19T09:00')
    assert weekly_slot(datetime(2026,10,26,1,0,tzinfo=timezone.utc)).startswith('2026-10-26T09:00')


def test_weekly_disable_dedup_and_partial_collection(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    sites = tmp_path/'sites.json'
    sites.write_text(json.dumps({'test':{'base_url':'https://example.com','allowed_hosts':['example.com'],'allowed_paths':['/']}}))
    settings = WeeklyConfig(site_id='test',llm='none')
    assert run_weekly(settings)['status'] == 'disabled'
    settings.enabled=True
    calls=[]
    def runner(state,progress):
        calls.append(state)
        return {'report':Report(run_id=str(len(calls)),site_id='test',started_at=datetime.now(timezone.utc).isoformat(),tools={}), 'directory':'reports/test'}
    def speed(*args): raise ValueError('SECRET raw failure')
    result=run_weekly(settings,sites=sites,audit_runner=runner,review_runner=runner,speed_collector=speed)
    assert result['status']=='partial' and len(calls)==2
    assert calls[-1]['include_queries'] is True and calls[-1]['days']==14
    assert 'SECRET' not in json.dumps(result)
    assert run_weekly(settings,sites=sites,audit_runner=runner)['status']=='already-claimed'
    assert len(calls)==2


def test_stop_blocks_weekly(tmp_path,monkeypatch):
    stop=tmp_path/'STOP'
    stop.write_text('stop')
    monkeypatch.setenv('GUARDIAN_STOP_FILE',str(stop))
    with pytest.raises(ValueError): run_weekly(WeeklyConfig(site_id='test',enabled=True))


def test_weekly_routes_reports_to_owner_without_serializing_objects(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    sites=tmp_path/'sites.json'
    sites.write_text(json.dumps({'test':{'base_url':'https://example.com','allowed_hosts':['example.com'],'allowed_paths':['/']}}))
    sent=[]
    def runner(state,progress):
        return {'report':Report(run_id='saved-run',site_id='test',started_at=datetime.now(timezone.utc).isoformat(),tools={})}
    class Bot:
        def __init__(self,*args): pass
        def report(self,run_id,**kwargs):
            sent.append((run_id,kwargs))
            return 'sent'
    settings=WeeklyConfig(site_id='test',enabled=True,llm='none',send_telegram=True,collect_speed=False)
    result=run_weekly(settings,sites=sites,audit_runner=runner,review_runner=runner,bot_factory=Bot)
    assert result['status']=='complete'
    assert sent[0]==('saved-run',{'important_only':True})
    assert sent[1][1]['context'].startswith('weekly:')
    assert result['stages']['review']['run_id']=='saved-run'
    assert 'Report(' not in json.dumps(result)
