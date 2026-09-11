"""Command-line interface for validation, deterministic recommendations, and the agent."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from fpl_agent.agent import OllamaAgent, build_tool_registry
from fpl_agent.data import load_fixtures, load_players, load_rules, load_team
from fpl_agent.evidence import (
    integrate_evidence,
    load_evidence_yaml,
    resolve_player_reference,
)
from fpl_agent.evidence_store import EvidenceStore
from fpl_agent.models import RecommendationReport
from fpl_agent.providers.brave import BraveSearchProvider
from fpl_agent.providers.cache import SearchCache
from fpl_agent.reporting import render_markdown
from fpl_agent.rules import RulesEngine
from fpl_agent.service import build_recommendation

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Local-first, explainable FPL analysis. No account changes are performed.",
)
evidence_app = typer.Typer(no_args_is_help=True, help="Manage local availability evidence.")
app.add_typer(evidence_app, name="evidence")

DEFAULT_PLAYERS = Path("examples/players.csv")
DEFAULT_FIXTURES = Path("examples/fixtures.csv")
DEFAULT_TEAM = Path("examples/team.yaml")
DEFAULT_RULES = Path("rules/2026_27.yaml")
DEFAULT_EVIDENCE_DB = Path("data/private/evidence.db")
DEFAULT_SEARCH_CACHE = Path("data/private/search-cache.db")


def _load_inputs(players_path: Path, fixtures_path: Path, team_path: Path, rules_path: Path):
    players = load_players(players_path)
    fixtures = load_fixtures(fixtures_path)
    team = load_team(team_path)
    rules = load_rules(rules_path)
    return players, fixtures, team, rules


def _load_evidence_overlay(
    players,
    evidence_db: Path | None,
    max_age_hours: int,
    allow_conflicts: bool,
    allow_stale: bool,
    as_of: datetime | None = None,
):
    if evidence_db is None:
        return players, [], []
    if not evidence_db.exists():
        raise ValueError(
            f"Evidence database {evidence_db} does not exist. Run 'fpl-agent evidence init'."
        )
    store = EvidenceStore(evidence_db)
    store.schema_version()
    return integrate_evidence(
        players,
        store.list_observations(),
        max_age_hours=max_age_hours,
        allow_conflicts=allow_conflicts,
        allow_stale=allow_stale,
        now=as_of,
    )


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--evidence-as-of must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--evidence-as-of must include a timezone, such as Z or +00:00")
    return parsed


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


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
    evidence_db: Annotated[Path | None, typer.Option("--evidence-db")] = None,
    evidence_max_age_hours: Annotated[
        int, typer.Option("--evidence-max-age-hours", min=1)
    ] = 168,
    allow_conflicting_evidence: Annotated[
        bool, typer.Option("--allow-conflicting-evidence")
    ] = False,
    allow_stale_evidence: Annotated[bool, typer.Option("--allow-stale-evidence")] = False,
    evidence_as_of: Annotated[str | None, typer.Option("--evidence-as-of")] = None,
) -> None:
    """Compute rules-valid transfer, lineup, bench, and captain recommendations."""
    players, fixtures, team, rules = _load_inputs(
        players_path, fixtures_path, team_path, rules_path
    )
    players, _, evidence_warnings = _load_evidence_overlay(
        players,
        evidence_db,
        evidence_max_age_hours,
        allow_conflicting_evidence,
        allow_stale_evidence,
        _parse_as_of(evidence_as_of),
    )
    report = build_recommendation(
        players, fixtures, team, rules, gameweek, horizon, max_transfers
    )
    report.warnings.extend(evidence_warnings)
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
    evidence_db: Annotated[Path | None, typer.Option("--evidence-db")] = None,
    evidence_max_age_hours: Annotated[
        int, typer.Option("--evidence-max-age-hours", min=1)
    ] = 168,
    evidence_as_of: Annotated[str | None, typer.Option("--evidence-as-of")] = None,
) -> None:
    """Let local Qwen select tools, then render their validated result with trusted code."""
    players, fixtures, team, rules = _load_inputs(
        players_path, fixtures_path, team_path, rules_path
    )
    players, _, evidence_warnings = _load_evidence_overlay(
        players,
        evidence_db,
        evidence_max_age_hours,
        False,
        False,
        _parse_as_of(evidence_as_of),
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
    report.warnings.extend(evidence_warnings)
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


@evidence_app.command("init")
def evidence_init(
    database: Annotated[Path, typer.Option("--db")] = DEFAULT_EVIDENCE_DB,
) -> None:
    """Create or migrate the local evidence database."""
    store = EvidenceStore(database)
    store.initialize()
    typer.echo(f"Evidence database ready at {database} (schema {store.schema_version()}).")


@evidence_app.command("import")
def evidence_import(
    input_path: Annotated[Path, typer.Argument(help="YAML file containing observations")],
    database: Annotated[Path, typer.Option("--db")] = DEFAULT_EVIDENCE_DB,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
) -> None:
    """Validate and import immutable evidence observations from YAML."""
    players = load_players(players_path)
    observations = load_evidence_yaml(input_path, players)
    store = EvidenceStore(database)
    store.initialize()
    results = store.add_many(observations)
    inserted = sum(result.inserted for result in results)
    quarantined = sum(observation.quarantined for observation in observations)
    typer.echo(
        f"Imported {inserted}; duplicates {len(results) - inserted}; "
        f"quarantined {quarantined}. Database: {database}"
    )
    for observation, result in zip(observations, results, strict=True):
        if observation.quarantined:
            typer.echo(
                f"  observation {result.observation_id}: quarantined "
                f"({', '.join(observation.safety_flags)})"
            )


@evidence_app.command("list")
def evidence_list(
    database: Annotated[Path, typer.Option("--db")] = DEFAULT_EVIDENCE_DB,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    player: Annotated[str | None, typer.Option("--player")] = None,
    include_quarantined: Annotated[bool, typer.Option("--include-quarantined")] = True,
) -> None:
    """List stored observations and their safety state."""
    if not database.exists():
        typer.echo(f"Evidence database does not exist: {database}", err=True)
        raise typer.Exit(code=1)
    players = load_players(players_path)
    player_id = resolve_player_reference(player, players) if player else None
    observations = EvidenceStore(database).list_observations(
        player_id, include_quarantined=include_quarantined
    )
    typer.echo("| ID | Player | Status | Chance | Published | Safety | Claim | Source |")
    typer.echo("|---:|---|---|---:|---|---|---|---|")
    for item in observations:
        safety = "quarantined" if item.quarantined else "accepted"
        typer.echo(
            f"| {item.id} | {_escape_table(players[item.player_id].name)} | {item.status} | "
            f"{item.chance_of_playing:.0%} | {item.published_at.isoformat()} | {safety} | "
            f"{_escape_table(item.claim)} | {item.source_url} |"
        )


@evidence_app.command("resolve")
def evidence_resolve(
    database: Annotated[Path, typer.Option("--db")] = DEFAULT_EVIDENCE_DB,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    max_age_hours: Annotated[int, typer.Option("--max-age-hours", min=1)] = 168,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Show derived availability and surface stale or conflicting evidence."""
    players = load_players(players_path)
    if not database.exists():
        typer.echo(f"Evidence database does not exist: {database}", err=True)
        raise typer.Exit(code=1)
    _, resolutions, warnings = integrate_evidence(
        players,
        EvidenceStore(database).list_observations(),
        max_age_hours=max_age_hours,
        now=_parse_as_of(as_of),
    )
    typer.echo("| Player | Status | Chance | Minutes | Stale | Conflict | Source |")
    typer.echo("|---|---|---:|---:|---|---|---|")
    for item in sorted(resolutions, key=lambda value: players[value.player_id].name):
        typer.echo(
            f"| {_escape_table(players[item.player_id].name)} | {item.status} | "
            f"{item.chance_of_playing:.0%} | {item.expected_minutes:.0f} | "
            f"{item.stale} | {item.conflict} | {item.source_url} |"
        )
    for warning in warnings:
        typer.echo(f"WARNING: {warning}")


@app.command()
def research(
    player: Annotated[str, typer.Option("--player")],
    allowed_domain: Annotated[list[str] | None, typer.Option("--allowed-domain")] = None,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    cache_path: Annotated[Path, typer.Option("--cache")] = DEFAULT_SEARCH_CACHE,
    max_results: Annotated[int, typer.Option("--max-results", min=1, max=20)] = 5,
    freshness: Annotated[str, typer.Option("--freshness")] = "pw",
) -> None:
    """Discover reviewable sources through Brave; never imports snippets as facts."""
    players = load_players(players_path)
    player_id = resolve_player_reference(player, players)
    selected = players[player_id]
    token = os.getenv("BRAVE_SEARCH_API_KEY")
    if not token:
        typer.echo(
            "Set BRAVE_SEARCH_API_KEY in your environment. Never commit the key to Git.", err=True
        )
        raise typer.Exit(code=1)
    cache = SearchCache(cache_path)
    cache.initialize()
    try:
        provider = BraveSearchProvider(
            token,
            allowed_domain or [],
            cache=cache,
            freshness=freshness,
        )
        documents = provider.search(
            f'"{selected.name}" {selected.club} injury availability team news',
            max_results=max_results,
        )
    except (ValueError, httpx.HTTPError) as exc:
        typer.echo(f"Research failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not documents:
        typer.echo("No results passed the reviewed domain allowlist.")
        return
    typer.echo(
        "Discovery results are unverified leads. Review the source, then create an evidence YAML "
        "observation manually."
    )
    for index, document in enumerate(documents, start=1):
        safety = "QUARANTINED" if document.quarantined else "review required"
        typer.echo(f"\n{index}. {document.title} [{safety}]\n   {document.url}")
        typer.echo(f"   {_escape_table(document.snippet)}")


if __name__ == "__main__":
    app()
