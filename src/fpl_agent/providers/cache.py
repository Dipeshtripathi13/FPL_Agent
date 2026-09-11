"""Small SQLite cache for paid search-provider responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class SearchCache:
    def __init__(self, path: str | Path, ttl_hours: int = 6) -> None:
        if ttl_hours < 1:
            raise ValueError("Cache TTL must be positive")
        self.path = Path(path)
        self.ttl = timedelta(hours=ttl_hours)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS search_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    def get(self, provider: str, request: dict[str, Any]) -> list[dict[str, Any]] | None:
        key = self._key(provider, request)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json, expires_at FROM search_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
            return None
        value = json.loads(row["response_json"])
        return value if isinstance(value, list) else None

    def put(
        self, provider: str, request: dict[str, Any], response: list[dict[str, Any]]
    ) -> None:
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO search_cache(
                    cache_key, provider, request_json, response_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self._key(provider, request),
                    provider,
                    json.dumps(request, sort_keys=True),
                    json.dumps(response, sort_keys=True),
                    now.isoformat(),
                    (now + self.ttl).isoformat(),
                ),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _key(provider: str, request: dict[str, Any]) -> str:
        payload = json.dumps(
            {"provider": provider, "request": request}, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()
