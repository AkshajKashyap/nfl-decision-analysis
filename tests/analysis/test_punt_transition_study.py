from __future__ import annotations

import polars as pl
import pytest

from coachiq.analysis.punt_transition_study import (
    PuntTransitionCandidateModel,
    validate_punt_study_seasons,
)
from coachiq.models import CanonicalState, fit_action_baselines


def _state(yards_to_goal: float) -> CanonicalState:
    return CanonicalState("A", "B", True, 0, 3, 1500, yards_to_goal, 4, 5, 3, 3, 0.0)


def _punt_rows() -> pl.DataFrame:
    rows = []
    for index in range(40):
        touchback = index == 0
        scoring = index == 1
        retained = index == 2
        destination = (
            80.0 if touchback else 75.0 if scoring else 85.0 if retained else 65.0
        )
        rows.append(
            {
                "season": 2023,
                "game_id": f"game_{index}",
                "play_id": index,
                "home_team": "A",
                "possession_team": "A",
                "defense_team": "B",
                "down": 4,
                "yards_to_go": 5,
                "yards_to_goal": 75.0,
                "quarter": 3,
                "game_seconds_remaining": 1500,
                "score_differential": 0,
                "posteam_timeouts_remaining": 3,
                "defteam_timeouts_remaining": 3,
                "actual_action": "punt",
                "disposition": "eligible",
                "factual_outcome": "touchdown"
                if scoring
                else "punt_blocked"
                if retained
                else "punted",
                "next_state_status": "reconstructed",
                "next_possession_team": "A" if retained else "B",
                "next_down": 1,
                "next_yards_to_go": 10.0,
                "next_yards_to_goal": destination,
                "next_quarter": 3,
                "next_game_seconds_remaining": 1492,
                "decision_team_score_differential_next": 7 if scoring else 0,
                "decision_team_timeouts_remaining_next": 3,
                "opponent_timeouts_remaining_next": 3,
                "kick_distance": 45.0,
                "is_touchback": touchback,
                "is_punt_blocked": retained,
            }
        )
    return pl.DataFrame(rows)


def test_boundary_aware_transport_is_bounded_query_relative_and_deterministic() -> None:
    base = fit_action_baselines(_punt_rows())
    model = PuntTransitionCandidateModel(base, "C")

    first = model.transition_distribution("punt", _state(65.0)).states
    second = model.transition_distribution("punt", _state(65.0)).states
    shifted = model.transition_distribution("punt", _state(66.0)).states

    assert first.equals(second)
    assert first["yards_to_goal"].min() >= 1
    assert first["yards_to_goal"].max() <= 99
    ordinary = first.filter(pl.col("factual_outcome") == "punted")
    shifted_ordinary = shifted.filter(pl.col("factual_outcome") == "punted")
    assert ordinary["yards_to_goal"].n_unique() == 2
    assert (
        abs(shifted_ordinary["yards_to_goal"].mean() - ordinary["yards_to_goal"].mean())
        < 1
    )


def test_candidate_preserves_touchback_scoring_and_possession_perspective() -> None:
    base = fit_action_baselines(_punt_rows())
    frozen = base.transition_distribution("punt", _state(65.0))
    model = PuntTransitionCandidateModel(base, "C")
    distribution = model.transition_distribution("punt", _state(65.0))
    states = distribution.states

    assert states.row(0, named=True)["yards_to_goal"] == 80.0
    assert states.row(1, named=True)["yards_to_goal"] == 75.0
    blocked = states.row(2, named=True)
    assert blocked["evaluation_team"] == "A"
    assert blocked["yards_to_goal"] == pytest.approx(79.1666666667)
    assert set(states["quarter"].to_list()) == {3}
    assert set(states["game_seconds_remaining"].to_list()) == {1492.0}
    non_field = [
        column
        for column in states.columns
        if column not in {"yards_to_goal", "yards_to_go"}
    ]
    assert states.select(non_field).equals(frozen.states.select(non_field))
    assert distribution.game_clusters == frozen.game_clusters


def test_direct_destination_preserves_support_and_observed_locations() -> None:
    base = fit_action_baselines(_punt_rows())
    direct = PuntTransitionCandidateModel(base, "B")
    state = _state(65.0)

    distribution = direct.transition_distribution("punt", state)

    assert direct.support("punt", state) == base.support("punt", state)
    assert distribution.states["yards_to_goal"].to_list() == pytest.approx(
        base.training_rows["next_yards_to_goal"].to_list()
    )


def test_study_rejects_both_protected_seasons() -> None:
    for protected in (2025, 2026):
        seasons = list(range(2014, 2025)) + [protected]
        with pytest.raises(ValueError, match=r"2025\+"):
            validate_punt_study_seasons(pl.DataFrame({"season": seasons}))
