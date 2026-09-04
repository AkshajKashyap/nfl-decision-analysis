from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from coachiq.analysis import (
    deterministic_manual_sample,
    extract_fourth_down_candidates,
    next_state_coverage,
)
from coachiq.data import NORMALIZED_SCHEMA

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "fourth_down_cases.json"
)


def _normalized_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    complete_rows: list[dict[str, Any]] = []
    for overrides in rows:
        row = {
            column: False if dtype == pl.Boolean else None
            for column, dtype in NORMALIZED_SCHEMA.items()
        }
        row.update(
            {
                "season": 2024,
                "season_type": "REG",
                "week": 1,
                "game_date": "2024-09-08",
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "play_sequence": 100,
                "home_team": "B",
                "away_team": "A",
                "possession_team": "A",
                "defense_team": "B",
                "down": 4,
                "yards_to_go": 2,
                "yards_to_goal": 50.0,
                "quarter": 2,
                "game_half": "Half1",
                "quarter_seconds_remaining": 300,
                "half_seconds_remaining": 300,
                "game_seconds_remaining": 2100,
                "posteam_score": 7,
                "defteam_score": 7,
                "score_differential": 0,
                "home_timeouts_remaining": 3,
                "away_timeouts_remaining": 3,
                "posteam_timeouts_remaining": 3,
                "defteam_timeouts_remaining": 3,
                "play_type": "pass",
                "nfl_play_type": "PASS",
                "description": "fourth-down fixture",
            }
        )
        row.update(overrides)
        complete_rows.append(row)
    return pl.DataFrame(complete_rows, schema=NORMALIZED_SCHEMA).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )


def _case_frame(case: dict[str, Any]) -> pl.DataFrame:
    play = dict(case["play"])
    next_state = dict(case["next_state"])
    game_id = play["game_id"]
    possession = play["possession_team"]
    defense = play["defense_team"]
    shared = {
        "game_id": game_id,
        "home_team": defense,
        "away_team": possession,
    }
    play.update(shared)
    next_state.update(shared)
    intermediate_rows = []
    for intermediate in case.get("intermediate_rows", []):
        row = dict(intermediate)
        row.update(shared)
        intermediate_rows.append(row)
    return _normalized_frame([play, *intermediate_rows, next_state])


def test_hand_labeled_historical_fixture_suite() -> None:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    for case in cases:
        candidates = extract_fourth_down_candidates(_case_frame(case))
        actual = candidates.filter(pl.col("play_id") == case["play"]["play_id"]).row(
            0, named=True
        )

        for field, expected in case["expected"].items():
            assert actual[field] == expected, f"{case['name']}: {field}"

    repeat_case = next(
        case
        for case in cases
        if case["name"] == "false_start_then_repeated_fourth_down"
    )
    repeated = extract_fourth_down_candidates(_case_frame(repeat_case)).filter(
        pl.col("play_id") == repeat_case["next_state"]["play_id"]
    )
    assert repeated.get_column("repeated_from_play_id").item() == 346


def test_candidates_only_include_fourth_down_and_use_source_sequence_order() -> None:
    # nflverse play IDs can be corrected out of chronology. The state with
    # play_id=100 follows play_id=200 because play_sequence is authoritative.
    frame = _normalized_frame(
        [
            {
                "play_id": 100,
                "play_sequence": 30,
                "down": 1,
                "possession_team": "B",
                "defense_team": "A",
                "yards_to_goal": 65.0,
                "quarter_seconds_remaining": 275,
                "game_seconds_remaining": 2075,
            },
            {
                "play_id": 200,
                "play_sequence": 20,
                "is_pass": True,
                "is_fourth_down_failed": True,
            },
            {
                "play_id": 300,
                "play_sequence": 10,
                "down": 3,
            },
        ]
    )

    result = extract_fourth_down_candidates(frame)

    assert result.get_column("play_id").to_list() == [200]
    assert result.get_column("next_play_id").item() == 100
    assert result.get_column("next_possession_team").item() == "B"


def test_exclusion_and_review_taxonomy_has_explicit_primary_reasons() -> None:
    frame = _normalized_frame(
        [
            {
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "yards_to_goal": None,
                "is_pass": True,
            },
            {
                "game_id": "2024_02_A_B",
                "play_id": 100,
                "quarter": 5,
                "quarter_seconds_remaining": 500,
                "game_seconds_remaining": 500,
                "is_pass": True,
            },
            {
                "game_id": "2024_03_A_B",
                "play_id": 100,
                "is_play_deleted": True,
                "is_pass": True,
            },
            {
                "game_id": "2024_04_A_B",
                "play_id": 100,
                "season_type": "PRE",
                "is_pass": True,
            },
            {
                "season": 2013,
                "game_id": "2013_01_A_B",
                "play_id": 100,
                "is_pass": True,
            },
            {
                "game_id": "2024_05_A_B",
                "play_id": 100,
                "play_type": "qb_spike",
                "nfl_play_type": "PASS",
                "is_pass": True,
                "is_qb_spike": True,
            },
            {
                "game_id": "2024_06_A_B",
                "play_id": 100,
                "play_type": None,
                "nfl_play_type": None,
            },
            {
                "game_id": "2024_07_A_B",
                "play_id": 100,
                "play_type": "timeout",
                "nfl_play_type": "TIMEOUT",
            },
        ]
    )

    result = extract_fourth_down_candidates(frame).sort("season", "game_id")

    assert result.get_column("disposition").to_list() == [
        "excluded",
        "excluded",
        "excluded",
        "excluded",
        "excluded",
        "excluded",
        "excluded",
        "review",
    ]
    assert result.get_column("disposition_reason").to_list() == [
        "season_out_of_scope",
        "missing_state",
        "overtime_out_of_scope",
        "deleted_play",
        "game_type_out_of_scope",
        "spike",
        "administrative_row",
        "ambiguous_action",
    ]


def test_structured_kick_precedence_preserves_aborted_kick_action() -> None:
    frame = _normalized_frame(
        [
            {
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "play_type": "run",
                "nfl_play_type": "UNSPECIFIED",
                "is_rush": True,
                "is_aborted_play": True,
                "is_punt_attempt": True,
            },
            {
                "game_id": "2024_02_A_B",
                "play_id": 100,
                "play_type": "run",
                "nfl_play_type": "UNSPECIFIED",
                "is_rush": True,
                "is_aborted_play": True,
            },
        ]
    )

    result = extract_fourth_down_candidates(frame).sort("game_id")

    assert result.select(
        "actual_action", "disposition", "disposition_reason"
    ).rows() == [
        ("punt", "eligible", None),
        ("unknown", "review", "aborted_play"),
    ]


def test_sack_and_scrimmage_recorded_fake_are_go_actions() -> None:
    frame = _normalized_frame(
        [
            {
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "play_type": "pass",
                "nfl_play_type": "SACK",
                "is_pass": True,
                "is_fourth_down_failed": True,
            },
            {
                "game_id": "2024_02_A_B",
                "play_id": 100,
                "play_type": "run",
                "nfl_play_type": "RUSH",
                "is_special_teams_play": True,
                "is_rush": True,
                "is_fourth_down_converted": True,
            },
        ]
    )

    result = extract_fourth_down_candidates(frame).sort("game_id")

    assert result.select("actual_action", "factual_outcome").rows() == [
        ("go", "failed"),
        ("go", "converted"),
    ]


def test_terminal_unavailable_and_ambiguous_next_states_are_not_invented() -> None:
    frame = _normalized_frame(
        [
            {
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "quarter": 4,
                "quarter_seconds_remaining": 4,
                "game_seconds_remaining": 4,
                "is_pass": True,
                "is_fourth_down_failed": True,
            },
            {
                "game_id": "2024_02_A_B",
                "play_id": 100,
                "quarter": 2,
                "is_pass": True,
                "is_fourth_down_failed": True,
            },
            {
                "game_id": "2024_03_A_B",
                "play_id": 100,
                "play_sequence": 100,
                "quarter": 4,
                "quarter_seconds_remaining": 5,
                "game_seconds_remaining": 5,
                "is_pass": True,
                "is_fourth_down_failed": True,
            },
            {
                "game_id": "2024_03_A_B",
                "play_id": 200,
                "play_sequence": 200,
                "quarter": 5,
                "quarter_seconds_remaining": 600,
                "game_seconds_remaining": 600,
                "down": 1,
            },
        ]
    )

    result = extract_fourth_down_candidates(frame).sort("game_id")

    assert result.get_column("next_state_status").to_list() == [
        "terminal",
        "unavailable",
        "ambiguous",
    ]
    assert result.get_column("is_endgame_transition_uncertain").to_list() == [
        False,
        True,
        True,
    ]
    assert result.row(0, named=True)["next_play_id"] is None
    assert result.row(1, named=True)["next_play_id"] is None


def test_factual_outcomes_keep_kick_and_turnover_results_distinct() -> None:
    frame = _normalized_frame(
        [
            {
                "game_id": "2024_01_A_B",
                "play_id": 100,
                "play_type": "field_goal",
                "nfl_play_type": "FIELD_GOAL",
                "is_field_goal_attempt": True,
                "field_goal_result": "blocked",
            },
            {
                "game_id": "2024_02_A_B",
                "play_id": 100,
                "play_type": "pass",
                "nfl_play_type": "PASS",
                "is_pass": True,
                "is_fumble_lost": True,
                "is_fourth_down_failed": True,
            },
        ]
    )

    result = extract_fourth_down_candidates(frame).sort("game_id")

    assert result.select("actual_action", "factual_outcome").rows() == [
        ("field_goal", "field_goal_blocked"),
        ("go", "fumble_lost"),
    ]


def test_diagnostics_sample_and_next_state_summary_are_deterministic() -> None:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    candidates = pl.concat(
        [extract_fourth_down_candidates(_case_frame(case)) for case in cases],
        how="diagonal_relaxed",
    )

    first = deterministic_manual_sample(candidates, 5)
    second = deterministic_manual_sample(candidates.reverse(), 5)

    assert (
        first.select("game_id", "play_id").rows()
        == second.select("game_id", "play_id").rows()
    )
    coverage = next_state_coverage(candidates)
    assert coverage["successful"] == coverage["reconstructed"] + coverage["terminal"]
    assert (
        coverage["successful"] + coverage["unavailable"] + coverage["ambiguous"]
        == candidates.height
    )
