# NFL Coaching Decision Auditor

CoachIQ is a planned NFL analytics project for estimating the quality of
coaching decisions, beginning with fourth downs. Counterfactual action values
will always be presented as model-based estimates under explicit assumptions,
not as known alternative outcomes.

The repository is at Milestone 1: reproducible historical nflverse ingestion
and a stable, normalized internal play representation. No decision model or
fourth-down scoring is implemented.

Read the [Milestone 0 foundation](docs/milestone-0-foundation.md) and the
[normalized data contract](docs/data-contract.md).

## Setup

CoachIQ requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run the fast, network-free checks:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Run a manual development-season validation through nflreadpy (this downloads
the official 2024 data, but does not cache data in the repository):

```bash
.venv/bin/python scripts/validate_pbp.py 2024 \
  --manifest-path /tmp/coachiq-pbp-2024-manifest.json
```

The validation script intentionally rejects 2025, which remains the disclosed
retrospective holdout. Use 2023 or 2024 for routine pipeline checks.
