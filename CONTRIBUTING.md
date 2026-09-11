# Contributing

Thank you for helping improve FPL Agent. This repository is designed for learning, so clear reasoning
and tests are as important as the implementation.

## Development workflow

1. Create a virtual environment and install `.[dev]`.
2. Create a focused branch.
3. Add or update tests with every behavior change.
4. Update the relevant learning chapter if an architectural concept changes.
5. Run `pytest` and `ruff check .` before opening a pull request.

## Data and intellectual property

Do not commit:

- FPL account credentials, cookies, access tokens, or private team responses.
- Scraped or redistributed Premier League/FPL datasets.
- Premier League or club logos, badges, photographs, or branding.
- Third-party data without an explicit compatible license.

Use small fictional fixtures in tests. A provider adapter must document its terms, license, rate
limits, attribution requirements, and retention rules.

## Safety expectations

Account-changing tools are out of scope unless the project has documented authorization. A new tool
must default to read-only, validate its input with a schema, have a bounded runtime, and be covered by
tests for malicious or malformed model arguments.
