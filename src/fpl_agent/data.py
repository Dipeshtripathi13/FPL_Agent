"""Load user-owned or properly licensed snapshots into typed domain models."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from fpl_agent.models import Fixture, FPLRules, Player, Position, TeamPick, TeamState


def money_to_units(value: str | int | float) -> int:
    """Convert pounds-million notation (7.5) to exact integer units (75)."""
    return round(float(value) * 10)


def units_to_money(value: int) -> str:
    return f"£{value / 10:.1f}m"


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


def _optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_players(path: str | Path) -> dict[int, Player]:
    players: dict[int, Player] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            player = Player(
                id=int(row["id"]),
                name=row["name"],
                club=row["club"],
                position=Position(row["position"].upper()),
                price=money_to_units(row["price"]),
                points_per_game=float(row["points_per_game"]),
                form=float(row["form"]),
                chance_of_playing=float(row["chance_of_playing"]) / 100,
                expected_minutes=float(row["expected_minutes"]),
                status=row.get("status", "available") or "available",
                news=row.get("news", "") or "",
                source_url=row.get("source_url") or None,
                source_published_at=_optional_datetime(row.get("source_published_at")),
            )
            if player.id in players:
                raise ValueError(f"Duplicate player id {player.id} in {path}")
            players[player.id] = player
    if not players:
        raise ValueError(f"No players found in {path}")
    return players


def load_fixtures(path: str | Path) -> list[Fixture]:
    fixtures: list[Fixture] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            fixtures.append(
                Fixture(
                    gameweek=int(row["gameweek"]),
                    club=row["club"],
                    opponent=row["opponent"],
                    is_home=_parse_bool(row["is_home"]),
                    difficulty=int(row["difficulty"]),
                )
            )
    return fixtures


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object at the root of {path}")
    return data


def load_team(path: str | Path) -> TeamState:
    data = _read_yaml(path)
    data["bank"] = money_to_units(data["bank"])
    data["squad"] = [
        TeamPick(
            player_id=int(item["player_id"]),
            purchase_price=money_to_units(item["purchase_price"]),
            selling_price=money_to_units(item["selling_price"]),
        )
        for item in data["squad"]
    ]
    return TeamState.model_validate(data)


def load_rules(path: str | Path) -> FPLRules:
    data = _read_yaml(path)
    data["initial_budget"] = money_to_units(data["initial_budget"])
    return FPLRules.model_validate(data)
