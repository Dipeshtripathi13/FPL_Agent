"""Application service that joins data, rules, projections, and optimization."""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_agent.models import Fixture, FPLRules, Player, RecommendationReport, TeamState
from fpl_agent.optimizer import TransferOptimizer
from fpl_agent.projection import ProjectionEngine
from fpl_agent.rules import RulesEngine


def build_recommendation(
    players: dict[int, Player],
    fixtures: list[Fixture],
    team: TeamState,
    rules: FPLRules,
    gameweek: int,
    horizon: int = 5,
    max_transfers: int = 2,
) -> RecommendationReport:
    if horizon < 1:
        raise ValueError("Horizon must be at least one gameweek")
    rules_engine = RulesEngine(rules, players)
    rules_engine.validate_team(team)
    projections = ProjectionEngine(players, fixtures).project_horizon(gameweek, horizon)
    plans, recommended_count, baseline = TransferOptimizer(
        players, rules, rules_engine
    ).optimize(team, projections, gameweek, horizon, max_transfers)

    warnings = [
        "This MVP is advisory only and never submits changes to an FPL account.",
        "Expected points are uncertain estimates, not guaranteed returns.",
    ]
    if any(
        player.source_url is None
        for player in players.values()
        if player.status != "available" or player.chance_of_playing < 1
    ):
        warnings.append("At least one availability claim has no evidence URL.")

    return RecommendationReport(
        generated_at=datetime.now(UTC),
        season=rules.season,
        gameweek=gameweek,
        horizon=horizon,
        current_horizon_points=round(baseline, 3),
        recommended_transfer_count=recommended_count,
        plans=plans,
        assumptions=[
            "Player and fixture files were supplied by the user or a permitted data source.",
            "The baseline projection blends points per game and recent form, then adjusts for "
            "minutes, availability, fixture difficulty, and venue.",
            "A 0.5-point option-value penalty per transfer discourages marginal moves.",
            "The best lineup and captain are recalculated independently for every horizon week.",
            "Chip strategy and price-change prediction are outside MVP scope.",
        ],
        warnings=warnings,
    )
