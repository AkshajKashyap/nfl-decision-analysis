"""Inspectable empirical fourth-down action and transition baselines."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

import polars as pl

from coachiq.models.state import CanonicalState, quarter_from_game_seconds

MIN_SUPPORT_OBSERVATIONS = 30
SPARSE_SUPPORT_OBSERVATIONS = 100
MAX_FIELD_GOAL_DISTANCE = 70.0


@dataclass(frozen=True)
class ActionSupport:
    """Observed overlap diagnostics for one queried action."""

    action: str
    available: bool
    in_support: bool
    reason: str | None
    observation_count: int
    game_count: int
    sparse: bool
    distance_to_nearest_observation: float | None


@dataclass(frozen=True)
class TransitionDistribution:
    """Empirical modeled next states and their training-game clusters."""

    action: str
    support: ActionSupport
    states: pl.DataFrame
    game_clusters: tuple[str, ...]


class ActionBaselineSet:
    """Separate empirical conditional baselines for go, field goal, and punt."""

    def __init__(self, training_rows: pl.DataFrame) -> None:
        self._training_rows = _prepare_training_rows(training_rows)
        self.training_seasons = tuple(
            sorted(int(value) for value in self._training_rows["season"].unique())
        )
        self._cells: dict[tuple[str, ...], pl.DataFrame] = {}
        for action in ("go", "field_goal", "punt"):
            action_rows = self._training_rows.filter(pl.col("actual_action") == action)
            columns = _cell_columns(action)
            for key, cell in action_rows.partition_by(columns, as_dict=True).items():
                values = key if isinstance(key, tuple) else (key,)
                self._cells[(action, *map(str, values))] = cell

    @property
    def training_rows(self) -> pl.DataFrame:
        """Expose immutable-by-convention rows for diagnostics."""

        return self._training_rows

    def support(self, action: str, state: CanonicalState) -> ActionSupport:
        """Return action availability and local empirical overlap."""

        _validate_action(action)
        available, availability_reason = _availability(action, state)
        rows = self._comparable_rows(action, state) if available else pl.DataFrame()
        count = rows.height
        game_count = rows["game_id"].n_unique() if count else 0
        distance = 0.0 if count else _nearest_cell_distance(self._cells, state, action)
        if not available:
            reason = availability_reason
        elif count < MIN_SUPPORT_OBSERVATIONS:
            reason = "fewer_than_30_comparable_observations"
        else:
            reason = None
        return ActionSupport(
            action=action,
            available=available,
            in_support=available and reason is None,
            reason=reason,
            observation_count=count,
            game_count=game_count,
            sparse=count < SPARSE_SUPPORT_OBSERVATIONS,
            distance_to_nearest_observation=distance,
        )

    def transition_distribution(
        self, action: str, state: CanonicalState
    ) -> TransitionDistribution:
        """Transport equally weighted local transitions onto a queried state."""

        support = self.support(action, state)
        if not support.in_support:
            return TransitionDistribution(action, support, _empty_state_frame(), ())
        rows = self._comparable_rows(action, state)
        next_seconds = (
            pl.lit(state.game_seconds_remaining) - pl.col("elapsed_seconds")
        ).clip(0.0, 3600.0)
        retained = pl.col("possession_retained")
        original_next_score = pl.lit(state.score_differential) + pl.col(
            "decision_score_delta"
        )
        query_decision_yards_to_goal_next = (
            pl.lit(state.yards_to_goal) + pl.col("decision_yards_to_goal_delta")
        ).clip(1.0, 99.0)
        next_yards_to_goal = (
            pl.when(pl.col("field_position_resets"))
            .then(pl.col("next_yards_to_goal"))
            .when(retained)
            .then(query_decision_yards_to_goal_next)
            .otherwise(100.0 - query_decision_yards_to_goal_next)
        )
        states = rows.select(
            pl.when(retained)
            .then(pl.lit(state.evaluation_team))
            .otherwise(pl.lit(state.opponent_team))
            .alias("evaluation_team"),
            pl.when(retained)
            .then(pl.lit(state.opponent_team))
            .otherwise(pl.lit(state.evaluation_team))
            .alias("opponent_team"),
            pl.when(retained)
            .then(pl.lit(state.is_home))
            .otherwise(pl.lit(not state.is_home))
            .alias("is_home"),
            pl.when(retained)
            .then(original_next_score)
            .otherwise(-original_next_score)
            .alias("score_differential"),
            next_seconds.map_elements(
                quarter_from_game_seconds, return_dtype=pl.Int8
            ).alias("quarter"),
            next_seconds.alias("game_seconds_remaining"),
            next_yards_to_goal.alias("yards_to_goal"),
            pl.col("next_down").alias("down"),
            pl.min_horizontal(
                pl.col("next_yards_to_go").cast(pl.Float64), next_yards_to_goal
            ).alias("yards_to_go"),
            pl.when(retained)
            .then(
                (
                    pl.lit(state.team_timeouts_remaining)
                    + pl.col("decision_timeout_delta")
                ).clip(0.0, 3.0)
            )
            .otherwise(
                (
                    pl.lit(state.opponent_timeouts_remaining)
                    + pl.col("opponent_timeout_delta")
                ).clip(0.0, 3.0)
            )
            .alias("team_timeouts_remaining"),
            pl.when(retained)
            .then(
                (
                    pl.lit(state.opponent_timeouts_remaining)
                    + pl.col("opponent_timeout_delta")
                ).clip(0.0, 3.0)
            )
            .otherwise(
                (
                    pl.lit(state.team_timeouts_remaining)
                    + pl.col("decision_timeout_delta")
                ).clip(0.0, 3.0)
            )
            .alias("opponent_timeouts_remaining"),
            pl.when(retained)
            .then(pl.lit(state.team_pregame_spread, dtype=pl.Float64))
            .otherwise(-pl.lit(state.team_pregame_spread, dtype=pl.Float64))
            .alias("team_pregame_spread"),
            "game_id",
            "factual_outcome",
        )
        return TransitionDistribution(
            action=action,
            support=support,
            states=states,
            game_clusters=tuple(rows["game_id"].to_list()),
        )

    def empirical_binary_probability(
        self, action: str, state: CanonicalState
    ) -> tuple[float | None, ActionSupport]:
        """Return Beta(1,1)-smoothed go-conversion or field-goal-make rate."""

        if action not in {"go", "field_goal"}:
            raise ValueError("binary probability is defined for go and field_goal")
        support = self.support(action, state)
        if not support.in_support:
            return None, support
        rows = self._comparable_rows(action, state)
        if action == "go":
            successes = rows.filter(
                pl.col("factual_outcome").is_in(
                    ("converted", "converted_by_penalty", "touchdown")
                )
            ).height
        else:
            successes = rows.filter(
                pl.col("factual_outcome") == "field_goal_made"
            ).height
        return (successes + 1.0) / (rows.height + 2.0), support

    def punt_expected_opponent_yards_to_goal(
        self, state: CanonicalState
    ) -> tuple[float | None, ActionSupport]:
        """Return the transported conditional mean and its support."""

        distribution = self.transition_distribution("punt", state)
        if not distribution.support.in_support:
            return None, distribution.support
        return (
            float(distribution.states["yards_to_goal"].mean()),
            distribution.support,
        )

    def _comparable_rows(self, action: str, state: CanonicalState) -> pl.DataFrame:
        if action == "field_goal":
            distance = derive_field_goal_distance(state.yards_to_goal)
            key = (action, _field_goal_bin(distance))
        elif action == "go":
            key = (
                action,
                _distance_bin(state.yards_to_go),
                _field_bin(state.yards_to_goal),
            )
        else:
            key = (action, _field_bin(state.yards_to_goal))
        return self._cells.get(key, self._training_rows.head(0))


def fit_action_baselines(candidates: pl.DataFrame) -> ActionBaselineSet:
    """Fit the fixed empirical action cells from eligible observed decisions."""

    return ActionBaselineSet(candidates)


def derive_field_goal_distance(yards_to_goal: float) -> float:
    """Use line of scrimmage plus 18 yards for snap/hold and end zone."""

    if not 0 <= yards_to_goal <= 100:
        raise ValueError("yards_to_goal must be within [0, 100]")
    return yards_to_goal + 18.0


def canonical_state_from_candidate(row: dict[str, object]) -> CanonicalState:
    """Convert an eligible decision row to the original team's perspective."""

    possession_team = str(row["possession_team"])
    return CanonicalState(
        evaluation_team=possession_team,
        opponent_team=str(row["defense_team"]),
        is_home=possession_team == row["home_team"],
        score_differential=float(row["score_differential"]),
        quarter=int(row["quarter"]),
        game_seconds_remaining=float(row["game_seconds_remaining"]),
        yards_to_goal=float(row["yards_to_goal"]),
        down=int(row["down"]),
        yards_to_go=float(row["yards_to_go"]),
        team_timeouts_remaining=float(row["posteam_timeouts_remaining"]),
        opponent_timeouts_remaining=float(row["defteam_timeouts_remaining"]),
        team_pregame_spread=(
            float(row["spread_line"])
            if row.get("spread_line") is not None
            and possession_team == row["home_team"]
            else -float(row["spread_line"])
            if row.get("spread_line") is not None
            else None
        ),
    )


def _prepare_training_rows(candidates: pl.DataFrame) -> pl.DataFrame:
    required = (
        "actual_action",
        "disposition",
        "factual_outcome",
        "next_state_status",
        "next_possession_team",
        "next_down",
        "next_yards_to_go",
        "next_yards_to_goal",
        "next_quarter",
        "next_game_seconds_remaining",
        "decision_team_score_differential_next",
        "decision_team_timeouts_remaining_next",
        "opponent_timeouts_remaining_next",
    )
    missing = [column for column in required if column not in candidates.columns]
    if missing:
        raise ValueError(f"candidate rows are missing columns: {', '.join(missing)}")
    complete_transition = pl.all_horizontal(
        pl.col(column).is_not_null()
        for column in (
            "next_possession_team",
            "next_down",
            "next_yards_to_go",
            "next_yards_to_goal",
            "next_quarter",
            "next_game_seconds_remaining",
            "decision_team_score_differential_next",
            "decision_team_timeouts_remaining_next",
            "opponent_timeouts_remaining_next",
        )
    )
    elapsed_seconds = pl.col("game_seconds_remaining") - pl.col(
        "next_game_seconds_remaining"
    )
    rows = candidates.filter(
        (pl.col("disposition") == "eligible")
        & pl.col("actual_action").is_in(("go", "field_goal", "punt"))
        & (pl.col("next_state_status") == "reconstructed")
        & ~pl.col("factual_outcome").is_in(("unknown", "down_replayed"))
        & ~((pl.col("quarter") <= 2) & (pl.col("next_quarter") >= 3))
        & complete_transition
        & elapsed_seconds.is_between(0, 120)
        & (
            (pl.col("actual_action") != "field_goal")
            | pl.col("kick_distance").is_between(18, MAX_FIELD_GOAL_DISTANCE)
        )
    )
    possession_retained = pl.col("next_possession_team") == pl.col("possession_team")
    decision_yards_to_goal_next = (
        pl.when(possession_retained)
        .then(pl.col("next_yards_to_goal"))
        .otherwise(100.0 - pl.col("next_yards_to_goal"))
    )
    decision_score_delta = (
        pl.col("decision_team_score_differential_next") - pl.col("score_differential")
    ).cast(pl.Float64)
    return rows.with_columns(
        _distance_bin_expression("yards_to_go").alias("distance_bin"),
        _field_bin_expression("yards_to_goal").alias("field_bin"),
        _field_goal_bin_expression("kick_distance").alias("action_bin"),
        possession_retained.alias("possession_retained"),
        elapsed_seconds.cast(pl.Float64).alias("elapsed_seconds"),
        decision_score_delta.alias("decision_score_delta"),
        (decision_yards_to_goal_next - pl.col("yards_to_goal"))
        .cast(pl.Float64)
        .alias("decision_yards_to_goal_delta"),
        decision_score_delta.ne(0).alias("field_position_resets"),
        (
            pl.col("decision_team_timeouts_remaining_next")
            - pl.col("posteam_timeouts_remaining")
        )
        .cast(pl.Float64)
        .alias("decision_timeout_delta"),
        (
            pl.col("opponent_timeouts_remaining_next")
            - pl.col("defteam_timeouts_remaining")
        )
        .cast(pl.Float64)
        .alias("opponent_timeout_delta"),
    )


def _availability(action: str, state: CanonicalState) -> tuple[bool, str | None]:
    if action == "field_goal":
        distance = derive_field_goal_distance(state.yards_to_goal)
        if distance > MAX_FIELD_GOAL_DISTANCE:
            return False, "field_goal_distance_above_70_yards"
    return True, None


def _nearest_cell_distance(
    cells: dict[tuple[str, ...], pl.DataFrame],
    state: CanonicalState,
    action: str,
) -> float | None:
    action_cells = [key for key in cells if key[0] == action]
    if not action_cells:
        return None
    if action == "field_goal":
        centers = {
            "under_30": 24.0,
            "30_39": 34.5,
            "40_49": 44.5,
            "50_59": 54.5,
            "60_70": 65.0,
        }
        query = centers[
            _field_goal_bin(derive_field_goal_distance(state.yards_to_goal))
        ]
        return min(abs(query - centers[key[1]]) / 10.0 for key in action_cells)
    if action == "punt":
        field_order = {
            "opponent_red_zone": 0,
            "opponent_21_49": 1,
            "own_21_to_midfield": 2,
            "own_1_20": 3,
        }
        query = field_order[_field_bin(state.yards_to_goal)]
        return float(min(abs(query - field_order[key[1]]) for key in action_cells))
    distance_order = {"1": 0, "2": 1, "3_5": 2, "6_10": 3, "11_plus": 4}
    field_order = {
        "opponent_red_zone": 0,
        "opponent_21_49": 1,
        "own_21_to_midfield": 2,
        "own_1_20": 3,
    }
    query_distance = distance_order[_distance_bin(state.yards_to_go)]
    query_field = field_order[_field_bin(state.yards_to_goal)]
    return float(
        min(
            hypot(
                query_distance - distance_order[key[1]],
                query_field - field_order[key[2]],
            )
            for key in action_cells
        )
    )


def _cell_columns(action: str) -> list[str]:
    if action == "go":
        return ["distance_bin", "field_bin"]
    if action == "field_goal":
        return ["action_bin"]
    return ["field_bin"]


def _distance_bin(value: float) -> str:
    if value <= 1:
        return "1"
    if value <= 2:
        return "2"
    if value <= 5:
        return "3_5"
    if value <= 10:
        return "6_10"
    return "11_plus"


def _field_bin(value: float) -> str:
    if value <= 20:
        return "opponent_red_zone"
    if value <= 49:
        return "opponent_21_49"
    if value <= 79:
        return "own_21_to_midfield"
    return "own_1_20"


def _field_goal_bin(value: float) -> str:
    if value < 30:
        return "under_30"
    if value < 40:
        return "30_39"
    if value < 50:
        return "40_49"
    if value < 60:
        return "50_59"
    return "60_70"


def _distance_bin_expression(column: str) -> pl.Expr:
    return (
        pl.when(pl.col(column) <= 1)
        .then(pl.lit("1"))
        .when(pl.col(column) <= 2)
        .then(pl.lit("2"))
        .when(pl.col(column) <= 5)
        .then(pl.lit("3_5"))
        .when(pl.col(column) <= 10)
        .then(pl.lit("6_10"))
        .otherwise(pl.lit("11_plus"))
    )


def _field_bin_expression(column: str) -> pl.Expr:
    return (
        pl.when(pl.col(column) <= 20)
        .then(pl.lit("opponent_red_zone"))
        .when(pl.col(column) <= 49)
        .then(pl.lit("opponent_21_49"))
        .when(pl.col(column) <= 79)
        .then(pl.lit("own_21_to_midfield"))
        .otherwise(pl.lit("own_1_20"))
    )


def _field_goal_bin_expression(column: str) -> pl.Expr:
    return (
        pl.when(pl.col(column).is_null())
        .then(pl.lit(None, dtype=pl.String))
        .when(pl.col(column) < 30)
        .then(pl.lit("under_30"))
        .when(pl.col(column) < 40)
        .then(pl.lit("30_39"))
        .when(pl.col(column) < 50)
        .then(pl.lit("40_49"))
        .when(pl.col(column) < 60)
        .then(pl.lit("50_59"))
        .otherwise(pl.lit("60_70"))
    )


def _validate_action(action: str) -> None:
    if action not in {"go", "field_goal", "punt"}:
        raise ValueError(f"unsupported baseline action: {action}")


def _empty_state_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "evaluation_team": pl.String,
            "opponent_team": pl.String,
            "is_home": pl.Boolean,
            "score_differential": pl.Float64,
            "quarter": pl.Int8,
            "game_seconds_remaining": pl.Float64,
            "yards_to_goal": pl.Float64,
            "down": pl.Int8,
            "yards_to_go": pl.Float64,
            "team_timeouts_remaining": pl.Float64,
            "opponent_timeouts_remaining": pl.Float64,
            "team_pregame_spread": pl.Float64,
            "game_id": pl.String,
            "factual_outcome": pl.String,
        }
    )


__all__ = [
    "MAX_FIELD_GOAL_DISTANCE",
    "MIN_SUPPORT_OBSERVATIONS",
    "SPARSE_SUPPORT_OBSERVATIONS",
    "ActionBaselineSet",
    "ActionSupport",
    "TransitionDistribution",
    "canonical_state_from_candidate",
    "derive_field_goal_distance",
    "fit_action_baselines",
]
