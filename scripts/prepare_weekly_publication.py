"""Prepare a deterministic CoachIQ review queue and gated public package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl

from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.data import normalize_pbp
from coachiq.product import (
    build_publication_package,
    build_review_card,
    deterministic_shortlist,
    select_close_call_companion,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weekly-report", type=Path, required=True)
    parser.add_argument("--operational-summary", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--audit-hashes", type=Path, required=True)
    parser.add_argument("--pbp-parquet", type=Path, required=True)
    parser.add_argument("--correction-check", type=Path, required=True)
    parser.add_argument("--review-output-dir", type=Path, required=True)
    parser.add_argument("--shortlist-size", type=int, default=10)
    parser.add_argument("--reviews-json", type=Path)
    parser.add_argument("--selected-ids-json", type=Path)
    parser.add_argument("--public-output-dir", type=Path)
    parser.add_argument("--generated-at-utc")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weekly = _load_json(args.weekly_report)
    operational = _load_json(args.operational_summary)
    source_manifest = _load_json(args.source_manifest)
    audit_hashes = _load_json(args.audit_hashes)
    correction = _load_json(args.correction_check)
    excluded = tuple(correction.get("excluded_game_ids", ()))
    shortlist = deterministic_shortlist(
        weekly, limit=args.shortlist_size, excluded_game_ids=excluded
    )
    facts = _source_facts(args.pbp_parquet)
    warnings = {
        f"{item['game_id']}:{int(item['play_id'])}": item["warnings"]
        for item in operational["tactical_warnings"]
    }
    unchanged = set(correction.get("unchanged_game_ids", ()))
    cards = []
    for record in shortlist:
        item_id = (
            f"{record['identity']['game_id']}:{int(record['identity']['play_id'])}"
        )
        game_id = str(record["identity"]["game_id"])
        state = (
            "pbp_fingerprint_unchanged_current_source_verified"
            if game_id in unchanged
            else "current_source_verified_correction_status_unresolved"
        )
        cards.append(
            build_review_card(
                record,
                source_facts=facts[item_id],
                tactical_warnings=warnings.get(item_id, ()),
                correction_state=state,
            )
        )
    close_call = select_close_call_companion(weekly)
    review_inputs = [card["editorial_review"] for card in cards]
    blockers = []
    if not correction.get("ready_for_publication"):
        blockers.append("source_correction_check_incomplete")
    if any(review["status"] == "pending_review" for review in review_inputs):
        blockers.append("human_editorial_review_pending")
    status = {
        "publication_package_ready": not blockers,
        "blockers": blockers,
        "shortlist_size": len(cards),
        "approved": 0,
        "held_or_rejected": 0,
        "pending_review": len(review_inputs),
        "selected_decision_ids": [],
        "externally_published": False,
    }
    artifacts = {
        "README.md": _render_readiness(cards, close_call, correction, status),
        "close-call-companion.json": _json(close_call),
        "correction-check.json": _json(correction),
        "current-audit-evidence.json": _json(
            {
                "readiness_status": operational["readiness_status"],
                "counts": {
                    field: operational[field]
                    for field in (
                        "games_scheduled",
                        "games_final",
                        "games_successfully_processed",
                        "failed_games",
                        "eligible_decisions",
                        "valued_decisions",
                        "clear_model_preferences",
                        "publication_safe_decisions",
                    )
                },
                "source_manifest": source_manifest,
                "deterministic_artifact_hashes": audit_hashes,
            }
        ),
        "package-status.json": _json(status),
        "review-cards.json": _json({"cards": cards}),
        "review-cards.md": _render_cards(cards),
        "review-inputs.json": _json({"reviews": review_inputs}),
        "shortlist.json": _json(
            {
                "selection_rule": (
                    "publication-v1-safe only; frozen action-story round robin; "
                    "one case per game before deterministic evidence-ordered fill"
                ),
                "excluded_game_ids": list(excluded),
                "decision_ids": [card["decision_id"] for card in cards],
            }
        ),
    }
    _write_artifacts(args.review_output_dir, artifacts)

    public_args = (
        args.reviews_json,
        args.selected_ids_json,
        args.public_output_dir,
        args.generated_at_utc,
    )
    if any(value is not None for value in public_args):
        if not all(value is not None for value in public_args):
            raise SystemExit(
                "public generation requires reviews, selected IDs, output directory, "
                "and generated timestamp"
            )
        reviews = _load_json(args.reviews_json)["reviews"]
        selected = _load_json(args.selected_ids_json)["selected_decision_ids"]
        public = build_publication_package(
            weekly=weekly,
            review_cards=cards,
            reviews=reviews,
            selected_decision_ids=selected,
            correction_check=correction,
            generated_at_utc=args.generated_at_utc,
        )
        _write_artifacts(args.public_output_dir, public)

    print(f"shortlist: {len(cards)}")
    print(f"review output: {args.review_output_dir}")
    print("publication package: " + ("READY" if not blockers else "NOT READY"))


def _source_facts(path: Path) -> dict[str, dict[str, Any]]:
    candidates = extract_fourth_down_candidates(normalize_pbp(pl.read_parquet(path)))
    eligible = candidates.filter(pl.col("disposition") == "eligible")
    return {
        f"{row['game_id']}:{int(row['play_id'])}": {
            "game_id": str(row["game_id"]),
            "play_id": int(row["play_id"]),
            "possession_team": str(row["possession_team"]),
            "possession_team_score": int(row["posteam_score"]),
            "defense_team_score": int(row["defteam_score"]),
            "quarter": int(row["quarter"]),
            "quarter_seconds_remaining": int(row["quarter_seconds_remaining"]),
            "score_differential": int(row["score_differential"]),
            "yards_to_go": float(row["yards_to_go"]),
            "yards_to_goal": float(row["yards_to_goal"]),
            "actual_action": str(row["actual_action"]),
            "factual_outcome": str(row["factual_outcome"]),
            "description": row.get("description"),
        }
        for row in eligible.iter_rows(named=True)
    }


def _render_cards(cards: list[dict[str, Any]]) -> str:
    lines = [
        "# CoachIQ 2026 Week 1 human-review cards",
        "",
        "Internal only. These records passed automated publication-v1 checks but "
        "have not been approved by a human.",
        "",
    ]
    for card in cards:
        identity = card["identity"]
        situation = card["situation"]
        factual = card["factual_play"]
        output = card["coachiq_output"]
        comparison = output["comparison"]
        diagnostics = output["safety_diagnostics"]
        minutes, seconds = divmod(int(situation["quarter_seconds_remaining"]), 60)
        lines.extend(
            (
                f"## {card['decision_id']}",
                "",
                f"- Game: {identity['away_team']} at {identity['home_team']}",
                f"- Situation: Q{situation['quarter']} {minutes}:{seconds:02d}; "
                f"{identity['possession_team']} "
                f"{situation['possession_team_score']}-"
                f"{situation['defense_team_score']}; fourth-and-"
                f"{situation['yards_to_go']:g}; yards to goal "
                f"{situation['yards_to_goal']:g}",
                f"- Actual action / outcome: `{factual['actual_action']}` / "
                f"`{factual['factual_outcome']}`",
                f"- Source description: {factual['source_description']}",
                f"- CoachIQ favored: "
                f"`{comparison['model_preferred_supported_action']}`; claimed gap "
                f"{float(comparison['claimed_comparison_gap']) * 100:.2f} pp; "
                f"minimum superiority "
                f"{float(comparison['minimum_pairwise_superiority']):.3f}",
                f"- Publication: `{card['publication']['status']}`; reasons: "
                f"{card['publication']['withholding_reasons'] or 'none'}; warnings: "
                f"{card['tactical_context_warnings'] or 'none'}",
                f"- Safety maxima: field "
                f"{float(diagnostics['maximum_field_clipping_mass']):.3%}; clock "
                f"{float(diagnostics['maximum_clock_clipping_mass']):.3%}; OT "
                f"{float(diagnostics['maximum_overtime_boundary_mass']):.3%}",
                f"- Source correction state: `{card['source_correction_state']}`",
                f"- Source fingerprint: `{card['provenance']['source']['sha256']}`",
                f"- Versions: `{card['provenance']['wp_model_version']}`, "
                f"`{card['provenance']['action_transition_model_version']}`, "
                f"`{card['provenance']['decision_value_version']}`, "
                f"`{card['provenance']['publication_policy_version']}`",
                "",
                "| Action | EWP | 90% interval | Support observations/games | "
                "Field / clock clipping |",
                "|---|---:|---:|---:|---:|",
            )
        )
        for action in output["modeled_actions"]:
            name = str(action["action"])
            ewp = action["expected_win_probability"]
            interval = (
                "unavailable"
                if ewp is None
                else f"{float(action['interval_lower']):.1%}–"
                f"{float(action['interval_upper']):.1%}"
            )
            clipping = (
                diagnostics["field_clipping_mass_by_action"].get(name),
                diagnostics["clock_clipping_mass_by_action"].get(name),
            )
            clipping_text = (
                "unavailable"
                if clipping[0] is None
                else f"{float(clipping[0]):.2%} / {float(clipping[1]):.2%}"
            )
            lines.append(
                f"| {name} | {'unavailable' if ewp is None else f'{float(ewp):.1%}'} "
                f"| {interval} | {action['support_observations']} / "
                f"{action['support_games']} | {clipping_text} |"
            )
        lines.extend(
            (
                "",
                "Pairwise evidence and the complete automated source-verification "
                "checklist are retained in `review-cards.json`.",
                "",
                f"Proposed neutral wording: {card['neutral_public_language']}",
                "",
                "Human result: `pending_review`",
                "",
            )
        )
    return "\n".join(lines)


def _render_readiness(
    cards: list[dict[str, Any]],
    close_call: dict[str, Any],
    correction: dict[str, Any],
    status: dict[str, Any],
) -> str:
    lines = [
        "# CoachIQ 2026 Week 1 publication readiness",
        "",
        "Status: **PUBLICATION PACKAGE NOT READY**",
        "",
        "No public report, social package, visual payload, or publication "
        "manifest has been emitted.",
        "",
        "## Current evidence",
        "",
        "- All 16 scheduled games remain final and all 16 were processed.",
        "- The corrected frozen rerun retained 203 eligible, 200 valued, 62 "
        "clear, and 43 publication-v1-safe decisions.",
        "- Two complete current-source runs were byte-identical apart from "
        "deliberately nondeterministic runtime metrics.",
        f"- The internal shortlist contains {len(cards)} cases; "
        "Denver–Kansas City is excluded while its source revision remains "
        "unresolved.",
        f"- Human outcomes: {status['approved']} approved, "
        f"{status['held_or_rejected']} held/rejected, "
        f"{status['pending_review']} pending.",
        f"- Close-call companion: `{close_call['decision_id']}`.",
        "- External publication state: `false`.",
        "",
        "## Blocking issues",
        "",
    ]
    if not correction.get("ready_for_publication"):
        lines.append(
            "1. The Week 1 schedule fingerprint changed and the PBP change is "
            "isolated to `2026_01_DEN_KC`, but the original raw snapshot and "
            "machine artifacts were not retained. Exact changed rows/cells and "
            "the full downstream publication impact therefore cannot be proven."
        )
    number = 2 if not correction.get("ready_for_publication") else 1
    lines.extend(
        (
            f"{number}. No human reviewer has supplied final checklist results. "
            "Automation has left all candidates at `pending_review` and assigned "
            "no approvals.",
            "",
            "## Required next step",
            "",
            (
                "Restore the original Milestone 9 schedule/PBP snapshot and machine "
                "reports to complete the exact correction diff. Then have a named "
                "human reviewer complete `review-inputs.json`. Only after both "
                "gates pass may the tool select three to five approved cases and "
                "emit `reports/2026/week-01.md`."
                if not correction.get("ready_for_publication")
                else "Have a named human reviewer complete `review-inputs.json`. "
                "Then select three to five approved cases and run the gated public "
                "package generation."
            ),
            "",
            "See `correction-check.json`, `review-cards.md`, `review-cards.json`, "
            "and `package-status.json` for the machine-readable evidence.",
            "",
        )
    )
    return "\n".join(lines)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _write_artifacts(directory: Path, artifacts: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (directory / name).write_text(content, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(content.encode()).hexdigest()
        for name, content in sorted(artifacts.items())
    }
    (directory / "hashes.json").write_text(_json(hashes), encoding="utf-8")


if __name__ == "__main__":
    main()
