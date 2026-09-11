"""Command-line interface for validation, deterministic recommendations, and the agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import httpx
import typer

from fpl_agent.agent import OllamaAgent, build_tool_registry
from fpl_agent.data import load_fixtures, load_players, load_rules, load_team
from fpl_agent.models import RecommendationReport
from fpl_agent.reporting import render_markdown
from fpl_agent.rules import RulesEngine
from fpl_agent.service import build_recommendation

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Local-first, explainable FPL analysis. No account changes are performed.",
)

DEFAULT_PLAYERS = Path("examples/players.csv")
DEFAULT_FIXTURES = Path("examples/fixtures.csv")
DEFAULT_TEAM = Path("examples/team.yaml")
DEFAULT_RULES = Path("rules/2026_27.yaml")


def _load_inputs(players_path: Path, fixtures_path: Path, team_path: Path, rules_path: Path):
    players = load_players(players_path)
    fixtures = load_fixtures(fixtures_path)
    team = load_team(team_path)
    rules = load_rules(rules_path)
    return players, fixtures, team, rules


@app.command()
def validate(
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    team_path: Annotated[Path, typer.Option("--team")] = DEFAULT_TEAM,
    rules_path: Annotated[Path, typer.Option("--rules")] = DEFAULT_RULES,
) -> None:
    """Validate a manually supplied squad against the season rule pack."""
    players = load_players(players_path)
    team = load_team(team_path)
    rules = load_rules(rules_path)
    RulesEngine(rules, players).validate_team(team)
    typer.echo(
        f"Valid {rules.season} squad: {len(team.squad)} players, "
        f"{team.free_transfers} free transfer(s)."
    )


@app.command()
def recommend(
    gameweek: Annotated[int, typer.Option("--gameweek", "-g", min=1)],
    horizon: Annotated[int, typer.Option("--horizon", "-h", min=1, max=8)] = 5,
    max_transfers: Annotated[int, typer.Option("--max-transfers", min=0, max=2)] = 2,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    fixtures_path: Annotated[Path, typer.Option("--fixtures")] = DEFAULT_FIXTURES,
    team_path: Annotated[Path, typer.Option("--team")] = DEFAULT_TEAM,
    rules_path: Annotated[Path, typer.Option("--rules")] = DEFAULT_RULES,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = None,
) -> None:
    """Compute rules-valid transfer, lineup, bench, and captain recommendations."""
    players, fixtures, team, rules = _load_inputs(
        players_path, fixtures_path, team_path, rules_path
    )
    report = build_recommendation(
        players, fixtures, team, rules, gameweek, horizon, max_transfers
    )
    markdown = render_markdown(report, players)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        typer.echo(f"Wrote Markdown report to {output}")
    else:
        typer.echo(markdown)
    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote JSON report to {json_output}")


@app.command(name="agent")
def run_agent(
    gameweek: Annotated[int, typer.Option("--gameweek", "-g", min=1)],
    prompt: Annotated[
        str,
        typer.Option("--prompt", "-p"),
    ] = "Analyse my team and explain the best plan.",
    model: Annotated[str, typer.Option("--model")] = os.getenv(
        "FPL_AGENT_MODEL", "qwen3:8b"
    ),
    ollama_url: Annotated[str, typer.Option("--ollama-url")] = os.getenv(
        "FPL_AGENT_OLLAMA_URL", "http://localhost:11434"
    ),
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    fixtures_path: Annotated[Path, typer.Option("--fixtures")] = DEFAULT_FIXTURES,
    team_path: Annotated[Path, typer.Option("--team")] = DEFAULT_TEAM,
    rules_path: Annotated[Path, typer.Option("--rules")] = DEFAULT_RULES,
    show_model_draft: Annotated[bool, typer.Option("--show-model-draft")] = False,
) -> None:
    """Let local Qwen select tools, then render their validated result with trusted code."""
    players, fixtures, team, rules = _load_inputs(
        players_path, fixtures_path, team_path, rules_path
    )
    registry = build_tool_registry(players, fixtures, team, rules)
    full_prompt = (
        f"The upcoming gameweek is {gameweek}. {prompt} "
        "Use a five-gameweek horizon and compare up to two transfers."
    )
    model_draft = OllamaAgent(registry, model=model, base_url=ollama_url).run(full_prompt)
    tool_result = registry.last_result("calculate_recommendation")
    if tool_result is None:
        typer.echo(
            "The model finished without calling calculate_recommendation; no plan can be trusted.",
            err=True,
        )
        raise typer.Exit(code=1)

    report_data = dict(tool_result)
    report_data.pop("player_directory", None)
    report = RecommendationReport.model_validate(report_data)
    typer.echo(render_markdown(report, players))
    typer.echo("## Agent audit\n")
    typer.echo(
        f"Qwen used {len(registry.call_history)} tool call(s). The factual report above was "
        "rendered from validated tool output, not copied from model prose."
    )
    if show_model_draft:
        typer.echo("\n### Unverified model draft\n")
        typer.echo(model_draft)


@app.command()
def doctor(
    model: Annotated[str, typer.Option("--model")] = os.getenv(
        "FPL_AGENT_MODEL", "qwen3:8b"
    ),
    ollama_url: Annotated[str, typer.Option("--ollama-url")] = os.getenv(
        "FPL_AGENT_OLLAMA_URL", "http://localhost:11434"
    ),
) -> None:
    """Check whether Ollama is reachable and the configured model is installed."""
    try:
        response = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        typer.echo(f"Ollama is unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    names = {item.get("name") for item in response.json().get("models", [])}
    if model not in names:
        typer.echo(f"Ollama is running, but {model!r} is not installed. Available: {sorted(names)}")
        raise typer.Exit(code=1)
    typer.echo(f"Ready: Ollama is running and {model!r} is installed.")


if __name__ == "__main__":
    app()
