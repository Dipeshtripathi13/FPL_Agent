"""Evidence models, import helpers, safety screening, and availability resolution."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from fpl_agent.models import Player, StrictModel


class EvidenceObservation(StrictModel):
    """One source-bound claim; observations are immutable after insertion."""

    id: int | None = None
    player_id: int
    claim: str = Field(min_length=1, max_length=500)
    status: str = Field(pattern=r"^(available|doubtful|injured|suspended|unknown)$")
    chance_of_playing: float = Field(ge=0, le=1)
    expected_minutes: float = Field(ge=0, le=120)
    source_url: str = Field(pattern=r"^https://")
    source_type: str = "manual"
    provider: str = "manual"
    published_at: datetime
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: float = Field(ge=0, le=1)
    quarantined: bool = False
    safety_flags: list[str] = Field(default_factory=list)

    @field_validator("published_at", "retrieved_at")
    @classmethod
    def timestamps_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def suspicious_claims_are_always_quarantined(self) -> EvidenceObservation:
        flags = sorted(set(self.safety_flags).union(detect_prompt_injection(self.claim)))
        if flags:
            self.quarantined = True
            self.safety_flags = flags
        return self


class ResolvedAvailability(StrictModel):
    player_id: int
    status: str
    chance_of_playing: float
    expected_minutes: float
    claim: str
    source_url: str
    published_at: datetime
    observation_ids: list[int]
    stale: bool
    conflict: bool
    warnings: list[str]


INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|override)\b.{0,50}\b(instruction|prompt|rule)s?\b",
        re.IGNORECASE,
    ),
    "role_impersonation": re.compile(
        r"(?:^|\s)(system|developer|assistant)\s*:", re.IGNORECASE
    ),
    "tool_markup": re.compile(r"</?(tool_call|tool_response|system|assistant)>|```tool", re.I),
    "action_injection": re.compile(
        r"\b(execute|invoke|call|run)\b.{0,40}\b(tool|command|transfer)\b", re.I
    ),
    "secret_request": re.compile(
        r"\b(reveal|print|send|upload)\b.{0,40}\b(token|password|secret|cookie)\b", re.I
    ),
}


def detect_prompt_injection(text: str) -> list[str]:
    """Flag common instruction-like payloads before evidence can reach a model.

    This heuristic is intentionally conservative and is not a complete prompt-injection defense.
    Quarantining suspicious observations is safer than attempting to clean and reuse them.
    """

    return [name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text)]


def resolve_player_reference(reference: int | str, players: dict[int, Player]) -> int:
    if isinstance(reference, int) or str(reference).isdigit():
        player_id = int(reference)
        if player_id not in players:
            raise ValueError(f"Unknown player id {player_id}")
        return player_id

    query = str(reference).strip().casefold()
    exact = [player.id for player in players.values() if player.name.casefold() == query]
    if len(exact) == 1:
        return exact[0]
    partial = [player.id for player in players.values() if query in player.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f"No player matches {reference!r}")
    names = ", ".join(players[player_id].name for player_id in partial)
    raise ValueError(f"Player reference {reference!r} is ambiguous: {names}")


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object at the root of {path}")
    return data


def load_evidence_yaml(
    path: str | Path,
    players: dict[int, Player],
    retrieved_at: datetime | None = None,
) -> list[EvidenceObservation]:
    data = _read_yaml(path)
    items = data.get("observations")
    if not isinstance(items, list):
        raise ValueError("Evidence YAML must contain an 'observations' list")
    retrieval_time = retrieved_at or datetime.now(UTC)
    observations: list[EvidenceObservation] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Evidence item {index} must be an object")
        reference = item.get("player_id", item.get("player"))
        if reference is None:
            raise ValueError(f"Evidence item {index} requires player_id or player")
        chance = float(item["chance_of_playing"])
        if chance > 1:
            chance /= 100
        claim = str(item["claim"]).strip()
        flags = detect_prompt_injection(claim)
        observations.append(
            EvidenceObservation(
                player_id=resolve_player_reference(reference, players),
                claim=claim,
                status=str(item["status"]).lower(),
                chance_of_playing=chance,
                expected_minutes=float(item["expected_minutes"]),
                source_url=str(item["source_url"]),
                source_type=str(item.get("source_type", "manual")),
                provider=str(item.get("provider", "manual")),
                published_at=item["published_at"],
                retrieved_at=item.get("retrieved_at", retrieval_time),
                confidence=float(item["confidence"]),
                quarantined=bool(flags),
                safety_flags=flags,
            )
        )
    return observations


class EvidenceResolver:
    """Resolve many immutable claims into one conservative availability view."""

    def __init__(self, max_age_hours: int = 168, conflict_confidence: float = 0.6) -> None:
        if max_age_hours < 1:
            raise ValueError("max_age_hours must be positive")
        self.max_age = timedelta(hours=max_age_hours)
        self.conflict_confidence = conflict_confidence

    def resolve(
        self,
        player_id: int,
        observations: list[EvidenceObservation],
        now: datetime | None = None,
    ) -> ResolvedAvailability | None:
        current_time = now or datetime.now(UTC)
        usable = [
            observation
            for observation in observations
            if observation.player_id == player_id and not observation.quarantined
        ]
        if not usable:
            return None

        fresh = [
            observation
            for observation in usable
            if timedelta(0) <= current_time - observation.published_at <= self.max_age
        ]
        candidates = fresh or usable

        def evidence_score(observation: EvidenceObservation) -> tuple[float, datetime]:
            age = max(timedelta(0), current_time - observation.published_at)
            freshness = max(0.1, 1 - age / self.max_age)
            return observation.confidence * freshness, observation.published_at

        primary = max(candidates, key=evidence_score)
        strong_fresh = [
            observation
            for observation in fresh
            if observation.confidence >= self.conflict_confidence
        ]
        statuses = {observation.status for observation in strong_fresh}
        chance_values = [observation.chance_of_playing for observation in strong_fresh]
        conflict = bool(
            "available" in statuses
            and bool(statuses.intersection({"doubtful", "injured", "suspended"}))
        ) or bool(chance_values and max(chance_values) - min(chance_values) >= 0.5)
        warnings: list[str] = []
        if not fresh:
            warnings.append(
                f"All evidence is older than {int(self.max_age.total_seconds() // 3600)} hours."
            )
        if conflict:
            warnings.append("Fresh high-confidence sources conflict; manual review is required.")

        return ResolvedAvailability(
            player_id=player_id,
            status=primary.status,
            chance_of_playing=primary.chance_of_playing,
            expected_minutes=primary.expected_minutes,
            claim=primary.claim,
            source_url=primary.source_url,
            published_at=primary.published_at,
            observation_ids=[
                observation.id for observation in candidates if observation.id is not None
            ],
            stale=not bool(fresh),
            conflict=conflict,
            warnings=warnings,
        )


def apply_resolved_evidence(
    players: dict[int, Player],
    resolutions: list[ResolvedAvailability],
    *,
    allow_conflicts: bool = False,
    allow_stale: bool = False,
) -> tuple[dict[int, Player], list[str]]:
    """Overlay accepted evidence while returning every fail-closed warning."""

    updated = dict(players)
    warnings: list[str] = []
    for resolution in resolutions:
        player = players.get(resolution.player_id)
        if player is None:
            warnings.append(f"Evidence refers to unknown player id {resolution.player_id}.")
            continue
        if resolution.conflict and not allow_conflicts:
            warnings.append(f"Conflicting evidence for {player.name} was not applied.")
            continue
        if resolution.stale and not allow_stale:
            warnings.append(f"Stale evidence for {player.name} was not applied.")
            continue
        updated[player.id] = player.model_copy(
            update={
                "status": resolution.status,
                "chance_of_playing": resolution.chance_of_playing,
                "expected_minutes": resolution.expected_minutes,
                "news": resolution.claim,
                "source_url": resolution.source_url,
                "source_published_at": resolution.published_at,
            }
        )
    return updated, warnings


def integrate_evidence(
    players: dict[int, Player],
    observations: list[EvidenceObservation],
    *,
    max_age_hours: int = 168,
    allow_conflicts: bool = False,
    allow_stale: bool = False,
    now: datetime | None = None,
) -> tuple[dict[int, Player], list[ResolvedAvailability], list[str]]:
    """Resolve stored observations and apply only policy-approved results."""

    resolver = EvidenceResolver(max_age_hours=max_age_hours)
    resolutions: list[ResolvedAvailability] = []
    warnings: list[str] = []
    known_ids = set(players)
    unknown_ids = sorted({item.player_id for item in observations} - known_ids)
    if unknown_ids:
        warnings.append(f"Evidence database contains unknown player ids: {unknown_ids}.")
    quarantined = [item for item in observations if item.quarantined]
    if quarantined:
        warnings.append(
            f"{len(quarantined)} suspicious evidence observation(s) were quarantined and ignored."
        )
    for player_id in known_ids:
        resolution = resolver.resolve(player_id, observations, now=now)
        if resolution is not None:
            resolutions.append(resolution)
            warnings.extend(
                f"{players[player_id].name}: {warning}" for warning in resolution.warnings
            )
    updated, overlay_warnings = apply_resolved_evidence(
        players,
        resolutions,
        allow_conflicts=allow_conflicts,
        allow_stale=allow_stale,
    )
    warnings.extend(overlay_warnings)
    return updated, resolutions, warnings
