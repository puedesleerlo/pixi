# Demo runbook (3 minutes) — v4 relay

**Bring:** a phone on cellular with the join URL as a QR (the lobby renders it); one teammate as
Maker with the intent pre-written; the Playground deck already holds the two seeded verdict cards
and 40 seeded edits (all drawn muted and labelled synthetic).

**Before judging:** run `./dev.sh` (or the deployed pair), open `/decks/PLAY/grammar` on the big
screen, and run at least one real relay at lunch so the replay has real material.

| t | Beat | Where |
|---|---|---|
| 0:00 | "Same disagreement, opposite verdicts — the usual comprehension test can't tell you which card is broken." | `/decks/PLAY` → the two planted cards (`planted: polysemous` / `noisy` in the health payload) |
| 0:15 | QR up. Judges join as Readers; teammate is Maker. "Sixty seconds, eight taps. Tell us what you got, not what we meant." | `/` → `/r/CODE` lobby → **Start the relay** |
| 0:30 | While they tap: two channels, one a real psychometric instrument (Osgood 1957); no LLM judges anything — the number is a distance you can recompute. | Compose → Read |
| 1:20 | Reveal: dots against the star; gap bars. "The room missed on *certain*." Maker score from reports. | Reveal v0 → **Pass the card to the editor** |
| 1:30 | One judge is the Editor: one change (swap the crown for the wheel), bet which axis moves, one line of rationale. | Edit (45 s) |
| 1:50 | Re-read with ghost markers. | Read v1 (45 s) |
| 2:30 | Reveal: an arrow per Reader, bet hit or missed, ΔF, the edited symbol's coefficient moves. "You just ran an experiment on a symbol." Landing if F ≥ 0.80. | Reveal v1 |
| 2:45 | Deck home: the chain (edit · bet · rationale · measured shift). Grammar with the drift filter. "A deck for wayfinding icons is a deck with a different library." | `/decks/PLAY`, `/grammar` |
| 3:00 | Done. Wifi dies → host presses **Replay a finished card**: the last real relay replays version by version, readings arriving over ten seconds. | Reveal → Replay |

**If the room has only 3 players** the Maker score needs 3 readers and will show "needs 3"; the
reveal, gaps, edit, bet and landing all still work. Four players (judges + Maker) is the target.

**Q&A one-liners** — see `docs/DECISIONS.md` for the reasoning behind each:
- *Isn't several editors a vote?* Nobody expresses a preference over outcomes; each editor changes
  the card they hold and predicts their own change; readers who never see the intent adjudicate.
- *The Maker approves editors — gatekeeping?* Who, not what. Approved edits land without review.
- *Same readers read twice — anchoring.* Within-subject design; ghost markers make it explicit;
  paired shifts are conservative; the pooled grammar measures naive readers, the paired estimator
  measures edits — both reported.
- *Three readings is thin.* Yes: the verdict needs ≥ 8 and is null-calibrated so small-N clustering
  cannot fake polysemy; seeds are flagged and drawn muted; real lunch relays sit beside them.
- *Why one edit per turn?* Attribution: one change with paired readers is a controlled experiment,
  and it lets the grammar separate symbols that always co-occur on real cards.
