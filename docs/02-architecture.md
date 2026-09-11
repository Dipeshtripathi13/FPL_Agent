# System architecture

## Layers

```mermaid
flowchart TB
    subgraph Inputs
      P[players.csv]
      F[fixtures.csv]
      T[team.yaml]
      Y[rules YAML]
      E[(evidence SQLite)]
      S[reviewed sources YAML]
    end
    subgraph Deterministic core
      L[Load and validate]
      R[RulesEngine]
      X[ProjectionEngine]
      O[TransferOptimizer]
      U[LineupOptimizer]
    end
    subgraph Interfaces
      C[CLI]
      J[JSON report]
      MD[Markdown report]
      A[OllamaAgent]
    end
    P --> L
    F --> L
    T --> L
    Y --> L
    E --> V[Evidence policy]
    S --> Q[Research provider]
    V --> L
    L --> R
    L --> X
    X --> O
    R --> O
    O --> U
    U --> J
    U --> MD
    V --> AU[Evidence audit]
    AU --> J
    AU --> MD
    C --> L
    A --> R
    A --> O
```

## Dependency direction

The domain models are at the center and do not know about the CLI or Ollama. The optimizer knows about
rules and projections but not about HTTP. The agent calls application services rather than duplicating
their logic.

This makes four future changes independent:

- Replace the heuristic projection with a trained model.
- Replace bounded enumeration with a multi-period MILP solver.
- Replace Ollama with another OpenAI-compatible local runtime.
- Add another licensed discovery provider behind the small provider protocol.

## One deterministic recommendation

```mermaid
sequenceDiagram
    participant CLI
    participant Loader
    participant Rules
    participant Projection
    participant Optimizer
    CLI->>Loader: Read snapshots
    Loader->>Rules: Typed squad
    Rules-->>CLI: Valid
    CLI->>Projection: GW + horizon
    Projection-->>Optimizer: Player xP by GW
    Optimizer->>Rules: Validate candidate transfers
    Rules-->>Optimizer: Accept/reject
    Optimizer->>Rules: Validate best lineups
    Optimizer-->>CLI: Roll, 1-transfer, 2-transfer plans
```

## One agent run

The agent is deliberately thin. It owns conversation state and the tool loop, while Python services
own facts and calculations. The registry exposes only five read-only tools, so even a malicious prompt
cannot cause an account change—the capability does not exist.

Evidence is resolved before that registry is built. Qwen sees only the policy-approved player view,
not quarantined search text or unresolved conflicting observations.

The source registry governs the separate research provider, not the agent. Its decision expires on a
date, while the recommendation's evidence audit captures the exact resolver decision for replay.
