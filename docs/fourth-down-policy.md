# Fourth-down reconstruction policy

Status: implemented in Milestone 2

Policy scope: observed decisions only

Development data: 2024 and earlier

This policy reconstructs what a team did on fourth down and the factual state
that followed. It does not estimate an alternative action, action value,
optimal choice, or decision quality.

## Candidate and eligibility definition

The audit population begins with every normalized row whose pre-play `down` is
4. Those rows are called **candidate audit rows** even when no coaching action
occurred. Keeping the full population makes exclusions and coverage measurable.
The stable identity remains `(game_id, play_id)`.

A row is `eligible` when all of the following are true:

- the season is 2014 or later and `season_type` is `REG` or `POST`;
- the row is in regulation, quarter 1 through 4;
- it is not deleted, a no-play, a kneel, a spike, or an administrative row;
- possession, opponent, down-and-distance, field position, clock, score
  differential, and both teams' timeout perspectives are present; and
- structured fields classify the selected action as `go`, `punt`, or
  `field_goal`.

Odd-looking late-game plays are not excluded just because the situation is
desperate or the upstream win probability is extreme. Milestone 2 adds no
subjective clock, score, or win-probability threshold.

Three deterministic Milestone 0 reporting tags accompany the audit:
`is_late_half` means at most 120 seconds remain in the second or fourth
quarter; nullable `is_extreme_wp` reports whether the upstream benchmark WP is
below 0.01 or above 0.99; and `is_endgame_transition_uncertain` marks an
`unavailable` or `ambiguous` next state. These are diagnostics, not eligibility
rules, and the WP tag is not used to classify action or outcome.

Every non-eligible candidate has one primary `disposition_reason`. The
precedence is deterministic:

1. `season_out_of_scope`
2. `game_type_out_of_scope`
3. `deleted_play`
4. `overtime_out_of_scope`
5. `penalty_no_play`
6. `clock_kill`
7. `spike`
8. `missing_state`
9. `administrative_row`
10. `aborted_play`
11. `unsupported_action`
12. `ambiguous_action`

Reasons 10 through 12 receive disposition `review`; the preceding reasons
receive `excluded`. A candidate with no reason is `eligible`. `review` means
the row remains visible but structured data does not support one of the three
ordinary action labels.

## Actual action classification

`actual_action` describes the selected action, independently of success:

1. `nfl_play_type == "FIELD_GOAL"` or `is_field_goal_attempt` gives
   `field_goal`.
2. `nfl_play_type == "PUNT"` or `is_punt_attempt` gives `punt`.
3. A non-aborted scrimmage rush, pass, sack, interception, or offensive fumble
   gives `go`. The normalized run/pass indicators are accepted alongside the
   NFL play type, covering scrambles and sneaks.
4. A fake recorded by nflverse as a scrimmage rush or pass, without a kick
   attempt flag, is therefore `go`.
5. Everything else is `unknown`.

Kick indicators deliberately have precedence over rush/pass artifacts. An
aborted snap is `unknown` unless structured kick fields still establish punt
or field-goal action. Kneels, spikes, no-plays, and deleted rows are also
`unknown`; no ordinary action occurred that this milestone can defend.

Descriptions are displayed for audit but never parsed to manufacture an
action. In particular, a phrase such as “Punt formation” is not enough to turn
an unstructured safety or aborted snap into `punt`.

The Milestone 1 normalized schema already contains the necessary evidence.
Sacks are explicit in `nfl_play_type`; scrambles, sneaks, and scrimmage-recorded
fakes share the same `go` result and are covered by existing rush/pass fields.
No ingestion columns were added for hypothetical distinctions that do not
change this policy.

## Factual outcomes

`factual_outcome` records what happened, separately from `actual_action`:

- go results: `converted`, `converted_by_penalty`, `failed`, `touchdown`,
  `return_touchdown`, `interception`, `fumble_lost`, or `down_replayed`;
- field-goal results: `field_goal_made`, `field_goal_missed`, or
  `field_goal_blocked`;
- punt results: `punted` or `punt_blocked`;
- unusual or non-decision results: `safety`, `no_play`, `clock_kill`, or
  `unknown`.

Scoring and possession-changing outcomes take precedence over generic
conversion/failure flags. `converted_by_penalty` is used when nflverse's
structured first-down-by-penalty flag accompanies a classifiable go snap. The
taxonomy is intentionally factual and coarse; later transition models may
represent yardage and return distributions without changing these labels.

## Penalties and repeated downs

- A `play_type == "no_play"` row is excluded as `penalty_no_play` and its
  action is `unknown`, even if the description reveals a formation or an
  apparent play. No action is inferred from alignment.
- A classifiable live-ball snap remains eligible. A structured defensive
  first down is `converted_by_penalty`; an official replay of fourth down is
  `down_replayed`.
- Declined and offsetting penalties are not interpreted from description text.
  The classifier uses the official structured result and reconstructed next
  state supplied by nflverse.
- `next_is_repeated_fourth_down` marks a same-team fourth down in the next
  factual state. The later candidate carries `repeated_from_play_id`, linking
  the sequence explicitly. A no-play row is not a coaching decision, while the
  later valid fourth-down snap is a new opportunity. If a classifiable
  live-ball snap is ever replayed, both observed choices remain visible but
  linked; downstream statistical work must not pretend the linked snaps are
  independent samples.

## Factual next-state reconstruction

The factual next state is the first later row in the same game that contains a
complete pre-snap scrimmage state:

- possession and defense teams;
- down, distance, and yards to the opponent goal line;
- quarter, quarter clock, and game clock;
- possession-team score, defense-team score, and score differential; and
- home, away, possession-team, and defense-team timeout counts.

Chronology uses nflverse `order_sequence`, normalized as `play_sequence`, with
`play_id` as a deterministic fallback and tie-breaker. `play_id` remains the
identity but is not assumed to be chronological: nflverse corrections can
leave corrected rows with a larger ID before a smaller-ID play.

This definition skips kickoffs, extra points, timeouts, end-period markers,
and other rows without a complete scrimmage state. A no-play row with a
complete pre-snap state is retained as a possible next state because it
faithfully describes the next fourth-down opportunity. Thus scoring plays
transition through the try and kickoff to the receiving team's first complete
scrimmage state.

The output preserves both the next possession's raw perspective and these
decision-team perspectives:

- `decision_team_score_differential_next`
- `decision_team_timeouts_remaining_next`
- `opponent_timeouts_remaining_next`

`next_state_status` has four values:

- `reconstructed`: a later complete, temporally consistent state exists;
- `terminal`: no later complete state exists, and the play was in the final
  120 seconds of regulation;
- `unavailable`: no later complete state exists and the narrow terminal rule
  is not satisfied; or
- `ambiguous`: a later complete row exists but its teams or clock conflict
  with the current game state. A regulation-to-overtime transition is
  intentionally ambiguous because the regulation game clock resets under a
  rules regime Milestone 2 does not represent.

No missing state is filled or estimated. Coverage diagnostics group
`reconstructed` and `terminal` as successful factual reconstruction while
printing the two components separately.

## End-game handling

Fourth-down kneels are excluded as `clock_kill`. Unsupported safety tactics
remain reviewable instead of being forced into `go` or `punt`. Other late-half
and desperation plays remain candidates under the same rules as any other
play. If their next state is missing or crosses into overtime, the decision row
is preserved with an explicit next-state status.

The broader Milestone 0 tags `must_score` and `clock_kill_available` are
intentionally not implemented here because their rule definitions remain
underspecified. They are not required to reconstruct the observed action and
must not become undocumented exclusion heuristics. The defined `extreme_wp`
benchmark tag is present but never filters a candidate.

## Known limitations

- The data cannot reliably identify formation intent for every fake or botched
  special-teams snap. Structured scrimmage plays become `go`; otherwise the
  action stays `unknown`.
- Intentional safety is not a supported fourth action. A safety with an
  ordinary structured sack may still be a factual `go` outcome; an
  `UNSPECIFIED` safety is held for review.
- Penalty enforcement is taken from nflverse's official resulting fields. The
  policy does not build a general declined/offsetting-penalty parser from prose.
- Terminal detection uses a deliberately narrow final-two-minutes rule. An
  earlier row with no later complete state is `unavailable`, not presumed to be
  the end of the game.
- A next state after a score includes the observed try and kickoff between the
  decision and the next scrimmage snap. This is the factual downstream state,
  not a claim that those intervening events were caused deterministically by
  the fourth-down action.
- Overtime candidates are audited and excluded from eligibility. Overtime
  transition semantics remain future work.

## Audit fixture and diagnostics

`tests/fixtures/fourth_down_cases.json` contains hand-labeled, minimally
transformed 2024 plays. It covers punts, field goals, go attempts, conversions,
failures, a defensive first-down penalty, a false start and repeated fourth
down, a touchdown, an interception, an end-game kneel, an aborted snap, and an
unsupported safety tactic. Tests require no network access.

Run the pre-holdout audit with:

```bash
.venv/bin/python scripts/audit_fourth_downs.py 2024 --summary-only
.venv/bin/python scripts/audit_fourth_downs.py 2024 --sample-only --sample-size 20
```

The script rejects 2025 and later seasons before loading data. Its manual
sample is selected by SHA-256 of `(game_id, play_id)`, so the same source asset
always produces the same sample regardless of input row order.
