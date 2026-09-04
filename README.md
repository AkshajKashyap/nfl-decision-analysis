# NFL Coaching Decision Auditor

CoachIQ is a planned NFL analytics project for estimating the quality of
coaching decisions, beginning with fourth downs. Counterfactual action values
will always be presented as model-based estimates under explicit assumptions,
not as known alternative outcomes.

The repository is at Milestone 2: reproducible historical nflverse ingestion,
a stable normalized play representation, and auditable reconstruction of
observed fourth-down decisions and factual next states. No counterfactual
decision model or fourth-down scoring is implemented.

Read the [Milestone 0 foundation](docs/milestone-0-foundation.md) and the
[normalized data contract](docs/data-contract.md). The implemented descriptive
policy is documented in [fourth-down reconstruction](docs/fourth-down-policy.md).

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

Audit Milestone 2 coverage and a deterministic manual sample on 2024:

```bash
.venv/bin/python scripts/audit_fourth_downs.py 2024 --summary-only
.venv/bin/python scripts/audit_fourth_downs.py 2024 --sample-only --sample-size 20
```

The fourth-down audit script blocks 2025 and later development analysis.
