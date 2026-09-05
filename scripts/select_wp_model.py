"""Run the chronological CoachIQ state-value model-selection protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from coachiq.analysis import evaluate_wp_development, evaluate_wp_prelock_validation
from coachiq.data import load_pbp, normalize_pbp
from coachiq.models import (
    LOCKED_WP_CANDIDATE_ID,
    LOCKED_WP_MODEL_VERSION,
    LOCKED_WP_USES_RECALIBRATION,
    build_state_value_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        help="Directory containing play_by_play_YEAR.parquet snapshots.",
    )
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bootstrap_replicates < 1:
        raise SystemExit("bootstrap replicates must be positive")
    normalized = _load_normalized(list(range(2014, 2025)), args.parquet_dir)
    state_rows = build_state_value_rows(normalized)
    development = evaluate_wp_development(
        state_rows.filter(pl.col("season") <= 2023),
        bootstrap_replicates=args.bootstrap_replicates,
    )
    report = {
        "selection": {
            "candidate_id": LOCKED_WP_CANDIDATE_ID,
            "model_version": LOCKED_WP_MODEL_VERSION,
            "use_recalibration": LOCKED_WP_USES_RECALIBRATION,
            "selected_before_2024_evaluation": True,
            "selection_basis": [
                "meaningful game-clustered proper-score improvement over A",
                "pregame value concentrated early and decayed to zero at expiration",
                "same development performance as C with three fewer features",
                "all declared football property checks passed",
                "recalibration did not improve pooled proper scores",
            ],
        },
        "development": development,
        "prelock_validation": evaluate_wp_prelock_validation(
            state_rows,
            candidate_id=LOCKED_WP_CANDIDATE_ID,
            use_recalibration=LOCKED_WP_USES_RECALIBRATION,
        ),
    }
    _print_development_report(development)
    _print_selection_and_prelock(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"machine-readable model-selection report: {args.json_output}")


def _load_normalized(seasons: list[int], parquet_dir: Path | None) -> pl.DataFrame:
    if not seasons or min(seasons) < 2014 or max(seasons) > 2024:
        raise SystemExit("model selection permits only seasons 2014-2024")
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


def _print_development_report(report: dict[str, object]) -> None:
    print("\nCoachIQ WP candidate specifications:")
    for candidate in report["candidates"]:
        print(
            f"  {candidate['candidate_id']}: {candidate['description']}; "
            f"features={len(candidate['feature_names'])}; "
            f"ridge={candidate['ridge_penalty']:g}"
        )
    for fold in report["folds"]:
        print(
            f"\ntrain 2014-{fold['evaluation_season'] - 1} -> "
            f"develop {fold['evaluation_season']}"
        )
        for candidate_id, values in fold["candidates"].items():
            raw = values["raw"]
            recalibrated = values["recalibrated"]
            print(
                f"  {candidate_id} raw: n={raw['observations']:,}, "
                f"LL={raw['log_loss']:.4f}, Brier={raw['brier_score']:.4f}, "
                f"ECE={raw['expected_calibration_error']:.4f}; "
                f"recal LL={recalibrated['log_loss']:.4f}, "
                f"Brier={recalibrated['brier_score']:.4f}, "
                f"ECE={recalibrated['expected_calibration_error']:.4f}"
            )

    print("\npooled 2020-2023 development metrics:")
    for candidate_id, values in report["pooled_development"].items():
        raw = values["raw"]
        recalibrated = values["recalibrated"]
        print(
            f"  {candidate_id}: raw LL={raw['log_loss']:.4f}, "
            f"Brier={raw['brier_score']:.4f}, "
            f"ECE={raw['expected_calibration_error']:.4f}; "
            f"recal LL={recalibrated['log_loss']:.4f}, "
            f"Brier={recalibrated['brier_score']:.4f}, "
            f"ECE={recalibrated['expected_calibration_error']:.4f}"
        )

    print("\ngame-clustered raw-model comparisons (candidate minus reference):")
    for name, comparison in report["clustered_comparisons"].items():
        log_loss = comparison["log_loss"]
        brier = comparison["brier_score"]
        print(
            f"  {name}: ΔLL={log_loss['difference']:+.5f} "
            f"[{log_loss['lower']:+.5f}, {log_loss['upper']:+.5f}], "
            f"ΔBrier={brier['difference']:+.5f} "
            f"[{brier['lower']:+.5f}, {brier['upper']:+.5f}]"
        )

    print("\npregame incremental value, C minus B:")
    for name, values in report["pregame_incremental_value"].items():
        print(
            f"  {name}: n={values['observations']:,}, "
            f"ΔLL={values['delta_log_loss_C_minus_B']:+.5f}, "
            f"ΔBrier={values['delta_brier_C_minus_B']:+.5f}, "
            f"ΔECE={values['delta_ece_C_minus_B']:+.4f}, "
            f"ECE B={values['B_expected_calibration_error']:.4f}, "
            f"C={values['C_expected_calibration_error']:.4f}"
        )

    print("\nfootball property checks (raw):")
    for candidate_id, modes in report["property_checks"].items():
        checks = modes["raw"]["checks"]
        summary = ", ".join(
            f"{name}={values['violations']}/{values['comparisons']}"
            for name, values in checks.items()
        )
        dominance = modes["raw"]["late_game_dominance"]["violations"]
        print(f"  {candidate_id}: {summary}; late dominance={dominance}")

    investigation = report["2022_investigation"]
    print("\n2022 concentration diagnostic:")
    for season in (2021, 2022, 2023):
        values = investigation[str(season)]
        trimmed = values["log_loss_excluding_five_largest_game_contributors"]
        games = ", ".join(
            row["game_id"] for row in values["five_largest_game_contributors"]
        )
        print(
            f"  {season}: LL={values['overall_log_loss']:.4f}; "
            f"excluding top five games={trimmed:.4f}; "
            f"top-five loss share={values['top_five_share_of_total_loss']:.1%}; "
            f"games={games}"
        )


def _print_selection_and_prelock(report: dict[str, object]) -> None:
    selection = report["selection"]
    validation = report["prelock_validation"]
    selected = validation["selected"]
    print(
        f"\nlocked {selection['model_version']}: candidate "
        f"{selection['candidate_id']}, recalibration="
        f"{selection['use_recalibration']}"
    )
    print(
        f"one-time 2024 pre-lock validation: n={selected['observations']:,}, "
        f"LL={selected['log_loss']:.4f}, "
        f"Brier={selected['brier_score']:.4f}, "
        f"ECE={selected['expected_calibration_error']:.4f}"
    )
    print("2024 fixed calibration bands:")
    for band in selected["calibration"]:
        observed = (
            "empty" if band["observed_rate"] is None else f"{band['observed_rate']:.3f}"
        )
        mean_prediction = (
            "empty"
            if band["mean_prediction"] is None
            else f"{band['mean_prediction']:.3f}"
        )
        print(
            f"  {band['band']}: n={band['observations']:,}, "
            f"mean={mean_prediction}, "
            f"observed={observed}, sparse={band['sparse']}"
        )
    print("2024 clock regimes:")
    for name, values in selected["clock_regimes"].items():
        print(
            f"  {name}: n={values['observations']:,}, "
            f"LL={values['log_loss']:.4f}, Brier={values['brier_score']:.4f}, "
            f"ECE={values['expected_calibration_error']:.4f}"
        )
    print("2024 score regimes:")
    for name, values in selected["score_regimes"].items():
        print(
            f"  {name}: n={values['observations']:,}, "
            f"LL={values['log_loss']:.4f}, Brier={values['brier_score']:.4f}, "
            f"ECE={values['expected_calibration_error']:.4f}"
        )


if __name__ == "__main__":
    main()
