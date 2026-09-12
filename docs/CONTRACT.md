# PIXIE — build contract v4 (Relay + Decks)

Single source of truth for how engine (E), data (D), server (S) and web (F) fit. Spec = PIXIE v4.
Changed from v2: cards are **composed** from slotted symbol crops; rounds are a **relay**
(compose → read → reveal → edit → read → reveal …); every record is **deck-scoped**.
Unchanged: axes, distances, verdict, ridge grammar, frozen PCA, embeddings, naming, store.

```
api/pixie/     engine (pure numpy) + relay.py (state machine) + store.py
api/service.py derived payloads   api/main.py routes   api/static/crops/<library>/<element>.png
data/libraries/<library_id>/elements.json   data/libraries.json   data/cards.json (source images for crops)
web/           Next.js 15 app
```
Run: `cd api && .venv/bin/uvicorn main:app --reload --port 8000` · `cd web && pnpm dev`.
Env: `MONGODB_URI` (optional), `K2_ENDPOINT`/`K2_API_KEY`/`K2_MODEL` (optional), `GEMINI_API_KEY`
(generation only, T2), `PIXIE_PUBLIC_URL` (base for image URLs, default `http://localhost:8000`),
`PIXIE_EMBED=hash` (offline embedder), `NEXT_PUBLIC_API_URL`.

---

## 1. Axes — unchanged
Index 0..7, value −3..+3, **negative = first pole**: active/passive · beginning/ending ·
giving/withholding · inward/outward · gain/loss · willing/compelled · certain/uncertain ·
singular/collective. `pixie.axes.AXES`, `web/src/lib/axes.ts`.

## 2. Slots — fixed, five
```
SLOTS = {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5}
```
`visual_salience` of an element on a version = its slot's value. `size_class: "large"` may go in any slot;
`"small"` may not go in `center`. A version has 2–5 elements, one per slot, no element twice.
Auto-assignment in Compose (client and server agree): iterate picked elements in pick order; the first
`large` one takes `center`; the rest fill `top, bottom, left, right` in that order; if no `large` was
picked, `center` stays empty (max 4 elements). Server validates the same rule.

Renderer (web): a paper frame (aspect 3:5), center slot = 52% width box in the middle, top/bottom =
40% wide boxes, left/right = 26% wide boxes; each holds an `<img>` (crop) or a **text tile** (label in
small caps on paper) when `image_url` is null. Same component on phone and big screen. Every element on
the card face looks the same whatever its origin; captions/labels live outside the face.

## 3. Data files

### `data/libraries.json`
```json
[{"id":"smith1909","name":"Smith 1909","kind":"base","source_deck":"Smith 1909","source_year":1909,
  "rights_note":"Pamela Colman Smith line art, 1909, public domain; crops from Wikimedia Commons scans"},
 {"id":"conver1760","name":"Conver 1760","kind":"base","source_deck":"Conver 1760","source_year":1760,"rights_note":"…"}]
```
### `data/libraries/<library_id>/elements.json` — the element sheet of one base library
```json
{"id":"star","library_id":"smith1909","label":"Star","gloss":"an eight-pointed star in the sky",
 "parent_id":"celestial","size_class":"small","origin":"cut",
 "source_card":"smith-17","bbox":[0.30,0.05,0.70,0.32],          // normalised x0,y0,x1,y1 on the source image; null → text tile
 "image_url":"/static/crops/smith1909/star.png",                 // null → text tile (origin "tile")
 "caption":"cut from The Star, Smith 1909, public domain",
 "historical_prior":[…8…],"prior_coded_by":"human","attestations":[{"card_id":"smith-17","source":"Waite 1911","note":"…"}]}
```
Groups (`parent_id: null`) live in the same file with no bbox/image and are never placed on a card.
Element ids are unique **across** libraries (prefix Marseille ones, e.g. `m_sun`), because a deck's design
matrix pools all enabled libraries. Every placeable element has `size_class`, `origin`, `caption`.
Generated elements (T2) are stored only in the DB (`origin:"generated"`, `library_id` = the deck's community
library, `historical_prior: null`, `caption:"generated · no attestation"`).

`api/scripts/build_crops.py` reads a library's sheet, downloads each `source_card` image (from
`data/cards.json` thumb URLs, cached under `data/_cache/images/`), crops `bbox` with Pillow, pads to the
slot aspect (small: 1:1, large: 3:4) on white, writes `api/static/crops/<library_id>/<id>.png`, and sets
`image_url`. Elements whose bbox is null keep `image_url: null` and render as tiles.

`data/cards.json` (44 source images, captions) stays as the crop source and for the corpus credits.

## 4. Engine (`api/pixie/`) — additions to v2
```python
# slots.py
SLOTS: dict[str,float]; SLOT_ORDER = ["center","top","bottom","left","right"]
auto_assign(elements: list[dict{id,size_class}]) -> list[{element_id, slot}]     # rule in §2
validate_version(elements: list[{element_id,slot}], elem_by_id) -> None | raises ValueError
design_row(version_elements, leaf_pos: dict[str,int], E: int) -> np.ndarray[E]    # slot salience per element

# metrics.py (+)
gaps(intent_axes, readings_axes) -> np.ndarray[8]            # g_k = intent_k − mean(reading_k)
paired_shift(prev: dict[reader_id, axes], cur: dict[reader_id, axes]) -> (delta: np.ndarray[8] | None, n_pairs)
bet_hit(delta_k, gap_before_k, threshold=0.5) -> bool         # sign match and |δ| ≥ threshold
LANDING_F = 0.80

# seeds.py (rewritten for v4)
generate_seeds(elements, n_cards=60, n_readings=300, n_edits=40, paired=4, noise_sd=0.8, seed=0, deck_id="playground")
 -> {"cards": [...], "versions": [...], "readings": [...],
     "planted": {"W_star": {eid: [8]}, "polysemous_card_id", "noisy_card_id", "V_lo"}}
# cards: composed of 2–5 placeable elements via auto_assign; intent axes = clip(X @ W*, −3, 3), statement templated.
# readings on v0: clip(X @ W* + N(0, 0.8)). Edits: 40 cards get a v1 with ONE move (add/remove/swap/move),
# edit.bet_axis = argmax |expected shift|, and 4 readers read BOTH v0 and v1 (same reader_id, same noise draw + true effect).
# Planted polysemous / noisy cards as in v2 (matched V). All synthetic=True.

# effects.py (T2 but cheap — ship it)
edit_effects(versions, readings) -> {element_id: {"n_edits": int, "mean_effect": [8]}}   # per edited element: mean over edits of paired shift / (±salience)
```
Estimator test: `corr(vec W, vec W*) > 0.8`; for ≥ 80 % of edited elements the paired mean effect lies inside
the pooled CI; both planted verdicts recovered. `PIXIE_EMBED=hash` in tests.

## 5. Store collections (memory or Mongo; every doc has `id` and, where applicable, `deck_id`)
```
libraries, elements, decks, rooms, cards, versions, readings, config, pca, meta
deck     {id, name, code, owner_id, libraries[], members[{guest_id,nickname,joined_at}], open_read, max_edits, ready_threshold, created_at, community_library_id}
card     {id, deck_id, mode:"room"|"deck", room_id?, maker_id, maker_nickname, intent{statement, axes, embedding}, approved_editors:"*"|[ids],
          status:"reading"|"open"|"landed"|"closed", title?, title_by?, latest_version_id, n_versions, encoder_ids[], created_at, finished_at?, synthetic}
version  {id, card_id, deck_id, v, elements[{element_id, slot}], edit?{type, element_id, to_element_id?, to_slot?, editor_id, editor_nickname, bet_axis, rationale}, created_at, synthetic}
reading  {id, deck_id, card_id, version_id, reader_id, nickname, room_id?, round_id?, free_text, axes, embedding, latency_ms, synthetic, model:false, created_at}
```
Boot: upsert libraries + elements from `data/`; create deck **Playground** (`code: "PLAY"`, libraries
`["smith1909"]` + its community library, `open_read: true`, `max_edits: 3`, `ready_threshold: 3`) if
missing; seed it (§4) once; fit and freeze the PCA on seed intents + readings.
Derived on read: transmission events, edit effects, grammar (per deck), verdicts (per version), chains.

## 6. Relay state machine (room mode) — `pixie/relay.py`
Room: `{id(code), code, deck_id, host_id, players[{guest_id,nickname,joined_at}], turn_order[guest_ids],
maker_index, makers_done[], scores{guest_id: int}, phase, round, history[], created_at}`.
Phases: `lobby → compose → read → reveal → edit → read → reveal → … → (next card) compose … → ended`.
Timers (server, lazy tick on every request): compose 90 s · read 60 s (v0) / 45 s (v ≥ 1) · reveal 30 s ·
edit 45 s. A phase also advances when everyone required has submitted. `MAX_EDITS` = deck.max_edits (3).

`round` = `{card_id, version_id, v, maker_id, holder_id, editor_id?, phase_ends_at, submitted_reader_ids[], reader_ids[], n_card}`
- **compose** (holder = maker): `POST /compose` → creates Card (status "reading") + Version v0 → `read`.
  Timeout → the maker is skipped (`history` notes it) → next maker or `ended`.
- **read**: readers = players − holder. `POST /reading` once per reader per version. All in or timeout → `reveal`.
  On `reveal` entry the server computes and freezes in `round.result`: fidelity, gaps, maker_score (v0) or
  edit_effect (v ≥ 1), landed (`F ≥ 0.80` and ≥ 2 human readings), and applies points: maker 3/1/0 at v0;
  editor +2 on a hit; on landing +1 to every encoder on the chain. Sets card.status to `landed`, or `closed`
  when `v == max_edits`, else keeps `reading`.
- **reveal**: 30 s or `POST /continue` (host or holder) → if card landed/closed: `history` += chain summary,
  `makers_done` += maker; if all players have been maker → `ended`; else `maker_index` += 1 → `compose`.
  Otherwise → `edit` with `editor_id` = next player after the current holder in `turn_order` who is not the maker.
- **edit** (holder = editor): `POST /edit` with exactly one move; server validates (§2 rules; `swap` keeps the
  slot; `move` changes a slot; `add` needs a free slot; `remove` keeps ≥ 2) → Version v+1 → `read` (45 s).
  Timeout → card `closed` ("editor timed out") → as after reveal.
- **replay**: `POST /replay` re-plays the last finished card of this room (else any room, else a seeded card with
  an edit): for each version, a `read` phase whose recorded readings "arrive" over 10 s, then a `reveal` of
  12 s, then the next version; ends in `reveal` of the last version. Replayed readings live in
  `round.replay_readings` only and never enter `readings`. No points.

Guest view `GET /api/rooms/{code}?guest_id=` → the room plus:
```
server_time, you: {guest_id, role: "host"|"player"|"maker"|"editor"|"reader"|"spectator", is_host, submitted, previous_axes: [8]|null},
round: {…, phase_ends_at, n_readers, n_submitted, version: {v, elements:[{element_id, slot, label, image_url, origin, size_class}]}, max_edits}
intent  — present ONLY for the holder while composing/editing (statement + axes + gaps_signed); never for readers.
reveal  — present in phase reveal (§7).
```

## 7. Reveal payload (phase `reveal`, per guest)
```json
{"card": {"id","status","title","title_by","maker_nickname","v","max_edits","landed":bool,
          "statement": "…" },                            // statement only once landed/closed; null otherwise
 "version": {"v","elements":[…as above…],"edit": {…, "editor_nickname"} | null},
 "intent_xy":[x,y], "radius":0.30, "pca_note":"…",
 "readings":[{"reader_id","nickname","axes","free_text","d_axes","d_embed","d_total","inside_radius","xy":[x,y],
              "prev_xy":[x,y]|null, "prev_axes":[8]|null, "shift":[8]|null, "synthetic":false}],
 "fidelity": 0.71, "fidelity_prev": 0.62|null, "delta_fidelity": 0.09|null,
 "gaps_abs":[{"axis":6,"abs":1.8}, …8 sorted desc…], "gaps_signed": [8] | null,   // signed only for encoders (maker/editor)
 "maker_score": {"points","f","n","needs":3} | null,                                 // v0 only
 "edit_effect": {"bet_axis":6,"delta":-1.2,"gap_before":-1.5,"hit":true,"n_pairs":3,"shift":[8],"points":2} | null,   // v ≥ 1
 "landing": {"landed":true,"threshold":0.80,"points_each":1,"encoders":["ana","bo"]} | null,
 "verdict": {…polysemy_verdict over ALL readings of this version, or "collecting"…},
 "grammar_strip": [{"element_id","label","slot","salience","coef","ci_low","ci_high","n","n_edits","historical_support"|null}],
 "grammar_strip_before": [ same, fitted without this version's readings ],
 "edited_element_id": "crown"|null,
 "you": {"d_total": 0.21|null, "shift":[8]|null}}
```
Readers listed in submission order. No ranking anywhere.

## 8. Endpoints
| Method & path | Body → returns |
|---|---|
| `GET /api/health` | `{ok, store, embed_backend, naming_backend, n_libraries, n_elements, n_decks, n_cards, n_readings, n_real, n_synthetic, config, planted}` |
| `GET /api/libraries` · `GET /api/libraries/{id}/elements` | libraries · placeable elements (+groups) |
| `GET /api/decks` | `[{id,name,code,n_members,n_cards,libraries}]` |
| `POST /api/decks` | `{name, libraries:["smith1909"], guest_id, nickname}` → deck (creator is owner + member); code = 4 consonants |
| `POST /api/decks/{code}/join` | `{guest_id, nickname}` → deck |
| `GET /api/decks/{code}` | deck home: deck + `cards` grouped by status, each with its **chain** (§9) |
| `GET /api/decks/{code}/elements` | picker: placeable elements of all enabled libraries, grouped by library |
| `GET /api/decks/{code}/grammar?include_synthetic=` | `{axes, n_readings, n_real, n_synthetic, n_edits, elements:[{element_id,library_id,label,parent_id,origin,coef,ci_low,ci_high,n,n_edits,mean_effect|null,historical_prior|null,historical_support|null}]}` |
| `GET /api/decks/{code}/bandwidth` | real data only: `[{n_elements, mean_fidelity, n_cards}]` |
| `GET /api/decks/{code}/cards/{card_id}` | card page = chain (§9) |
| `GET /api/grammar` | alias for Playground |
| `POST /api/rooms` | `{nickname, guest_id?, deck_code?="PLAY"}` → `{guest_id, room}` |
| `POST /api/rooms/{code}/join` | `{nickname, guest_id?}` → `{guest_id, room}` |
| `GET /api/rooms/{code}?guest_id=` | guest view (§6) |
| `POST /api/rooms/{code}/start` | `{guest_id}` host, ≥ 3 players (2 allowed with a warning flag `small_room: true`) |
| `POST /api/rooms/{code}/compose` | `{guest_id, statement, axes[8], elements:[{element_id, slot}]}` |
| `POST /api/rooms/{code}/reading` | `{guest_id, axes[8], free_text?, latency_ms?}` |
| `POST /api/rooms/{code}/edit` | `{guest_id, type:"add"|"remove"|"swap"|"move", element_id, to_element_id?, to_slot?, bet_axis:0..7, rationale?}` |
| `POST /api/rooms/{code}/continue` | `{guest_id}` host or holder: leave `reveal` early |
| `POST /api/rooms/{code}/replay` | `{guest_id}` host |
| `GET/POST /api/config` · `GET /api/geometry` | as v2 |
| **T2 deck mode** `POST /api/decks/{code}/cards` `{guest_id, statement, axes, elements, approved_editors?}` · `GET /api/decks/{code}/read?guest_id=` (queue → version with fewest human readings among `reading` cards) · `POST /api/decks/{code}/cards/{id}/readings` · `POST /api/decks/{code}/cards/{id}/edit` `{guest_id, version_id, …move…}` (409 `"someone edited first — read v+1"` on a stale version) · `POST /api/decks/{code}/cards/{id}/approved_editors` `{guest_id, approved_editors}` (maker only) | |

## 9. Chain (deck entry / card page)
```json
{"card": {"id","deck_id","mode","status","title","title_by","maker_nickname","landed","statement"|null,"created_at","finished_at","max_edits"},
 "versions": [{"v","version_id","elements":[…],"edit": {"type","element_id","element_label","to_element_id","to_element_label","to_slot","editor_nickname","bet_axis","rationale"}|null,
               "n_readings","n_real","fidelity","delta_fidelity","edit_effect": {...}|null, "points": {"maker":3}|{"editor":2}|null}],
 "landing": {…}|null}
```
`statement` is included once the card is landed/closed (public), otherwise null.

## 10. Web routes
| Route | Screen |
|---|---|
| `/` | Join: nickname, New room (in Playground), Join code; one-line framing |
| `/r/[code]` | Lobby (code, QR, players, turn order) · Compose (intent, 8 scales, element picker grouped by library with captions, auto-slotted live preview) · Read (composed card, 8 dot rows, ghost markers from `you.previous_axes`, optional phrase, countdown) · Reveal (plot with star/dots/arrows, gap bars, score / bet / ΔF / landing, verdict, grammar strip animating before→after with the edited element highlighted, Continue for host/holder, Replay for host) · Edit (card + intent + signed gaps, ONE move UI: pick add/remove/swap/move, bet axis, rationale, countdown) · Ended (chains of this room) |
| `/decks/[code]` | Deck home: cards grouped by status with chains (rationale under each edit, bet, measured shift), members, link to grammar; T2: read link, compose |
| `/decks/[code]/grammar` and `/grammar` | matrix (as v2) + `n_edits`/mean effect column; generated elements marked; "drifting" filter; bandwidth curve |
| `/dev` | config |
Design as v2: ink `#141414`, paper `#f4efe6`, accent `#c8361e` (real), muted `#9b9b93` (synthetic), rules `#d9d2c3`; small dashed mark for generated symbols outside the card face; shift arrows and the narrowing band are the hero animations.
