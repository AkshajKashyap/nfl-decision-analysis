"""Prospective CoachIQ live-shadow operational safeguards."""

from coachiq.operations.shadow import (
    SHADOW_PROTOCOL_SHA256,
    CorrectionReport,
    EditorialReview,
    GameReadiness,
    ShadowOperationalReport,
    SourceManifest,
    apply_editorial_review,
    assess_game_readiness,
    build_shadow_brief,
    build_source_manifest,
    compare_source_manifests,
    finalize_operational_evidence,
    run_shadow_week,
    tactical_context_warnings,
    validate_live_shadow_request,
    validate_weekly_shadow_output,
)

__all__ = [
    "SHADOW_PROTOCOL_SHA256",
    "CorrectionReport",
    "EditorialReview",
    "GameReadiness",
    "ShadowOperationalReport",
    "SourceManifest",
    "apply_editorial_review",
    "assess_game_readiness",
    "build_shadow_brief",
    "build_source_manifest",
    "compare_source_manifests",
    "finalize_operational_evidence",
    "run_shadow_week",
    "tactical_context_warnings",
    "validate_live_shadow_request",
    "validate_weekly_shadow_output",
]
