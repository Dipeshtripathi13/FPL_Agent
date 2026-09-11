from fpl_agent.rules import RulesEngine
from fpl_agent.service import build_recommendation


def test_optimizer_compares_zero_one_and_two_transfers(players, fixtures, team, rules):
    report = build_recommendation(players, fixtures, team, rules, 4, horizon=5, max_transfers=2)
    assert [plan.transfer_count for plan in report.plans] == [0, 1, 2]
    assert report.recommended_transfer_count in {0, 1, 2}
    assert report.plans[0].expected_gain_vs_roll == 0
    assert report.plans[2].transfer_hit == 4


def test_every_generated_lineup_is_legal(players, fixtures, team, rules):
    report = build_recommendation(players, fixtures, team, rules, 4)
    engine = RulesEngine(rules, players)
    for plan in report.plans:
        updated = engine.apply_transfers(team, plan.transfers)
        engine.validate_lineup(updated, plan.lineup)


def test_injured_player_has_an_explicit_decision(players, fixtures, team, rules):
    report = build_recommendation(players, fixtures, team, rules, 4)
    for plan in report.plans:
        assert any(decision.player_id == 6 for decision in plan.injury_decisions)
