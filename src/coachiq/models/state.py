"""Canonical possession-relative football state representation."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import polars as pl

from coachiq.data.schema import validate_normalized_pbp

CANONICAL_STATE_COLUMNS = (
    "evaluation_team",
    "opponent_team",
    "is_home",
    "score_differential",
    "quarter",
    "game_seconds_remaining",
    "yards_to_goal",
    "down",
    "yards_to_go",
    "team_timeouts_remaining",
    "opponent_timeouts_remaining",
    "team_pregame_spread",
)


@dataclass(frozen=True)
class CanonicalState:
    """A state from the perspective of the team whose value is requested."""

    evaluation_team: str
    opponent_team: str
    is_home: bool
    score_differential: float
    quarter: int
    game_seconds_remaining: float
    yards_to_goal: float
    down: int
    yards_to_go: float
    team_timeouts_remaining: float
    opponent_timeouts_remaining: float
    team_pregame_spread: float | None = None

    def to_frame(self) -> pl.DataFrame:
        """Return a one-row frame accepted by the state-value model."""

        return pl.DataFrame([asdict(self)])


def build_state_value_rows(pbp: pl.DataFrame) -> pl.DataFrame:
    """Build non-no-play regulation states with eventual observed game targets."""

    validate_normalized_pbp(pbp)
    required = (
        "possession_team",
        "defense_team",
        "home_team",
        "away_team",
        "score_differential",
        "quarter",
        "game_seconds_remaining",
        "yards_to_goal",
        "down",
        "yards_to_go",
        "posteam_timeouts_remaining",
        "defteam_timeouts_remaining",
        "home_score_differential_final",
    )
    complete = pl.all_horizontal(pl.col(column).is_not_null() for column in required)
    in_scope = (
        (pl.col("season") >= 2014)
        & pl.col("season_type").is_in(("REG", "POST"))
        & pl.col("quarter").is_between(1, 4)
        & ~pl.col("is_no_play").fill_null(False)
        & ~pl.col("is_play_deleted").fill_null(False)
    )
    is_home = pl.col("possession_team") == pl.col("home_team")
    team_pregame_spread = (
        pl.when(pl.col("spread_line").is_null())
        .then(pl.lit(None, dtype=pl.Float64))
        .when(is_home)
        .then(pl.col("spread_line"))
        .otherwise(-pl.col("spread_line"))
    )
    home_margin = pl.col("home_score_differential_final")
    target = (
        pl.when(home_margin == 0)
        .then(0.5)
        .when((home_margin > 0) == is_home)
        .then(1.0)
        .otherwise(0.0)
    )
    return (
        pbp.filter(complete & in_scope)
        .select(
            "season",
            "game_id",
            "play_id",
            "possession_team",
            "defense_team",
            pl.col("possession_team").alias("evaluation_team"),
            pl.col("defense_team").alias("opponent_team"),
            is_home.alias("is_home"),
            pl.col("score_differential").cast(pl.Float64),
            "quarter",
            pl.col("game_seconds_remaining").cast(pl.Float64),
            "yards_to_goal",
            "down",
            pl.col("yards_to_go").cast(pl.Float64),
            pl.col("posteam_timeouts_remaining")
            .cast(pl.Float64)
            .alias("team_timeouts_remaining"),
            pl.col("defteam_timeouts_remaining")
            .cast(pl.Float64)
            .alias("opponent_timeouts_remaining"),
            team_pregame_spread.alias("team_pregame_spread"),
            target.alias("eventual_win_equivalent"),
            pl.col("win_probability").alias("nflverse_win_probability"),
            pl.col("vegas_win_probability").alias("nflverse_vegas_win_probability"),
        )
        .sort("season", "game_id", "play_id")
    )


def probability_for_team(
    possession_team_probability: float,
    possession_team: str,
    evaluation_team: str,
) -> float:
    """Convert a possession-team value to another team's perspective."""

    if possession_team == evaluation_team:
        return possession_team_probability
    return 1.0 - possession_team_probability


def quarter_from_game_seconds(game_seconds_remaining: float) -> int:
    """Map regulation game seconds to the applicable quarter."""

    if game_seconds_remaining > 2700:
        return 1
    if game_seconds_remaining > 1800:
        return 2
    if game_seconds_remaining > 900:
        return 3
    return 4


__all__ = [
    "CANONICAL_STATE_COLUMNS",
    "CanonicalState",
    "build_state_value_rows",
    "probability_for_team",
    "quarter_from_game_seconds",
]
