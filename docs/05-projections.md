# Expected-points projections

## Forecasting is not optimization

A projection estimates what may happen to one player. Optimization selects a legal collection of
players given those estimates. Keeping these separate lets us improve forecasting without rewriting
the squad solver.

## MVP heuristic

For each player and fixture:

```text
recent rate = 0.55 × points per game + 0.45 × form

fixture xP = recent rate
           × min(expected minutes / 90, 1)
           × probability of playing
           × fixture difficulty multiplier
           × venue multiplier
```

The gameweek projection is the sum across supplied fixtures. This naturally represents doubles and
blanks.

Difficulty multipliers are deliberately visible:

| Difficulty | Multiplier |
|---:|---:|
| 1 | 1.20 |
| 2 | 1.10 |
| 3 | 1.00 |
| 4 | 0.90 |
| 5 | 0.80 |

The weights are teaching defaults, not fitted claims. A mature model should learn parameters from
historical pre-deadline data and produce calibrated probability distributions.

## Injury example

Consider a defender with recent rate `4.0`, expected minutes `25`, appearance probability `0.20`, and
a neutral away fixture:

```text
4.0 × (25/90) × 0.20 × 1.00 × 0.97 ≈ 0.22 xP
```

That low value may place the player on the bench, but it does not automatically mean “sell.” The
optimizer also considers replacement quality, the planning horizon, budget, point hits, and the value
of saving a transfer.

## Building a better model

Later feature groups can include:

- Starting and 60-minute probabilities.
- Team scoring and clean-sheet probabilities.
- Non-penalty expected goals and expected assists per 90.
- Set-piece and penalty roles.
- Saves, bonus, cards, and defensive contributions.
- Rest days, travel, fixture congestion, and rotation.
- Manager changes and role changes with explicit decay.

Possible models include a hierarchical Poisson model for team goals, gradient-boosted player-return
models, and a separate calibrated minutes model.

## Avoiding leakage

For a historical Gameweek 10 backtest, only use information available before the Gameweek 10
deadline. End-of-season aggregates, revised injury news, final lineups, and later price changes leak
the answer into the input and make a weak model look strong.

Useful forecast metrics include mean absolute error, ranked correlation, Brier score for appearance,
and calibration plots. Actual FPL points are noisy, so judge performance across many gameweeks.
