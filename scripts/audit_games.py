"""Produce deterministic CoachIQ publication-v1 game or weekly JSON audits."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import polars as pl

from coachiq.data import normalize_pbp
from coachiq.product import (
    SourceMetadata,
    audit_game,
    audit_week,
    fit_frozen_models,
    stable_json_dumps,
    validate_policy_development_boundary,
)

TRAINING_SEASONS = tuple(range(2014, 2025))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--week", type=int)
    target.add_argument("--game-id")
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        required=True,
        help="Directory containing explicit play_by_play_YEAR.parquet snapshots.",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument(
        "--source-retrieved-at-utc",
        help="Optional snapshot retrieval timestamp; defaults to file mtime.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_policy_development_boundary((args.season,))
    started = perf_counter()
    raw_by_season: dict[int, pl.DataFrame] = {}
    normalized_by_season: dict[int, pl.DataFrame] = {}
    needed = tuple(sorted(set((*TRAINING_SEASONS, args.season))))
    paths: dict[int, Path] = {}
    for season in needed:
        path = args.parquet_dir / f"play_by_play_{season}.parquet"
        if not path.exists():
            raise SystemExit(f"missing explicit snapshot: {path}")
        paths[season] = path
        raw_by_season[season] = pl.read_parquet(path)
        normalized_by_season[season] = normalize_pbp(raw_by_season[season])
        print(
            f"loaded {season}: {raw_by_season[season].height:,} raw / "
            f"{normalized_by_season[season].height:,} normalized rows"
        )
    loaded_at = perf_counter()
    historical = pl.concat(
        [normalized_by_season[season] for season in TRAINING_SEASONS]
    ).sort(["season", "game_id", "play_id", "play_sequence"], nulls_last=True)
    models = fit_frozen_models(
        historical, project_root=Path(__file__).resolve().parents[1]
    )
    fitted_at = perf_counter()

    target = normalized_by_season[args.season]
    if args.week is not None:
        selected = target.filter(pl.col("week") == args.week)
        weeks = (args.week,)
    else:
        selected = target.filter(pl.col("game_id") == args.game_id)
        weeks = tuple(sorted(int(value) for value in selected["week"].unique()))
    if not selected.height:
        raise SystemExit("selected game/week has no rows in the explicit snapshot")
    source_path = paths[args.season]
    retrieved = (
        args.source_retrieved_at_utc
        or datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC).isoformat()
    )
    source = SourceMetadata(
        source="explicit nflverse parquet snapshot",
        retrieved_at_utc=retrieved,
        seasons=(args.season,),
        weeks=weeks,
        row_count=raw_by_season[args.season].height,
        sha256=_sha256(source_path),
        resolved_assets=(source_path.name,),
    )
    report = (
        audit_week(selected, models, source=source)
        if args.week is not None
        else audit_game(selected, models, source=source)
    )
    audited_at = perf_counter()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(stable_json_dumps(report), encoding="utf-8")
    print(f"machine-readable audit: {args.json_output}")
    print(
        "runtime seconds: "
        f"load/normalize={loaded_at - started:.3f}, "
        f"fit={fitted_at - loaded_at:.3f}, "
        f"audit={audited_at - fitted_at:.3f}, "
        f"total={audited_at - started:.3f}"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
