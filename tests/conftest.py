from pathlib import Path

import pytest

from fpl_agent.data import load_fixtures, load_players, load_rules, load_team

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def players():
    return load_players(ROOT / "examples/players.csv")


@pytest.fixture
def fixtures():
    return load_fixtures(ROOT / "examples/fixtures.csv")


@pytest.fixture
def team():
    return load_team(ROOT / "examples/team.yaml")


@pytest.fixture
def rules():
    return load_rules(ROOT / "rules/2026_27.yaml")
