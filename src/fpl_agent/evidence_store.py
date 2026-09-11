"""SQLite persistence for immutable evidence observations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fpl_agent.evidence import EvidenceObservation

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class InsertResult:
    observation_id: int
    inserted: bool


class EvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    claim TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chance_of_playing REAL NOT NULL,
                    expected_minutes REAL NOT NULL,
                    source_url TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    quarantined INTEGER NOT NULL,
                    safety_flags TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_player_published
                ON evidence_observations(player_id, published_at DESC);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def add(self, observation: EvidenceObservation) -> InsertResult:
        digest = self._content_hash(observation)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO evidence_observations(
                    player_id, claim, status, chance_of_playing, expected_minutes,
                    source_url, source_type, provider, published_at, retrieved_at,
                    confidence, quarantined, safety_flags, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.player_id,
                    observation.claim,
                    observation.status,
                    observation.chance_of_playing,
                    observation.expected_minutes,
                    observation.source_url,
                    observation.source_type,
                    observation.provider,
                    observation.published_at.isoformat(),
                    observation.retrieved_at.isoformat(),
                    observation.confidence,
                    int(observation.quarantined),
                    json.dumps(observation.safety_flags),
                    digest,
                ),
            )
            inserted = cursor.rowcount == 1
            row = connection.execute(
                "SELECT id FROM evidence_observations WHERE content_hash = ?", (digest,)
            ).fetchone()
        return InsertResult(observation_id=int(row["id"]), inserted=inserted)

    def add_many(self, observations: list[EvidenceObservation]) -> list[InsertResult]:
        return [self.add(observation) for observation in observations]

    def list_observations(
        self,
        player_id: int | None = None,
        *,
        include_quarantined: bool = True,
    ) -> list[EvidenceObservation]:
        where: list[str] = []
        parameters: list[int] = []
        if player_id is not None:
            where.append("player_id = ?")
            parameters.append(player_id)
        if not include_quarantined:
            where.append("quarantined = 0")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM evidence_observations
                {clause}
                ORDER BY published_at DESC, id DESC
                """,  # noqa: S608 - clause is built only from fixed strings
                parameters,
            ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
        if row is None:
            raise RuntimeError("Evidence database is not initialized")
        return int(row["value"])

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
    def _content_hash(observation: EvidenceObservation) -> str:
        stable = {
            "player_id": observation.player_id,
            "claim": observation.claim,
            "status": observation.status,
            "chance_of_playing": observation.chance_of_playing,
            "expected_minutes": observation.expected_minutes,
            "source_url": observation.source_url,
            "source_type": observation.source_type,
            "provider": observation.provider,
            "published_at": observation.published_at.isoformat(),
            "confidence": observation.confidence,
        }
        payload = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _row_to_observation(row: sqlite3.Row) -> EvidenceObservation:
        return EvidenceObservation(
            id=row["id"],
            player_id=row["player_id"],
            claim=row["claim"],
            status=row["status"],
            chance_of_playing=row["chance_of_playing"],
            expected_minutes=row["expected_minutes"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            provider=row["provider"],
            published_at=row["published_at"],
            retrieved_at=row["retrieved_at"],
            confidence=row["confidence"],
            quarantined=bool(row["quarantined"]),
            safety_flags=json.loads(row["safety_flags"]),
        )
