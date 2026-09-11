"""An intentionally simple and explainable expected-points baseline."""

from __future__ import annotations

from collections import defaultdict

from fpl_agent.models import Fixture, Player, PlayerProjection

DIFFICULTY_MULTIPLIER = {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.90, 5: 0.80}


class ProjectionEngine:
    """Turn player form, availability, minutes, and fixtures into expected points.

    This is a baseline for learning, not a claim that these hand-selected weights
    are statistically optimal. The backtesting chapter explains how to replace
    them with fitted and calibrated models without changing the optimizer.
    """

    def __init__(self, players: dict[int, Player], fixtures: list[Fixture]) -> None:
        self.players = players
        self.fixtures_by_key: dict[tuple[str, int], list[Fixture]] = defaultdict(list)
        for fixture in fixtures:
            self.fixtures_by_key[(fixture.club, fixture.gameweek)].append(fixture)

    def project_player(self, player: Player, gameweek: int) -> PlayerProjection:
        fixtures = self.fixtures_by_key.get((player.club, gameweek), [])
        if not fixtures:
            return PlayerProjection(
                player_id=player.id,
                gameweek=gameweek,
                expected_points=0.0,
                fixture_count=0,
                explanation="Blank gameweek: no fixture was supplied for the player's club.",
            )

        recent_rate = 0.55 * player.points_per_game + 0.45 * player.form
        minutes_factor = min(player.expected_minutes / 90, 1.0)
        availability_factor = player.chance_of_playing
        expected_points = 0.0
        fixture_labels: list[str] = []

        for fixture in fixtures:
            difficulty_factor = DIFFICULTY_MULTIPLIER[fixture.difficulty]
            venue_factor = 1.03 if fixture.is_home else 0.97
            expected_points += (
                recent_rate
                * minutes_factor
                * availability_factor
                * difficulty_factor
                * venue_factor
            )
            venue = "H" if fixture.is_home else "A"
            fixture_labels.append(f"{fixture.opponent} ({venue}, FDR {fixture.difficulty})")

        explanation = (
            f"Recent-rate blend {recent_rate:.2f}; minutes factor {minutes_factor:.2f}; "
            f"availability {availability_factor:.0%}; fixtures: {', '.join(fixture_labels)}."
        )
        return PlayerProjection(
            player_id=player.id,
            gameweek=gameweek,
            expected_points=round(expected_points, 3),
            fixture_count=len(fixtures),
            explanation=explanation,
        )

    def project_horizon(
        self, first_gameweek: int, horizon: int
    ) -> dict[tuple[int, int], PlayerProjection]:
        return {
            (player.id, gameweek): self.project_player(player, gameweek)
            for player in self.players.values()
            for gameweek in range(first_gameweek, first_gameweek + horizon)
        }
