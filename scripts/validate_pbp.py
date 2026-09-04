"""Manually inspect CoachIQ's Milestone 1 PBP pipeline on a development season."""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from coachiq.data import build_manifest, load_pbp, normalize_pbp, write_manifest

DEFAULT_DEVELOPMENT_SEASON = 2024
IMPORTANT_STATE_COLUMNS = (
    "game_id",
    "play_id",
    "possession_team",
    "defense_team",
    "down",
    "yards_to_go",
    "yards_to_goal",
    "quarter",
    "game_seconds_remaining",
    "score_differential",
    "posteam_timeouts_remaining",
    "defteam_timeouts_remaining",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "seasons",
        nargs="*",
        type=int,
        default=[DEFAULT_DEVELOPMENT_SEASON],
        help="Historical development season(s); defaults to 2024.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        help="Optional explicit path for the retrieval manifest JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if 2025 in args.seasons:
        raise SystemExit(
            "2025 is the retrospective holdout and is intentionally blocked by this "
            "development validation script. Use 2023 or 2024."
        )

    raw = load_pbp(args.seasons)
    normalized = normalize_pbp(raw)
    manifest = build_manifest(raw, args.seasons)

    raw_fourth_down_rows = raw.select(
        pl.col("down").cast(pl.Int8, strict=False).eq(4).sum().alias("count")
    ).item()
    null_counts = normalized.select(
        [
            pl.col(column).is_null().sum().alias(column)
            for column in IMPORTANT_STATE_COLUMNS
        ]
    ).row(0, named=True)

    print(f"requested seasons: {', '.join(map(str, manifest.requested_seasons))}")
    print(f"observed seasons: {', '.join(map(str, manifest.observed_seasons))}")
    print(f"raw rows: {raw.height}")
    print(f"normalized rows: {normalized.height}")
    print(f"normalized columns: {normalized.width}")
    print(f"games: {normalized.get_column('game_id').n_unique()}")
    print(f"raw rows with down == 4: {raw_fourth_down_rows}")
    print("important normalized null counts:")
    for column, count in null_counts.items():
        print(f"  {column}: {count}")

    if args.manifest_path:
        write_manifest(manifest, args.manifest_path)
        print(f"manifest: {args.manifest_path}")


if __name__ == "__main__":
    main()
