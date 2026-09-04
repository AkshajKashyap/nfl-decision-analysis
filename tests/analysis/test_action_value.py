from __future__ import annotations

import numpy as np
from tests.models.test_action_baselines import candidate_training_rows
from tests.models.test_state_value import _state_rows

from coachiq.analysis import estimate_action_value
from coachiq.models import CanonicalState, fit_action_baselines, fit_state_value_model


def test_expected_value_composition_and_cluster_interval_are_reproducible() -> None:
    action_models = fit_action_baselines(candidate_training_rows())
    state_model = fit_state_value_model(_state_rows())
    state = CanonicalState("A", "B", True, 0, 2, 2000, 85, 4, 5, 3, 3)

    first = estimate_action_value(
        state, "punt", action_models, state_model, bootstrap_replicates=50
    )
    second = estimate_action_value(
        state, "punt", action_models, state_model, bootstrap_replicates=50
    )

    assert first == second
    assert first.expected_win_probability is not None
    assert 0 <= first.interval_lower <= first.expected_win_probability
    assert first.expected_win_probability <= first.interval_upper <= 1
    distribution = action_models.transition_distribution("punt", state)
    possession_values = state_model.predict_proba(distribution.states)
    manually_inverted = 1.0 - possession_values
    assert first.expected_win_probability == np.mean(manually_inverted)


def test_unsupported_action_returns_no_value_or_fake_interval() -> None:
    action_models = fit_action_baselines(candidate_training_rows())
    state_model = fit_state_value_model(_state_rows())
    state = CanonicalState("A", "B", True, 0, 2, 2000, 80, 4, 1, 3, 3)

    estimate = estimate_action_value(state, "field_goal", action_models, state_model)

    assert estimate.expected_win_probability is None
    assert estimate.interval_lower is None
    assert estimate.interval_upper is None
    assert estimate.support.in_support is False
