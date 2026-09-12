# PIXIE — Platform Specification (v5)

**Communities build decks together. Every deck has its own symbols, its own style, and its
own evidence of what its cards actually communicate.**

Status: complete specification for an agent-built platform. Supersedes v1–v4.
Working name: PIXIE (after Pamela Colman Smith's nickname). UI copy in English and Spanish.

---

## 0. Read me first

**What this document is.** A full product and engineering specification: objects, roles,
every menu and screen, every flow, the image pipeline, the coherence system, the
measurement engine, the base-deck catalog, the API, and a build plan in vertical slices
with acceptance tests. It is written to be handed to coding agents (Claude Code / Cursor)
section by section, and to be read by humans who want to know what the product does.

**What changed from v4.** v4 was a 19-hour hackathon cut. v5 is the platform:
a first-class **Deck** object with structure, style guide and symbol registry; **card creation
with an image model**; **one-operation edits with high fidelity to the original image**;
**deck-level symbols**; a **coherence system** across cards; **multi-user decks**, **forks**
with lineage and upstream proposals; a **catalog of ten base decks**; roles with a
permission matrix and menus defined per role; a full API. The measurement core is intact.

**How to hand it to an agent.** Build in the order of §13. Each slice names its acceptance
tests; a slice is done when they pass and the slice is demoable. Sections §3–§12 are the
source of truth for names, fields, states and rules — agents must use these names verbatim.

---

## 1. The product in one page

**PIXIE is a place where a group of people build a tarot-style deck together and find out
whether it works.**

1. **Start a deck** — from scratch, from one of the historical *base decks* (Smith 1909,
   Marseille 1760, Sola Busca 1491…), or by *forking* someone else's deck.
2. **Give it a style and a vocabulary** — a style guide (references, palette, line) that
   every card follows, and a registry of *symbols* (crown, downward water, threshold…)
   that belong to the deck. Symbols are added at deck level, never invented inside a card.
3. **Create cards** with an image model — from a prompt, from a reference card, or by
   reinterpreting a whole base deck in the deck's style. Each card's maker writes a private
   *intent*: what the card is supposed to communicate.
4. **Edit cards one change at a time** — add a symbol, remove one, replace one — and the
   model returns the same card with just that change. Every edit records who made it,
   why, and what they bet it would do.
5. **Play** — live sessions where readers who never saw the intent report what they
   received; the deck learns which symbols carry which meanings, and every card gets a
   verdict: *legible*, *polysemous* (reads in several coherent ways) or *noisy*.
6. **Keep it coherent and share it** — a coherence dashboard shows style outliers, symbols
   that mean different things on different cards, empty positions, cards that need
   readings. Publish the deck, let others fork it, accept their proposals upstream.

**Why it is different.** Every other tool lets you draw cards or vote on meanings. PIXIE
measures transmission: a maker encodes, a reader decodes, the distance is computed by a
metric anyone can recompute, and the deck's symbol grammar is the accumulated evidence.
Nobody votes; makers only control their own cards; readers are never scored; no language
model decides whether a reading is right.

**Glossary.**
- **Base deck** — a public-domain historical deck in the catalog; read-only; used to start decks.
- **Deck** — a community's deck: members, style guide, symbols, cards, sessions, grammar, forks.
- **Structure** — the set of positions a deck has (78 tarot positions, 22 majors, 36 Lenormand, or free).
- **Symbol** — a deck-level vocabulary entry with a declared meaning and a measured one.
- **Card** — a position in a deck filled by a maker with an intent and a chain of versions.
- **Version** — one image of a card plus how it was made (generation or a single edit).
- **Edit** — one symbol operation on a version, rendered by the image model with high fidelity.
- **Intent** — what the maker meant the card to communicate; private to encoders.
- **Reading** — what a reader received, on two channels (text and eight semantic scales).
- **Session** — a live multiplayer game in a deck: reading rounds and relays.
- **Grammar** — the deck's measured symbol → meaning table, with confidence.
- **Coherence** — how well the deck holds together: style, meaning, structure, transmission.
- **Fork** — a copy of a deck with lineage; can propose changes upstream.

---

## 2. Users, roles, permissions

### 2.1 Account types
- **Guest** — no account; identified by a signed cookie token; may read cards and join sessions
  as a reader; may be upgraded to an account keeping their readings.
- **User** — account (email magic link or Google via Auth0); owns decks, holds deck roles.
- **Admin** — platform operator: base-deck ingestion, moderation, quotas, provider keys.

### 2.2 Deck roles (per deck)
- **Owner** — one per deck; everything below plus members, roles, visibility, fork policy,
  transfer, delete.
- **Curator** — manages symbols (add, approve proposals, merge, retire), style guide,
  structure, sessions, upstream proposals, batch reinterpretation; can create and archive
  cards; can open branches.
- **Member** — creates cards (if settings allow), proposes symbols, edits cards where
  approved, plays as maker/editor, reads.
- **Reader** — any signed-in non-member on a public/unlisted deck: reads, plays as reader.

### 2.3 Card roles (per card, inside a deck)
- **Maker** — the card's creator: sets the intent, sets `approved_editors`, answers edit
  requests, may archive their own card. **Cannot veto edits by approved editors.**
- **Editor** — approved on that card: may perform edits (one operation per version).

### 2.4 Permission matrix

| Action | Guest | Reader | Member | Curator | Owner | Admin |
|---|---|---|---|---|---|---|
| View public deck, cards, grammar | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| View unlisted deck (with link) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| View private deck | – | – | ✓ | ✓ | ✓ | ✓ |
| Read a card (submit a reading) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Join session as reader | ✓* | ✓ | ✓ | ✓ | ✓ | ✓ |
| Join session as maker/editor | – | – | ✓ | ✓ | ✓ | – |
| Host a session | – | – | ✓ | ✓ | ✓ | – |
| Create card | – | – | ✓† | ✓ | ✓ | – |
| Edit card | – | – | if approved | if approved‡ | if approved‡ | – |
| Set intent / approved editors on own card | – | – | Maker | Maker | Maker | – |
| Propose symbol | – | – | ✓ | ✓ | ✓ | – |
| Add / approve / merge / retire symbol | – | – | – | ✓ | ✓ | – |
| Edit style guide, structure | – | – | – | ✓ | ✓ | – |
| Batch reinterpret base deck | – | – | – | ✓ | ✓ | – |
| Open branches on a card | – | – | – | ✓ | ✓ | – |
| Accept upstream proposals | – | – | – | ✓ | ✓ | – |
| Manage members and roles | – | – | – | – | ✓ | – |
| Visibility, fork policy, quotas, delete | – | – | – | – | ✓ | – |
| Fork deck | – | ✓§ | ✓§ | ✓ | ✓ | – |
| Ingest base deck, moderate, set provider keys | – | – | – | – | – | ✓ |

\* if `allow_guest_readers`. † if `who_can_create_cards = members`. ‡ curators/owners are
not implicitly approved editors; a maker's list governs their card unless the deck policy is
`any_member` or `curators`. § if `allow_forks` and the deck is visible to them.

**Rules that never change:** nobody approves or vetoes readings; makers approve editors,
never edits; symbol proposals are curated by role, never voted; readers are never scored.

---

## 3. Domain model

All collections carry `_id`, `created_at`, `updated_at`. `deck_id` is on every deck-scoped
record. Images are immutable per version and live in object storage; records hold URLs.

### 3.1 User
```
User        _id, email?, name, avatar_url?, auth0_sub?, guest_token?, locale: "en"|"es",
            created_at, upgraded_from_guest_at?
```

### 3.2 BaseDeck (catalog, read-only)
```
BaseDeck    _id, slug, name, tradition, year, origin, rights_note, source_urls[],
            structure_template_id, card_count, status: "ready"|"partial"|"planned"
            symbol_registry_id            # curated registry extracted from this deck
            attestation_sources[]         # e.g. Waite 1911 Pictorial Key
BaseCard    _id, base_deck_id, position_key, title, image_url, thumb_url, caption,
            attested_meaning_text?, attested_axes?: float[8]
```

### 3.3 Deck
```
Deck        _id, slug, name, description, cover_url?
            owner_id, visibility: "private"|"unlisted"|"public"
            structure_template_id                       # see 3.4
            style_guide: StyleGuide                     # see 3.5
            origin: {kind: "blank"|"base"|"fork", base_deck_id?, forked_from_deck_id?,
                     forked_at_version_snapshot_id?}
            settings: {
              who_can_create_cards: "members"|"curators",
              default_editor_policy: "any_member"|"curators"|"maker_list",
              allow_branches: bool, allow_forks: bool, allow_guest_readers: bool,
              ready_threshold: 3, max_edits_per_card: 6,
              candidates_per_generation: 2, fidelity_threshold: 0.85, style_threshold: 0.70,
              generation_quota_month: 200, live_generation_in_sessions: bool
            }
            stats: {cards, filled_positions, symbols, readings, sessions, forks,
                    coherence_index, mean_fidelity}
            lineage: {ancestors[], children[]}         # denormalized for display
Membership  _id, deck_id, user_id, role: "owner"|"curator"|"member", invited_by?, joined_at
Invitation  _id, deck_id, email?|link_token, role, expires_at, accepted_at?
```

### 3.4 StructureTemplate
```
StructureTemplate  _id, key: "tarot78"|"majors22"|"minors56"|"lenormand36"|"mantegna50"|
                   "free", name, positions[] {key, title, group, order}
```
A `free` deck has no fixed positions; cards get generated keys `free-0001…`.

### 3.5 StyleGuide (part of Deck)
```
StyleGuide  prompt_prefix: string           # "black ink line art on cream paper, single figure…"
            negative_prompt?: string
            palette[]: hex, line: "ink"|"woodcut"|"painted"|"flat"|"photo"|"custom"
            reference_images[] {url, source: "base_card"|"upload"|"generated", weight}
            border: {style, color}, aspect: "2.75x4.75"|"1x1.7"|"custom"
            style_centroid_embedding?: float[768]   # recomputed when references or approved cards change
```

### 3.6 Symbol (deck-level registry)
```
Symbol      _id, deck_id, key, name, gloss, tags[]
            declared_axes: float[8], declared_text
            exemplar: {image_url, origin: "base_crop"|"generated"|"upload", source_ref?}
            placement: "any"|"center"|"top"|"bottom"|"left"|"right"
            origin: "inherited_base"|"inherited_fork"|"community"|"upstream"
            inherited_from?: {base_deck_id?, deck_id?, symbol_id}
            attestations[] {source, note}
            prior_axes?: float[8], prior_source?: "attestation"|"parent_grammar"|null
            status: "active"|"proposed"|"merged"|"retired", merged_into_symbol_id?
            proposed_by?, approved_by?, approved_at?
            measured: {coef: float[8], ci_low, ci_high, n_cards, n_readings, n_edits,
                       coherence: "consistent"|"contested"|"untested",
                       declared_vs_measured: float}   # cosine
SymbolProposal  _id, deck_id, symbol_draft (as above), note <= 280, status: "open"|"approved"|"declined", decided_by?, decision_note?
```

### 3.7 Card, Version, Edit
```
Card        _id, deck_id, position_key, title?, maker_id
            intent: {statement <= 140, axes: float[8]}          # visible to encoders only
            approved_editors: "*"|[user_id]                      # resolved against deck policy
            edit_requests[] {user_id, note <= 140, status: "open"|"approved"|"declined"}
            status: "draft"|"reading"|"open"|"landed"|"closed"|"archived"
            current_version_id, branches[] {branch_key, head_version_id}
            tags[], share_token
Version     _id, card_id, deck_id, v, branch_key: "main"|string, base_version_id?
            image_url, thumb_url, width, height
            symbols_declared[] {symbol_id, placement?}
            symbols_detected[] {symbol_id, salience 0..1, bbox?, tagged_by: "vision"|"human"}
            how: Generation | Edit
            checks: {fidelity?: float, containment?: float, style_score: float,
                     symbols_missing[] , safety: "ok"|"blocked"}
            created_by, created_at
Generation  {mode: "prompt"|"reference"|"reinterpret"|"upload"|"variation",
             reference_image_url?, prompt_user, prompt_full, provider, model, seed?,
             candidates[] {image_url, style_score}, chosen_index}
Edit        {op: "add"|"remove"|"replace"|"emphasize"|"deemphasize"|"reposition"|"cosmetic",
             symbol_id?, to_symbol_id?, region?: {x,y,w,h},
             prompt_user?, prompt_full, provider, model, seed?,
             candidates[] {image_url, fidelity, containment, style_score}, chosen_index,
             bet_axis?: 0..7, rationale <= 140, editor_id,
             counts_as_experiment: bool}          # false for "cosmetic"
```

### 3.8 Reading, TransmissionEvent, EditEffect, Verdict, Grammar
```
Reading            _id, deck_id, card_id, version_id, reader_id (user or guest), session_id?, round_id?
                   free_text?, axes: float[8], embedding?: float[384], latency_ms,
                   synthetic: bool, created_at
TransmissionEvent  version_id, reading_id, d_axes, d_embed?, d_total, inside_radius
EditEffect         version_id, n_pairs, shift: float[8], gap_before, gap_after, bet_hit?, delta_fidelity
Verdict            version_id, n, V, S, S_null95, k, verdict: "legible"|"polysemous"|"noisy"|"collecting",
                   clusters[] {label, centroid, n}
Grammar            deck_id, symbol_id, coef, ci_low, ci_high, n_readings, n_edits,
                   prior_axes?, drift_from_prior?: float, computed_at
```

### 3.9 Session, Round
```
Session     _id, deck_id, code (4 letters), host_id, mode: "reading"|"relay"
            settings: {read_timer: 60, edit_timer: 45, generation_timer: 40,
                       live_generation: bool, guests_allowed: bool, max_edits: 3}
            players[] {user_or_guest_id, nickname, role: "host"|"player"|"reader", connected}
            state: "lobby"|"compose"|"read"|"reveal"|"edit"|"generating"|"summary"|"ended"
            round_ends_at?, current_card_id?, current_version_id?, turn_order[], turn_index
Round       _id, session_id, kind: "read"|"edit", card_id, version_id, maker_or_editor_id,
            started_at, ended_at, readings[], effect?: EditEffect, scores[] {user_id, points, reason}
```

### 3.10 Forks and upstream
```
ForkSnapshot      _id, source_deck_id, target_deck_id, taken_at,
                  copied: {symbols: n, cards: n, style: true, structure: true}
UpstreamProposal  _id, from_deck_id, to_deck_id, kind: "version"|"symbol",
                  version_id?|symbol_id?, note <= 280, status: "open"|"accepted"|"declined",
                  decided_by?, decision_note?, result_ref?
```

### 3.11 Jobs, Notifications, Activity
```
Job           _id, kind: "generate"|"edit"|"tag"|"fidelity"|"grammar"|"reinterpret_batch"|
              "ingest_base"|"export", deck_id?, payload, status: "queued"|"running"|"done"|"failed",
              progress 0..1, result?, error?, attempts, created_by
Notification  _id, user_id, kind, deck_id?, card_id?, text, read_at?
Activity      _id, deck_id, actor_id, kind, refs{}, created_at     # the deck's feed
```

### 3.12 Card status machine
```
draft ──(v0 image chosen)──► reading ──(≥ ready_threshold readings on head)──► open
open ──(edit accepted)──► reading            open/reading ──(F ≥ 0.80)──► landed
reading/open ──(edits = max_edits)──► closed   any ──(maker/curator)──► archived
```

---

## 4. Navigation and menus — by role

### 4.1 Global navigation (top bar)
`Home · Explore · My Decks · Play (join by code) · Notifications · Profile`
Guests see `Home · Explore · Play · Sign in`.

### 4.2 Home — the dashboard (the general desktop to join)
- **Join a session**: code field + QR scanner button (mobile) — prominent.
- **Your decks** (owner/curator/member) with status chips: cards, empty positions, needs
  readings, open proposals.
- **Cards waiting for you**: to read (from decks you follow), open for your edit, requests
  to your cards.
- **Activity**: recent edits, landings, forks, proposals across your decks.
- **Start**: *New deck* · *Fork a deck* · *Browse base decks*.

### 4.3 Explore
- **Base decks** catalog: cards, tradition, year, rights, "Start a deck from this".
- **Public decks**: sort by coherence index, cards, forks, recent; filters by structure and
  tradition; each shows lineage badge (fork of …) and "Fork" button.
- **Search** across decks, cards, symbols.

### 4.4 Deck workspace — left navigation (items shown per role)

| Item | Guest/Reader | Member | Curator | Owner |
|---|---|---|---|---|
| Overview | ✓ | ✓ | ✓ | ✓ |
| Cards | view | view · **New card** | + archive, branches, **Reinterpret base deck** | ✓ |
| Symbols | view | view · **Propose** | + **Add**, **Proposals inbox**, **Import from base**, merge, retire | ✓ |
| Play | join | + **Host session**, reading queue | + session settings defaults | ✓ |
| Grammar & Coherence | ✓ | ✓ | ✓ | ✓ |
| History & Forks | ✓ | ✓ | + **Upstream inbox** | ✓ |
| Members | view | view | invite | roles, remove |
| Settings | – | – | style guide, structure | all |

**Overview** — description, lineage strip (ancestors → this deck → forks), stats, coherence
index, transmission summary, activity feed, "Share" (link, embed, QR).

**Cards** — grid laid out by structure (groups and positions; empty positions render as
"+ create"); filters: needs readings · open for edit · landed · closed · contested · off-style ·
mine. Card tile: thumbnail, position, verdict chip, fidelity, editors count, branch icon.

**Symbols** — table: exemplar, name, gloss, declared meaning (8 mini-bars), measured
meaning (8 mini-bars with CI), cards using it, coherence status, origin, prior source.
Row → Symbol detail. Buttons by role (above).

**Play** — sessions (live, scheduled, past) with join; "Host session" (Member+); the deck's
**reading queue** link and QR; async stats (readings this week).

**Grammar & Coherence** — tabs: *Grammar* (symbol × axis matrix with CI bands, filters
"drifting from prior", "contested", "untested"; synthetic toggle) · *Coherence* (§7 dashboard)
· *Transmission* (fidelity per card, verdict distribution, bandwidth curve).

**History & Forks** — versions feed across cards (who, op, bet, shift), sessions log,
lineage tree, forks list, upstream proposals (inbox for curators; outbox on forks).

**Members** — list with roles, invite by email or link, pending invitations.

**Settings** — General (name, description, cover, visibility) · Structure · Style guide ·
Permissions (`who_can_create_cards`, `default_editor_policy`, `allow_branches`,
`allow_forks`, `allow_guest_readers`) · Measurement (`ready_threshold`, `max_edits_per_card`,
`fidelity_threshold`, `style_threshold`) · Generation (`candidates_per_generation`, quota,
provider) · Export · Danger zone (transfer, delete).

### 4.5 Card Studio (per card) — tabs
`View · Generate · Edit · Versions · Readings · Access`
- **View** — current version large; symbols declared/detected with warnings; verdict; fidelity;
  intent (encoders only, blurred toggle for makers presenting to readers); chain summary;
  actions by role: *Read this card* (anyone), *Edit* (approved), *Request to edit* (member),
  *Archive* (maker/curator), *Share*.
- **Generate** — §5.4.
- **Edit** — §5.5. The **edit menu**.
- **Versions** — chain (main) and branches as a graph; compare two versions side by side
  with diff heatmap; restore (creates a new version with `how: Edit{op: "cosmetic"}` and a
  note); branch (curator).
- **Readings** — plot, gap bars, shift arrows per edit, list of readings (anonymized for
  non-curators), "collecting · N/threshold".
- **Access** (maker; curators view) — `approved_editors` control: policy inherited from deck
  or *maker's list*; edit requests inbox with notes; approve/decline person.

### 4.6 Session screens (mobile-first)
`Lobby · Reader · Maker · Editor · Generating · Reveal · Summary`
Lobby shows code + QR, players with roles, settings (mode, timers, live generation), Start.
Roles rotate per round; the host may reassign.

### 4.7 Profile
Account, locale, decks, contributions (cards made, edits, bets hit, readings given — private
by default), guest upgrade, sign out.

### 4.8 Admin console
Base decks (ingest from manifest, rights checklist, status) · Providers (keys, model IDs,
health) · Quotas · Moderation queue (reports on cards/symbols/decks) · Feature flags · Metrics.

---

## 5. Flows

### 5.1 Onboarding and joining
1. Landing → *Sign in* (magic link / Google) or *Continue as guest* (readers, session players).
2. First visit after sign-in: Home with three starts: *New deck*, *Fork a deck*, *Join a session*.
3. Join a session: code or QR → nickname → Lobby. Guests allowed if the session says so.
4. Guest → account upgrade keeps guest readings and session history.

### 5.2 Create a deck (wizard, 5 steps)
1. **Name & visibility.**
2. **Start from**: *Blank* · *Base deck* (pick from catalog) · *Fork* (pick a visible deck).
3. **Structure**: template (preselected from base deck), or `free`.
4. **Style guide**: choose a base deck's look (prefills `prompt_prefix`, `line`, references
   from its cards), or upload 1–5 references, or describe it. Preview: the system generates
   one test card (quota-free) so the style is visible before committing.
5. **Vocabulary**: *Import symbols from base deck* (checklist, prefilled with the curated
   registry) and/or *start empty*. Invite members (optional). → Deck created; Overview.

Starting from a base deck offers two card modes: **Inherit** (each position's v0 is the base
card image, provenance = base card) or **Reference only** (positions empty; base cards
available in Generate as references). Curators can later run **Reinterpret base deck** (§5.6).

### 5.3 Symbols — deck-level vocabulary
- **Add** (curator): name, gloss, tags, declared meaning (8 sliders + one line), placement,
  exemplar: *crop from a base card* (pick card, drag a rectangle), *generate* (prompt in deck
  style; single symbol, white background) or *upload*. Attestation notes optional. Saved
  `status: active`, `origin: community`.
- **Propose** (member): same form → `SymbolProposal`; curators' inbox; approve (creates the
  symbol, `proposed_by` kept) or decline with a note. Not a vote.
- **Import from base deck**: select from the base deck's curated registry; imported symbols
  carry `origin: inherited_base`, attestations and `prior_axes` from attestation.
- **Merge** (curator): symbol B into A — versions' declared/detected references are rewritten,
  B becomes `merged`; grammar recomputes. **Rename** keeps key. **Retire** hides from pickers,
  keeps history.
- Symbol detail: cards using it (with per-card measured effect and angle to the symbol's
  mean effect), declared vs measured, prior and drift, contested pairs, proposals history.

**Rule:** a card can only declare symbols that exist in its deck's registry. The Generate and
Edit menus offer *"This needs a symbol that isn't in the deck → propose it"* which opens the
proposal form and returns to the studio when approved.

### 5.4 Create a card — the Generate menu
Entry: Cards → empty position "+ create", or Cards → *New card* (free decks), or a
position's existing card → Generate tab (new branch or regenerate v0 if still `draft`).

Form:
1. **Position** (fixed if entered from a position) and optional title.
2. **Mode**:
   - *From prompt* — text; the deck `prompt_prefix` is shown locked above it.
   - *From reference* — pick a base card (catalog), a card from this deck or an upload; the
     model keeps composition and reinterprets in deck style (`strength` slider: 0.3–0.8).
   - *Variation* — of the current version (draft only).
   - *Upload* — own artwork with a rights attestation checkbox; no generation.
3. **Symbols** — multi-select from the registry, at least one; each adds its gloss to
   `prompt_full`; placement hints per symbol if set.
4. **Intent** (private) — statement ≤ 140 + 8 sliders. Required before the card leaves `draft`.
5. **Candidates** — 1–4 (deck default 2). *Generate* → job with progress; candidates appear
   with **style score** and **symbols detected** ticks; the maker picks one → v0; status
   `reading`. Rejected candidates are kept 7 days for regeneration seeds.
6. Checks: safety block → message and no charge; missing declared symbol → warning
   "not rendered visibly: crown" with *Regenerate* or *Keep and confirm presence* (human tag).

### 5.5 Edit a card — the Edit menu
Entry: Card Studio → Edit (approved editors; the card must be `open`, or `reading` if the
editor is a curator with `allow_branches`).

**Operation (choose exactly one):**
| Op | Inputs | Counts as experiment |
|---|---|---|
| Add symbol | symbol, placement or region rectangle | yes |
| Remove symbol | symbol (from detected/declared) | yes |
| Replace symbol | from → to, keep placement | yes |
| Emphasize / De-emphasize | symbol, ±1 step (size/contrast/centrality) | yes |
| Reposition | symbol, target region | yes |
| Cosmetic | free prompt (lighting, line cleanup, border) — no symbol change allowed | no |

Then: optional *how* text (style words only; the system rejects text that names a symbol
not selected), **rationale** ≤ 140 (required), **bet axis** (required for experiments; the
picker is preloaded with the three largest current gaps), candidates 1–4.

*Generate edit* → job → candidates with **fidelity**, **containment**, **style score**, and
symbol detection; the editor picks one (their own edit) → new version on the branch; card
returns to `reading`; readers are notified through the queue. Candidates below
`fidelity_threshold` are shown greyed with "changed more than requested" and a one-click
*Retry with stronger preservation*; the system already retried twice automatically (§6.4).

**Lock and turns (async):** an edit request must reference the head `version_id`; if it is
stale the server answers `409 version_stale` with the new head; the UI reloads the card.
Only one experiment per version on `main`; branches (curator) may fork from any version.

**Live edits in sessions:** same menu, reduced (Add / Remove / Replace), 1 candidate, timer
`generation_timer`; if generation exceeds it, the session continues with the previous
version and the edit lands asynchronously.

### 5.6 Reinterpret a base deck (batch, curator)
Pick base deck and positions (all or a group) → each position becomes a `reference` generation
with the deck's style, symbols auto-declared from the base registry mapping for that card,
intents left empty for makers to fill (cards stay `draft` until an intent exists; the batch
can assign makers). Quota check first; progress per card; failures are retried individually.
This is how a coherent 78-card deck exists in an afternoon.

### 5.7 Play — live sessions
**Reading round** (mode `reading`): host picks a card (or the deck's *needs readings* queue);
readers read (60 s, eight taps, optional phrase); reveal: dots vs star, gap bars, maker score
if the maker is present, verdict or "collecting"; next card.

**Relay** (mode `relay`): compose (choose an existing card; makers may quick-generate if
`live_generation`) → read → reveal → edit (one op; live generation if enabled) → read (ghost
markers, 45 s) → reveal (arrows, bet hit/miss, ΔF, grammar band narrows) → loop until landed
or `max_edits` → summary. Scoring per §8.3. Roles rotate; readers never score.

Presence via SSE; reconnect resumes; server timers; a phase advances when all submitted or
time is up. Session summary lists cards touched, shifts, bets, and grammar changes.

### 5.8 Read asynchronously — the reading queue
A deck's `/read` link (and QR) serves the version with the fewest human readings among cards
in `reading`, skipping versions the reader has already read. Guests allowed by setting. After
submitting, the reader sees the reveal for that version (never the intent text — only the
plot, since the intent star is shown only after `ready_threshold` readings exist).

### 5.9 Approvals and requests
- Deck policy sets the default (`any_member` / `curators` / `maker_list`); a maker may narrow
  or widen it on their card (`approved_editors`).
- Members request to edit with a note; the maker approves the **person**; the request thread
  is visible to the maker and the requester.
- Curators approve symbol proposals; owners set roles. Nothing is tallied anywhere.

### 5.10 Fork and upstream
- **Fork** (button on any deck you may see, if `allow_forks`): creates a deck with
  `origin.kind = fork`, copies structure, style guide, active symbols (`origin:
  inherited_fork`, `prior_axes` = parent's measured coefficients when `n_readings ≥ 20`,
  else parent's prior), and every card's head version as v0 with `base_version_id` pointing
  to the parent version. Readings and grammar are **not** copied; the fork's grammar starts
  from the inherited priors. A `ForkSnapshot` records what was copied. Lineage updates on
  both decks.
- **Sync from parent** (curator on the fork): cherry-pick new parent symbols or card
  versions since the snapshot.
- **Upstream proposal** (curator on the fork): send a version or a symbol to the parent with a
  note; parent curators accept (imported as a new branch version / new symbol with
  `origin: upstream`) or decline with a note.

### 5.11 Share and export
Public deck page and card pages (chain view) with Open Graph previews; share links with
`share_token` for unlisted decks; session invite links; embed snippet for a card chain;
export ZIP (images, `manifest.json`, `grammar.csv`, `readings.csv` anonymized); print sheet
PDF (2.75 × 4.75 in, 9 per page, crop marks).

### 5.12 Notifications
Card open for your edit · your edit landed / card landed · reading requested (queue digest) ·
edit request received / decided · proposal received / decided · fork created · upstream
proposal received / decided · session starting. In-app always; email digest optional.

---

## 6. Image pipeline

### 6.1 Providers (adapter interface)
```
ImageProvider.generate(prompt_full, style_refs[], aspect, n, seed?) -> images[]
ImageProvider.edit(image, prompt_full, mask?, style_refs[], preserve: "high"|"medium", n, seed?) -> images[]
ImageProvider.symbol(prompt_full, n) -> images[]      # single symbol, white background
```
- **Primary:** the Gemini image model (image + text → image; supports reference-preserving
  edits and multiple reference images). Model ID is configuration, verified at build time.
- **Alternate:** FLUX.1 Kontext (Black Forest Labs) for edits — built for in-context,
  reference-preserving edits; OpenAI image edits as third.
- Provider choice per deck (`settings.provider`) with platform default; every job records
  provider, model and seed.

### 6.2 Prompt assembly
```
prompt_full (generate) = style.prompt_prefix
                       + " Position: {position.title}."
                       + " Symbols: " + join(symbol.name + " — " + symbol.gloss + placement)
                       + " " + prompt_user
                       + " Single card, full bleed inside border, no text."
prompt_full (edit)     = "Edit the provided card. Change only: {op sentence}. "
                       + "Keep everything else identical: composition, figures, colors, line style, "
                       + "border, framing. Same size and aspect. " + (how text)
op sentences:  add → "add {symbol.name} ({gloss}) at {placement/region}"
               remove → "remove {symbol.name}; fill the area consistently with the surroundings"
               replace → "replace {from} with {to} in the same place and scale"
               emphasize → "make {symbol} more prominent (larger/more central/higher contrast) by one step"
               reposition → "move {symbol} to {region}, keep its appearance"
```
Trademarked deck names and living artists are stripped from `prompt_user` by a denylist;
the deck's `negative_prompt` is appended where the provider supports it.

### 6.3 Style references
Up to 3 references per call: the style guide's `reference_images` by weight, then the deck's
most on-style approved cards. `style_centroid_embedding` = mean image embedding of references
and landed cards; recomputed on change.

### 6.4 Fidelity for edits — measured, not judged
Computed on the worker for every edit candidate:
- `embed_cos` = cosine between image embeddings (DINOv2 or CLIP ViT-L/14, local) of base and
  candidate.
- `ssim_out` = SSIM between base and candidate **outside** the expected change region
  (region given by the op, else the symbol's placement zone, else the whole image → then
  `ssim_out` is SSIM over the whole image).
- `containment` = share of pixel-difference mass (blurred absolute diff) inside the expected
  region.
- `fidelity = 0.5 * clamp((embed_cos − 0.6) / 0.4) + 0.5 * ssim_out`, in 0..1.
- Threshold `fidelity_threshold` (default 0.85). Below it the worker retries automatically:
  retry 1 with `preserve: "high"` and an explicit mask from the region; retry 2 with a
  reduced-strength prompt ("smaller change"). Up to 2 retries; the best candidates are
  returned with their scores; those under threshold are greyed in the UI.
- A **diff heatmap** is stored per candidate and shown in Versions → Compare.
No language model rates fidelity; a judge can recompute these numbers.

### 6.5 Style score and symbol detection
- `style_score` = cosine to `style_centroid_embedding`; below `style_threshold` → "off-style"
  chip; curators can require regeneration for off-style cards.
- **Symbol detection**: vision tagger (Gemini) receives the image and the deck's registry
  (names + glosses) and returns `{symbol_id, present, salience 0..1, bbox}` as JSON.
  Reconciled with declared symbols: declared ∧ detected → salience from detector; declared ∧
  ¬detected → warning, salience 0.3 flagged `declared_only` until a human confirms; detected
  ∧ ¬declared → suggestion "also detected: tower — add to declared?". The measurement uses
  detected salience; the tagger never scores transmission.

### 6.6 Jobs, quotas, storage, safety
- Mongo-backed job queue, one worker process per provider; SSE `job.progress` to the UI;
  retries with backoff; idempotency key = hash(base_version, op, prompt_full, seed).
- Quotas: `generation_quota_month` per deck, per-user rate limit (10 jobs / 10 min),
  candidates ≤ 4. Cache hits are free.
- Storage: originals (PNG) + thumbnails (WebP) in S3-compatible object storage behind a CDN;
  signed URLs for private decks; images immutable per version.
- Safety: provider filters + platform policy (no real persons, no trademarked decks, no
  hateful or sexual content); blocked candidates are logged with the reason and not charged;
  report button on every card and symbol → moderation queue.
- Cost telemetry per deck (images, provider, estimated cost) visible to owners.

---

## 7. Coherence system

Coherence answers "does this deck hold together?" on four axes, on the Grammar & Coherence
page and as chips throughout.

1. **Style coherence** — distribution of `style_score` across current versions; outliers
   listed with *Regenerate to match style*; mean and spread on the Overview.
2. **Semantic coherence** — for each symbol with ≥ 2 tested cards (cards where it appears
   and the version has ≥ `ready_threshold` readings): per-card effect vectors (paired
   estimates where available, else pooled residual contribution); the symbol is
   **consistent** if every per-card effect is within 45° of the symbol's mean effect,
   **contested** otherwise, **untested** if < 2 cards. **Coherence index** = consistent /
   (consistent + contested). Contested symbols show both cards, their chains, and the angle.
   `declared_vs_measured` per symbol surfaces "meaning drift": the deck says a crown means
   *certain*, the readers say *compelled*.
3. **Structural coherence** — positions filled / total; duplicates; cards in `draft` without
   intent; cards `closed` without landing.
4. **Transmission** — mean fidelity across landed/closed cards; verdict distribution;
   cards needing readings; the bandwidth curve (fidelity vs number of detected symbols).

Coherence never edits anything by itself. It ranks work: the Cards filters (*contested*,
*off-style*, *needs readings*, *empty*) are its outputs.

---

## 8. Measurement engine

### 8.1 Two channels
**A — free text** ≤ 140 chars, embedded (MiniLM, 384-d). Required for intents, optional for
readings. **B — semantic differential** (Osgood, Suci & Tannenbaum 1957), eight 7-point
bipolar scales −3…+3: active↔passive · beginning↔ending · giving↔withholding ·
inward↔outward · gain↔loss · willing↔compelled · certain↔uncertain · singular↔collective.
Reader UI: eight rows of seven dots, no defaults, submit only when all set; ghost markers on
re-reads (must re-tap).

### 8.2 Distance, fidelity, gaps
```
d_axes  = ||a_intent - a_reading||_2 / (6*sqrt(8))
d_embed = (1 - cosine(e_intent, e_reading)) / 2           # if both texts exist
d_total = 0.6*d_axes + 0.4*d_embed  else d_axes
F_v     = 1 - mean(d_total) over human readings of version v
g_k     = intent_k - mean(reading_k)                       # per axis, shown as sorted bars
```
Weights are configurable at platform level; not tunable per deck.

### 8.3 Scoring (sessions only)
Maker of the card in a reading round: `r = 0.30`, `f` = share inside radius, N ≥ 3:
`0.25 ≤ f ≤ 0.75` → 3 (calibrated ambiguity), `f > 0.75` → 1, `f < 0.25` → 0.
Editor: paired shift on the bet axis `δ_k` over readers who read v−1 and v; hit if toward the
intent and `|δ_k| ≥ 0.5` → 2. Landing `F ≥ 0.80` → +1 to every encoder in the chain.
Readers never score. Points live in the session summary only.

### 8.4 Verdict (per version, N ≥ 8 human readings)
Axes only. `V` = mean pairwise distance / (2√8); `S` = max silhouette over k ∈ {2,3};
null = 200 isotropic draws at the same V; `S_null95`. `V < V_lo` → legible;
`V ≥ V_lo ∧ S > S_null95` → polysemous (k clusters named by K2, template fallback);
`V ≥ V_lo ∧ S ≤ S_null95` → noisy. `V_lo` = platform constant calibrated on seeds (0.30).
Below N = 8: `collecting`.

### 8.5 Grammar (per deck)
Pooled ridge of reading axes on detected salience of registry symbols (`alpha = 1.0`,
intercept, bootstrap 200 for 95% CIs), recomputed by job on every reading batch (debounced
5 s). **Edit-effect estimator**: each experiment edit yields a paired observation of
`±salience · W[symbol]`; reported as `n_edits` and mean paired effect beside the pooled
coefficient. **Priors**: `attestation` for symbols inherited from base decks, `parent_grammar`
for forks, none for community symbols; `drift_from_prior = 1 − cosine(coef, prior)`.
Cross-deck view: same `inherited_from.symbol_id` across decks, shown side by side.

### 8.6 Seeds and estimator tests
A synthetic deck ("Playground · synthetic") is generated at deploy: planted `W*` from the
Smith registry priors, 60 cards, 300 readings, 40 paired edits, one planted polysemous and
one planted noisy version with matched V. CI asserts `corr(vec(W), vec(W*)) > 0.8`, paired
estimates within CI, verdicts recovered. Synthetic data is flagged and drawn in a muted color.

### 8.7 What models may and may not do
May: embed text, tag symbols, name clusters and landed cards, draft attested priors for
catalog registries (human-reviewed), generate and edit images. May not: decide whether a
reading matches an intent, whether a bet hit, whether a card landed, or how faithful an
edit is. Those are computed.

---

## 9. Base-deck catalog and ingestion

| Base deck | Cards | Year | Rights | Source (ingestion) | Status at launch |
|---|---|---|---|---|---|
| Smith 1909 (Waite-Smith line art) | 78 | 1909 | Public domain (US, pre-1929) | Wikimedia Commons | ready |
| Tarot de Marseille — Conver | 78 | 1760 | Public domain | BnF Gallica / Wikimedia | ready |
| Tarot de Marseille — Noblet | 78 (some restored) | c. 1650 | Public domain | BnF Gallica | partial |
| Sola Busca | 78 | 1491 | Public domain | Wikimedia (Brera) | ready |
| Visconti-Sforza (Morgan–Bergamo) | 74 surviving | c. 1450 | Public domain | Morgan Library / Wikimedia | ready |
| Grand Etteilla | 78 | 1789 | Public domain | BnF Gallica / Wikimedia | ready |
| Tarocchi "del Mantegna" | 50 | c. 1465 | Public domain | Wikimedia | ready |
| Petit Lenormand (Game of Hope) | 36 | 1846 | Public domain | Wikimedia | ready |
| Minchiate Fiorentine | 97 | 18th c. | Public domain | Wikimedia / BnF | partial |
| AIGA / DOT Symbol Signs (non-tarot) | 50 | 1974–79 | Public domain | aiga.org | ready |
| Noto Emoji (non-tarot) | subset 120 | — | Apache 2.0 / OFL | GitHub | ready |

Rules: no U.S. Games recolored edition; no "Rider-Waite" in any name, tag or prompt
(trademark); every base card shows source, year and rights; the Admin rights checklist
(source page, license text, date, reviewer) is stored per base deck and must be complete
before `status: ready`.

**Ingestion** (Admin, job `ingest_base`): manifest JSON per deck `{cards: [{position_key,
title, image_url, caption}], structure_template, attestation_sources}` → download, normalize
(aspect, max 2048 px, WebP thumbs), store, create `BaseCard`s. **Registry extraction**: run
the vision tagger over all cards with an open vocabulary → cluster proposals → a curator
edits the base registry (name, gloss, `attested_axes` drafted by K2 from the attestation
text, human-reviewed) → `symbol_registry` with `origin: inherited_base` available for import.
Base decks are versioned (`v1`, `v2`) so decks can record which registry version they imported.

---

## 10. Architecture and stack

- **Web** — Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui; mobile-first for play
  and reading, desktop-first for the studio and workspace; i18n (EN/ES) with `next-intl`.
- **API** — FastAPI (Python 3.11): auth, decks, symbols, cards, sessions, readings, grammar,
  forks, jobs, admin. **Worker** — same codebase, separate process: image jobs, tagging,
  fidelity, grammar recompute, ingestion, export. Numpy, scikit-learn, Pillow,
  scikit-image (SSIM), open_clip or DINOv2 (image embeddings), sentence-transformers.
- **Realtime** — Server-Sent Events from the API for session state, presence, job progress,
  notifications; polling fallback (1.5 s) in the client. No websockets required.
- **Data** — MongoDB Atlas (all collections; Atlas Vector Search optional for "cards read like
  this"); object storage S3-compatible (Cloudflare R2 or Vultr Object Storage) behind a CDN.
- **Auth** — Auth0 (magic link + Google) for accounts; signed guest tokens; deck-scoped
  authorization middleware; share tokens for unlisted resources.
- **Providers** — image (Gemini primary, FLUX Kontext alternate, OpenAI third), vision
  tagger (Gemini), naming (IFM K2), voice (ElevenLabs, optional). All behind adapters with
  caching, retries, health checks.
- **Hosting** — Vercel (web); API + worker as containers on a VM (Vultr) or a container
  platform; Caddy for TLS; environment-driven configuration; secrets in the host's manager.
- **Observability** — structured logs, job dashboards in Admin, error tracking, provider
  latency/cost metrics.

---

## 11. API reference (REST, JSON; `Authorization: Bearer` or guest cookie)

**Auth** — `POST /auth/guest` · `POST /auth/upgrade` · `GET /me`
**Base decks** — `GET /base-decks` · `GET /base-decks/{slug}` · `GET /base-decks/{slug}/cards` ·
`GET /base-decks/{slug}/symbols`
**Decks** — `POST /decks` (wizard payload) · `GET /decks?visibility=public&sort=` ·
`GET /decks/{id}` · `PATCH /decks/{id}` · `DELETE /decks/{id}` · `POST /decks/{id}/fork` ·
`GET /decks/{id}/lineage` · `POST /decks/{id}/sync-from-parent` · `GET /decks/{id}/activity` ·
`GET /decks/{id}/export` (job) · `GET /decks/{id}/coherence` · `GET /decks/{id}/grammar`
**Members** — `GET/POST /decks/{id}/members` · `PATCH /decks/{id}/members/{uid}` ·
`POST /decks/{id}/invitations` · `POST /invitations/{token}/accept`
**Symbols** — `GET/POST /decks/{id}/symbols` · `PATCH /symbols/{sid}` · `POST /symbols/{sid}/merge` ·
`POST /symbols/{sid}/retire` · `POST /decks/{id}/symbols/import` ·
`POST /decks/{id}/symbol-proposals` · `PATCH /symbol-proposals/{pid}` (approve/decline)
**Cards** — `GET/POST /decks/{id}/cards` · `GET /cards/{cid}` · `PATCH /cards/{cid}` (intent, title,
access) · `POST /cards/{cid}/archive` · `POST /cards/{cid}/edit-requests` ·
`PATCH /cards/{cid}/edit-requests/{rid}` · `GET /cards/{cid}/versions` ·
`POST /cards/{cid}/generate` (job) · `POST /cards/{cid}/edit` (job; body includes
`base_version_id` → `409 version_stale`) · `POST /versions/{vid}/choose` (candidate index) ·
`POST /versions/{vid}/restore` · `POST /cards/{cid}/branches` · `GET /versions/{vid}/compare/{vid2}`
**Reinterpret** — `POST /decks/{id}/reinterpret` (base deck, positions) → batch job
**Readings** — `GET /decks/{id}/read/next` · `POST /versions/{vid}/readings` ·
`GET /versions/{vid}/reveal` · `GET /versions/{vid}/verdict`
**Sessions** — `POST /decks/{id}/sessions` · `POST /sessions/join` (code) · `GET /sessions/{sid}` ·
`POST /sessions/{sid}/start|advance|end` · `POST /sessions/{sid}/rounds/{rid}/submit` ·
`POST /sessions/{sid}/edit` (live edit job) · `GET /sessions/{sid}/events` (SSE)
**Forks & upstream** — `POST /decks/{id}/upstream-proposals` · `GET /decks/{id}/upstream-proposals` ·
`PATCH /upstream-proposals/{pid}`
**Jobs & notifications** — `GET /jobs/{jid}` · `GET /jobs/{jid}/events` (SSE) ·
`GET /notifications` · `PATCH /notifications/{nid}`
**Admin** — `POST /admin/base-decks/ingest` · `GET /admin/providers/health` · `GET /admin/moderation` ·
`PATCH /admin/quotas` · `GET /admin/metrics`

Errors: `401`, `403 role_required`, `404`, `409 version_stale | quota_exceeded | position_taken`,
`422 validation`, `429 rate_limited`, `503 provider_unavailable` (with retry-after).

---

## 12. Non-functional requirements

- **Performance** — pages < 2 s on 4G; session state propagation < 1.5 s; reading submit
  < 300 ms; generation 8–25 s with progress; edit fidelity scoring < 3 s per candidate;
  grammar recompute < 2 s for 5,000 readings.
- **Scale** — sessions of 3–30 players; decks up to 2,000 cards and 500 symbols; 10k users;
  images served from CDN.
- **Reliability** — jobs idempotent and retried; provider failover; SSE reconnect; server
  timers; every metric reproducible from stored readings.
- **Security** — deck-scoped authorization on every route; signed URLs for private images;
  rate limits; input validation; secrets never in the client; audit log for role and
  visibility changes.
- **Privacy** — readings are anonymized in public views; guest tokens expire in 90 days;
  export excludes personal data; delete account removes identity, keeps anonymized readings.
- **Accessibility** — 44 px touch targets, WCAG AA contrast, keyboard navigation in the
  studio, alt text from captions and declared symbols.
- **i18n** — EN/ES for all UI; base-deck captions in source language + English.
- **Costs** — image generation ~$0.02–0.05 per image; default 2 candidates; monthly quota per
  deck; cost telemetry to owners and admins.

---

## 13. Build plan — vertical slices for coding agents

Assumptions: repo with `web/`, `api/`, `worker/`, `shared/` (schemas as JSON Schema →
TypeScript + Pydantic); CI runs unit tests and the estimator test; provider keys and two
base-deck manifests (Smith 1909, Marseille Conver) prepared before slice 1; four people can
run four agents in parallel along service boundaries after slice 2.

| # | Slice | Delivers | Acceptance tests (must pass, demoable) |
|---|---|---|---|
| 1 | Foundations | monorepo, schemas, auth (Auth0 + guest), Mongo, object storage, jobs, SSE, i18n shell, Home | sign in; guest token; create a job and watch progress over SSE; EN/ES toggle |
| 2 | Base decks | ingestion job, catalog pages, registry extraction with curator review | Smith and Marseille ingested with captions; registry of ≥ 30 symbols each with attested priors; rights checklist complete |
| 3 | Decks | wizard (blank/base/fork stub), structure, style guide with preview card, members/invites/roles, settings, Overview, Cards grid with empty positions | create deck from Smith with Inherit → 78 positions filled; permissions matrix enforced by tests |
| 4 | Symbols | registry table, add/propose/approve/import/merge/retire, symbol detail | member proposal → curator approval → symbol usable in Generate; merge rewrites references |
| 5 | Generate | Generate menu (prompt / reference / variation / upload), candidates, style score, symbol detection, intent, draft→reading | card from prompt and from base reference, style score computed, missing-symbol warning shown |
| 6 | Edit | Edit menu with all ops, fidelity/containment/style scoring, auto-retries, diff heatmap, versions graph, compare/restore, lock `409` | add-crown edit returns fidelity ≥ 0.85 on 8/10 test cards; stale version rejected; cosmetic op flagged non-experiment |
| 7 | Reading & measurement | reading queue, reader UI with ghosts, reveal, distances, gaps, verdict with null, grammar with CIs, edit-effect estimator, seeds & estimator test in CI | estimator test green; verdict on planted cards correct; grammar band narrows after new readings |
| 8 | Sessions | lobby/code/QR, reading round, relay with live edit, timers, presence, scoring, summary | 6 phones complete a relay; reconnect mid-round; live edit within 40 s or async fallback |
| 9 | Coherence | dashboard, coherence index, contested detection, off-style, structural, transmission, bandwidth curve, Cards filters | contested symbol appears when two cards disagree by > 45°; index recomputes |
| 10 | Forks & upstream | fork with snapshot and priors, lineage tree, sync from parent, upstream proposals inbox/outbox | fork copies 78 cards + symbols with priors; proposal accepted lands as branch version |
| 11 | Reinterpret & share | batch reinterpret, public pages with OG, share tokens, embed, export ZIP, print PDF | 22 majors reinterpreted in deck style in one batch; export opens; PDF prints 9 per page |
| 12 | Admin & polish | providers health, quotas, moderation, metrics, notifications digest, accessibility pass, demo data | moderation report flows; quota block returns `409`; AA contrast audit passes |

Effort with agents: slices 1–4 ≈ 10–14 agent-hours, 5–7 ≈ 14–18, 8–9 ≈ 8–10, 10–12 ≈ 8–10;
about 40–55 agent-hours plus human review, parallelizable four ways after slice 2. The
integration risk is concentrated in slices 6 and 8; build them early and test on phones.

### 13.1 Demo script (3 minutes, judges in the room)
1. **0:00** Home: *Join a session* is on screen; two cards from the deck with identical
   variance and opposite verdicts. "The usual test can't tell which is broken. Ours can."
2. **0:15** Deck workspace: the deck was started from Smith 1909, reinterpreted in its own
   style this afternoon; Symbols table with declared vs measured meaning; one symbol
   *contested*.
3. **0:40** Card Studio → Edit: *Add crown*, bet on *certain*, rationale. Generate: candidate
   returns with fidelity 0.91 and the diff heatmap — "same card, one change, and here's the
   proof it changed nothing else."
4. **1:10** QR up; judges join as readers; 60 seconds on the new version with ghost markers
   from the earlier round (rehearsed with lunch readers).
5. **2:10** Reveal: arrows, bet hit, ΔF, the crown's band narrows; the coherence index ticks.
6. **2:30** History & Forks: lineage tree, a fork's upstream proposal in the inbox; accept it.
7. **2:50** "A deck of wayfinding icons is a deck with a different base deck." Done.
   Wifi dies → replay mode on the same screens.

### 13.2 Judging-criteria map
Originality → transmission measurement, polysemy-vs-noise with a null, deck-level symbol
grammar, forks with measured priors. Technical difficulty → high-fidelity edit pipeline with
computable fidelity, paired edit-effect estimator, coherence engine, live sessions with
generation. Demo quality → judges read and edit live; every number recomputable. Usefulness →
coherent decks in an afternoon; corpus-agnostic (icons, emoji). Track relevance → rooms,
roles, turns, forks, proposals: multiplayer at every layer.

---

## 14. Open decisions (owner to confirm; defaults in place)

1. Default `default_editor_policy` for new decks: **any_member** (recommended; maximizes
   experiments) vs `maker_list`.
2. Whether forks of private decks are allowed for members: default **yes**.
3. Whether live generation in sessions is on by default: default **off** (studio edits are
   the reliable path; turn on per session).
4. Print export in the first release: default **yes** (cheap once export exists).

---

## Appendix A — Structure templates
`tarot78`: 22 majors (0–21) + 4 suits × 14 (Ace–10, Page, Knight, Queen, King); groups
*Majors / Wands / Cups / Swords / Pentacles*. `majors22`, `minors56` subsets. `lenormand36`:
1–36 with the classic titles. `mantegna50`: five groups of ten. `free`: unbounded.

## Appendix B — Symbol registry seed for Smith 1909 (curator starting list)
crown · sun · moon · star · tower · downward water · upward water · cup · sword · wand ·
pentacle · throne · path · mountain · wall · gate/threshold · bridge · dog · lion · serpent ·
bird · rose · lily · wheel · veil · pillar · pillar pair · staff · blindfold · bandage/binding ·
key · ship · garden · child · elder · rider · falling figure · seated figure · standing pair ·
lightning · flame · rain · sunrise/sunset · cross · scales · hourglass · lantern.

## Appendix C — Event names (SSE)
`session.state` · `session.presence` · `session.round` · `job.progress` · `job.done` ·
`job.failed` · `card.version_created` · `card.status` · `notification.new` · `grammar.updated`.

## Appendix D — References
Osgood, Suci & Tannenbaum (1957) *The Measurement of Meaning* · Lewis (1969) *Convention* ·
Rousseeuw (1987) *Silhouettes* · ISO 9186-1 comprehensibility testing · Raiffa (1982) *The Art
and Science of Negotiation* (single negotiating text) · Ehtamo, Kettunen & Hämäläinen (2001),
Heiskanen, Ehtamo & Hämäläinen (2001), Caragiannis et al. (2016) for the cross-card layer.
