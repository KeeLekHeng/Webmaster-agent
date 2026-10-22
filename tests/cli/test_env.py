import os
import sys

from guardian.cli import main


def test_cli_loads_local_env_without_echo_or_interpolation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GUARDIAN_MODEL", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.setenv("AGENT_ENABLED", "false")
    (tmp_path / ".env").write_text(
        "ANTHROPIC_API_KEY=synthetic-${GUARDIAN_MODEL}\nGUARDIAN_MODEL=test-model\nAGENT_ENABLED=true\n")
    monkeypatch.setattr(sys, "argv", ["guardian", "explain"])
    assert main() == 0
    assert os.environ["ANTHROPIC_API_KEY"] == "synthetic-${GUARDIAN_MODEL}"
    assert os.environ["GUARDIAN_MODEL"] == "test-model"
    assert os.environ["AGENT_ENABLED"] == "false"
    assert "synthetic-" not in capsys.readouterr().out


def test_weekly_uses_configured_storage_and_site_paths(tmp_path,monkeypatch):
    import json
    from guardian.scheduling import weekly
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('AGENT_ENABLED','true')
    monkeypatch.setenv('GUARDIAN_CONFIG','/app/config/sites.json')
    monkeypatch.setenv('GUARDIAN_OUTPUT','reports-custom')
    monkeypatch.setenv('GUARDIAN_DB','data/custom.sqlite3')
    schedule=tmp_path/'weekly.json'
    schedule.write_text(json.dumps({'site_id':'test','enabled':False}))
    captured={}
    def runner(settings,**kwargs):
        captured.update(kwargs)
        return {'status':'disabled'}
    monkeypatch.setattr(weekly,'run_weekly',runner)
    monkeypatch.setattr(sys,'argv',['guardian','weekly-digest','--schedule-config',str(schedule)])
    assert main()==0
    assert captured=={'sites':'/app/config/sites.json','output':'reports-custom','history':'data/custom.sqlite3'}
