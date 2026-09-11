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


def test_evidence_commands_import_list_and_resolve(tmp_path):
    database = tmp_path / "evidence.db"
    init_result = runner.invoke(app, ["evidence", "init", "--db", str(database)])
    assert init_result.exit_code == 0

    import_result = runner.invoke(
        app,
        [
            "evidence",
            "import",
            str(ROOT / "examples/evidence.yaml"),
            "--db",
            str(database),
            "--players",
            str(ROOT / "examples/players.csv"),
        ],
    )
    assert import_result.exit_code == 0
    assert "Imported 2" in import_result.stdout

    list_result = runner.invoke(
        app,
        [
            "evidence",
            "list",
            "--db",
            str(database),
            "--players",
            str(ROOT / "examples/players.csv"),
            "--player",
            "Flint",
        ],
    )
    assert list_result.exit_code == 0
    assert "Flint" in list_result.stdout
    assert "accepted" in list_result.stdout

    resolve_result = runner.invoke(
        app,
        [
            "evidence",
            "resolve",
            "--db",
            str(database),
            "--players",
            str(ROOT / "examples/players.csv"),
            "--as-of",
            "2026-09-12T00:00:00Z",
        ],
    )
    assert resolve_result.exit_code == 0
    assert "Flint" in resolve_result.stdout
    assert "False" in resolve_result.stdout


def test_evidence_as_of_requires_timezone(tmp_path):
    database = tmp_path / "evidence.db"
    runner.invoke(app, ["evidence", "init", "--db", str(database)])
    result = runner.invoke(
        app,
        [
            "evidence",
            "resolve",
            "--db",
            str(database),
            "--as-of",
            "2026-09-12T00:00:00",
        ],
    )
    assert result.exit_code != 0
    assert "must include a timezone" in str(result.exception)


def test_research_requires_environment_key(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "research",
            "--player",
            "Flint",
            "--allowed-domain",
            "club.example",
            "--players",
            str(ROOT / "examples/players.csv"),
        ],
    )
    assert result.exit_code == 1
    assert "BRAVE_SEARCH_API_KEY" in result.stderr
