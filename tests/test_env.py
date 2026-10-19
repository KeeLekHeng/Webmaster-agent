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
