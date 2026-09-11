# Data and provenance

## Why input data is explicit

The MVP reads snapshots rather than silently collecting them. This keeps experiments reproducible,
makes the source of every claim visible, and avoids coupling the core to an undocumented website.

```mermaid
flowchart LR
    S[Permitted source or manual research] --> R[Raw observation]
    R --> N[Normalize identifiers and units]
    N --> V[Pydantic validation]
    V --> C[Local calculation]
    C --> O[Report with provenance]
```

## Player CSV

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Stable identifier within your snapshot |
| `name` | text | Display name |
| `club` | text | Club identifier used by fixture rows |
| `position` | enum | `GK`, `DEF`, `MID`, or `FWD` |
| `price` | decimal | Current buying price in millions |
| `points_per_game` | number | Season or selected-window rate |
| `form` | number | Recent performance rate |
| `chance_of_playing` | 0–100 | Estimated probability of appearing |
| `expected_minutes` | 0–120 | Estimated minutes conditional on the gameweek |
| `status` | text | For example `available`, `doubtful`, `injured` |
| `news` | text | Short evidence-based availability statement |
| `source_url` | URL | Where the availability statement came from |
| `source_published_at` | datetime | ISO-8601 evidence timestamp |

`chance_of_playing` is an estimate, not a fact. CSV values are the baseline snapshot. The evidence
pipeline can overlay a newer derived estimate without changing that original file.

## Evidence observations

`examples/evidence.yaml` is the human-review interchange format. `fpl-agent evidence import` validates
each item and appends it to `data/private/evidence.db`. One row means one source-bound claim, not the
final truth about a player.

```mermaid
erDiagram
    PLAYER ||--o{ EVIDENCE_OBSERVATION : "is about"
    PLAYER {
      int id
      string name
    }
    EVIDENCE_OBSERVATION {
      int id
      int player_id
      string claim
      string status
      float chance_of_playing
      float expected_minutes
      string source_url
      datetime published_at
      datetime retrieved_at
      float confidence
      bool quarantined
      string content_hash
    }
```

Publication time answers “when could this claim have been known?” Retrieval time answers “when did
this run obtain it?” The distinction prevents a newly fetched old article from looking like fresh
news. The content hash makes retries idempotent, and the append-only store retains conflicting claims
for audit. See [Evidence pipeline](11-evidence-pipeline.md) for the resolver policy.

## Fixture CSV

There is one row per club per fixture. A double gameweek therefore has two rows for the same club and
gameweek; a blank gameweek has none.

| Field | Meaning |
|---|---|
| `gameweek` | Gameweek number |
| `club` | Must match `players.csv` |
| `opponent` | Human-readable opponent |
| `is_home` | Boolean venue flag |
| `difficulty` | Integer from 1 (easiest) to 5 (hardest) |

## Team YAML

The team file contains bank value, free transfers, active chip, and 15 picks. Purchase and selling
prices are separate because FPL sale-price rules mean the current market price is not necessarily what
your team receives when selling.

Prices become integer tenths internally:

```text
£7.5m -> 75
```

Integer money avoids floating-point errors such as treating `7.1 + 0.2` as slightly more or less than
`7.3`.

## Source hierarchy

Prefer, in order:

1. Official club statements and press conferences used under their permitted terms.
2. Properly licensed structured sports-data providers.
3. Reputable reporting that identifies its source.
4. Social posts only when clearly labeled as low-confidence evidence.

Store retrieval time separately from publication time. A page fetched today may contain a week-old
claim. Discovery adapters cache responses and honor provider rate limits, but you must still review
each provider's data retention, attribution, and redistribution rights.

## Private-data workflow

Keep real files under `data/private/`; Git ignores this directory. Before every commit, run:

```bash
git status --short
git diff --cached
```

Never place an access token, session cookie, password, email login, or private API response in a model
prompt or tracked file.
