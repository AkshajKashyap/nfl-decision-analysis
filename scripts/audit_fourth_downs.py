"""Audit fourth-down reconstruction on a pre-holdout development season."""

from __future__ import annotations

import argparse

import polars as pl

from coachiq.analysis import (
    count_by,
    deterministic_manual_sample,
    extract_fourth_down_candidates,
    next_state_coverage,
)
from coachiq.data import load_pbp, normalize_pbp

DEFAULT_DEVELOPMENT_SEASON = 2024
LATEST_ALLOWED_DEVELOPMENT_SEASON = 2024
SAMPLE_COLUMNS = (
    "game_id",
    "play_id",
    "quarter",
    "clock",
    "possession_team",
    "yards_to_goal",
    "yards_to_go",
    "actual_action",
    "disposition",
    "disposition_reason",
    "factual_outcome",
    "next_state_status",
    "description",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "season",
        nargs="?",
        type=int,
        default=DEFAULT_DEVELOPMENT_SEASON,
        help="One development season; defaults to 2024 and never permits 2025+.",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--summary-only", action="store_true", help="Omit the manual sample."
    )
    output.add_argument(
        "--sample-only", action="store_true", help="Omit coverage diagnostics."
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of deterministic manual-audit rows (default: 20).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.season > LATEST_ALLOWED_DEVELOPMENT_SEASON:
        raise SystemExit(
            "2025 and later seasons are blocked by this development audit. "
            "Use 2024 or earlier."
        )
    if args.sample_size < 0:
        raise SystemExit("--sample-size cannot be negative")

    normalized = normalize_pbp(load_pbp([args.season]))
    candidates = extract_fourth_down_candidates(normalized)

    if not args.sample_only:
        _print_coverage(normalized, candidates, args.season)
    if not args.summary_only:
        if not args.sample_only:
            print()
        _print_sample(candidates, args.sample_size)


def _print_coverage(
    normalized: pl.DataFrame, candidates: pl.DataFrame, season: int
) -> None:
    total = normalized.height
    candidate_total = candidates.height
    fourth_down_total = normalized.filter(pl.col("down") == 4).height
    disposition_counts = dict(count_by(candidates, "disposition"))

    print(f"CoachIQ fourth-down reconstruction coverage: {season}")
    print(f"normalized rows: {total:,}")
    print(
        f"down == 4 rows: {fourth_down_total:,} ({_percent(fourth_down_total, total)})"
    )
    print(
        f"candidate audit rows: {candidate_total:,} "
        f"({_percent(candidate_total, fourth_down_total)})"
    )
    print("disposition counts (percentage of candidates):")
    for label in ("eligible", "excluded", "review"):
        count = disposition_counts.get(label, 0)
        print(f"  {label}: {count:,} ({_percent(count, candidate_total)})")

    _print_breakdown(
        "action counts", count_by(candidates, "actual_action"), candidate_total
    )
    reasons = candidates.filter(pl.col("disposition_reason").is_not_null())
    _print_breakdown(
        "non-eligible reason counts",
        count_by(reasons, "disposition_reason"),
        candidate_total,
    )

    next_counts = next_state_coverage(candidates)
    print("next-state reconstruction (percentage of candidates):")
    print(
        "  successful: "
        f"{next_counts['successful']:,} "
        f"({_percent(next_counts['successful'], candidate_total)})"
    )
    print(f"    reconstructed: {next_counts['reconstructed']:,}")
    print(f"    terminal: {next_counts['terminal']:,}")
    for label in ("unavailable", "ambiguous"):
        count = next_counts[label]
        print(f"  {label}: {count:,} ({_percent(count, candidate_total)})")


def _print_breakdown(
    title: str, counts: list[tuple[str, int]], denominator: int
) -> None:
    print(f"{title} (percentage of candidates):")
    for label, count in counts:
        print(f"  {label}: {count:,} ({_percent(count, denominator)})")


def _print_sample(candidates: pl.DataFrame, size: int) -> None:
    sample = deterministic_manual_sample(candidates, size).with_columns(
        (
            (pl.col("quarter_seconds_remaining") // 60).cast(pl.String).str.zfill(2)
            + pl.lit(":")
            + (pl.col("quarter_seconds_remaining") % 60).cast(pl.String).str.zfill(2)
        ).alias("clock")
    )
    print(f"deterministic manual sample ({sample.height} rows):")
    with pl.Config(
        tbl_cols=-1,
        tbl_rows=-1,
        tbl_width_chars=240,
        fmt_str_lengths=72,
    ):
        print(sample.select(SAMPLE_COLUMNS))


def _percent(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.00%"
    return f"{100 * numerator / denominator:.2f}%"


if __name__ == "__main__":
    main()
