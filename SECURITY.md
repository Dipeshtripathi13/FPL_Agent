# Security policy

## Supported version

The latest release on the default branch receives security fixes.

## Secrets

FPL Agent does not need FPL credentials. Do not paste credentials into prompts or place them in
CSV/YAML files. Local model settings may be kept in `.env`, which is ignored by Git.

The optional research adapter reads `BRAVE_SEARCH_API_KEY` from the environment. Store the real value
in the operating-system keychain or a private shell environment and redact it from logs. There is no
CLI key option, which avoids placing it in shell history. `.env.example` must contain placeholder
names only.

## Untrusted content

News articles, search results, model messages, CSV files, and YAML files are untrusted input. Search
results are review leads, not evidence. Suspicious text is quarantined, and stale or conflicting
evidence fails closed before the agent harness is built. The model cannot bypass Pydantic validation,
the rules engine, provider allowlists, or the absence of account-changing tools. Web content must
never be interpreted as system instructions.

Reusable source permissions must include a review date and expiry in the private source registry.
An expired review is not accepted merely because the same domain was used successfully before.

## Reporting a vulnerability

Open a private GitHub security advisory rather than a public issue. Include reproduction steps and
the affected version, but never include live account credentials.
