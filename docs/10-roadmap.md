# Roadmap

## MVP — implemented

- Typed manual snapshot loaders.
- Versioned 2026/27 rule pack.
- Explainable expected-points baseline.
- Blank and double gameweek support.
- Legal lineup, bench, captain, and vice-captain optimization.
- Bounded zero-, one-, and two-transfer comparison.
- Injury transfer/bench/start decisions.
- Markdown and JSON reports.
- Local Qwen/Ollama read-only tool loop.
- Fictional examples, tests, documentation, and CI.

## Milestone 2 — evidence pipeline — implemented

- Provider interface and bounded Brave Search discovery adapter.
- Required source allowlist, six-hour cache, request rate limit, and terms-review guidance.
- Immutable SQLite observations separated from derived availability estimates.
- Exact and unambiguous partial player-name resolution.
- Reproducible freshness policy, conflict reporting, and fail-closed overlays.
- Prompt-injection quarantine with an executable test corpus.

### Milestone 2.1 — evidence usability — implemented

- Evidence timeline report per player with freshness and selection state.
- Observation IDs, set fingerprint, overrides, and resolver results in recommendation JSON.
- Expiring configuration registry for reviewed domains and their terms-review dates.
- Provider-expansion policy documented: add adapters only with access and redistribution permission.

## Milestone 3 — fitted forecasting

- Import properly licensed historical data.
- Deadline-correct feature snapshots.
- Separate minutes, attacking returns, clean sheets, and bonus models.
- Calibration and uncertainty intervals.
- Rolling backtest reports and baseline comparisons.

## Milestone 4 — multiweek optimization

- HiGHS mixed-integer model.
- Transfer rollovers and explicit saved-transfer value.
- Player selling-price evolution scenarios.
- Bench coverage and vice-captain fallback value.
- Blank/double gameweek and chip planning.
- Risk preferences such as safe, balanced, and aggressive.

## Milestone 5 — user experience

- Interactive local web dashboard.
- Interactive visualization of the local evidence timeline.
- Side-by-side plan comparison.
- Approval records and weekly learning journal.
- Local scheduler that prepares—but does not submit—a report before deadlines.

## Conditional milestone — execution adapter

This milestone starts only with documented permission to automate FPL access. Until then, implement it
against a fake server and use manual changes in the official FPL interface.

With authorization, it still requires two-phase approval, state revalidation, maximum-hit policies,
deadline buffers, secret storage, audit logs, read-back verification, and a kill switch.

## Suggested study rhythm

Spend one week per milestone slice:

1. Read the corresponding chapter.
2. Predict what the code should do.
3. Run the tests and fictional scenario.
4. Change one assumption.
5. Add a test before implementing a feature.
6. Write what surprised you in a personal learning log.
