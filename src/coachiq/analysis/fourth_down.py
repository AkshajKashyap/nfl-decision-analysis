"""Auditable reconstruction of observed fourth-down decisions."""

from __future__ import annotations

from enum import StrEnum

import polars as pl

from coachiq.data.schema import validate_normalized_pbp


class DecisionDisposition(StrEnum):
    """Whether a fourth-down row is usable as an observed coaching decision."""

    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    REVIEW = "review"


class ActualAction(StrEnum):
    """Observed action selected on fourth down."""

    GO = "go"
    PUNT = "punt"
    FIELD_GOAL = "field_goal"
    UNKNOWN = "unknown"


class DispositionReason(StrEnum):
    """Single primary reason why a candidate is not eligible."""

    SEASON_OUT_OF_SCOPE = "season_out_of_scope"
    GAME_TYPE_OUT_OF_SCOPE = "game_type_out_of_scope"
    DELETED_PLAY = "deleted_play"
    OVERTIME_OUT_OF_SCOPE = "overtime_out_of_scope"
    PENALTY_NO_PLAY = "penalty_no_play"
    CLOCK_KILL = "clock_kill"
    SPIKE = "spike"
    MISSING_STATE = "missing_state"
    ADMINISTRATIVE_ROW = "administrative_row"
    ABORTED_PLAY = "aborted_play"
    UNSUPPORTED_ACTION = "unsupported_action"
    AMBIGUOUS_ACTION = "ambiguous_action"


class FactualOutcome(StrEnum):
    """Observed result, kept separate from the selected action."""

    CONVERTED = "converted"
    CONVERTED_BY_PENALTY = "converted_by_penalty"
    FAILED = "failed"
    TOUCHDOWN = "touchdown"
    RETURN_TOUCHDOWN = "return_touchdown"
    INTERCEPTION = "interception"
    FUMBLE_LOST = "fumble_lost"
    FIELD_GOAL_MADE = "field_goal_made"
    FIELD_GOAL_MISSED = "field_goal_missed"
    FIELD_GOAL_BLOCKED = "field_goal_blocked"
    PUNTED = "punted"
    PUNT_BLOCKED = "punt_blocked"
    SAFETY = "safety"
    DOWN_REPLAYED = "down_replayed"
    NO_PLAY = "no_play"
    CLOCK_KILL = "clock_kill"
    UNKNOWN = "unknown"


class NextStateStatus(StrEnum):
    """Confidence in the factual post-decision state."""

    RECONSTRUCTED = "reconstructed"
    TERMINAL = "terminal"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


_MINIMUM_SEASON = 2014
_SUPPORTED_GAME_TYPES = ("REG", "POST")
_GO_NFL_PLAY_TYPES = (
    "RUSH",
    "PASS",
    "SACK",
    "INTERCEPTION",
    "FUMBLE_RECOVERED_BY_OPPONENT",
)
_CORE_STATE_COLUMNS = (
    "season_type",
    "possession_team",
    "defense_team",
    "yards_to_go",
    "yards_to_goal",
    "quarter",
    "quarter_seconds_remaining",
    "game_seconds_remaining",
    "score_differential",
    "home_timeouts_remaining",
    "away_timeouts_remaining",
    "posteam_timeouts_remaining",
    "defteam_timeouts_remaining",
)
_NEXT_STATE_COLUMNS = (
    "play_id",
    "play_sequence",
    "possession_team",
    "defense_team",
    "down",
    "yards_to_go",
    "yards_to_goal",
    "quarter",
    "quarter_seconds_remaining",
    "game_seconds_remaining",
    "posteam_score",
    "defteam_score",
    "score_differential",
    "home_timeouts_remaining",
    "away_timeouts_remaining",
    "posteam_timeouts_remaining",
    "defteam_timeouts_remaining",
)


def extract_fourth_down_candidates(pbp: pl.DataFrame) -> pl.DataFrame:
    """Return every normalized fourth-down row with an auditable disposition.

    The result preserves every normalized source column. It adds action,
    disposition, factual-outcome, repeated-down, and next-state audit fields.
    No counterfactual values or model-based judgments are produced.
    """

    validate_normalized_pbp(pbp)
    ordered_pbp = (
        pbp.with_columns(pl.coalesce("play_sequence", "play_id").alias("_source_order"))
        .sort(["season", "game_id", "_source_order", "play_id"])
        .with_columns(pl.int_range(pl.len()).over("game_id").alias("_transition_index"))
    )
    candidates = ordered_pbp.filter(pl.col("down") == 4).with_columns(
        _actual_action_expression().alias("actual_action")
    )
    candidates = candidates.with_columns(
        _disposition_expression().alias("disposition"),
        _disposition_reason_expression().alias("disposition_reason"),
    )
    candidates = _attach_next_states(candidates, ordered_pbp)
    candidates = candidates.with_columns(
        (pl.col("quarter").is_in((2, 4)) & (pl.col("half_seconds_remaining") <= 120))
        .fill_null(False)
        .alias("is_late_half"),
        pl.when(pl.col("win_probability").is_null())
        .then(pl.lit(None, dtype=pl.Boolean))
        .otherwise(
            (pl.col("win_probability") < 0.01) | (pl.col("win_probability") > 0.99)
        )
        .alias("is_extreme_wp"),
        pl.col("next_state_status")
        .is_in((NextStateStatus.UNAVAILABLE, NextStateStatus.AMBIGUOUS))
        .alias("is_endgame_transition_uncertain"),
        (
            (pl.col("next_state_status") == NextStateStatus.RECONSTRUCTED)
            & (pl.col("next_possession_team") == pl.col("possession_team"))
            & (pl.col("next_down") == 4)
        )
        .fill_null(False)
        .alias("next_is_repeated_fourth_down"),
    )
    candidates = _attach_repeat_links(candidates)
    return (
        candidates.with_columns(_factual_outcome_expression().alias("factual_outcome"))
        .drop("_source_order", "_transition_index")
        .sort(["season", "game_id", "play_sequence", "play_id"], nulls_last=True)
    )


def _actual_action_expression() -> pl.Expr:
    field_goal = (pl.col("nfl_play_type") == "FIELD_GOAL") | _is_true(
        "is_field_goal_attempt"
    )
    punt = (pl.col("nfl_play_type") == "PUNT") | _is_true("is_punt_attempt")
    structured_go = (
        pl.col("nfl_play_type").is_in(_GO_NFL_PLAY_TYPES)
        | pl.col("play_type").is_in(("run", "pass"))
        | _is_true("is_rush")
        | _is_true("is_pass")
    )
    unsupported_safety = _is_true("is_safety") & (
        pl.col("nfl_play_type") == "UNSPECIFIED"
    )

    return (
        pl.when(
            _is_true("is_no_play")
            | _is_true("is_play_deleted")
            | _is_true("is_qb_kneel")
            | _is_true("is_qb_spike")
            | pl.col("play_type").is_in(("qb_kneel", "qb_spike"))
        )
        .then(pl.lit(ActualAction.UNKNOWN))
        .when(field_goal)
        .then(pl.lit(ActualAction.FIELD_GOAL))
        .when(punt)
        .then(pl.lit(ActualAction.PUNT))
        .when(_is_true("is_aborted_play") | unsupported_safety)
        .then(pl.lit(ActualAction.UNKNOWN))
        .when(structured_go)
        .then(pl.lit(ActualAction.GO))
        .otherwise(pl.lit(ActualAction.UNKNOWN))
    )


def _disposition_expression() -> pl.Expr:
    reason = _disposition_reason_expression()
    return (
        pl.when(reason.is_null())
        .then(pl.lit(DecisionDisposition.ELIGIBLE))
        .when(
            reason.is_in(
                (
                    DispositionReason.ABORTED_PLAY,
                    DispositionReason.UNSUPPORTED_ACTION,
                    DispositionReason.AMBIGUOUS_ACTION,
                )
            )
        )
        .then(pl.lit(DecisionDisposition.REVIEW))
        .otherwise(pl.lit(DecisionDisposition.EXCLUDED))
    )


def _disposition_reason_expression() -> pl.Expr:
    missing_state = pl.any_horizontal(
        pl.col(column).is_null() for column in _CORE_STATE_COLUMNS
    )
    administrative = (
        pl.col("play_type").is_null()
        & pl.col("nfl_play_type").is_null()
        & (pl.col("actual_action") == ActualAction.UNKNOWN)
    )
    unsupported = (
        _is_true("is_special_teams_play")
        | _is_true("is_safety")
        | (pl.col("nfl_play_type") == "UNSPECIFIED")
    )

    return (
        pl.when(pl.col("season") < _MINIMUM_SEASON)
        .then(pl.lit(DispositionReason.SEASON_OUT_OF_SCOPE))
        .when(
            pl.col("season_type").is_not_null()
            & ~pl.col("season_type").is_in(_SUPPORTED_GAME_TYPES)
        )
        .then(pl.lit(DispositionReason.GAME_TYPE_OUT_OF_SCOPE))
        .when(_is_true("is_play_deleted"))
        .then(pl.lit(DispositionReason.DELETED_PLAY))
        .when(pl.col("quarter") > 4)
        .then(pl.lit(DispositionReason.OVERTIME_OUT_OF_SCOPE))
        .when(_is_true("is_no_play"))
        .then(pl.lit(DispositionReason.PENALTY_NO_PLAY))
        .when(_is_true("is_qb_kneel") | (pl.col("play_type") == "qb_kneel"))
        .then(pl.lit(DispositionReason.CLOCK_KILL))
        .when(_is_true("is_qb_spike") | (pl.col("play_type") == "qb_spike"))
        .then(pl.lit(DispositionReason.SPIKE))
        .when(missing_state)
        .then(pl.lit(DispositionReason.MISSING_STATE))
        .when(administrative)
        .then(pl.lit(DispositionReason.ADMINISTRATIVE_ROW))
        .when(
            _is_true("is_aborted_play")
            & (pl.col("actual_action") == ActualAction.UNKNOWN)
        )
        .then(pl.lit(DispositionReason.ABORTED_PLAY))
        .when((pl.col("actual_action") == ActualAction.UNKNOWN) & unsupported)
        .then(pl.lit(DispositionReason.UNSUPPORTED_ACTION))
        .when(pl.col("actual_action") == ActualAction.UNKNOWN)
        .then(pl.lit(DispositionReason.AMBIGUOUS_ACTION))
        .otherwise(pl.lit(None, dtype=pl.String))
    )


def _attach_next_states(candidates: pl.DataFrame, pbp: pl.DataFrame) -> pl.DataFrame:
    state_is_complete = pl.all_horizontal(
        pl.col(column).is_not_null()
        for column in (
            "possession_team",
            "defense_team",
            "down",
            "yards_to_go",
            "yards_to_goal",
            "quarter",
            "quarter_seconds_remaining",
            "game_seconds_remaining",
            "posteam_score",
            "defteam_score",
            "score_differential",
            "home_timeouts_remaining",
            "away_timeouts_remaining",
            "posteam_timeouts_remaining",
            "defteam_timeouts_remaining",
        )
    )
    next_states = (
        pbp.filter(state_is_complete & ~_is_true("is_play_deleted"))
        .select(
            "game_id",
            pl.col("_transition_index").alias("next_transition_index"),
            *[pl.col(column).alias(f"next_{column}") for column in _NEXT_STATE_COLUMNS],
        )
        .sort(["game_id", "next_transition_index"])
    )

    joined = candidates.sort(["game_id", "_transition_index"]).join_asof(
        next_states,
        left_on="_transition_index",
        right_on="next_transition_index",
        by="game_id",
        strategy="forward",
        allow_exact_matches=False,
        check_sortedness=False,
    )
    has_next = pl.col("next_play_id").is_not_null()
    current_teams = pl.concat_list("possession_team", "defense_team")
    invalid_team_state = has_next & (
        ~pl.col("next_possession_team").is_in(current_teams)
        | ~pl.col("next_defense_team").is_in(current_teams)
        | (pl.col("next_possession_team") == pl.col("next_defense_team"))
    )
    invalid_clock = has_next & (
        (pl.col("next_game_seconds_remaining") > pl.col("game_seconds_remaining"))
        | (pl.col("next_quarter") < pl.col("quarter"))
    )
    terminal = (
        ~has_next & (pl.col("quarter") == 4) & (pl.col("game_seconds_remaining") <= 120)
    ).fill_null(False)

    status = (
        pl.when(invalid_team_state.fill_null(False) | invalid_clock.fill_null(False))
        .then(pl.lit(NextStateStatus.AMBIGUOUS))
        .when(has_next)
        .then(pl.lit(NextStateStatus.RECONSTRUCTED))
        .when(terminal)
        .then(pl.lit(NextStateStatus.TERMINAL))
        .otherwise(pl.lit(NextStateStatus.UNAVAILABLE))
    )
    decision_team_next_score = (
        pl.when(pl.col("next_possession_team") == pl.col("possession_team"))
        .then(pl.col("next_score_differential"))
        .when(pl.col("next_defense_team") == pl.col("possession_team"))
        .then(-pl.col("next_score_differential"))
        .otherwise(pl.lit(None, dtype=pl.Int16))
    )
    decision_team_next_timeouts = (
        pl.when(pl.col("next_possession_team") == pl.col("possession_team"))
        .then(pl.col("next_posteam_timeouts_remaining"))
        .when(pl.col("next_defense_team") == pl.col("possession_team"))
        .then(pl.col("next_defteam_timeouts_remaining"))
        .otherwise(pl.lit(None, dtype=pl.Int8))
    )
    opponent_next_timeouts = (
        pl.when(pl.col("next_possession_team") == pl.col("possession_team"))
        .then(pl.col("next_defteam_timeouts_remaining"))
        .when(pl.col("next_defense_team") == pl.col("possession_team"))
        .then(pl.col("next_posteam_timeouts_remaining"))
        .otherwise(pl.lit(None, dtype=pl.Int8))
    )
    return joined.with_columns(
        status.alias("next_state_status"),
        decision_team_next_score.alias("decision_team_score_differential_next"),
        decision_team_next_timeouts.alias("decision_team_timeouts_remaining_next"),
        opponent_next_timeouts.alias("opponent_timeouts_remaining_next"),
    ).drop("next_transition_index")


def _attach_repeat_links(candidates: pl.DataFrame) -> pl.DataFrame:
    repeat_sources = candidates.filter(pl.col("next_is_repeated_fourth_down")).select(
        "game_id",
        pl.col("next_play_id").alias("play_id"),
        pl.col("play_id").alias("repeated_from_play_id"),
    )
    return candidates.join(
        repeat_sources,
        on=["game_id", "play_id"],
        how="left",
        validate="1:1",
    )


def _factual_outcome_expression() -> pl.Expr:
    field_goal_result = pl.col("field_goal_result").str.to_lowercase()
    return (
        pl.when(_is_true("is_no_play"))
        .then(pl.lit(FactualOutcome.NO_PLAY))
        .when(_is_true("is_qb_kneel"))
        .then(pl.lit(FactualOutcome.CLOCK_KILL))
        .when(_is_true("is_return_touchdown"))
        .then(pl.lit(FactualOutcome.RETURN_TOUCHDOWN))
        .when(_is_true("is_touchdown"))
        .then(pl.lit(FactualOutcome.TOUCHDOWN))
        .when(_is_true("is_safety"))
        .then(pl.lit(FactualOutcome.SAFETY))
        .when(
            (pl.col("actual_action") == ActualAction.FIELD_GOAL)
            & (field_goal_result == "made")
        )
        .then(pl.lit(FactualOutcome.FIELD_GOAL_MADE))
        .when(
            (pl.col("actual_action") == ActualAction.FIELD_GOAL)
            & (field_goal_result == "missed")
        )
        .then(pl.lit(FactualOutcome.FIELD_GOAL_MISSED))
        .when(
            (pl.col("actual_action") == ActualAction.FIELD_GOAL)
            & (field_goal_result == "blocked")
        )
        .then(pl.lit(FactualOutcome.FIELD_GOAL_BLOCKED))
        .when(
            (pl.col("actual_action") == ActualAction.PUNT) & _is_true("is_punt_blocked")
        )
        .then(pl.lit(FactualOutcome.PUNT_BLOCKED))
        .when(pl.col("actual_action") == ActualAction.PUNT)
        .then(pl.lit(FactualOutcome.PUNTED))
        .when(
            (pl.col("actual_action") == ActualAction.GO)
            & _is_true("is_first_down_by_penalty")
        )
        .then(pl.lit(FactualOutcome.CONVERTED_BY_PENALTY))
        .when(
            (pl.col("actual_action") == ActualAction.GO) & _is_true("is_interception")
        )
        .then(pl.lit(FactualOutcome.INTERCEPTION))
        .when((pl.col("actual_action") == ActualAction.GO) & _is_true("is_fumble_lost"))
        .then(pl.lit(FactualOutcome.FUMBLE_LOST))
        .when(
            (pl.col("actual_action") == ActualAction.GO)
            & pl.col("next_is_repeated_fourth_down")
        )
        .then(pl.lit(FactualOutcome.DOWN_REPLAYED))
        .when(
            (pl.col("actual_action") == ActualAction.GO)
            & _is_true("is_fourth_down_converted")
        )
        .then(pl.lit(FactualOutcome.CONVERTED))
        .when(
            (pl.col("actual_action") == ActualAction.GO)
            & _is_true("is_fourth_down_failed")
        )
        .then(pl.lit(FactualOutcome.FAILED))
        .otherwise(pl.lit(FactualOutcome.UNKNOWN))
    )


def _is_true(column: str) -> pl.Expr:
    return pl.col(column).fill_null(False)


__all__ = [
    "ActualAction",
    "DecisionDisposition",
    "DispositionReason",
    "FactualOutcome",
    "NextStateStatus",
    "extract_fourth_down_candidates",
]
