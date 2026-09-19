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
    original_shortlist = deterministic_shortlist(weekly, limit=args.shortlist_size)
    shortlist, quarantined_decision_ids = _filter_shortlist_for_correction(
        original_shortlist,
        correction=correction,
        source_manifest=source_manifest,
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
                source_game_fingerprint=source_manifest["per_game_fingerprints"][
                    game_id
                ],
                tactical_warnings=warnings.get(item_id, ()),
                correction_state=state,
            )
        )
    close_call = select_close_call_companion(weekly)
    review_inputs = [card["editorial_review"] for card in cards]
    blockers = []
    if not correction.get("unchanged_games_may_proceed_to_human_review"):
        blockers.append("scoped_correction_policy_not_applied")
    if any(review["status"] == "pending_review" for review in review_inputs):
        blockers.append("human_editorial_review_pending")
    status = {
        "publication_package_ready": not blockers,
        "blockers": blockers,
        "shortlist_size": len(cards),
        "approved": 0,
        "held_or_rejected": 0,
        "pending_review": len(review_inputs),
        "quarantined_game_ids": sorted(
            set(correction.get("changed_game_ids", ()))
            | set(correction.get("excluded_game_ids", ()))
        ),
        "quarantined_decision_ids": quarantined_decision_ids,
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
        "human-review.md": _render_cards(cards),
        "review-inputs.json": _json({"reviews": review_inputs}),
        "shortlist.json": _json(
            {
                "selection_rule": (
                    "form the original publication-v1-safe frozen shortlist first; "
                    "then remove changed-game cases without replacement"
                ),
                "original_decision_ids": [
                    f"{record['identity']['game_id']}:"
                    f"{int(record['identity']['play_id'])}"
                    for record in original_shortlist
                ],
                "quarantined_game_ids": status["quarantined_game_ids"],
                "quarantined_decision_ids": quarantined_decision_ids,
                "decision_ids": [card["decision_id"] for card in cards],
                "replacement_candidates_added": False,
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


def _filter_shortlist_for_correction(
    original_shortlist: tuple[dict[str, Any], ...],
    *,
    correction: dict[str, Any],
    source_manifest: dict[str, Any],
) -> tuple[tuple[dict[str, Any], ...], list[str]]:
    """Remove quarantined games from the fixed shortlist without backfilling."""

    quarantined_games = set(correction.get("changed_game_ids", ())) | set(
        correction.get("excluded_game_ids", ())
    )
    unchanged_games = set(correction.get("unchanged_game_ids", ()))
    expected_fingerprints = correction.get("unchanged_game_fingerprints", {})
    current_fingerprints = source_manifest.get("per_game_fingerprints", {})
    retained = []
    quarantined_decisions = []
    for record in original_shortlist:
        game_id = str(record["identity"]["game_id"])
        item_id = f"{game_id}:{int(record['identity']['play_id'])}"
        if game_id in quarantined_games:
            quarantined_decisions.append(item_id)
            continue
        if game_id not in unchanged_games:
            raise ValueError(
                f"shortlisted game lacks unchanged-source proof: {game_id}"
            )
        expected = expected_fingerprints.get(game_id)
        current = current_fingerprints.get(game_id)
        if not expected or current != expected:
            raise ValueError(f"shortlisted game fingerprint is not verified: {game_id}")
        retained.append(record)
    return tuple(retained), quarantined_decisions


def _render_cards(cards: list[dict[str, Any]]) -> str:
    lines = [
        "# CoachIQ 2026 Week 1 human-review cards",
        "",
        "Internal only. Denver–Kansas City is quarantined and absent. Every card "
        "below remains `pending_review`; automation has assigned no approval.",
        "",
        "For each card, return exactly one status: `approved`, "
        "`hold_for_context`, `reject_data_issue`, or `reject_model_form_risk`, "
        "plus a short reviewer note. Do not edit the evidence fields.",
        "",
    ]
    for card in cards:
        identity = card["identity"]
        situation = card["situation"]
        factual = card["factual_play"]
        output = card["coachiq_output"]
        comparison = output["comparison"]
        diagnostics = output["safety_diagnostics"]
        modeled = {action["action"]: action for action in output["modeled_actions"]}
        actual_name = str(factual["actual_action"])
        favored_name = str(comparison["model_preferred_supported_action"])
        comparison_name = str(comparison["claimed_comparison_action"])
        actual_ewp = float(modeled[actual_name]["expected_win_probability"])
        favored_ewp = float(modeled[favored_name]["expected_win_probability"])
        pairwise = _favored_pairwise(comparison, favored_name, comparison_name)
        minutes, seconds = divmod(int(situation["quarter_seconds_remaining"]), 60)
        lines.extend(
            (
                f"## {card['decision_id']}",
                "",
                "### Factual play",
                "",
                f"- Matchup / play: {identity['away_team']} at "
                f"{identity['home_team']}, play `{identity['play_id']}`",
                f"- Quarter / clock: Q{situation['quarter']} {minutes}:{seconds:02d}",
                f"- Score: {identity['possession_team']} "
                f"{situation['possession_team_score']}, "
                f"{_defense_team(identity)} {situation['defense_team_score']}",
                f"- Possession: `{identity['possession_team']}`",
                f"- Down / distance: fourth-and-{situation['yards_to_go']:g}",
                f"- Field position: {_field_position(identity, situation)}",
                f"- Raw description: {factual['source_description']}",
                f"- Actual action: `{actual_name}`",
                f"- Factual outcome: `{factual['factual_outcome']}`",
                "",
                "### Model evidence and safety",
                "",
                f"- CoachIQ-favored action: `{favored_name}`",
                f"- Actual-action EWP: {actual_ewp:.2%}",
                f"- Favored-action EWP: {favored_ewp:.2%}",
                f"- Modeled gap: {float(comparison['claimed_comparison_gap']):.2%} "
                f"over `{comparison_name}`",
                f"- Pairwise superiority: {pairwise['superiority']:.3f}",
                f"- 90% paired difference interval: "
                f"{pairwise['lower']:.2%} to {pairwise['upper']:.2%}",
                f"- Field clipping maximum: "
                f"{float(diagnostics['maximum_field_clipping_mass']):.3%}; clock "
                f"clipping maximum: "
                f"{float(diagnostics['maximum_clock_clipping_mass']):.3%}",
                f"- OT-boundary mass: "
                f"{float(diagnostics['maximum_overtime_boundary_mass']):.3%}",
                f"- Tactical-context warnings: "
                f"{card['tactical_context_warnings'] or 'none'}",
                f"- Source correction state: `{card['source_correction_state']}`",
                f"- Game source fingerprint: `{card['source_game_fingerprint']}`",
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
                f"Proposed neutral public sentence: {card['neutral_public_language']}",
                "",
                "### Human response",
                "",
                "- Status: `pending_review`",
                "- Allowed final status: `approved` / `hold_for_context` / "
                "`reject_data_issue` / `reject_model_form_risk`",
                "- Reviewer notes: _",
                "",
            )
        )
    return "\n".join(lines)


def _favored_pairwise(
    comparison: dict[str, Any], favored: str, compared: str
) -> dict[str, float]:
    for evidence in comparison["pairwise_evidence"]:
        if not evidence["available"] or {
            evidence["action_a"],
            evidence["action_b"],
        } != {
            favored,
            compared,
        }:
            continue
        if evidence["action_a"] == favored:
            return {
                "superiority": float(evidence["probability_a_exceeds_b"]),
                "lower": float(evidence["interval_lower"]),
                "upper": float(evidence["interval_upper"]),
            }
        return {
            "superiority": float(evidence["probability_b_exceeds_a"]),
            "lower": -float(evidence["interval_upper"]),
            "upper": -float(evidence["interval_lower"]),
        }
    raise ValueError(f"missing pairwise evidence for {favored} versus {compared}")


def _field_position(identity: dict[str, Any], situation: dict[str, Any]) -> str:
    yards_to_goal = float(situation["yards_to_goal"])
    possession = str(identity["possession_team"])
    defense = _defense_team(identity)
    if yards_to_goal > 50:
        return f"{possession} {100 - yards_to_goal:g}"
    if yards_to_goal < 50:
        return f"{defense} {yards_to_goal:g}"
    return "50-yard line"


def _defense_team(identity: dict[str, Any]) -> str:
    possession = str(identity["possession_team"])
    teams = (str(identity["away_team"]), str(identity["home_team"]))
    return next(team for team in teams if team != possession)


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
        "- The original ten-case shortlist was formed before correction "
        "filtering. Its Denver–Kansas City case was removed without backfill.",
        f"- The unaffected human-review queue contains {len(cards)} cases.",
        "- `2026_01_DEN_KC` remains quarantined. No decision from that game may "
        "be selected for Week 1 publication.",
        f"- Human outcomes: {status['approved']} approved, "
        f"{status['held_or_rejected']} held/rejected, "
        f"{status['pending_review']} pending.",
        f"- Close-call companion: `{close_call['decision_id']}`.",
        "- External publication state: `false`.",
        "",
        "## Blocking issues",
        "",
    ]
    lines.extend(
        (
            "1. No human reviewer has supplied final checklist results. "
            "Automation has left all candidates at `pending_review` and assigned "
            "no approvals.",
            "",
            "## Quarantine evidence",
            "",
            "The original Denver–Kansas City row-level snapshot cannot be "
            "recovered exactly. That is an archival limitation, not permission "
            "to waive the correction check and not a scientific-model failure. "
            "The changed game remains excluded under the Week 1 package policy.",
            "",
            "## Required next step",
            "",
            "Have a named human reviewer return one allowed final status and notes "
            "for every card in `human-review.md`. Do not select public cases or "
            "generate `reports/2026/week-01.md` until those results are supplied.",
            "",
            "See `correction-check.json`, `human-review.md`, `review-cards.json`, "
            "and `package-status.json`.",
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
