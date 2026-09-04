"""Print deterministic pre-2025 fourth-down baseline EWP examples."""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from coachiq.analysis import estimate_all_actions, extract_fourth_down_candidates
from coachiq.data import load_pbp, normalize_pbp
from coachiq.models import (
    ActionBaselineSet,
    build_state_value_rows,
    canonical_state_from_candidate,
    fit_action_baselines,
    fit_state_value_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-start", type=int, default=2014)
    parser.add_argument("--training-end", type=int, default=2023)
    parser.add_argument("--example-season", type=int, default=2024)
    parser.add_argument("--bootstrap-replicates", type=int, default=400)
    parser.add_argument("--parquet-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (
        args.training_start < 2014
        or args.training_end < args.training_start
        or args.example_season <= args.training_end
        or args.example_season > 2024
    ):
        raise SystemExit(
            "require ordered 2014+ training seasons and a later example season <= 2024"
        )
    seasons = list(range(args.training_start, args.training_end + 1)) + [
        args.example_season
    ]
    normalized = _load_normalized(seasons, args.parquet_dir)
    training_pbp = normalized.filter(pl.col("season") <= args.training_end)
    example_pbp = normalized.filter(pl.col("season") == args.example_season)
    state_model = fit_state_value_model(build_state_value_rows(training_pbp))
    action_models = fit_action_baselines(extract_fourth_down_candidates(training_pbp))
    examples = _select_examples(
        extract_fourth_down_candidates(example_pbp), action_models
    )

    print(
        f"CoachIQ baseline worked examples: train {args.training_start}-"
        f"{args.training_end}, inspect {args.example_season}"
    )
    print("All EWP values are model-based estimates, not known counterfactuals.\n")
    for label, row in examples:
        state = canonical_state_from_candidate(row)
        clock = f"{int(row['quarter_seconds_remaining']) // 60:02d}:"
        clock += f"{int(row['quarter_seconds_remaining']) % 60:02d}"
        print(
            f"{label}: {row['game_id']} play {row['play_id']} | "
            f"Q{row['quarter']} {clock}, {row['possession_team']} "
            f"4th-and-{row['yards_to_go']} at "
            f"yards_to_goal={row['yards_to_goal']:.0f}, "
            f"score diff={row['score_differential']:+d}"
        )
        print(f"  observed: {row['actual_action']} -> {row['factual_outcome']}")
        for estimate in estimate_all_actions(
            state,
            action_models,
            state_model,
            bootstrap_replicates=args.bootstrap_replicates,
        ):
            support = estimate.support
            if estimate.expected_win_probability is None:
                print(
                    f"  {estimate.action}: insufficient support "
                    f"(n={support.observation_count}, games={support.game_count}, "
                    f"reason={support.reason})"
                )
            else:
                print(
                    f"  {estimate.action}: EWP "
                    f"{estimate.expected_win_probability:.1%} "
                    f"(90% game-bootstrap interval "
                    f"{estimate.interval_lower:.1%}-{estimate.interval_upper:.1%}; "
                    f"n={support.observation_count}, games={support.game_count})"
                )
        print()


def _load_normalized(seasons: list[int], parquet_dir: Path | None) -> pl.DataFrame:
    frames = []
    for season in seasons:
        if parquet_dir:
            path = parquet_dir / f"play_by_play_{season}.parquet"
            if not path.exists():
                raise SystemExit(f"missing snapshot: {path}")
            raw = pl.read_parquet(path)
        else:
            raw = load_pbp([season])
        frames.append(normalize_pbp(raw))
    return pl.concat(frames).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )


def _select_examples(
    candidates: pl.DataFrame, action_models: ActionBaselineSet
) -> list[tuple[str, dict[str, object]]]:
    eligible = candidates.filter(pl.col("disposition") == "eligible").sort(
        "game_id", "play_sequence", "play_id"
    )
    definitions = (
        (
            "obvious punt",
            (pl.col("actual_action") == "punt")
            & (pl.col("yards_to_goal") >= 75)
            & (pl.col("yards_to_go") >= 8),
        ),
        (
            "obvious field goal",
            (pl.col("actual_action") == "field_goal")
            & pl.col("yards_to_goal").is_between(15, 30)
            & (pl.col("game_seconds_remaining") > 600),
        ),
        (
            "short fourth down near midfield",
            pl.col("yards_to_goal").is_between(45, 55) & (pl.col("yards_to_go") <= 2),
        ),
        (
            "fourth-and-short in opponent territory",
            (pl.col("yards_to_goal") <= 30) & (pl.col("yards_to_go") <= 2),
        ),
        (
            "late-game high leverage",
            (pl.col("quarter") == 4)
            & (pl.col("quarter_seconds_remaining") <= 300)
            & (pl.col("score_differential").abs() <= 8),
        ),
    )
    selected: list[tuple[str, dict[str, object]]] = []
    used: set[tuple[str, int]] = set()
    for label, expression in definitions:
        row = _first_unused(eligible.filter(expression), used)
        if row:
            selected.append((label, row))
            used.add((str(row["game_id"]), int(row["play_id"])))

    weakest: tuple[int, dict[str, object]] | None = None
    for row in eligible.iter_rows(named=True):
        key = (str(row["game_id"]), int(row["play_id"]))
        if key in used:
            continue
        state = canonical_state_from_candidate(row)
        actual_support = action_models.support(str(row["actual_action"]), state)
        candidate = (actual_support.observation_count, row)
        if weakest is None or candidate[0] < weakest[0]:
            weakest = candidate
    if weakest:
        selected.append(("weak support", weakest[1]))
    return selected


def _first_unused(
    rows: pl.DataFrame, used: set[tuple[str, int]]
) -> dict[str, object] | None:
    for row in rows.iter_rows(named=True):
        if (str(row["game_id"]), int(row["play_id"])) not in used:
            return row
    return None


if __name__ == "__main__":
    main()
