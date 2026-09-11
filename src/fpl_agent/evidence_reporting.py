"""Human-readable evidence timeline rendering."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from fpl_agent.evidence import EvidenceObservation, ResolvedAvailability
from fpl_agent.models import Player


def _markdown_cell(value: object) -> str:
    return escape(str(value)).replace("|", "\\|").replace("\n", " ")


def _observation_state(
    observation: EvidenceObservation,
    as_of: datetime,
    max_age: timedelta,
) -> str:
    if observation.quarantined:
        return "quarantined"
    age = as_of - observation.published_at
    if age < timedelta(0):
        return "future"
    if age <= max_age:
        return "fresh"
    return "stale"


def render_evidence_timeline(
    player: Player,
    observations: list[EvidenceObservation],
    resolution: ResolvedAvailability | None,
    *,
    as_of: datetime,
    max_age_hours: int,
) -> str:
    """Render observations chronologically and identify the resolver's selection."""

    lines = [
        f"# Evidence timeline — {player.name}",
        "",
        f"As of: `{as_of.isoformat()}`  ",
        f"Freshness window: `{max_age_hours}` hours  ",
        f"Observations: `{len(observations)}`",
        "",
        "## Derived availability",
        "",
    ]
    if resolution is None:
        lines.append(
            "No usable observation could be resolved. The baseline player snapshot remains."
        )
    else:
        default_policy = (
            "blocked by default" if resolution.stale or resolution.conflict else "applied"
        )
        lines.extend(
            [
                f"- Status: **{resolution.status}**",
                f"- Chance of playing: **{resolution.chance_of_playing:.0%}**",
                f"- Expected minutes: **{resolution.expected_minutes:.0f}**",
                f"- Selected observation: **{resolution.selected_observation_id}**",
                f"- Policy result: **{default_policy}**",
                f"- Stale: **{resolution.stale}**; conflict: **{resolution.conflict}**",
            ]
        )
    lines.extend(
        [
            "",
            "## Observation history",
            "",
            "| ID | Published | State | Status | Chance | Minutes | Confidence | "
            "Selected | Claim | Source |",
            "|---:|---|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    max_age = timedelta(hours=max_age_hours)
    for observation in sorted(
        observations, key=lambda item: (item.published_at, item.id or 0)
    ):
        selected = (
            "yes"
            if resolution and observation.id == resolution.selected_observation_id
            else ""
        )
        state = _observation_state(observation, as_of, max_age)
        source = _markdown_cell(observation.source_url)
        lines.append(
            f"| {observation.id or ''} | {observation.published_at.isoformat()} | {state} | "
            f"{observation.status} | {observation.chance_of_playing:.0%} | "
            f"{observation.expected_minutes:.0f} | {observation.confidence:.0%} | "
            f"{selected} | {_markdown_cell(observation.claim)} | {source} |"
        )
    if not observations:
        lines.append("|  |  |  |  |  |  |  |  | No observations stored. |  |")
    lines.extend(
        [
            "",
            "> Timeline rows are untrusted source claims. Only the deterministic derived "
            "availability can enter the player overlay, and stale, conflicting, future, or "
            "quarantined input fails closed by default.",
            "",
        ]
    )
    return "\n".join(lines)
