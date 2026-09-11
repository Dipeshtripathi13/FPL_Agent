"""Command-line interface for validation, deterministic recommendations, and the agent."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from fpl_agent.agent import OllamaAgent, build_tool_registry
from fpl_agent.data import load_fixtures, load_players, load_rules, load_team
from fpl_agent.evidence import (
    EvidenceResolver,
    build_evidence_audit,
    integrate_evidence,
    load_evidence_yaml,
    resolve_player_reference,
)
from fpl_agent.evidence_reporting import render_evidence_timeline
from fpl_agent.evidence_store import EvidenceStore
from fpl_agent.models import RecommendationReport
from fpl_agent.providers.brave import BraveSearchProvider
from fpl_agent.providers.cache import SearchCache
from fpl_agent.reporting import render_markdown
from fpl_agent.rules import RulesEngine
from fpl_agent.service import build_recommendation
from fpl_agent.source_policy import load_source_policy

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Local-first, explainable FPL analysis. No account changes are performed.",
)
evidence_app = typer.Typer(no_args_is_help=True, help="Manage local availability evidence.")
app.add_typer(evidence_app, name="evidence")
sources_app = typer.Typer(no_args_is_help=True, help="Manage reviewed research sources.")
app.add_typer(sources_app, name="sources")

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
        return players, [], [], None
    if not evidence_db.exists():
        raise ValueError(
            f"Evidence database {evidence_db} does not exist. Run 'fpl-agent evidence init'."
        )
    store = EvidenceStore(evidence_db)
    schema_version = store.schema_version()
    observations = store.list_observations()
    effective_as_of = as_of or datetime.now(UTC)
    updated, resolutions, warnings = integrate_evidence(
        players,
        observations,
        max_age_hours=max_age_hours,
        allow_conflicts=allow_conflicts,
        allow_stale=allow_stale,
        now=effective_as_of,
    )
    audit = build_evidence_audit(
        observations,
        resolutions,
        players,
        schema_version=schema_version,
        as_of=effective_as_of,
        max_age_hours=max_age_hours,
        allow_conflicts=allow_conflicts,
        allow_stale=allow_stale,
    )
    return updated, resolutions, warnings, audit


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Evidence as-of time must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Evidence as-of time must include a timezone, such as Z or +00:00")
    return parsed


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Source-policy as-of time must be an ISO date such as 2026-09-11") from exc


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
    players, _, evidence_warnings, evidence_audit = _load_evidence_overlay(
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
    report = report.model_copy(
        update={
            "warnings": [*report.warnings, *evidence_warnings],
            "evidence_audit": evidence_audit,
        }
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
    players, _, evidence_warnings, evidence_audit = _load_evidence_overlay(
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
    try:
        model_draft = OllamaAgent(registry, model=model, base_url=ollama_url).run(full_prompt)
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Agent failed safely: {exc}", err=True)
        raise typer.Exit(code=1) from exc
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
    report = report.model_copy(
        update={
            "warnings": [*report.warnings, *evidence_warnings],
            "evidence_audit": evidence_audit,
        }
    )
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


@evidence_app.command("timeline")
def evidence_timeline(
    player: Annotated[str, typer.Option("--player")],
    database: Annotated[Path, typer.Option("--db")] = DEFAULT_EVIDENCE_DB,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    max_age_hours: Annotated[int, typer.Option("--max-age-hours", min=1)] = 168,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Render one player's immutable observation history and resolver outcome."""
    if not database.exists():
        typer.echo(f"Evidence database does not exist: {database}", err=True)
        raise typer.Exit(code=1)
    players = load_players(players_path)
    player_id = resolve_player_reference(player, players)
    effective_as_of = _parse_as_of(as_of) or datetime.now(UTC)
    observations = EvidenceStore(database).list_observations(player_id)
    resolution = EvidenceResolver(max_age_hours=max_age_hours).resolve(
        player_id, observations, now=effective_as_of
    )
    markdown = render_evidence_timeline(
        players[player_id],
        observations,
        resolution,
        as_of=effective_as_of,
        max_age_hours=max_age_hours,
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        typer.echo(f"Wrote evidence timeline to {output}")
    else:
        typer.echo(markdown)


@sources_app.command("check")
def sources_check(
    config: Annotated[Path, typer.Argument(help="YAML reviewed-source registry")],
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Show which documented source reviews are current, expired, or disabled."""
    try:
        policy = load_source_policy(config)
        statuses = policy.evaluate(_parse_date(as_of))
    except (OSError, ValueError) as exc:
        typer.echo(f"Source policy failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("| Source | Domain | Reviewed | Expires | Enabled | Current | Reason |")
    typer.echo("|---|---|---|---|---|---|---|")
    for status in statuses:
        typer.echo(
            f"| {_escape_table(status.name)} | {status.domain} | {status.reviewed_at} | "
            f"{status.review_expires_at} | {status.enabled} | {status.current} | "
            f"{status.reason} |"
        )


@app.command()
def research(
    player: Annotated[str, typer.Option("--player")],
    allowed_domain: Annotated[list[str] | None, typer.Option("--allowed-domain")] = None,
    source_config: Annotated[Path | None, typer.Option("--source-config")] = None,
    source_as_of: Annotated[str | None, typer.Option("--source-as-of")] = None,
    players_path: Annotated[Path, typer.Option("--players")] = DEFAULT_PLAYERS,
    cache_path: Annotated[Path, typer.Option("--cache")] = DEFAULT_SEARCH_CACHE,
    max_results: Annotated[int, typer.Option("--max-results", min=1, max=20)] = 5,
    freshness: Annotated[str, typer.Option("--freshness")] = "pw",
) -> None:
    """Discover reviewable sources through Brave; never imports snippets as facts."""
    players = load_players(players_path)
    player_id = resolve_player_reference(player, players)
    selected = players[player_id]
    domains = set(allowed_domain or [])
    if source_config:
        try:
            statuses = load_source_policy(source_config).evaluate(_parse_date(source_as_of))
        except (OSError, ValueError) as exc:
            typer.echo(f"Source policy failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        domains.update(status.domain for status in statuses if status.current)
        for status in statuses:
            if not status.current and status.enabled:
                typer.echo(
                    f"WARNING: {status.domain} was excluded ({status.reason}; "
                    f"review expires {status.review_expires_at}).",
                    err=True,
                )
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
            sorted(domains),
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

    typer.echo(f"Reviewed domains used: {', '.join(sorted(domains))}")
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
