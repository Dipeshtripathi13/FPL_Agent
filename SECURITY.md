# Security policy

## Supported version

The latest release on the default branch receives security fixes.

## Secrets

FPL Agent does not need FPL credentials for the MVP. Do not paste credentials into prompts or place
them in CSV/YAML files. Local model settings may be kept in `.env`, which is ignored by Git.

If later integrations require API keys, store them in the operating-system keychain or environment
variables and redact them from logs. `.env.example` must contain placeholder names only.

## Untrusted content

News articles, search results, model messages, CSV files, and YAML files are untrusted input. The
model may summarize evidence but cannot bypass Pydantic validation, the rules engine, or tool
allowlists. Web content must never be interpreted as system instructions.

## Reporting a vulnerability

Open a private GitHub security advisory rather than a public issue. Include reproduction steps and
the affected version, but never include live account credentials.
