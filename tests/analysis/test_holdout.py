from __future__ import annotations

from pathlib import Path

import pytest
from scripts.audit_decision_values import _load_normalized as load_decision_development
from scripts.evaluate_baseline import _validate_development_range
from scripts.select_wp_model import _load_normalized as load_wp_development

from coachiq.analysis.holdout import (
    FROZEN_SOURCE_HASHES,
    HISTORICAL_SEASONS,
    frozen_artifact_identity,
    holdout_run_policy,
    validate_holdout_boundary,
)
from coachiq.models import LOCKED_WP_MODEL_VERSION, LOCKED_WP_USES_RECALIBRATION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_2025_is_allowed_only_at_the_exact_holdout_boundary() -> None:
    validate_holdout_boundary(HISTORICAL_SEASONS, (2025,))

    with pytest.raises(ValueError, match="2014-2024"):
        validate_holdout_boundary(tuple(range(2015, 2025)), (2025,))
    with pytest.raises(ValueError, match="exactly 2025"):
        validate_holdout_boundary(HISTORICAL_SEASONS, (2024, 2025))
    with pytest.raises(SystemExit, match="2025"):
        _validate_development_range(2014, 2025)
    with pytest.raises(SystemExit, match="2014-2024"):
        load_decision_development([2025], None)
    with pytest.raises(SystemExit, match="2014-2024"):
        load_wp_development([2025], None)


def test_frozen_holdout_metadata_prevents_training_or_recalibration_drift() -> None:
    first = frozen_artifact_identity(PROJECT_ROOT)
    second = frozen_artifact_identity(PROJECT_ROOT)

    assert first == second
    assert first["source_sha256"] == FROZEN_SOURCE_HASHES
    assert first["training_seasons"] == list(range(2014, 2025))
    assert first["holdout_season"] == 2025
    assert first["wp_model_version"] == LOCKED_WP_MODEL_VERSION == "coachiq-wp-v1"
    assert first["wp_uses_recalibration"] is LOCKED_WP_USES_RECALIBRATION is False
    assert first["bootstrap_replicates"] == 200
    assert first["bootstrap_seed"] == 2505


def test_holdout_report_policy_is_deterministic_and_evaluation_only() -> None:
    first = holdout_run_policy()
    second = holdout_run_policy()

    assert first == second
    assert first["evaluation_only"] is True
    assert first["fit_seasons"] == list(range(2014, 2025))
    assert first["evaluation_season"] == 2025
    assert first["recalibration_on_holdout"] is False
    assert first["model_selection_on_holdout"] is False
    assert first["threshold_or_cell_tuning_on_holdout"] is False
