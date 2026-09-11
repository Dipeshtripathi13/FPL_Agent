"""Typed domain objects shared by every layer of the application.

Keeping these models independent from the LLM is deliberate: model output is
untrusted until it has been parsed and validated against these contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(StrEnum):
    GOALKEEPER = "GK"
    DEFENDER = "DEF"
    MIDFIELDER = "MID"
    FORWARD = "FWD"


class Player(StrictModel):
    id: int
    name: str
    club: str
    position: Position
    price: int = Field(description="Current price in tenths of a million pounds")
    points_per_game: float = Field(ge=0)
    form: float = Field(ge=0)
    chance_of_playing: float = Field(ge=0, le=1)
    expected_minutes: float = Field(ge=0, le=120)
    status: str = "available"
    news: str = ""
    source_url: str | None = None
    source_published_at: datetime | None = None


class Fixture(StrictModel):
    gameweek: int = Field(gt=0)
    club: str
    opponent: str
    is_home: bool
    difficulty: int = Field(ge=1, le=5)


class TeamPick(StrictModel):
    player_id: int
    purchase_price: int = Field(ge=0)
    selling_price: int = Field(ge=0)


class TeamState(StrictModel):
    entry_id: str = "manual"
    bank: int = Field(ge=0, description="Money in the bank in tenths of a million")
    free_transfers: int = Field(ge=0)
    active_chip: str | None = None
    squad: list[TeamPick]

    @field_validator("squad")
    @classmethod
    def unique_players(cls, picks: list[TeamPick]) -> list[TeamPick]:
        ids = [pick.player_id for pick in picks]
        if len(ids) != len(set(ids)):
            raise ValueError("A squad cannot contain the same player twice")
        return picks


class LineupLimits(StrictModel):
    minimum: dict[Position, int]
    maximum: dict[Position, int]


class FPLRules(StrictModel):
    season: str
    squad_size: int = 15
    starting_size: int = 11
    initial_budget: int = 1000
    max_players_per_club: int = 3
    squad_positions: dict[Position, int]
    lineup: LineupLimits
    max_free_transfers: int = 5
    additional_transfer_cost: int = 4
    max_transfers_per_gameweek: int = 20
    chips: list[str]
    chip_sets: int = 2
    deadline_minutes_before_first_match: int = 90


class PlayerProjection(StrictModel):
    player_id: int
    gameweek: int
    expected_points: float
    fixture_count: int
    explanation: str


class Lineup(StrictModel):
    gameweek: int
    starters: list[int]
    bench_goalkeeper: int
    bench_order: list[int]
    captain: int
    vice_captain: int
    expected_points: float

    @model_validator(mode="after")
    def roles_are_valid(self) -> Lineup:
        if self.captain == self.vice_captain:
            raise ValueError("Captain and vice-captain must be different")
        if self.captain not in self.starters or self.vice_captain not in self.starters:
            raise ValueError("Captain and vice-captain must be starters")
        return self


class Transfer(StrictModel):
    player_out: int
    player_in: int
    selling_price: int
    purchase_price: int


class InjuryDecision(StrictModel):
    player_id: int
    action: str
    reason: str
    evidence_url: str | None = None


class TransferPlan(StrictModel):
    transfer_count: int
    transfers: list[Transfer]
    bank_after: int
    transfer_hit: int
    option_value_penalty: float
    gross_horizon_points: float
    objective_points: float
    expected_gain_vs_roll: float
    lineup: Lineup
    injury_decisions: list[InjuryDecision]


class PlayerEvidenceAudit(StrictModel):
    player_id: int
    observation_ids: list[int]
    selected_observation_id: int | None
    applied: bool
    blocked_reasons: list[str]
    stale: bool
    conflict: bool


class EvidenceAudit(StrictModel):
    schema_version: int
    as_of: datetime
    max_age_hours: int = Field(ge=1)
    allow_conflicts: bool
    allow_stale: bool
    observation_count: int = Field(ge=0)
    observation_ids: list[int]
    observation_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quarantined_observation_ids: list[int]
    unknown_player_observation_ids: list[int]
    player_resolutions: list[PlayerEvidenceAudit]

    @field_validator("as_of")
    @classmethod
    def as_of_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence audit as_of must include a timezone")
        return value


class RecommendationReport(StrictModel):
    generated_at: datetime
    season: str
    gameweek: int
    horizon: int
    current_horizon_points: float
    recommended_transfer_count: int
    plans: list[TransferPlan]
    assumptions: list[str]
    warnings: list[str]
    evidence_audit: EvidenceAudit | None = None
