from __future__ import annotations

import polars as pl
import pytest

from coachiq.models import (
    CanonicalState,
    derive_field_goal_distance,
    fit_action_baselines,
)


def candidate_training_rows() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(40):
        rows.append(_candidate(index, "go", yards_to_go=1, success=True))
        rows.append(_candidate(100 + index, "go", yards_to_go=8, success=False))
        rows.append(_candidate(200 + index, "field_goal", kick_distance=38))
        rows.append(
            _candidate(
                300 + index,
                "punt",
                yards_to_goal=85,
                next_yards_to_goal=60 + index % 11,
            )
        )
    return pl.DataFrame(rows)


def _candidate(
    index: int,
    action: str,
    *,
    yards_to_go: int = 1,
    yards_to_goal: float = 15.0,
    next_yards_to_goal: float = 70.0,
    success: bool = True,
    kick_distance: int | None = None,
) -> dict[str, object]:
    retained = action == "go" and success
    outcome = {
        "go": "converted" if success else "failed",
        "field_goal": "field_goal_made" if index % 5 else "field_goal_missed",
        "punt": "punted",
    }[action]
    return {
        "season": 2023,
        "game_id": f"game_{index}",
        "play_id": index,
        "home_team": "A",
        "possession_team": "A",
        "defense_team": "B",
        "down": 4,
        "yards_to_go": yards_to_go,
        "yards_to_goal": yards_to_goal,
        "quarter": 2,
        "game_seconds_remaining": 2000,
        "score_differential": 0,
        "posteam_timeouts_remaining": 3,
        "defteam_timeouts_remaining": 3,
        "actual_action": action,
        "disposition": "eligible",
        "factual_outcome": outcome,
        "next_state_status": "reconstructed",
        "next_possession_team": "A" if retained else "B",
        "next_down": 1,
        "next_yards_to_go": 10,
        "next_yards_to_goal": next_yards_to_goal,
        "next_quarter": 2,
        "next_game_seconds_remaining": 1992,
        "decision_team_score_differential_next": 3
        if outcome == "field_goal_made"
        else 0,
        "decision_team_timeouts_remaining_next": 3,
        "opponent_timeouts_remaining_next": 3,
        "kick_distance": kick_distance,
    }


def _state(*, yards_to_go: float = 1, yards_to_goal: float = 15) -> CanonicalState:
    return CanonicalState(
        "A", "B", True, 0, 2, 2000, yards_to_goal, 4, yards_to_go, 3, 3
    )


def test_field_goal_distance_is_explicit_and_extremes_are_unavailable() -> None:
    model = fit_action_baselines(candidate_training_rows())

    assert derive_field_goal_distance(32) == 50
    with pytest.raises(ValueError):
        derive_field_goal_distance(101)
    support = model.support("field_goal", _state(yards_to_goal=60))
    assert support.available is False
    assert support.reason == "field_goal_distance_above_70_yards"


def test_go_probability_conditions_on_yards_to_go() -> None:
    model = fit_action_baselines(candidate_training_rows())

    short_probability, short_support = model.empirical_binary_probability(
        "go", _state(yards_to_go=1)
    )
    long_probability, long_support = model.empirical_binary_probability(
        "go", _state(yards_to_go=8)
    )

    assert short_support.in_support and long_support.in_support
    assert short_probability is not None and long_probability is not None
    assert short_probability > long_probability


def test_punt_preserves_an_empirical_field_position_distribution() -> None:
    model = fit_action_baselines(candidate_training_rows())
    state = _state(yards_to_goal=85)

    distribution = model.transition_distribution("punt", state)
    expected, support = model.punt_expected_opponent_yards_to_goal(state)

    assert support.in_support
    assert distribution.states.height == 40
    assert distribution.states["yards_to_goal"].n_unique() > 1
    assert expected == pytest.approx(distribution.states["yards_to_goal"].mean())


def test_non_scoring_field_position_is_transported_relative_to_query() -> None:
    model = fit_action_baselines(candidate_training_rows())

    original = model.transition_distribution("punt", _state(yards_to_goal=85)).states
    shifted = model.transition_distribution("punt", _state(yards_to_goal=95)).states

    assert shifted["yards_to_goal"].to_list() == pytest.approx(
        (original["yards_to_goal"] - 10).to_list()
    )


def test_scoring_restart_field_position_is_absolute_but_miss_is_relative() -> None:
    model = fit_action_baselines(candidate_training_rows())

    states = model.transition_distribution(
        "field_goal", _state(yards_to_goal=20)
    ).states

    assert set(
        states.filter(pl.col("factual_outcome") == "field_goal_made")[
            "yards_to_goal"
        ].to_list()
    ) == {70.0}
    assert set(
        states.filter(pl.col("factual_outcome") == "field_goal_missed")[
            "yards_to_goal"
        ].to_list()
    ) == {65.0}


@pytest.mark.parametrize(
    ("action", "yards_to_goal"),
    (("go", 15), ("field_goal", 20), ("punt", 85)),
)
def test_hypothetical_transitions_preserve_query_score_and_time_context(
    action: str, yards_to_goal: float
) -> None:
    model = fit_action_baselines(candidate_training_rows())
    late_deficit = CanonicalState("A", "B", True, -3, 4, 120, yards_to_goal, 4, 1, 1, 0)
    early_lead = CanonicalState("A", "B", True, 14, 2, 2500, yards_to_goal, 4, 1, 3, 2)

    late = model.transition_distribution(action, late_deficit).states
    early = model.transition_distribution(action, early_lead).states
    late_original_score = late.select(
        pl.when(pl.col("evaluation_team") == "A")
        .then(pl.col("score_differential"))
        .otherwise(-pl.col("score_differential"))
    ).to_series()
    early_original_score = early.select(
        pl.when(pl.col("evaluation_team") == "A")
        .then(pl.col("score_differential"))
        .otherwise(-pl.col("score_differential"))
    ).to_series()

    assert (early_original_score - late_original_score).to_list() == pytest.approx(
        [17.0] * late.height
    )
    assert (
        early["game_seconds_remaining"] - late["game_seconds_remaining"]
    ).to_list() == pytest.approx([2380.0] * late.height)
    late_original_timeouts = late.select(
        pl.when(pl.col("evaluation_team") == "A")
        .then(pl.col("team_timeouts_remaining"))
        .otherwise(pl.col("opponent_timeouts_remaining"))
    ).to_series()
    early_original_timeouts = early.select(
        pl.when(pl.col("evaluation_team") == "A")
        .then(pl.col("team_timeouts_remaining"))
        .otherwise(pl.col("opponent_timeouts_remaining"))
    ).to_series()
    assert set(late_original_timeouts.to_list()) == {1.0}
    assert set(early_original_timeouts.to_list()) == {3.0}
    assert set(late["quarter"].to_list()) == {4}
    assert set(early["quarter"].to_list()) == {2}


def test_halftime_and_nonlocal_successors_are_not_transition_evidence() -> None:
    rows = candidate_training_rows()
    halftime = _candidate(998, "punt", yards_to_goal=85.0)
    halftime["quarter"] = 2
    halftime["next_quarter"] = 3
    nonlocal_clock = _candidate(997, "punt", yards_to_goal=85.0)
    nonlocal_clock["next_game_seconds_remaining"] = 1800

    model = fit_action_baselines(
        pl.concat([rows, pl.DataFrame([halftime, nonlocal_clock])])
    )

    assert model.training_rows.height == rows.height


def test_hypothetical_possession_change_flips_score_and_home_perspective() -> None:
    model = fit_action_baselines(candidate_training_rows())
    state = CanonicalState(
        "A",
        "B",
        True,
        -4,
        2,
        2000,
        15,
        4,
        1,
        3,
        2,
        team_pregame_spread=6.0,
    )

    field_goal_states = model.transition_distribution("field_goal", state).states
    punt_states = model.transition_distribution("punt", _state(yards_to_goal=85)).states

    assert set(field_goal_states["score_differential"].to_list()) == {1.0, 4.0}
    assert set(field_goal_states["evaluation_team"].to_list()) == {"B"}
    assert set(field_goal_states["is_home"].to_list()) == {False}
    assert set(field_goal_states["team_pregame_spread"].to_list()) == {-6.0}
    assert set(punt_states["evaluation_team"].to_list()) == {"B"}


def test_replayed_snap_is_not_independent_action_outcome_evidence() -> None:
    rows = candidate_training_rows()
    replayed = _candidate(999, "go", yards_to_go=1, success=False)
    replayed["factual_outcome"] = "down_replayed"

    model = fit_action_baselines(pl.concat([rows, pl.DataFrame([replayed])]))

    assert model.training_rows.height == rows.height
