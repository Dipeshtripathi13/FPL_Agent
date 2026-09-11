# Agentic AI fundamentals

## What makes this an agent?

A chatbot maps a message to a reply. An agent runs a loop in which a model can observe state, select a
tool, receive the result, and decide what to do next.

```text
agent = model + tools + loop + state + policies + evaluation
```

In FPL Agent:

- **Model:** local Qwen generates tool calls and explanations.
- **Tools:** validate the team, inspect evidence, read rules, and calculate recommendations.
- **Loop:** `OllamaAgent.run` repeats until the model returns a final answer or reaches a turn limit.
- **State:** the supplied squad, players, fixtures, rules, and message history.
- **Policies:** no mutation tools, strict schemas, deterministic rule validation, and bounded turns.
- **Evaluation:** unit tests, scenario tests, backtests, and safety assertions.

## Deterministic and stochastic components

| Component | Type | Why |
|---|---|---|
| Parse a price | Deterministic | `£7.5m` must always become integer `75` |
| Validate formation | Deterministic | A rule has one correct interpretation |
| Optimize supplied expected points | Deterministic | The same inputs should give the same choice |
| Interpret ambiguous injury wording | Stochastic | Natural language contains uncertainty |
| Explain the trade-off | Stochastic | Multiple correct explanations are possible |

A common beginner mistake is to ask the LLM to do all five jobs. That produces plausible prose but
weak reproducibility. This project makes the model a coordinator and communicator around tested code.

## Tool calling

The model receives JSON schemas describing available functions. It may respond with a call such as:

```json
{
  "name": "calculate_recommendation",
  "arguments": {"gameweek": 4, "horizon": 5, "max_transfers": 2}
}
```

The harness validates the function name, invokes Python, serializes the result, and sends it back to
the model. Qwen never directly runs arbitrary Python or shell commands in this MVP.

## Autonomy levels

| Level | Behavior | MVP |
|---|---|---:|
| 0 | Static report | Supported |
| 1 | Model requests a computed result | Supported |
| 2 | Model selects among read-only tools | Supported |
| 3 | Model proposes an external action for approval | Supported conceptually |
| 4 | Model executes an approved action | Fake adapter only |
| 5 | Unattended external actions | Excluded |

More autonomy is not automatically better. Good agent engineering gives a system only the authority
needed for its task. In this MVP, Qwen can choose tools, but trusted code renders the factual plan
because live evaluation showed that a small local model could contradict a correct tool result.
