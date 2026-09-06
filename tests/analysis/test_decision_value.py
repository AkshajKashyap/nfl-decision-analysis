from __future__ import annotations

from dataclasses import replace

import polars as pl
import pytest
from tests.models.test_action_baselines import candidate_training_rows
from tests.models.test_state_value import _state_rows

from coachiq.analysis import (
    ACTION_TRANSITION_MODEL_VERSION,
    DECISION_VALUE_VERSION,
    DecisionThresholdPolicy,
    audit_decision_value,
    build_decision_bootstrap_context,
    format_decision_value_audit,
)
from coachiq.models import CanonicalState, fit_action_baselines, fit_locked_wp_model


def _models(*, dense: bool = False):
    candidates = candidate_training_rows()
    if dense:
        candidates = candidates.vstack(candidates).vstack(candidates)
    state_rows = _state_rows()
    return fit_action_baselines(candidates), fit_locked_wp_model(state_rows)


def test_decision_audit_gap_pairs_metadata_and_reproducibility() -> None:
    action_models, state_model = _models()
    state = CanonicalState("A", "B", True, 0, 2, 2000, 15, 4, 1, 3, 3)

    first = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        bootstrap_replicates=50,
    )
    second = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        bootstrap_replicates=50,
    )

    assert first == second
    assert format_decision_value_audit(first) == format_decision_value_audit(second)
    assert "coachiq-decision-v1" in format_decision_value_audit(first)
    assert first.decision_value_version == DECISION_VALUE_VERSION
    assert first.action_transition_model_version == ACTION_TRANSITION_MODEL_VERSION
    assert first.wp_model_version == "coachiq-wp-v1"
    assert first.raw_action_value_gap == pytest.approx(
        first.highest_supported_action_ewp - first.actual_action_ewp
    )
    for value in first.actions:
        if value.expected_win_probability is not None:
            assert 0 <= value.expected_win_probability <= 1
            assert 0 <= value.interval_lower <= value.interval_upper <= 1
    for pair in first.pairwise_differences:
        if pair.available:
            by_action = {
                value.action: value.expected_win_probability for value in first.actions
            }
            assert pair.difference == pytest.approx(
                by_action[pair.action_a] - by_action[pair.action_b]
            )
            assert 0 <= pair.probability_a_exceeds_b <= 1
            assert 0 <= pair.probability_b_exceeds_a <= 1
            assert 0 <= pair.probability_tied <= 1
            assert (
                pair.probability_a_exceeds_b
                + pair.probability_b_exceeds_a
                + pair.probability_tied
            ) == pytest.approx(1.0)


def test_unsupported_actual_and_single_supported_action_abstain() -> None:
    action_models, state_model = _models()
    actual_unsupported = audit_decision_value(
        CanonicalState("A", "B", True, 0, 2, 2000, 85, 4, 1, 3, 3),
        "field_goal",
        action_models,
        state_model,
        bootstrap_replicates=20,
    )
    single_supported = audit_decision_value(
        CanonicalState("A", "B", True, 0, 2, 2000, 85, 4, 1, 3, 3),
        "punt",
        action_models,
        state_model,
        bootstrap_replicates=20,
    )

    assert actual_unsupported.actual_action_ewp is None
    assert actual_unsupported.raw_action_value_gap is None
    assert actual_unsupported.classification == "insufficient_support"
    assert single_supported.supported_action_count == 1
    assert single_supported.raw_action_value_gap is None
    assert single_supported.classification == "insufficient_support"


def test_classification_threshold_boundary_and_support_propagation() -> None:
    action_models, state_model = _models(dense=True)
    state = CanonicalState("A", "B", True, 0, 3, 900, 15, 4, 1, 3, 3)
    permissive = DecisionThresholdPolicy(0.0, 0.5, False, "test-permissive")
    conservative = replace(
        permissive,
        minimum_gap=1.0,
        superiority_probability=1.0,
        version="test-conservative",
    )

    clear = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        threshold_policy=permissive,
        bootstrap_replicates=30,
    )
    close = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        threshold_policy=conservative,
        bootstrap_replicates=30,
    )

    assert clear.classification == "clear_model_preference"
    assert close.classification == "close_call"
    punt = next(value for value in clear.actions if value.action == "punt")
    assert punt.support_status == "unsupported"
    assert punt.expected_win_probability is None

    boundary = DecisionThresholdPolicy(
        clear.model_preferred_minimum_gap,
        clear.model_preferred_minimum_superiority,
        False,
        "test-boundary",
    )
    at_boundary = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        threshold_policy=boundary,
        bootstrap_replicates=30,
    )
    above_boundary = audit_decision_value(
        state,
        "field_goal",
        action_models,
        state_model,
        threshold_policy=replace(
            boundary,
            minimum_gap=boundary.minimum_gap + 1e-10,
            version="test-above-boundary",
        ),
        bootstrap_replicates=30,
    )

    assert at_boundary.classification == "clear_model_preference"
    assert above_boundary.classification == "close_call"


def test_possession_inversion_and_protected_season() -> None:
    action_models, state_model = _models()
    state = CanonicalState("A", "B", True, 0, 2, 2000, 85, 4, 1, 3, 3)
    audit = audit_decision_value(
        state,
        "punt",
        action_models,
        state_model,
        bootstrap_replicates=20,
    )
    punt = next(value for value in audit.actions if value.action == "punt")
    distribution = action_models.transition_distribution("punt", state)
    expected = 1.0 - state_model.predict_proba(distribution.states).mean()

    assert punt.expected_win_probability == pytest.approx(expected)

    protected = candidate_training_rows().with_columns(
        candidate_training_rows()["season"] * 0 + 2025
    )
    with pytest.raises(ValueError, match="2025"):
        audit_decision_value(
            state,
            "punt",
            fit_action_baselines(protected),
            state_model,
            bootstrap_replicates=10,
        )

    with pytest.raises(ValueError, match="2025"):
        audit_decision_value(
            state,
            "punt",
            action_models,
            replace(state_model, training_seasons=(2025,)),
            bootstrap_replicates=10,
        )

    with pytest.raises(ValueError, match="regulation"):
        audit_decision_value(
            replace(state, quarter=5),
            "punt",
            action_models,
            state_model,
            bootstrap_replicates=10,
        )


def test_identical_successor_distributions_produce_identical_action_values() -> None:
    candidates = (
        candidate_training_rows()
        .filter(
            pl.col("actual_action").is_in(("go", "field_goal"))
            & ((pl.col("actual_action") == "field_goal") | (pl.col("yards_to_go") == 1))
        )
        .with_columns(
            pl.lit("failed").alias("factual_outcome"),
            pl.lit("B").alias("next_possession_team"),
            pl.lit(70.0).alias("next_yards_to_goal"),
            pl.lit(0).alias("decision_team_score_differential_next"),
        )
    )
    state_model = fit_locked_wp_model(_state_rows())
    audit = audit_decision_value(
        CanonicalState("A", "B", True, 0, 2, 2000, 15, 4, 1, 3, 3),
        "go",
        fit_action_baselines(candidates),
        state_model,
        bootstrap_replicates=30,
    )
    values = {value.action: value.expected_win_probability for value in audit.actions}
    go_minus_field_goal = next(
        pair
        for pair in audit.pairwise_differences
        if pair.action_a == "go" and pair.action_b == "field_goal"
    )

    assert values["go"] == pytest.approx(values["field_goal"])
    assert go_minus_field_goal.difference == pytest.approx(0.0)
    assert go_minus_field_goal.interval_lower == pytest.approx(0.0)
    assert go_minus_field_goal.interval_upper == pytest.approx(0.0)
    assert go_minus_field_goal.probability_a_exceeds_b == 0
    assert go_minus_field_goal.probability_b_exceeds_a == 0
    assert go_minus_field_goal.probability_tied == 1


def test_overtime_boundary_safeguard_uses_action_transition_mass() -> None:
    action_models, state_model = _models(dense=True)
    policy = DecisionThresholdPolicy(0.0, 0.5, False, "test-permissive")

    no_boundary = audit_decision_value(
        CanonicalState("A", "B", True, 0, 4, 30, 15, 4, 1, 3, 3),
        "field_goal",
        action_models,
        state_model,
        threshold_policy=policy,
        bootstrap_replicates=20,
    )
    boundary = audit_decision_value(
        CanonicalState("A", "B", True, 0, 4, 5, 15, 4, 1, 3, 3),
        "field_goal",
        action_models,
        state_model,
        threshold_policy=policy,
        bootstrap_replicates=20,
    )

    assert no_boundary.maximum_overtime_boundary_mass == 0
    assert no_boundary.classification_reason != (
        "supported_action_has_unmodeled_overtime_transition_mass"
    )
    assert boundary.maximum_overtime_boundary_mass > 0
    assert boundary.classification == "limited_support"
    assert boundary.classification_reason == (
        "supported_action_has_unmodeled_overtime_transition_mass"
    )


def test_bootstrap_context_must_match_action_model_training_games() -> None:
    action_models, state_model = _models()
    other_models = fit_action_baselines(
        candidate_training_rows().with_columns(
            (pl.col("game_id") + "-different").alias("game_id")
        )
    )
    context = build_decision_bootstrap_context(other_models, bootstrap_replicates=10)

    with pytest.raises(ValueError, match="training games"):
        audit_decision_value(
            CanonicalState("A", "B", True, 0, 2, 2000, 15, 4, 1, 3, 3),
            "go",
            action_models,
            state_model,
            bootstrap_replicates=10,
            bootstrap_context=context,
        )
