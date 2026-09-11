import pytest

from fpl_agent.projection import ProjectionEngine


def test_easier_fixture_produces_more_points(players, fixtures):
    engine = ProjectionEngine(players, fixtures)
    northport = engine.project_player(players[8], 4)
    southbank = engine.project_player(players[9], 4)
    assert northport.expected_points > southbank.expected_points


def test_blank_gameweek_is_zero(players, fixtures):
    projection = ProjectionEngine(players, fixtures).project_player(players[1], 99)
    assert projection.expected_points == 0
    assert projection.fixture_count == 0


def test_injury_reduces_projection(players, fixtures):
    engine = ProjectionEngine(players, fixtures)
    assert engine.project_player(players[6], 4).expected_points < 1


def test_double_gameweek_adds_both_fixtures(players, fixtures):
    from fpl_agent.models import Fixture

    doubled = fixtures + [
        Fixture(gameweek=4, club="Northport", opponent="Meadow", is_home=True, difficulty=2)
    ]
    single = ProjectionEngine(players, fixtures).project_player(players[8], 4)
    double = ProjectionEngine(players, doubled).project_player(players[8], 4)
    assert double.fixture_count == 2
    assert double.expected_points == pytest.approx(2 * single.expected_points, abs=0.002)
