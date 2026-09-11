"""Typed registry for reviewed web-source domains and expiring terms decisions."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from fpl_agent.models import StrictModel

DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
BLOCKED_GAME_DOMAINS = {
    "fantasy.premierleague.com",
    "draft.premierleague.com",
    "fplchallenge.premierleague.com",
}


def is_blocked_game_domain(domain: str) -> bool:
    normalized = domain.casefold().strip(". ")
    return any(
        normalized == blocked or normalized.endswith(f".{blocked}")
        for blocked in BLOCKED_GAME_DOMAINS
    )


class ReviewedSource(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    domain: str
    terms_url: str = Field(pattern=r"^https://")
    reviewed_at: date
    review_after_days: int = Field(default=180, ge=1, le=3650)
    purpose: str = Field(min_length=1, max_length=300)
    enabled: bool = True

    @field_validator("domain")
    @classmethod
    def domain_must_be_a_bare_hostname(cls, value: str) -> str:
        normalized = value.casefold().strip(". ")
        if not DOMAIN_PATTERN.fullmatch(normalized):
            raise ValueError("domain must be a bare hostname such as news.example.com")
        if is_blocked_game_domain(normalized):
            raise ValueError(
                f"automated FPL game domain is blocked by project policy: {normalized}"
            )
        return normalized

    @property
    def review_expires_at(self) -> date:
        return self.reviewed_at + timedelta(days=self.review_after_days)


class SourceReviewStatus(StrictModel):
    name: str
    domain: str
    reviewed_at: date
    review_expires_at: date
    enabled: bool
    current: bool
    reason: Literal["current", "disabled", "review_in_future", "review_expired"]


class SourcePolicy(StrictModel):
    version: Literal[1] = 1
    sources: list[ReviewedSource] = Field(min_length=1)

    @model_validator(mode="after")
    def domains_must_be_unique(self) -> SourcePolicy:
        domains = [source.domain for source in self.sources]
        if len(domains) != len(set(domains)):
            raise ValueError("source domains must be unique")
        return self

    def evaluate(self, as_of: date | None = None) -> list[SourceReviewStatus]:
        evaluation_date = as_of or date.today()
        statuses: list[SourceReviewStatus] = []
        for source in self.sources:
            if not source.enabled:
                reason = "disabled"
            elif source.reviewed_at > evaluation_date:
                reason = "review_in_future"
            elif evaluation_date > source.review_expires_at:
                reason = "review_expired"
            else:
                reason = "current"
            statuses.append(
                SourceReviewStatus(
                    name=source.name,
                    domain=source.domain,
                    reviewed_at=source.reviewed_at,
                    review_expires_at=source.review_expires_at,
                    enabled=source.enabled,
                    current=reason == "current",
                    reason=reason,
                )
            )
        return statuses

    def current_domains(self, as_of: date | None = None) -> list[str]:
        return [status.domain for status in self.evaluate(as_of) if status.current]


def load_source_policy(path: str | Path) -> SourcePolicy:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object at the root of {path}")
    return SourcePolicy.model_validate(data)
