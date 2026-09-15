"""Deterministic human-review and public-package contracts for CoachIQ."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

FROZEN_VERSIONS = {
    "wp_model_version": "coachiq-wp-v1",
    "action_transition_model_version": "coachiq-action-transition-v1",
    "decision_value_version": "coachiq-decision-v1",
    "publication_policy_version": "coachiq-publication-v1",
}

EDITORIAL_RESULTS = (
    "approved",
    "hold_for_context",
    "reject_data_issue",
    "reject_model_form_risk",
)

HUMAN_REVIEW_CHECKS = (
    "source_game_state",
    "possession",
    "score",
    "quarter_and_clock",
    "down_and_distance",
    "field_position_orientation",
    "actual_action_classification",
    "factual_outcome",
    "tactical_context",
    "fake_or_unusual_formation",
    "clipping_within_policy",
    "zero_overtime_boundary_mass",
    "complete_non_sparse_support",
    "pairwise_evidence",
    "neutral_model_based_wording",
)

_PROHIBITED_PATTERNS = {
    "mistake": re.compile(r"\bmistake\b", re.IGNORECASE),
    "wrong": re.compile(r"\bwrong\b", re.IGNORECASE),
    "objectively": re.compile(r"\bobjectively\b", re.IGNORECASE),
    "optimal": re.compile(r"\boptimal\b", re.IGNORECASE),
    "cost_them": re.compile(r"\bcost\s+(?:them|the\s+team)\b", re.IGNORECASE),
    "lost_win_probability": re.compile(
        r"\blost\b.{0,32}\bwin\s+probabilit(?:y|ies)\b", re.IGNORECASE
    ),
    "terrible_call": re.compile(r"\bterrible\s+call\b", re.IGNORECASE),
    "worst_coach": re.compile(r"\bworst\s+coach\b", re.IGNORECASE),
    "blew_it": re.compile(r"\bblew\s+it\b", re.IGNORECASE),
    "expected_wins_lost": re.compile(r"\bexpected\s+wins?\s+lost\b", re.IGNORECASE),
}

_BUCKET_ORDER = (
    ("punt", "go"),
    ("go", "go"),
    ("punt", "punt"),
    ("field_goal", "go"),
    ("field_goal", "field_goal"),
    ("go", "field_goal"),
    ("punt", "field_goal"),
    ("go", "punt"),
    ("field_goal", "punt"),
)


def decision_id(record: Mapping[str, Any]) -> str:
    """Return the canonical stable ID for a publication record."""

    identity = record["identity"]
    return f"{identity['game_id']}:{int(identity['play_id'])}"


def weekly_records(weekly: Mapping[str, Any] | Any) -> tuple[dict[str, Any], ...]:
    """Flatten records from either a WeeklyAudit or its serialized payload."""

    payload = weekly.to_dict() if hasattr(weekly, "to_dict") else weekly
    return tuple(record for game in payload["games"] for record in game["decisions"])


def deterministic_shortlist(
    weekly: Mapping[str, Any] | Any,
    *,
    limit: int = 10,
    excluded_game_ids: Iterable[str] = (),
) -> tuple[dict[str, Any], ...]:
    """Build a varied shortlist using frozen record evidence only."""

    if limit < 1:
        raise ValueError("shortlist limit must be positive")
    excluded = set(excluded_game_ids)
    candidates = [
        record
        for record in weekly_records(weekly)
        if _is_publication_safe(record)
        and str(record["identity"]["game_id"]) not in excluded
    ]
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in candidates:
        key = (
            str(record["actual_decision"]["actual_action"]),
            str(record["comparison"]["model_preferred_supported_action"]),
        )
        buckets.setdefault(key, []).append(record)
    for values in buckets.values():
        values.sort(key=_shortlist_sort_key)

    ordered_buckets = [key for key in _BUCKET_ORDER if key in buckets]
    ordered_buckets.extend(sorted(set(buckets) - set(ordered_buckets)))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_games: set[str] = set()

    # The first pass round-robins action stories and limits game repetition.
    made_progress = True
    while len(selected) < limit and made_progress:
        made_progress = False
        for key in ordered_buckets:
            choice = next(
                (
                    record
                    for record in buckets[key]
                    if decision_id(record) not in selected_ids
                    and str(record["identity"]["game_id"]) not in selected_games
                ),
                None,
            )
            if choice is None:
                continue
            _append_choice(choice, selected, selected_ids, selected_games)
            made_progress = True
            if len(selected) == limit:
                break

    # If necessary, fill deterministically without the one-case-per-game preference.
    remaining = sorted(
        (record for record in candidates if decision_id(record) not in selected_ids),
        key=_shortlist_sort_key,
    )
    for record in remaining:
        if len(selected) == limit:
            break
        _append_choice(record, selected, selected_ids, selected_games)
    return tuple(selected)


def build_review_card(
    record: Mapping[str, Any],
    *,
    source_facts: Mapping[str, Any],
    tactical_warnings: Sequence[str] = (),
    correction_state: str,
) -> dict[str, Any]:
    """Expose all scientific and factual context without asserting human review."""

    _validate_frozen_record(record)
    identity = record["identity"]
    situation = record["situation"]
    actual = record["actual_decision"]
    auto_checks = {
        "game_id": str(source_facts["game_id"]) == str(identity["game_id"]),
        "play_id": int(source_facts["play_id"]) == int(identity["play_id"]),
        "possession": str(source_facts["possession_team"])
        == str(identity["possession_team"]),
        "quarter": int(source_facts["quarter"]) == int(situation["quarter"]),
        "quarter_seconds_remaining": int(source_facts["quarter_seconds_remaining"])
        == int(situation["quarter_seconds_remaining"]),
        "yards_to_go": float(source_facts["yards_to_go"])
        == float(situation["yards_to_go"]),
        "yards_to_goal": float(source_facts["yards_to_goal"])
        == float(situation["yards_to_goal"]),
        "score_differential": int(source_facts["score_differential"])
        == int(situation["score_differential"]),
        "actual_action": str(source_facts["actual_action"])
        == str(actual["actual_action"]),
        "factual_outcome": str(source_facts["factual_outcome"])
        == str(actual["factual_outcome"]),
        "source_description": source_facts.get("description")
        == actual.get("source_description"),
    }
    if not all(auto_checks.values()):
        failed = ", ".join(key for key, passed in auto_checks.items() if not passed)
        raise ValueError(f"review-card source mismatch: {failed}")
    return {
        "decision_id": decision_id(record),
        "identity": dict(identity),
        "situation": {
            **dict(situation),
            "possession_team_score": int(source_facts["possession_team_score"]),
            "defense_team_score": int(source_facts["defense_team_score"]),
        },
        "factual_play": dict(actual),
        "coachiq_output": {
            "modeled_actions": record["modeled_actions"],
            "comparison": record["comparison"],
            "safety_diagnostics": record["safety_diagnostics"],
        },
        "publication": record["publication"],
        "tactical_context_warnings": list(tactical_warnings),
        "provenance": record["provenance"],
        "source_verification": auto_checks,
        "source_correction_state": correction_state,
        "neutral_public_language": record["public_language"],
        "editorial_review": pending_review_input(record),
    }


def pending_review_input(record: Mapping[str, Any]) -> dict[str, Any]:
    """Create a deliberately non-approving human-review input template."""

    return {
        "decision_id": decision_id(record),
        "status": "pending_review",
        "reviewer": None,
        "reviewer_type": None,
        "reviewed_at_utc": None,
        "checklist": {name: False for name in HUMAN_REVIEW_CHECKS},
        "note": None,
    }


def validate_human_review(
    record: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    correction_check: Mapping[str, Any],
) -> None:
    """Validate a final human decision and forbid publication-policy overrides."""

    status = review.get("status")
    if status not in EDITORIAL_RESULTS:
        raise ValueError(f"unknown or non-final editorial status: {status}")
    if review.get("decision_id") != decision_id(record):
        raise ValueError("editorial decision ID does not match record")
    if review.get("reviewer_type") != "human":
        raise ValueError("final editorial results require reviewer_type='human'")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("final editorial results require a named human reviewer")
    _validate_utc_timestamp(review.get("reviewed_at_utc"), "reviewed_at_utc")
    checks = review.get("checklist")
    if not isinstance(checks, Mapping) or set(checks) != set(HUMAN_REVIEW_CHECKS):
        raise ValueError("final editorial result requires the complete checklist")
    if not all(isinstance(value, bool) for value in checks.values()):
        raise ValueError("editorial checklist values must be booleans")

    if status == "approved":
        if not _is_publication_safe(record):
            raise ValueError(
                "human review cannot approve a publication-withheld decision"
            )
        if not all(checks.values()):
            raise ValueError("approval requires every human-review check to pass")
        validate_correction_check(correction_check)


def validate_correction_check(correction_check: Mapping[str, Any]) -> None:
    """Require a complete, current source correction check before approval use."""

    _validate_utc_timestamp(
        correction_check.get("checked_at_utc"), "correction checked_at_utc"
    )
    if not correction_check.get("exact_diff_complete"):
        raise ValueError("source correction exact diff is incomplete")
    if not correction_check.get("current_audit_regenerated"):
        raise ValueError("current source was not regenerated through the frozen audit")
    if not correction_check.get("deterministic_rerun_passed"):
        raise ValueError("current source deterministic rerun did not pass")
    if not correction_check.get("ready_for_publication"):
        raise ValueError("source correction check is not ready for publication")


def select_close_call_companion(
    weekly: Mapping[str, Any] | Any,
) -> dict[str, Any]:
    """Choose one clean close call and render explicitly non-directional wording."""

    clean = []
    for record in weekly_records(weekly):
        reasons = set(record["publication"].get("withholding_reasons", ()))
        if record["comparison"].get(
            "decision_v1_classification"
        ) == "close_call" and reasons == {"decision_v1_close_call"}:
            clean.append(record)
    if not clean:
        raise ValueError("no clean close-call companion is available")
    record = sorted(clean, key=_close_call_sort_key)[0]
    supported = sorted(
        (
            action
            for action in record["modeled_actions"]
            if action.get("expected_win_probability") is not None
        ),
        key=lambda action: (
            -float(action["expected_win_probability"]),
            str(action["action"]),
        ),
    )
    if len(supported) < 2:
        raise ValueError("close-call companion requires two supported actions")
    first, second = supported[:2]
    gap = abs(
        float(first["expected_win_probability"])
        - float(second["expected_win_probability"])
    )
    wording = (
        f"CoachIQ treated {decision_id(record)} as a close call, not a directional "
        f"claim. {_action_label(str(first['action'])).capitalize()} and "
        f"{_action_label(str(second['action']))} were separated by "
        f"{gap * 100:.1f} percentage points, and the frozen uncertainty rule did "
        "not establish a clear preference."
    )
    return {
        "decision_id": decision_id(record),
        "identity": record["identity"],
        "situation": record["situation"],
        "actions": (first, second),
        "modeled_gap": gap,
        "classification": "close_call",
        "publication_status": record["publication"]["status"],
        "wording": wording,
    }


def prohibited_language_violations(text: str) -> tuple[str, ...]:
    """Return stable codes for prohibited claims found in public-facing text."""

    return tuple(
        code for code, pattern in _PROHIBITED_PATTERNS.items() if pattern.search(text)
    )


def methodology_note() -> str:
    """Return the reusable, deliberately modest public methodology note."""

    return (
        "CoachIQ compares modeled fourth-down alternatives using historical NFL "
        "play-by-play, a frozen win-probability model, empirical action "
        "transitions, uncertainty estimates, and strict publication filters. "
        "Results are model estimates, not known counterfactual outcomes."
    )


def provenance_footer(source: Mapping[str, Any]) -> str:
    """Render compact human-visible frozen-version and source provenance."""

    return (
        "CoachIQ WP: `coachiq-wp-v1` · transitions: "
        "`coachiq-action-transition-v1` · decision: `coachiq-decision-v1` · "
        "publication: `coachiq-publication-v1` · source retrieved: "
        f"`{source['retrieved_at_utc']}` · Week 1 fingerprint: "
        f"`{source['sha256']}`"
    )


def build_publication_package(
    *,
    weekly: Mapping[str, Any] | Any,
    review_cards: Sequence[Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
    selected_decision_ids: Sequence[str],
    correction_check: Mapping[str, Any],
    generated_at_utc: str,
) -> dict[str, str]:
    """Build public artifacts only from fully approved, correction-safe inputs."""

    _validate_utc_timestamp(generated_at_utc, "generated_at_utc")
    validate_correction_check(correction_check)
    if not 8 <= len(review_cards) <= 12:
        raise ValueError("a publication package requires an 8-12 case review shortlist")
    if not 3 <= len(selected_decision_ids) <= 5:
        raise ValueError("a publication package requires 3-5 selected decisions")
    if len(set(selected_decision_ids)) != len(selected_decision_ids):
        raise ValueError("selected decision IDs must be unique")

    records = {decision_id(record): record for record in weekly_records(weekly)}
    card_ids = [str(card["decision_id"]) for card in review_cards]
    if len(set(card_ids)) != len(card_ids):
        raise ValueError("review-card decision IDs must be unique")
    reviews_by_id = {str(review["decision_id"]): review for review in reviews}
    if len(reviews_by_id) != len(reviews) or set(reviews_by_id) != set(card_ids):
        raise ValueError("every shortlisted case requires exactly one final review")
    for item_id in card_ids:
        if item_id not in records:
            raise ValueError(f"review card not found in weekly audit: {item_id}")
        validate_human_review(
            records[item_id], reviews_by_id[item_id], correction_check=correction_check
        )
    for item_id in selected_decision_ids:
        if item_id not in card_ids:
            raise ValueError(f"selected decision was not shortlisted: {item_id}")
        if reviews_by_id[item_id]["status"] != "approved":
            raise ValueError(f"selected decision is not human-approved: {item_id}")

    selected_cards = [
        next(card for card in review_cards if card["decision_id"] == item_id)
        for item_id in selected_decision_ids
    ]
    close_call = select_close_call_companion(weekly)
    source = _weekly_source(weekly)
    if source["sha256"] != correction_check.get("current_week_fingerprint"):
        raise ValueError("correction fingerprint does not match the weekly audit")

    report = _render_public_report(selected_cards, close_call, source)
    social = _render_social_drafts(selected_cards)
    visual_payload = [_visual_payload(card) for card in selected_cards]
    public_json_payload = {
        "title": "CoachIQ 2026 Week 1 Report",
        "generated_at_utc": generated_at_utc,
        "selected_decisions": selected_cards,
        "close_call_companion": close_call,
        "methodology_note": methodology_note(),
        "visual_data": visual_payload,
        "provenance": {**FROZEN_VERSIONS, "source": source},
    }
    public_json = _stable_json(public_json_payload)
    visual_json = _stable_json({"decisions": visual_payload})

    for name, content in {
        "week-01.md": report,
        "week-01.json": public_json,
        "social-drafts.md": social,
    }.items():
        violations = prohibited_language_violations(content)
        if violations:
            raise ValueError(
                f"prohibited public language in {name}: {', '.join(violations)}"
            )

    manifest = {
        "season": int(_weekly_payload(weekly)["season"]),
        "week": int(_weekly_payload(weekly)["week"]),
        "selected_decision_ids": list(selected_decision_ids),
        "editorial_results": [reviews_by_id[item_id] for item_id in card_ids],
        "reviewer_timestamps": {
            item_id: reviews_by_id[item_id]["reviewed_at_utc"] for item_id in card_ids
        },
        "source_fingerprint": source["sha256"],
        "source_retrieved_at_utc": source["retrieved_at_utc"],
        "report_sha256": _sha256(report),
        "json_sha256": _sha256(public_json),
        "visual_payload_sha256": _sha256(visual_json),
        "versions": FROZEN_VERSIONS,
        "correction_check_timestamp": correction_check["checked_at_utc"],
        "generated_at_utc": generated_at_utc,
        "externally_published": False,
    }
    return {
        "publication-manifest.json": _stable_json(manifest),
        "social-drafts.md": social,
        "visual-data.json": visual_json,
        "week-01.json": public_json,
        "week-01.md": report,
    }


def _append_choice(
    record: dict[str, Any],
    selected: list[dict[str, Any]],
    selected_ids: set[str],
    selected_games: set[str],
) -> None:
    selected.append(record)
    selected_ids.add(decision_id(record))
    selected_games.add(str(record["identity"]["game_id"]))


def _is_publication_safe(record: Mapping[str, Any]) -> bool:
    publication = record.get("publication", {})
    return (
        publication.get("status") == "publishable"
        and bool(publication.get("publishable"))
        and not publication.get("withholding_reasons")
        and bool(record.get("public_language"))
    )


def _validate_frozen_record(record: Mapping[str, Any]) -> None:
    if not _is_publication_safe(record):
        raise ValueError("review cards may contain only publication-v1-safe records")
    provenance = record.get("provenance", {})
    for field, expected in FROZEN_VERSIONS.items():
        if provenance.get(field) != expected:
            raise ValueError(f"frozen provenance mismatch: {field}")
    if provenance.get("training_through_season") != 2024:
        raise ValueError("publication record is not frozen at the 2024 boundary")


def _shortlist_sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    comparison = record["comparison"]
    return (
        -float(comparison.get("actual_action_modeled_gap") or 0.0),
        -float(comparison.get("minimum_preference_gap") or 0.0),
        -float(comparison.get("minimum_pairwise_superiority") or 0.0),
        str(record["identity"]["game_id"]),
        int(record["identity"]["play_id"]),
    )


def _close_call_sort_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    comparison = record["comparison"]
    return (
        -float(comparison.get("minimum_preference_gap") or 0.0),
        str(record["identity"]["game_id"]),
        int(record["identity"]["play_id"]),
    )


def _validate_utc_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")


def _action_label(action: str) -> str:
    return {
        "go": "going for it",
        "field_goal": "attempting a field goal",
        "punt": "punting",
    }[action]


def _weekly_payload(weekly: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    return weekly.to_dict() if hasattr(weekly, "to_dict") else weekly


def _weekly_source(weekly: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    return _weekly_payload(weekly)["provenance"]["source"]


def _render_public_report(
    cards: Sequence[Mapping[str, Any]],
    close_call: Mapping[str, Any],
    source: Mapping[str, Any],
) -> str:
    lines = [
        "# CoachIQ 2026 Week 1 Report",
        "",
        "A small human-reviewed set of fourth-down decisions from the first "
        "prospective week of the frozen CoachIQ v1 workflow.",
        "",
        "## Selected decisions",
        "",
    ]
    for card in cards:
        identity = card["identity"]
        lines.extend(
            (
                f"### {identity['away_team']} at {identity['home_team']} — "
                f"play {identity['play_id']}",
                "",
                str(card["neutral_public_language"]),
                "",
            )
        )
    lines.extend(
        (
            "## A close-call companion",
            "",
            str(close_call["wording"]),
            "",
            "## How to read CoachIQ",
            "",
            methodology_note(),
            "",
            "## Provenance",
            "",
            provenance_footer(source),
            "",
        )
    )
    return "\n".join(lines)


def _render_social_drafts(cards: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Internal social drafts — do not publish automatically", ""]
    for card in cards:
        item_id = card["decision_id"]
        language = card["neutral_public_language"]
        lines.extend(
            (
                f"## {item_id}",
                "",
                "### X / Twitter",
                "",
                f"{language} Model estimate, not a known counterfactual.",
                "",
                "### Reddit",
                "",
                f"{language} {methodology_note()}",
                "",
                "### LinkedIn (building-in-public angle)",
                "",
                "We completed a human-reviewed output from a frozen NFL "
                f"decision-analysis workflow. {language} The emphasis is on "
                "precommitted models, explicit uncertainty, and conservative "
                "publication gates.",
                "",
            )
        )
    return "\n".join(lines)


def _visual_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    identity = card["identity"]
    situation = card["situation"]
    comparison = card["coachiq_output"]["comparison"]
    modeled = {
        action["action"]: action for action in card["coachiq_output"]["modeled_actions"]
    }
    actual = str(card["factual_play"]["actual_action"])
    favored = str(comparison["model_preferred_supported_action"])
    return {
        "decision_id": card["decision_id"],
        "matchup": f"{identity['away_team']} at {identity['home_team']}",
        "quarter": situation["quarter"],
        "quarter_seconds_remaining": situation["quarter_seconds_remaining"],
        "possession_team_score": situation["possession_team_score"],
        "defense_team_score": situation["defense_team_score"],
        "yards_to_go": situation["yards_to_go"],
        "yards_to_goal": situation["yards_to_goal"],
        "actual_action": actual,
        "coachiq_favored_action": favored,
        "actual_action_ewp": modeled[actual]["expected_win_probability"],
        "favored_action_ewp": modeled[favored]["expected_win_probability"],
        "modeled_gap": comparison["claimed_comparison_gap"],
        "support_indicator": {
            action: {
                "status": values["support_status"],
                "observations": values["support_observations"],
                "games": values["support_games"],
            }
            for action, values in modeled.items()
            if values["available"]
        },
    }


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


__all__ = [
    "EDITORIAL_RESULTS",
    "FROZEN_VERSIONS",
    "HUMAN_REVIEW_CHECKS",
    "build_publication_package",
    "build_review_card",
    "decision_id",
    "deterministic_shortlist",
    "methodology_note",
    "pending_review_input",
    "prohibited_language_violations",
    "provenance_footer",
    "select_close_call_companion",
    "validate_correction_check",
    "validate_human_review",
    "weekly_records",
]
