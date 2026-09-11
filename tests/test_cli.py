from pathlib import Path

from typer.testing import CliRunner

from fpl_agent.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_validate_command():
    result = runner.invoke(
        app,
        [
            "validate",
            "--players",
            str(ROOT / "examples/players.csv"),
            "--team",
            str(ROOT / "examples/team.yaml"),
            "--rules",
            str(ROOT / "rules/2026_27.yaml"),
        ],
    )
    assert result.exit_code == 0
    assert "Valid 2026/27 squad" in result.stdout


def test_recommend_command_writes_markdown_and_json(tmp_path):
    markdown = tmp_path / "report.md"
    json_report = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "recommend",
            "--gameweek",
            "4",
            "--players",
            str(ROOT / "examples/players.csv"),
            "--fixtures",
            str(ROOT / "examples/fixtures.csv"),
            "--team",
            str(ROOT / "examples/team.yaml"),
            "--rules",
            str(ROOT / "rules/2026_27.yaml"),
            "--output",
            str(markdown),
            "--json-output",
            str(json_report),
        ],
    )
    assert result.exit_code == 0
    assert "Decision summary" in markdown.read_text()
    assert '"gameweek":4' in json_report.read_text().replace(" ", "").replace("\n", "")


def test_agent_command_suppresses_unverified_model_draft(monkeypatch):
    def fake_run(agent, prompt):
        agent.registry.call(
            "calculate_recommendation", {"gameweek": 4, "horizon": 5, "max_transfers": 2}
        )
        return "INCORRECT MODEL CLAIM"

    monkeypatch.setattr("fpl_agent.cli.OllamaAgent.run", fake_run)
    result = runner.invoke(
        app,
        [
            "agent",
            "--gameweek",
            "4",
            "--players",
            str(ROOT / "examples/players.csv"),
            "--fixtures",
            str(ROOT / "examples/fixtures.csv"),
            "--team",
            str(ROOT / "examples/team.yaml"),
            "--rules",
            str(ROOT / "rules/2026_27.yaml"),
        ],
    )
    assert result.exit_code == 0
    assert "FPL Agent recommendation" in result.stdout
    assert "INCORRECT MODEL CLAIM" not in result.stdout
    assert "rendered from validated tool output" in result.stdout
