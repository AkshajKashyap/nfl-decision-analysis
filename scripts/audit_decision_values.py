"""Run reproducible pre-2025 CoachIQ fourth-down decision-value audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from coachiq.analysis import (
    DECISION_BOOTSTRAP_REPLICATES,
    evaluate_decision_diagnostics,
)
from coachiq.data import load_pbp, normalize_pbp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "section",
        choices=("diagnostics", "worked", "largest"),
        nargs="?",
        default="diagnostics",
    )
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        help="Directory containing play_by_play_YEAR.parquet snapshots.",
    )
    parser.add_argument(
        "--input-report",
        type=Path,
        help="Read a prior full JSON report instead of loading play-by-play.",
    )
    parser.add_argument(
        "--bootstrap-replicates", type=int, default=DECISION_BOOTSTRAP_REPLICATES
    )
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bootstrap_replicates < 1:
        raise SystemExit("bootstrap replicates must be positive")
    if args.input_report and (args.parquet_dir or args.json_output):
        raise SystemExit("--input-report cannot be combined with data/output options")
    if args.input_report:
        report = json.loads(args.input_report.read_text(encoding="utf-8"))
    else:
        normalized = _load_normalized(list(range(2014, 2025)), args.parquet_dir)
        report = evaluate_decision_diagnostics(
            normalized,
            bootstrap_replicates=args.bootstrap_replicates,
            progress=print,
        )
    if args.section == "diagnostics":
        _print_diagnostics(report)
    elif args.section == "worked":
        _print_audits(report["worked_audits"], "worked decision audits")
    else:
        _print_audits(report["largest_gap_audit"], "largest action-value gaps")
        flags = report["largest_gap_structural_flags"]
        print(f"\nstructural flags: {flags['totals']}")
        print(f"suspicious cases: {len(flags['suspicious_cases'])}")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"machine-readable decision report: {args.json_output}")


def _load_normalized(seasons: list[int], parquet_dir: Path | None) -> pl.DataFrame:
    if seasons != list(range(2014, 2025)):
        raise SystemExit("decision diagnostics require exactly 2014-2024")
    frames = []
    for season in seasons:
        if parquet_dir:
            path = parquet_dir / f"play_by_play_{season}.parquet"
            if not path.exists():
                raise SystemExit(f"missing snapshot: {path}")
            raw = pl.read_parquet(path)
        else:
            raw = load_pbp([season])
        normalized = normalize_pbp(raw)
        frames.append(normalized)
        print(f"loaded {season}: {normalized.height:,} normalized rows")
    return pl.concat(frames).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )


def _print_diagnostics(report: dict[str, object]) -> None:
    protocol = report["protocol"]
    print(
        f"\n{protocol['decision_value_version']} using "
        f"{protocol['wp_model_version']}; "
        f"bootstrap={protocol['bootstrap_replicates']} training-game replicates"
    )
    pooled = report["pooled"]
    print(f"pooled eligible decisions: {pooled['decisions']:,}")
    print("supported-action coverage:")
    for count, values in pooled["supported_action_counts"].items():
        print(f"  {count} actions: {values['decisions']:,} ({values['rate']:.1%})")
    print("classifications:")
    for name, values in pooled["classification"].items():
        print(f"  {name}: {values['decisions']:,} ({values['rate']:.1%})")
    print("actual-action unsupported rates:")
    for action, values in pooled["actual_action_support"].items():
        print(
            f"  {action}: {values['unsupported']:,}/{values['decisions']:,} "
            f"({values['unsupported_rate']:.1%})"
        )
    sparse = pooled["sparse_support_frequency"]
    overtime = pooled["overtime_boundary_frequency"]
    print(
        f"any sparse supported action: {sparse['decisions']:,} ({sparse['rate']:.1%})"
    )
    print(
        f"modeled OT-boundary transition mass: {overtime['decisions']:,} "
        f"({overtime['rate']:.2%})"
    )

    gaps = pooled["action_gap_distribution"]["overall"]
    print(
        "action-value gap distribution: "
        f"n={gaps['observations']:,}, median={gaps['median']:.3%}, "
        f"p75={gaps['p75']:.3%}, p90={gaps['p90']:.3%}, "
        f"p95={gaps['p95']:.3%}, max={gaps['maximum']:.3%}"
    )
    print("action-value gap by actual action:")
    for action, values in pooled["action_gap_distribution"]["by_actual_action"].items():
        print(
            f"  {action}: n={values['observations']:,}, "
            f"median={values['median']:.3%}, p90={values['p90']:.3%}, "
            f"max={values['maximum']:.3%}"
        )
    factual = pooled["factual_action_value_validation"]["overall"]
    print(
        "factual-action EWP validation: "
        f"n={factual['observations']:,}, LL={factual['log_loss']:.4f}, "
        f"Brier={factual['brier_score']:.4f}, "
        f"ECE={factual['expected_calibration_error']:.4f}"
    )
    print("temporal stability:")
    for row in report["temporal_stability"]:
        classifications = row["classification"]
        clear = classifications.get("clear_model_preference", {"rate": 0.0})["rate"]
        close = classifications.get("close_call", {"rate": 0.0})["rate"]
        limited = classifications.get("limited_support", {"rate": 0.0})["rate"]
        insufficient = classifications.get("insufficient_support", {"rate": 0.0})[
            "rate"
        ]
        support = row["supported_action_counts"]
        print(
            f"  {row['season']}: n={row['decisions']:,}, "
            f"support 3/2/1/0="
            f"{support['3']['decisions']}/{support['2']['decisions']}/"
            f"{support['1']['decisions']}/{support['0']['decisions']}, "
            f"clear={clear:.1%}, close={close:.1%}, "
            f"limited+insufficient={limited + insufficient:.1%}, "
            f"sparse={row['sparse_support_rate']:.1%}, "
            f"median/p90/p95/max gap={row['gap_median']:.3%}/"
            f"{row['gap_p90']:.3%}/{row['gap_p95']:.3%}/"
            f"{row['gap_maximum']:.3%}"
        )
    print("threshold sensitivity:")
    for row in report["threshold_sensitivity"]:
        clear = row["classification"]["clear_model_preference"]
        selected = " selected" if row["is_selected_policy"] else ""
        print(
            f"  gap={row['minimum_gap']:.1%}, "
            f"P={row['superiority_probability']:.1%}: "
            f"clear={clear['rate']:.1%}, "
            f"reclassified={row['reclassification_rate_vs_selected']:.1%}"
            f"{selected}"
        )
    monte_carlo = report["monte_carlo_stability"]
    print(
        "Monte Carlo resolution/stability: "
        f"resolution={monte_carlo['empirical_probability_resolution']:.2%}, "
        f"SE@95%={monte_carlo['binomial_standard_error_at_selected_cutoff']:.2%}, "
        f"reclassified at +/- one draw="
        f"{monte_carlo['reclassification_at_one_draw_lower']['rate']:.2%}/"
        f"{monte_carlo['reclassification_at_one_draw_upper']['rate']:.2%}"
    )
    print("stress tests:")
    for row in report["stress_tests"]:
        audit = row["audit"]
        print(
            f"  {row['label']}: preferred={audit['model_preferred_action']}, "
            f"classification={audit['classification']}, "
            f"bounds={row['probability_bounds_pass']}, "
            f"extreme-FG-abstention={row['extreme_field_goal_abstention_pass']}"
        )


def _print_audits(rows: list[dict[str, object]], title: str) -> None:
    print(f"\n{title}:")
    for row in rows:
        situation = row["situation"]
        label = row.get("audit_label", "large_gap")
        print(
            f"\n{label}: {row['game_id']} play {row['play_id']} | "
            f"{situation['possession_team']} Q{situation['quarter']} "
            f"{situation['quarter_seconds_remaining'] // 60:02d}:"
            f"{situation['quarter_seconds_remaining'] % 60:02d}, "
            f"4th-and-{situation['yards_to_go']:g}, "
            f"yards_to_goal={situation['yards_to_goal']:g}, "
            f"score={situation['score_differential']:+d}"
        )
        _print_nested_audit(row["audit"])
        if "transition_audit" in row:
            play = row["play_audit"]
            print(
                f"  factual reconstruction: outcome={play['factual_outcome']}, "
                f"next_status={play['next_state_status']}, "
                f"next_team={play['next_possession_team']}, "
                f"next_clock={play['next_game_seconds_remaining']}, "
                f"next_score={play['decision_team_score_differential_next']}, "
                f"next_timeouts={play['decision_team_timeouts_remaining_next']}/"
                f"{play['opponent_timeouts_remaining_next']}"
            )
            print(f"  description: {play['description']}")
            for action, transport in row["transition_audit"].items():
                if "structural_flags" not in transport:
                    print(
                        f"  {action} transport: {transport['support_status']} "
                        f"({transport['reason']})"
                    )
                    continue
                print(
                    f"  {action} transport: cell={transport['support_cell']}, "
                    f"retained/changed="
                    f"{transport['possession_retained_samples']}/"
                    f"{transport['possession_changed_samples']}, "
                    f"scoring restarts={transport['scoring_restart_samples']}, "
                    f"OT-boundary={transport['overtime_boundary_mass']:.2%}, "
                    f"flags={transport['structural_flags']}, "
                    f"pre-clip boundaries={transport['transport_boundary_counts']}"
                )


def _print_nested_audit(audit: dict[str, object]) -> None:
    print(
        f"  actual={audit['actual_action']}; "
        f"classification={audit['classification']}; "
        f"model-preferred={audit['model_preferred_action']}; "
        f"actual-action gap={_probability(audit['raw_action_value_gap'])}"
    )
    for value in audit["actions"]:
        if value["expected_win_probability"] is None:
            print(
                f"  {value['action']}: {value['support_status']}; "
                f"n={value['support_observations']}, "
                f"games={value['support_games']}, reason={value['support_reason']}"
            )
        else:
            print(
                f"  {value['action']}: EWP={value['expected_win_probability']:.2%} "
                f"[{value['interval_lower']:.2%}, {value['interval_upper']:.2%}], "
                f"support={value['support_status']}, "
                f"n={value['support_observations']}, games={value['support_games']}, "
                f"OT-boundary={value['overtime_boundary_mass']:.2%}"
            )
    for pair in audit["pairwise_differences"]:
        if pair["available"]:
            print(
                f"  {pair['action_a']} minus {pair['action_b']}: "
                f"{pair['difference']:+.2%} "
                f"[{pair['interval_lower']:+.2%}, {pair['interval_upper']:+.2%}], "
                f"P(A>B)={pair['probability_a_exceeds_b']:.1%}, "
                f"P(B>A)={pair['probability_b_exceeds_a']:.1%}, "
                f"P(tie)={pair['probability_tied']:.1%}"
            )
        else:
            print(
                f"  {pair['action_a']} minus {pair['action_b']}: unavailable "
                f"({pair['unavailable_reason']})"
            )
    print(
        f"  versions: {audit['decision_value_version']}, "
        f"{audit['wp_model_version']}, {audit['action_transition_model_version']}"
    )


def _probability(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.2%}"


if __name__ == "__main__":
    main()
