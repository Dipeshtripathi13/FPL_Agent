"""Human-readable report rendering."""

from __future__ import annotations

from fpl_agent.data import units_to_money
from fpl_agent.models import Player, RecommendationReport, TransferPlan


def _name(players: dict[int, Player], player_id: int) -> str:
    return players[player_id].name


def _plan_markdown(plan: TransferPlan, players: dict[int, Player], recommended: bool) -> str:
    marker = " — RECOMMENDED" if recommended else ""
    lines = [f"### {plan.transfer_count} transfer(s){marker}", ""]
    lines.extend(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| Gross horizon points | {plan.gross_horizon_points:.2f} |",
            f"| Transfer hit | -{plan.transfer_hit} |",
            f"| Transfer option-value penalty | -{plan.option_value_penalty:.2f} |",
            f"| Objective points | {plan.objective_points:.2f} |",
            f"| Gain versus rolling | {plan.expected_gain_vs_roll:+.2f} |",
            f"| Bank after | {units_to_money(plan.bank_after)} |",
            "",
        ]
    )
    if plan.transfers:
        lines.extend(["| Sell | Buy | Price change |", "|---|---|---:|"])
        for transfer in plan.transfers:
            delta = transfer.selling_price - transfer.purchase_price
            lines.append(
                f"| {_name(players, transfer.player_out)} | "
                f"{_name(players, transfer.player_in)} | {units_to_money(delta)} |"
            )
        lines.append("")
    else:
        lines.extend(["Roll the transfer and keep the current squad.", ""])

    lineup = plan.lineup
    lines.extend(
        [
            f"**Starting XI:** {', '.join(_name(players, pid) for pid in lineup.starters)}",
            "",
            f"**Captain:** {_name(players, lineup.captain)}  ",
            f"**Vice-captain:** {_name(players, lineup.vice_captain)}  ",
            f"**Reserve goalkeeper:** {_name(players, lineup.bench_goalkeeper)}  ",
            f"**Outfield bench order:** "
            f"{', '.join(_name(players, pid) for pid in lineup.bench_order)}",
            "",
            f"Expected GW{lineup.gameweek} points including captain: "
            f"**{lineup.expected_points:.2f}**",
            "",
        ]
    )
    if plan.injury_decisions:
        lines.extend(["#### Availability decisions", ""])
        for decision in plan.injury_decisions:
            evidence = f" ([evidence]({decision.evidence_url}))" if decision.evidence_url else ""
            lines.append(
                f"- **{_name(players, decision.player_id)} — {decision.action}:** "
                f"{decision.reason}{evidence}"
            )
        lines.append("")
    return "\n".join(lines)


def render_markdown(report: RecommendationReport, players: dict[int, Player]) -> str:
    lines = [
        f"# FPL Agent recommendation — Gameweek {report.gameweek}",
        "",
        f"Generated: `{report.generated_at.isoformat()}`  ",
        f"Season: `{report.season}`  ",
        f"Planning horizon: `{report.horizon}` gameweeks",
        "",
        "## Decision summary",
        "",
        f"The optimizer recommends **{report.recommended_transfer_count} transfer(s)**. "
        f"The roll baseline objective is **{report.current_horizon_points:.2f} points**.",
        "",
        "The objective subtracts confirmed FPL hits and a small transfer option-value penalty. "
        "It is a comparison score, not a promise of actual points.",
        "",
        "## Compared plans",
        "",
    ]
    for plan in report.plans:
        lines.append(
            _plan_markdown(
                plan,
                players,
                recommended=plan.transfer_count == report.recommended_transfer_count,
            )
        )

    if report.evidence_audit is not None:
        audit = report.evidence_audit
        lines.extend(
            [
                "## Evidence audit",
                "",
                f"As of: `{audit.as_of.isoformat()}`  ",
                f"Policy: `{audit.max_age_hours}`-hour freshness window; "
                f"allow conflicts `{audit.allow_conflicts}`; allow stale `{audit.allow_stale}`  ",
                f"Observation-set fingerprint: `{audit.observation_set_sha256}`  ",
                f"Stored observations: `{audit.observation_count}`",
                "",
                "| Player | Observation IDs | Selected | Applied | Blocked reasons |",
                "|---|---|---:|---|---|",
            ]
        )
        for item in audit.player_resolutions:
            observation_ids = ", ".join(str(value) for value in item.observation_ids) or "—"
            blocked = ", ".join(item.blocked_reasons) or "—"
            lines.append(
                f"| {_name(players, item.player_id)} | {observation_ids} | "
                f"{item.selected_observation_id or '—'} | {item.applied} | {blocked} |"
            )
        if not audit.player_resolutions:
            lines.append("| — | — | — | — | No usable observations |")
        if audit.quarantined_observation_ids:
            lines.extend(
                [
                    "",
                    "Quarantined observation IDs: "
                    + ", ".join(str(value) for value in audit.quarantined_observation_ids),
                ]
            )
        if audit.unknown_player_observation_ids:
            lines.extend(
                [
                    "",
                    "Unknown-player observation IDs: "
                    + ", ".join(str(value) for value in audit.unknown_player_observation_ids),
                ]
            )
        lines.append("")

    lines.extend(["## Assumptions", ""])
    lines.extend(f"- {assumption}" for assumption in report.assumptions)
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.append("")
    return "\n".join(lines)
