# Glossary

| Term | Meaning in this project |
|---|---|
| Agent | A model operating in a controlled loop with tools, state, and policies |
| Tool call | Structured model request to invoke a named function |
| Harness | Code that manages prompts, tools, results, limits, and safety rules |
| Schema | Machine-checkable description of valid input or output |
| Guardrail | Control that prevents or detects an unsafe/invalid action |
| Deterministic | Same input produces the same output |
| Stochastic | Output can vary because it is probabilistic |
| Expected points / xP | Probability-weighted estimate of future FPL points |
| Calibration | Whether predicted probabilities match observed frequencies |
| Data leakage | Using information that was unavailable at prediction time |
| Provenance | Where a datum came from and when it was observed |
| Observation | One immutable, source-bound claim; not automatically the final truth |
| Derived availability | Resolver output computed from one or more observations |
| Freshness window | Maximum accepted age of an observation at a chosen as-of time |
| Conflict | Strong fresh observations disagree enough to require review |
| Quarantine | Retain suspicious input for audit while preventing its use |
| Entity resolution | Map a source name or identifier to exactly one local player |
| Allowlist | Explicit set of reviewed domains permitted by a provider adapter |
| Provider | Replaceable adapter for discovering external source documents |
| Cache | Local reuse of a previous provider response for a bounded time |
| Temporal leakage | Using information that was unavailable at the simulated decision time |
| FDR | Fixture Difficulty Rating from 1 to 5 in this input schema |
| Horizon | Number of future gameweeks considered |
| Objective | Numeric score the optimizer tries to maximize |
| Constraint | Rule every candidate solution must satisfy |
| Option value | Benefit of retaining flexibility for a future decision |
| Point hit | Points deducted for transfers beyond the free allowance |
| MILP | Mixed-integer linear programming, useful for multiweek planning |
| Dry run | Generate and validate an action without submitting it |
| Two-phase approval | Approve an exact plan, then revalidate before execution |
| Prompt injection | Untrusted text attempting to change the agent's instructions |
| Fail closed | Stop when safety or validity cannot be proven |
