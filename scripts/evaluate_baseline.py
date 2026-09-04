"""Run expanding-window diagnostics for the transparent CoachIQ baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from coachiq.analysis import evaluate_baseline
from coachiq.data import load_pbp, normalize_pbp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-season", type=int, default=2014)
    parser.add_argument("--end-season", type=int, default=2024)
    parser.add_argument("--first-evaluation-season", type=int, default=2020)
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        help="Optional directory containing play_by_play_YEAR.parquet snapshots.",
    )
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _validate_development_range(args.start_season, args.end_season)
    seasons = list(range(args.start_season, args.end_season + 1))
    normalized = _load_normalized(seasons, args.parquet_dir)
    report = evaluate_baseline(
        normalized, first_evaluation_season=args.first_evaluation_season
    )
    _print_report(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"machine-readable report: {args.json_output}")


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
        print(f"loaded {season}: {frames[-1].height:,} normalized rows")
    return pl.concat(frames).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )


def _print_report(report: dict[str, object]) -> None:
    invariants = report["invariants"]
    print("\nMilestone 2 invariants:")
    for name, value in invariants.items():
        print(f"  {name}: {value:,}")
    print("\nfield-goal distance check (kick_distance vs yards_to_goal + 18):")
    for row in report["field_goal_distance_validation"]:
        print(
            f"  {row['season']}: n={row['attempts']:,}, "
            f"MAE={row['mean_absolute_error']:.3f} yards, "
            f"exact={row['exact_match_rate']:.1%}, "
            f"range={row['minimum_difference']:+.0f}.."
            f"{row['maximum_difference']:+.0f}"
        )
    for split in report["splits"]:
        train = split["training_seasons"]
        state = split["state_value"]
        print(
            f"\ntrain {train[0]}-{train[-1]} -> evaluate {split['evaluation_season']}"
        )
        print(
            "  state value: "
            f"n={state['observations']:,}, log loss={state['log_loss']:.4f}, "
            f"Brier={state['brier_score']:.4f}, "
            f"ECE={state['expected_calibration_error']:.4f}"
        )
        constant = state["constant_benchmark"]
        print(
            "  constant benchmark: "
            f"log loss={constant['log_loss']:.4f}, "
            f"Brier={constant['brier_score']:.4f}"
        )
        nflverse = state["nflverse_wp_reference"]
        if nflverse:
            print(
                "  nflverse WP reference: "
                f"n={nflverse['observations']:,}, "
                f"log loss={nflverse['log_loss']:.4f}, "
                f"Brier={nflverse['brier_score']:.4f}"
            )
        for action in ("go", "field_goal"):
            values = split[action]
            metrics = values["metrics"]
            print(
                f"  {action}: supported={values['supported_observations']:,}/"
                f"{values['eligible_observed_outcomes']:,}, "
                f"unsupported={values['unsupported_rate']:.1%}, "
                f"log loss={metrics['log_loss']:.4f}, "
                f"Brier={metrics['brier_score']:.4f}"
            )
        punt = split["punt"]
        print(
            f"  punt: supported={punt['supported_observations']:,}/"
            f"{punt['eligible_observed_outcomes']:,}, "
            f"unsupported={punt['unsupported_rate']:.1%}, "
            f"field-position MAE={punt['mean_absolute_error_yards_to_goal']:.2f}, "
            f"RMSE={punt['root_mean_squared_error_yards_to_goal']:.2f}"
        )
        print("  action support over every eligible query:")
        for action, values in split["support"].items():
            print(
                f"    {action}: {values['supported']:,}/{values['queries']:,} "
                f"supported ({1.0 - values['unsupported_rate']:.1%}); "
                f"median local n={values['median_comparable_observations']:.0f}"
            )


def _validate_development_range(start: int, end: int) -> None:
    if start < 2014 or end < start:
        raise SystemExit("use an ordered season range beginning in 2014 or later")
    if end > 2024:
        raise SystemExit("2025 and later are blocked from baseline development")


if __name__ == "__main__":
    main()
