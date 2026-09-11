"""Deterministic FPL rule validation.

The model is never allowed to waive these checks. If a rule cannot be proven,
the plan is rejected rather than guessed.
"""

from __future__ import annotations

from collections import Counter

from fpl_agent.models import FPLRules, Lineup, Player, Position, TeamPick, TeamState, Transfer


class RuleViolation(ValueError):
    """Raised when a team, lineup, or transfer plan violates a game rule."""


class RulesEngine:
    def __init__(self, rules: FPLRules, players: dict[int, Player]) -> None:
        self.rules = rules
        self.players = players

    def validate_team(self, team: TeamState) -> None:
        if len(team.squad) != self.rules.squad_size:
            raise RuleViolation(
                f"Squad has {len(team.squad)} players; expected {self.rules.squad_size}"
            )
        if team.free_transfers > self.rules.max_free_transfers:
            raise RuleViolation(
                f"Free transfers {team.free_transfers} exceed season maximum "
                f"{self.rules.max_free_transfers}"
            )
        unknown = [pick.player_id for pick in team.squad if pick.player_id not in self.players]
        if unknown:
            raise RuleViolation(f"Unknown player ids in squad: {unknown}")

        squad_players = [self.players[pick.player_id] for pick in team.squad]
        positions = Counter(player.position for player in squad_players)
        for position, required in self.rules.squad_positions.items():
            actual = positions[position]
            if actual != required:
                raise RuleViolation(f"Squad requires {required} {position}; found {actual}")

        clubs = Counter(player.club for player in squad_players)
        over_limit = {
            club: count
            for club, count in clubs.items()
            if count > self.rules.max_players_per_club
        }
        if over_limit:
            raise RuleViolation(f"Too many players from a club: {over_limit}")

    def validate_lineup(self, team: TeamState, lineup: Lineup) -> None:
        squad_ids = {pick.player_id for pick in team.squad}
        selected = lineup.starters + [lineup.bench_goalkeeper] + lineup.bench_order
        if len(lineup.starters) != self.rules.starting_size:
            raise RuleViolation("Starting lineup must contain exactly 11 players")
        if len(selected) != self.rules.squad_size or len(set(selected)) != len(selected):
            raise RuleViolation("Lineup must contain every squad player exactly once")
        if set(selected) != squad_ids:
            raise RuleViolation("Lineup players do not match the squad")

        counts = Counter(self.players[player_id].position for player_id in lineup.starters)
        for position, minimum in self.rules.lineup.minimum.items():
            if counts[position] < minimum:
                raise RuleViolation(f"Lineup requires at least {minimum} {position}")
        for position, maximum in self.rules.lineup.maximum.items():
            if counts[position] > maximum:
                raise RuleViolation(f"Lineup allows at most {maximum} {position}")
        if self.players[lineup.bench_goalkeeper].position != Position.GOALKEEPER:
            raise RuleViolation("The reserve goalkeeper slot must contain a goalkeeper")

    def apply_transfers(self, team: TeamState, transfers: list[Transfer]) -> TeamState:
        if len(transfers) > self.rules.max_transfers_per_gameweek:
            raise RuleViolation("Transfer count exceeds the gameweek limit")
        if len({transfer.player_out for transfer in transfers}) != len(transfers):
            raise RuleViolation("A player cannot be transferred out twice")
        if len({transfer.player_in for transfer in transfers}) != len(transfers):
            raise RuleViolation("A player cannot be transferred in twice")

        picks = {pick.player_id: pick for pick in team.squad}
        bank = team.bank
        for transfer in transfers:
            if transfer.player_out not in picks:
                raise RuleViolation(f"Player {transfer.player_out} is not in the squad")
            if transfer.player_in in picks:
                raise RuleViolation(f"Player {transfer.player_in} is already in the squad")
            outgoing = self.players[transfer.player_out]
            incoming = self.players.get(transfer.player_in)
            if incoming is None:
                raise RuleViolation(f"Unknown incoming player {transfer.player_in}")
            if outgoing.position != incoming.position:
                raise RuleViolation("Transfers must preserve squad position counts")
            if transfer.selling_price != picks[transfer.player_out].selling_price:
                raise RuleViolation("Transfer uses an incorrect selling price")
            if transfer.purchase_price != incoming.price:
                raise RuleViolation("Transfer uses an incorrect purchase price")
            bank += transfer.selling_price - transfer.purchase_price
            del picks[transfer.player_out]
            picks[transfer.player_in] = TeamPick(
                player_id=transfer.player_in,
                purchase_price=transfer.purchase_price,
                selling_price=transfer.purchase_price,
            )

        if bank < 0:
            raise RuleViolation("Transfers exceed the available budget")
        updated = TeamState(
            entry_id=team.entry_id,
            bank=bank,
            free_transfers=team.free_transfers,
            active_chip=team.active_chip,
            squad=list(picks.values()),
        )
        self.validate_team(updated)
        return updated
