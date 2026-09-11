from fpl_agent.data import money_to_units, units_to_money


def test_money_uses_exact_tenths():
    assert money_to_units("7.5") == 75
    assert money_to_units(7) == 70
    assert units_to_money(75) == "£7.5m"


def test_sample_data_loads(players, fixtures, team, rules):
    assert len(players) == 25
    assert len(fixtures) == 40
    assert len(team.squad) == rules.squad_size == 15
