"""Deterministic lineup and bounded transfer-search optimizers."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import combinations, product

from fpl_agent.models import (
    FPLRules,
    InjuryDecision,
    Lineup,
    Player,
    PlayerProjection,
    Position,
    TeamPick,
    TeamState,
    Transfer,
    TransferPlan,
)
from fpl_agent.rules import RulesEngine, RuleViolation


class LineupOptimizer:
    def __init__(
        self,
        players: dict[int, Player],
        rules: FPLRules,
        rules_engine: RulesEngine,
    ) -> None:
        self.players = players
        self.rules = rules
        self.rules_engine = rules_engine

    def optimize(
        self,
        team: TeamState,
        gameweek: int,
        projections: dict[tuple[int, int], PlayerProjection],
    ) -> Lineup:
        by_position: dict[Position, list[int]] = defaultdict(list)
        for pick in team.squad:
            by_position[self.players[pick.player_id].position].append(pick.player_id)

        def points(player_id: int) -> float:
            return projections[(player_id, gameweek)].expected_points

        for ids in by_position.values():
            ids.sort(key=points, reverse=True)

        goalkeeper = by_position[Position.GOALKEEPER][0]
        best_starters: list[int] | None = None
        best_base_points = float("-inf")

        for defenders in range(
            self.rules.lineup.minimum[Position.DEFENDER],
            self.rules.lineup.maximum[Position.DEFENDER] + 1,
        ):
            for midfielders in range(
                self.rules.lineup.minimum[Position.MIDFIELDER],
                self.rules.lineup.maximum[Position.MIDFIELDER] + 1,
            ):
                forwards = 10 - defenders - midfielders
                if not (
                    self.rules.lineup.minimum[Position.FORWARD]
                    <= forwards
                    <= self.rules.lineup.maximum[Position.FORWARD]
                ):
                    continue
                starters = (
                    [goalkeeper]
                    + by_position[Position.DEFENDER][:defenders]
                    + by_position[Position.MIDFIELDER][:midfielders]
                    + by_position[Position.FORWARD][:forwards]
                )
                base_points = sum(points(player_id) for player_id in starters)
                if base_points > best_base_points:
                    best_base_points = base_points
                    best_starters = starters

        if best_starters is None:  # pragma: no cover - protected by squad validation
            raise RuleViolation("No legal formation can be built from this squad")

        captain, vice_captain = sorted(best_starters, key=points, reverse=True)[:2]
        starter_set = set(best_starters)
        reserve_goalkeeper = next(
            player_id
            for player_id in by_position[Position.GOALKEEPER]
            if player_id not in starter_set
        )
        bench_order = sorted(
            [
                pick.player_id
                for pick in team.squad
                if pick.player_id not in starter_set
                and self.players[pick.player_id].position != Position.GOALKEEPER
            ],
            key=points,
            reverse=True,
        )
        lineup = Lineup(
            gameweek=gameweek,
            starters=best_starters,
            bench_goalkeeper=reserve_goalkeeper,
            bench_order=bench_order,
            captain=captain,
            vice_captain=vice_captain,
            expected_points=round(best_base_points + points(captain), 3),
        )
        self.rules_engine.validate_lineup(team, lineup)
        return lineup


class TransferOptimizer:
    """Evaluate roll, one-transfer, and two-transfer plans.

    Candidate pools are deliberately bounded. This makes the search fast and
    inspectable for an MVP; a later milestone replaces it with multi-period MILP.
    """

    def __init__(
        self,
        players: dict[int, Player],
        rules: FPLRules,
        rules_engine: RulesEngine,
        candidate_limit_per_position: int = 8,
        option_value_per_transfer: float = 0.5,
    ) -> None:
        self.players = players
        self.rules = rules
        self.rules_engine = rules_engine
        self.candidate_limit_per_position = candidate_limit_per_position
        self.option_value_per_transfer = option_value_per_transfer
        self.lineup_optimizer = LineupOptimizer(players, rules, rules_engine)

    def optimize(
        self,
        team: TeamState,
        projections: dict[tuple[int, int], PlayerProjection],
        first_gameweek: int,
        horizon: int,
        max_transfers: int,
    ) -> tuple[list[TransferPlan], int, float]:
        max_transfers = max(0, min(max_transfers, 2))
        horizon_totals = {
            player_id: sum(
                projections[(player_id, gameweek)].expected_points
                for gameweek in range(first_gameweek, first_gameweek + horizon)
            )
            for player_id in self.players
        }

        roll_plan = self._evaluate(
            team,
            team,
            [],
            projections,
            first_gameweek,
            horizon,
            baseline_objective=None,
        )
        baseline = roll_plan.objective_points
        roll_plan.expected_gain_vs_roll = 0.0
        best_by_count: dict[int, TransferPlan] = {0: roll_plan}
        current_ids = {pick.player_id for pick in team.squad}

        candidate_pools: dict[Position, list[int]] = {}
        for position in Position:
            candidate_pools[position] = sorted(
                [
                    player.id
                    for player in self.players.values()
                    if player.position == position and player.id not in current_ids
                ],
                key=lambda player_id: horizon_totals[player_id],
                reverse=True,
            )[: self.candidate_limit_per_position]

        picks_by_id = {pick.player_id: pick for pick in team.squad}
        for transfer_count in range(1, max_transfers + 1):
            best: TransferPlan | None = None
            for outgoing_ids in combinations(current_ids, transfer_count):
                required = Counter(self.players[player_id].position for player_id in outgoing_ids)
                for incoming_ids in self._incoming_combinations(required, candidate_pools):
                    transfers = self._pair_transfers(outgoing_ids, incoming_ids, picks_by_id)
                    try:
                        candidate_team = self.rules_engine.apply_transfers(team, transfers)
                    except RuleViolation:
                        continue
                    plan = self._evaluate(
                        candidate_team,
                        team,
                        transfers,
                        projections,
                        first_gameweek,
                        horizon,
                        baseline_objective=baseline,
                    )
                    if best is None or plan.objective_points > best.objective_points:
                        best = plan
            if best is not None:
                best_by_count[transfer_count] = best

        plans = [best_by_count[count] for count in sorted(best_by_count)]
        recommended = max(plans, key=lambda plan: plan.objective_points)
        return plans, recommended.transfer_count, baseline

    def _incoming_combinations(
        self,
        required: Counter[Position],
        pools: dict[Position, list[int]],
    ) -> Iterable[tuple[int, ...]]:
        grouped_choices: list[list[tuple[int, ...]]] = []
        for position, count in sorted(required.items(), key=lambda item: item[0].value):
            choices = list(combinations(pools[position], count))
            if not choices:
                return
            grouped_choices.append(choices)
        for grouped in product(*grouped_choices):
            yield tuple(player_id for group in grouped for player_id in group)

    def _pair_transfers(
        self,
        outgoing_ids: tuple[int, ...],
        incoming_ids: tuple[int, ...],
        picks_by_id: dict[int, TeamPick],
    ) -> list[Transfer]:
        outgoing_by_position: dict[Position, list[int]] = defaultdict(list)
        incoming_by_position: dict[Position, list[int]] = defaultdict(list)
        for player_id in outgoing_ids:
            outgoing_by_position[self.players[player_id].position].append(player_id)
        for player_id in incoming_ids:
            incoming_by_position[self.players[player_id].position].append(player_id)

        transfers: list[Transfer] = []
        for position in outgoing_by_position:
            for player_out, player_in in zip(
                sorted(outgoing_by_position[position]),
                sorted(incoming_by_position[position]),
                strict=True,
            ):
                pick = picks_by_id[player_out]
                transfers.append(
                    Transfer(
                        player_out=player_out,
                        player_in=player_in,
                        selling_price=pick.selling_price,
                        purchase_price=self.players[player_in].price,
                    )
                )
        return transfers

    def _evaluate(
        self,
        team: TeamState,
        original_team: TeamState,
        transfers: list[Transfer],
        projections: dict[tuple[int, int], PlayerProjection],
        first_gameweek: int,
        horizon: int,
        baseline_objective: float | None,
    ) -> TransferPlan:
        lineups = [
            self.lineup_optimizer.optimize(team, gameweek, projections)
            for gameweek in range(first_gameweek, first_gameweek + horizon)
        ]
        gross = sum(lineup.expected_points for lineup in lineups)
        transfer_hit = max(0, len(transfers) - team.free_transfers) * (
            self.rules.additional_transfer_cost
        )
        option_penalty = len(transfers) * self.option_value_per_transfer
        objective = gross - transfer_hit - option_penalty
        gain = 0.0 if baseline_objective is None else objective - baseline_objective
        return TransferPlan(
            transfer_count=len(transfers),
            transfers=transfers,
            bank_after=team.bank,
            transfer_hit=transfer_hit,
            option_value_penalty=option_penalty,
            gross_horizon_points=round(gross, 3),
            objective_points=round(objective, 3),
            expected_gain_vs_roll=round(gain, 3),
            lineup=lineups[0],
            injury_decisions=self._injury_decisions(original_team, transfers, lineups[0]),
        )

    def _injury_decisions(
        self, team: TeamState, transfers: list[Transfer], lineup: Lineup
    ) -> list[InjuryDecision]:
        outgoing = {transfer.player_out for transfer in transfers}
        starter_ids = set(lineup.starters)
        decisions: list[InjuryDecision] = []
        for pick in team.squad:
            player = self.players[pick.player_id]
            if player.chance_of_playing >= 0.75 and player.status == "available":
                continue
            if player.id in outgoing:
                action = "transfer"
                reason = "The optimized plan sells this flagged player over the selected horizon."
            elif player.id not in starter_ids:
                action = "bench"
                reason = "Bench cover is preferred to spending a transfer in this plan."
            else:
                action = "start_with_risk"
                reason = (
                    "The reduced-availability projection still places the player in the best XI."
                )
            if player.news:
                reason = f"{reason} Evidence supplied: {player.news}"
            decisions.append(
                InjuryDecision(
                    player_id=player.id,
                    action=action,
                    reason=reason,
                    evidence_url=player.source_url,
                )
            )
        return decisions
