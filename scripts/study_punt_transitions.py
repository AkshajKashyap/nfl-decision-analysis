"""Run pre-2025 CoachIQ punt-transition diagnostics and experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from coachiq.analysis.punt_transition_study import (
    PUNT_STUDY_SEASONS,
    compare_punt_candidates,
    diagnose_punt_v1,
    evaluate_punt_decision_sensitivity,
    select_raw_punt_audit_fields,
)
from coachiq.data import normalize_pbp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", choices=("diagnose", "compare", "decision"))
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        required=True,
        help="Directory containing only play_by_play_2014.parquet through 2024.",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized = []
    raw_audits = []
    for season in PUNT_STUDY_SEASONS:
        path = args.parquet_dir / f"play_by_play_{season}.parquet"
        if not path.exists():
            raise SystemExit(f"missing development snapshot: {path}")
        raw = pl.read_parquet(path)
        observed = sorted(int(value) for value in raw["season"].unique())
        if observed != [season] or season > 2024:
            raise SystemExit("punt study accepts only exact 2014-2024 snapshots")
        normalized.append(normalize_pbp(raw))
        raw_audits.append(select_raw_punt_audit_fields(raw))
        print(f"loaded development season {season}: {raw.height:,} rows")
    pbp = pl.concat(normalized).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )
    if args.section == "diagnose":
        report = diagnose_punt_v1(pbp, pl.concat(raw_audits))
    elif args.section == "compare":
        report = compare_punt_candidates(pbp)
    else:
        report = evaluate_punt_decision_sensitivity(pbp, progress=print)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"punt study {args.section}: {args.json_output}")


if __name__ == "__main__":
    main()
