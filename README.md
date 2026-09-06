# NFL Coaching Decision Auditor

CoachIQ is a planned NFL analytics project for estimating the quality of
coaching decisions, beginning with fourth downs. Counterfactual action values
will always be presented as model-based estimates under explicit assumptions,
not as known alternative outcomes.

The repository is at Milestone 5: the owned state-value specification remains
frozen as `coachiq-wp-v1`, and the auditable fourth-down comparison layer is
frozen as `coachiq-decision-v1`. Conditional empirical go, field-goal, and punt
baselines remain descriptive. Their expected-win-probability comparisons are
model-based estimates with explicit support and limited bootstrap uncertainty,
not known alternative outcomes or coach grades.

Read the [Milestone 0 foundation](docs/milestone-0-foundation.md) and the
[normalized data contract](docs/data-contract.md). The implemented descriptive
policy is documented in [fourth-down reconstruction](docs/fourth-down-policy.md).
The assumptions and chronological evaluation of the first action-value
baseline are documented in [baseline methodology](docs/baseline-methodology.md).
The model-selection evidence, calibration diagnostics, and version lock are in
the [win-probability model card](docs/wp-model-card.md).
The canonical action comparison, paired bootstrap, support policy,
classification thresholds, and limitations are in the
[decision-value methodology](docs/decision-value-methodology.md).

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

Run the expanding-window Milestone 3 evaluation and deterministic worked
examples (each command loads only 2014–2024 data):

```bash
.venv/bin/python scripts/evaluate_baseline.py \
  --json-output /tmp/coachiq-baseline-report.json
.venv/bin/python scripts/worked_examples.py
```

Both scripts also accept `--parquet-dir` for explicit local raw snapshots named
`play_by_play_YEAR.parquet`. They reject 2025 and later before loading data.

Reproduce the complete Milestone 4 selection and one-time pre-lock validation
report (including full calibration bands and regime metrics):

```bash
PYTHONPATH=src .venv/bin/python scripts/select_wp_model.py \
  --bootstrap-replicates 1000 \
  --json-output /tmp/coachiq-wp-model-selection.json
```

Run the complete Milestone 5 chronological report and reuse it for the worked
and largest-gap audit views (all commands are restricted to 2014--2024):

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py diagnostics \
  --parquet-dir /tmp --bootstrap-replicates 200 \
  --json-output /tmp/coachiq-decision-v1.json
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py worked \
  --input-report /tmp/coachiq-decision-v1.json
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py largest \
  --input-report /tmp/coachiq-decision-v1.json
```
