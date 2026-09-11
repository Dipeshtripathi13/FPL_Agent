from copy import deepcopy

import pytest

from fpl_agent.models import TeamPick
from fpl_agent.rules import RulesEngine, RuleViolation


def test_sample_squad_is_valid(players, team, rules):
    RulesEngine(rules, players).validate_team(team)


def test_unknown_player_is_rejected(players, team, rules):
    invalid = deepcopy(team)
    invalid.squad[-1] = TeamPick(player_id=999, purchase_price=50, selling_price=50)
    with pytest.raises(RuleViolation, match="Unknown player"):
        RulesEngine(rules, players).validate_team(invalid)


def test_negative_bank_transfer_is_rejected(players, team, rules):
    from fpl_agent.models import Transfer

    transfer = Transfer(
        player_out=7,
        player_in=18,
        selling_price=40,
        purchase_price=52,
    )
    poor_team = team.model_copy(update={"bank": 0})
    with pytest.raises(RuleViolation, match="budget"):
        RulesEngine(rules, players).apply_transfers(poor_team, [transfer])


def test_too_many_free_transfers_are_rejected(players, team, rules):
    invalid = team.model_copy(update={"free_transfers": 6})
    with pytest.raises(RuleViolation, match="Free transfers"):
        RulesEngine(rules, players).validate_team(invalid)


def test_more_than_three_players_from_a_club_are_rejected(players, team, rules):
    changed_players = dict(players)
    changed_players[7] = changed_players[7].model_copy(update={"club": "Northport"})
    with pytest.raises(RuleViolation, match="Too many players"):
        RulesEngine(rules, changed_players).validate_team(team)
