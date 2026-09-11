# FPL Agent

FPL Agent is a local-first, explainable learning project that recommends Fantasy Premier League
transfers, a starting XI, bench order, captain, and vice-captain. A local Qwen model can call the
read-only analysis tools through Ollama and explain the deterministic result.

> **MVP safety boundary:** this repository does not log in to FPL, scrape the FPL game, or submit
> account changes. It operates on manually supplied, user-owned, synthetic, or properly licensed
> snapshots and produces advice for a human to review.

The sample players and clubs are entirely fictional. This project is not affiliated with or endorsed
by the Premier League or Fantasy Premier League.

## What the project can do

- Validate a 15-player squad against versioned 2026/27 rules.
- Project player points over one to eight gameweeks.
- Understand blank and double gameweeks from the supplied fixture rows.
- Compare rolling a transfer with the best one- and two-transfer candidates.
- Account for available money, actual selling prices, free transfers, and point hits.
- Optimize a legal formation, captain, vice-captain, reserve goalkeeper, and bench order.
- Turn availability evidence into an explicit `transfer`, `bench`, or `start_with_risk` decision.
- Let a local `qwen3:8b` model select safe tools, then render their validated result.
- Store source-bound availability observations in an immutable local SQLite history.
- Resolve player names, freshness, and conflicting evidence with fail-closed policies.
- Discover reviewable web sources through an allowlisted, cached Brave Search adapter.
- Render per-player evidence timelines and embed evidence fingerprints in reports.
- Expire reusable domain permissions through a reviewed-source registry.
- Produce Markdown and machine-readable JSON reports.

The project does not automatically turn search snippets into facts, predict price changes, optimize
chips, learn model weights from historical data, or make account changes. Those are later milestones,
described in [the roadmap](docs/10-roadmap.md).

## Quick start

Python 3.11 or newer is required. Ollama is optional for deterministic analysis and required only for
the `agent` command.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Validate the fictional learning squad:

```bash
fpl-agent validate
```

Generate the deterministic Gameweek 4 report:

```bash
fpl-agent recommend --gameweek 4 \
  --output reports/gameweek-4.md \
  --json-output reports/gameweek-4.json
```

Check the local model runtime and ask Qwen to use the tools:

```bash
fpl-agent doctor --model qwen3:8b
fpl-agent agent --gameweek 4 --model qwen3:8b
```

The model's free-form draft is suppressed because it is not a trustworthy data contract. Use
`--show-model-draft` only to study model behavior; the normal output is rendered from validated tool
results.

Build a local evidence history and use it in the recommendation:

```bash
fpl-agent evidence init
fpl-agent evidence import examples/evidence.yaml
fpl-agent evidence resolve --as-of 2026-09-12T00:00:00Z
fpl-agent evidence timeline --player Flint --as-of 2026-09-12T00:00:00Z
fpl-agent recommend --gameweek 4 \
  --evidence-db data/private/evidence.db \
  --evidence-as-of 2026-09-12T00:00:00Z
```

The `--evidence-as-of` option makes the fictional dated example reproducible. Omit it for a live
decision so freshness is measured against the current time. Read the
[evidence pipeline tutorial](docs/11-evidence-pipeline.md) before using real sources.

Check a fictional source registry—the `.invalid` entries cannot contact real sites:

```bash
fpl-agent sources check examples/research-sources.yaml --as-of 2026-09-12
```

Copy and replace that file under `data/private/` before real research. The
[audit and source-governance tutorial](docs/13-audits-and-source-governance.md) explains why reviews
expire and how recommendation fingerprints work.

Run the quality checks:

```bash
pytest
ruff check .
```

## Architecture

```mermaid
flowchart LR
    W[Allowlisted search leads] --> M[Human-reviewed evidence]
    S[Reviewed-source registry] --> W
    M --> E[(Immutable SQLite history)]
    E --> F[Freshness + conflict policy]
    F --> D[Typed player snapshot]
    U[Manual or licensed snapshots] --> D
    D --> R[Rules engine]
    D --> P[Projection engine]
    R --> O[Transfer and lineup optimizer]
    P --> O
    O --> C[CLI / JSON / Markdown]
    Q[Local Qwen through Ollama] --> H[Read-only tool harness]
    H --> R
    H --> O
    O --> H
    H --> EX[Educational explanation]
```

The model is not the rules engine or the calculator. It decides which read-only tools to call and
explains their structured results. This is the project's most important design decision: stochastic
language generation is useful around deterministic domain logic, not in place of it.

Search results are not evidence either. The research adapter returns unverified leads; a human must
review and import a typed observation before it can affect the optimizer.

Read [What is an agent?](docs/01-agentic-ai.md) and then the
[architecture walkthrough](docs/02-architecture.md) for a detailed tour.

## Use your own snapshots

Copy the files in `examples/` and replace the fictional values:

```bash
cp examples/team.yaml data/private/my-team.yaml
cp examples/players.csv data/private/my-players.csv
cp examples/fixtures.csv data/private/my-fixtures.csv
cp examples/evidence.yaml data/private/my-evidence.yaml
```

`data/private/` is ignored by Git. Keep the column names unchanged, use prices in millions such as
`7.5`, and record an evidence URL and timestamp for any availability claim. Then run:

```bash
fpl-agent evidence import data/private/my-evidence.yaml
fpl-agent recommend --gameweek 4 \
  --team data/private/my-team.yaml \
  --players data/private/my-players.csv \
  --fixtures data/private/my-fixtures.csv \
  --evidence-db data/private/evidence.db
```

The schemas and field meanings are explained in [Data and provenance](docs/03-data.md).

## Why account automation is excluded

The current FPL Terms state that participants must not use automated systems to access the game and
extract information. The interfaces used by the FPL website are also not a documented, stable public
developer API. Automating a browser would not remove that restriction.

For an open-source educational project, the responsible design is therefore:

1. Analyze manually supplied or properly licensed data.
2. Generate a complete, auditable recommendation.
3. Let the account owner review and apply the change in the official interface.
4. Develop any future write adapter only against a fake server unless written authorization is
   obtained.

References:

- [Official FPL game rules](https://fantasy.premierleague.com/help/rules)
- [Official FPL terms and conditions](https://fantasy.premierleague.com/help/terms)
- [Official Premier League website terms](https://www.premierleague.com/en/terms-and-conditions)
- [Qwen function-calling documentation](https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md)
- [Ollama tool-calling documentation](https://github.com/ollama/ollama/blob/main/docs/capabilities/tool-calling.mdx)

## Learning path

The documentation is arranged as a small course:

1. [Start here: end-to-end visual guide](docs/14-end-to-end-guide.md)
2. [Follow a complete GW5 request](docs/15-gw5-request-walkthrough.md)
3. [Learning plan](docs/00-learning-plan.md)
4. [Agentic AI fundamentals](docs/01-agentic-ai.md)
5. [System architecture](docs/02-architecture.md)
6. [Data and provenance](docs/03-data.md)
7. [FPL rules as code](docs/04-rules-engine.md)
8. [Expected-points modeling](docs/05-projections.md)
9. [Optimization](docs/06-optimization.md)
10. [The Qwen tool harness](docs/07-agent-harness.md)
11. [Safety and compliance](docs/08-safety.md)
12. [Testing and evaluation](docs/09-evaluation.md)
13. [Roadmap](docs/10-roadmap.md)
14. [Evidence pipeline](docs/11-evidence-pipeline.md)
15. [Safe web research](docs/12-safe-web-research.md)
16. [Audits and source governance](docs/13-audits-and-source-governance.md)
17. [Glossary](docs/glossary.md)

## Repository map

```text
FPL_Agent/
├── src/fpl_agent/       # Application code
│   └── providers/       # Bounded external discovery adapters
├── rules/               # Season-versioned deterministic rule packs
├── examples/            # Fictional data safe to commit
├── tests/               # Executable behavior and safety checks
├── docs/                # The learning course
└── .github/workflows/   # Automated quality checks
```

## License

Source code is available under the [MIT License](LICENSE). No rights are granted to Premier League
data, names, badges, logos, or other third-party intellectual property.
