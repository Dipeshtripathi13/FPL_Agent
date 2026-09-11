"""Provider contracts keep external search separate from trusted evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import Field

from fpl_agent.models import StrictModel


class ProviderDocument(StrictModel):
    provider: str
    title: str
    url: str = Field(pattern=r"^https://")
    snippet: str
    published_at: datetime | None = None
    retrieved_at: datetime
    safety_flags: list[str] = Field(default_factory=list)

    @property
    def quarantined(self) -> bool:
        return bool(self.safety_flags)


class EvidenceProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int = 5) -> list[ProviderDocument]: ...
