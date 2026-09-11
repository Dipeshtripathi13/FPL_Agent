# Follow one request: “Review my team for GW5”

This chapter follows one user request through every component until the user receives a result.

## Before the question: prepare current evidence

The agent does **not** browse automatically during a review. Research and evidence approval are a
separate preparation phase:

```mermaid
flowchart LR
    U[User chooses<br/>reviewed domains] --> S[research command]
    S --> B[Brave Search API]
    B --> L[Untrusted leads]
    L --> H[Human opens and<br/>checks source]
    H --> Y[Human writes<br/>evidence YAML]
    Y --> I[evidence import]
    I --> D[(Local evidence.db)]
```

Why the manual step? A search snippet may be wrong, stale, or malicious. It cannot become a player
fact by itself.

For the fictional walkthrough, prepare the database:

```bash
fpl-agent evidence init
fpl-agent evidence import examples/evidence.yaml
```

## Step 1: the user starts the GW5 review

The user runs:

```bash
fpl-agent agent --gameweek 5 \
  --prompt "Review my team. Recommend transfers, starting XI, captain and vice-captain." \
  --evidence-db data/private/evidence.db \
  --evidence-as-of 2026-09-18T00:00:00Z
```

This uses the Qwen route. There is also a direct deterministic route:

```mermaid
flowchart TD
    U[User wants a GW5 review] --> C{Which command?}
    C -->|agent| Q[Qwen selects a<br/>read-only tool]
    C -->|recommend| P[Call trusted Python<br/>directly]
    Q --> P
    P --> R[Same deterministic<br/>recommendation core]
```

Use `recommend` when you only need the result. Use `agent` when you want to study model tool
selection. Both use the same rules, projection, and optimizer code.

## Step 2: the complete interaction

Read this sequence from top to bottom:

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant C as CLI
    participant L as Data loaders
    participant E as Evidence policy
    participant H as Tool harness
    participant Q as Local Qwen
    participant R as Rules engine
    participant P as Projection engine
    participant O as Optimizer
    participant M as Report renderer

    U->>C: agent --gameweek 5 + question
    C->>L: Load players, fixtures, team, rules
    L-->>C: Typed Python objects
    C->>E: Read observations at as-of time
    E-->>C: Safe player overlay + warnings + audit
    C->>H: Build five read-only tools
    H->>Q: Question + system policy + tool schemas
    Q-->>H: calculate_recommendation(GW5, horizon=5, transfers=2)
    H->>R: Validate current squad and candidates
    R-->>H: Legal / rejected
    H->>P: Project every player for GW5–GW9
    P-->>H: Expected-points table
    H->>O: Compare roll, 1-transfer, 2-transfer plans
    O-->>H: Best legal plans and lineups
    H-->>Q: Structured tool result
    Q-->>H: Short completion message
    H->>H: Select last validated recommendation result
    H->>M: Result + player names + evidence audit
    M-->>C: Trusted Markdown report
    C-->>U: Transfers, XI, bench, captain, warnings, audit
    U->>U: Review and apply manually in official FPL UI
```

Qwen starts the calculation by choosing a tool. It does not calculate expected points, decide whether
a formation is legal, or write the final factual report.

## Step 3: what happens to one player

Follow fictional defender Flint through the run:

```mermaid
flowchart LR
    A[players.csv<br/>baseline Flint] --> O[Create player copy]
    B[evidence.db<br/>injured, 10%, 5 min] --> F{Fresh and<br/>consistent?}
    F -->|yes| O
    F -->|no| W[Keep baseline<br/>and add warning]
    O --> X[Very low GW5 xP]
    X --> C{Best use in<br/>each plan?}
    C -->|sold| T[transfer]
    C -->|kept, not XI| BN[bench]
    C -->|kept, in XI| SR[start_with_risk]
```

The evidence does not directly say “bench Flint.” It changes availability inputs. The projection
engine reduces Flint's expected points, and the optimizer decides whether transfer, bench, or risky
start is best for each plan.

## Step 4: how the optimizer builds the answer

```mermaid
flowchart TD
    XP[GW5–GW9 player xP] --> Z[Plan A: roll transfer]
    XP --> ONE[Plan B: best legal<br/>one transfer]
    XP --> TWO[Plan C: best legal<br/>two transfers]
    Z --> L[Optimize XI and captain]
    ONE --> L
    TWO --> L
    L --> H[Subtract transfer hits]
    H --> V[Subtract 0.5 points<br/>per transfer for option value]
    V --> BEST[Choose highest objective]
```

For every candidate, the rules engine checks squad size, positions, club limits, budget, selling
prices, and legal formation. Illegal plans never reach the final comparison.

## Step 5: the fictional result the user sees

With the current example files and evidence evaluated at `2026-09-18T00:00:00Z`, trusted code returns:

```mermaid
flowchart TB
    RESULT[GW5 recommendation] --> PLAN[2 transfers]
    PLAN --> T1[Kite → Thorne]
    PLAN --> T2[Oak → Vale]
    PLAN --> HIT[4-point hit]
    RESULT --> GAIN[Objective gain vs roll<br/>+15.47]
    RESULT --> CAP[Captain: Indigo<br/>Vice: Harbor]
    RESULT --> BENCH[Outfield bench<br/>Linden → Grove → Flint]
```

The starting XI is:

```text
GK:  Alder
DEF: Dune, Cedar, Elm
MID: Indigo (C), Harbor (VC), Thorne, Juniper
FWD: Vale, Maple, Nova
```

These numbers are produced by fictional teaching data. They will change when the inputs or algorithm
change and are not real FPL advice.

## Step 6: how failure branches behave

```mermaid
flowchart TD
    A[GW5 request] --> B{Inputs valid?}
    B -->|no| X1[Stop: explain invalid file or squad]
    B -->|yes| C{Evidence safe and current?}
    C -->|no| W[Keep baseline + warning]
    C -->|yes| D[Apply evidence overlay]
    W --> E{Qwen calls recommendation tool?}
    D --> E
    E -->|no| X2[Stop: no trusted plan]
    E -->|runtime failure| X3[Stop safely: no partial report]
    E -->|yes| F{Candidate plans legal?}
    F -->|some illegal| G[Reject those candidates]
    F -->|legal plans remain| H[Render trusted result]
    G --> H
    H --> I[Human review]
    I -->|accept| J[Apply manually]
    I -->|reject| K[Make no account change]
```

Failing closed means uncertainty produces no automatic authority. A warning cannot silently become
permission to change the account.

## Step 7: what is inside the final result

| Report section | What the user learns |
|---|---|
| Decision summary | Recommended number of transfers |
| Compared plans | Roll, one-transfer, and two-transfer objective scores |
| Transfers | Exact sell/buy names and prices |
| Starting XI | Legal GW5 formation |
| Captain and vice-captain | Highest projected starting options |
| Bench | Reserve goalkeeper and ordered outfield substitutes |
| Availability decisions | Transfer, bench, or start-with-risk reasoning |
| Evidence audit | Observation IDs, selected rows, policy and fingerprint |
| Warnings | Uncertainty, stale/conflicting evidence, or unsupported scope |
| Agent audit | Number of Qwen tool calls and trusted-rendering statement |

The `agent` command prints Markdown. The `recommend` command can also save machine-readable JSON with
`--json-output`.

## Try it interactively

### Checkpoint A — inspect before asking Qwen

```bash
fpl-agent evidence timeline --player Flint \
  --as-of 2026-09-18T00:00:00Z
```

Before continuing, predict: will Flint start, sit on the bench, or be transferred?

### Checkpoint B — run without Qwen

```bash
fpl-agent recommend --gameweek 5 \
  --evidence-db data/private/evidence.db \
  --evidence-as-of 2026-09-18T00:00:00Z
```

Write down the transfers, captain, and objective score.

### Checkpoint C — run through Qwen

```bash
fpl-agent agent --gameweek 5 \
  --prompt "Review my team and calculate the best plan." \
  --evidence-db data/private/evidence.db \
  --evidence-as-of 2026-09-18T00:00:00Z
```

Compare it with Checkpoint B. The factual plan should match because Qwen calls the same trusted
service.

### Checkpoint D — make the evidence stale

Move the clock forward:

```bash
fpl-agent recommend --gameweek 5 \
  --evidence-db data/private/evidence.db \
  --evidence-as-of 2026-10-01T00:00:00Z
```

Find the stale-evidence warning and compare the plan. This shows that time is part of the input.

## The request in one line

```text
User question → typed inputs → evidence policy → Qwen tool choice → trusted calculation
→ deterministic report → human review → manual action
```

That is the complete end-to-end lifecycle of a GW5 request in the current project.
