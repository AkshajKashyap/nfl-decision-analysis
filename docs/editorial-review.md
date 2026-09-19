# CoachIQ editorial review workflow

Status: operational workflow around the unchanged `coachiq-publication-v1`
policy. It is not a model or publication-policy revision.

## Safety boundary

The machine publication policy runs before editorial review. Only records whose
machine status is `publishable`, whose withholding-reason list is empty, and
whose frozen provenance is complete may enter a directional review queue.
Human review may reduce that queue. It may never promote a withheld record.

The four final human results are:

- `approved`: all 15 checklist items passed and the case may be considered for
  a publication package;
- `hold_for_context`: the record is mechanically safe, but a simple public
  treatment would omit important football context;
- `reject_data_issue`: a factual or source-data problem prevents use; and
- `reject_model_form_risk`: the reviewer identifies a structural risk not
  adequately communicated by the proposed case.

`pending_review` is a queue state, not a final human result. Final results must
name a reviewer, declare `reviewer_type: human`, include a UTC timestamp, and
retain the complete checklist. Automation must not assign `approved`.

## Reviewer checklist

For every shortlisted record, verify all of the following against the cited
source row and the full technical review card:

1. source game state;
2. possession;
3. score;
4. quarter and clock;
5. down and distance;
6. field-position orientation;
7. actual-action classification;
8. factual outcome;
9. tactical context;
10. fake plays or unusual formations;
11. field and clock clipping against publication-v1;
12. zero overtime-boundary mass;
13. complete, non-sparse support;
14. pairwise evidence; and
15. neutral, model-based wording.

Automated source checks in a review card are aids, not substitutes for these
human judgments.

## Correction check

A fresh source snapshot must be fingerprinted immediately before review use.
When a fingerprint changes, preserve both identities, locate the changed
games and rows, rerun affected games through the frozen stack, identify every
affected decision, and state whether publication status or values changed.
Approval use is fail-closed until the exact diff, regeneration, and a
deterministic duplicate run all pass. A current rerun alone does not prove what
changed in a prior snapshot.

For the Week 1 package only, the documented archival failure is handled by
quarantining every decision from the changed game. The original ten-case
shortlist is formed first and then filtered; removed cases are not replaced.
Only games whose retained Milestone 9 and correction-run fingerprints match
may continue to human review. The inability to recover an old row-level
snapshot is an archival limitation, not a scientific-model failure and not
permission to waive correction evidence for the changed game.

## Shortlist and final selection

The default shortlist contains ten publication-v1-safe cases. It round-robins
existing actual/favored action combinations, prefers one case per game before
repeating a game, and uses only frozen gap, pairwise evidence, and stable IDs
for ordering. This creates editorial variety without a learned ranking or a
scientific-status change.

The first public package contains three to five human-approved cases. Selection
should favor factual cleanliness, complete support, understandable context,
and action/game-state variety. The largest gap is not automatically the best
editorial case.

## Public claims

Use model-qualified phrases such as “CoachIQ favored,” “the model estimated,”
“modeled advantage,” and “under CoachIQ v1.” Results are estimates, not known
counterfactual outcomes. Do not describe a coach or decision with claims such
as “mistake,” “wrong,” “objectively,” “optimal,” “cost them,” “terrible call,”
“worst coach,” or “expected wins lost.” The deterministic phrase guard must
pass the report and all social drafts.

Explain the method once per package: CoachIQ uses historical NFL play-by-play,
a frozen win-probability model, empirical action transitions, uncertainty,
and conservative publication filters. Do not imply causal identification.

## Close-call companion

One clean `withhold_close_call` may accompany a package as an educational,
explicitly non-directional example. It must remain labeled `close_call`, state
that the uncertainty rule did not establish a clear preference, and must not
be counted among approved directional cases.

## Provenance and manifest

The human-facing footer identifies the four frozen versions, source retrieval
timestamp, and Week 1 fingerprint. The machine manifest additionally records
the ordered selected IDs, every final review and timestamp, source fingerprint,
report/JSON/visual hashes, correction-check timestamp, generation timestamp,
and `externally_published: false`.

Package generation requires identical explicit review inputs and timestamps.
Two executions must produce byte-identical markdown, JSON, wording, ordering,
provenance, social drafts, visual payload, and manifest. The workflow writes
files only; it has no publication or distribution capability.

The review queue is prepared with `scripts/prepare_weekly_publication.py` from
an explicit weekly report, operational summary, source manifest, artifact-hash
index, PBP snapshot, and correction check. Public-output arguments are optional
as a group. Omitting them creates only internal review artifacts; supplying an
incomplete correction check or a non-approved selected case fails without
writing a public package.
