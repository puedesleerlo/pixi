# PIXIE — build contract (T1)

This file is the single source of truth for how the four parts of the build fit together.
If you change a shape here, change it everywhere. Spec = the PIXIE v2 document (§1–§8).

Layout:

```
api/            FastAPI + engine (Python 3.11, .venv via uv)
  main.py       HTTP routes (thin; calls pixie/*)
  pixie/        engine package — pure functions on numpy, no HTTP
  tests/        pytest; the §6.7 estimator test lives here
  scripts/      one-off batch jobs (Gemini tagging)
data/           corpus + vocabulary + tags, all JSON, committed
web/            Next.js 15 App Router + TS + Tailwind (pnpm)
docs/           this file, decisions, demo script
```

Run: `cd api && .venv/bin/uvicorn main:app --reload --port 8000` · `cd web && pnpm dev`.
Env: `MONGODB_URI` (optional → memory store), `GEMINI_API_KEY` (optional, tagging script only),
`K2_ENDPOINT` + `K2_API_KEY` (optional, cluster naming), `NEXT_PUBLIC_API_URL` (web, default `http://localhost:8000`).

---

## 1. Axes (fixed, everywhere)

Eight bipolar scales, index 0..7. Value in **−3..+3**, integers from the UI, floats internally.
**Negative = first pole, positive = second pole.**

| i | −3 pole | +3 pole |
|---|---|---|
| 0 | active | passive |
| 1 | beginning | ending |
| 2 | giving | withholding |
| 3 | inward | outward |
| 4 | gain | loss |
| 5 | willing | compelled |
| 6 | certain | uncertain |
| 7 | singular | collective |

Python: `pixie.axes.AXES = [("active","passive"), ...]`, `pixie.axes.axes_to_words(vec, k=3) -> "ending · passive · giving"`.
TS: `web/src/lib/axes.ts` exports the same list in the same order.

Reader UI maps the seven dots left→right to −3,−2,−1,0,1,2,3.

---

## 2. Data files (`data/`)

### `data/cards.json` — list of 44
```json
{
  "id": "smith-17",                   // "smith-00".."smith-21", "conver-00".."conver-21" (number in the deck's own order)
  "title": "The Star",                 // English title (Conver: "L'Étoile (The Star)")
  "arcana": "major",
  "number": 17,                        // number printed on the card in its own deck (Smith: Strength=8, Justice=11; Conver: Justice=8, Force=11; Fool=0)
  "image_url": "https://upload.wikimedia.org/…full…",
  "thumb_url":  "https://upload.wikimedia.org/…600px…",
  "source_deck": "Smith 1909" | "Conver 1760",
  "source_year": 1909,
  "rights_note": "Public domain (Pamela Colman Smith, 1909). Wikimedia Commons: File:RWS Tarot 17 Star.jpg",
  "caption": "Pamela Colman Smith, 1909 · public domain",     // rendered under every image
  "commons_title": "File:RWS Tarot 17 Star.jpg",
  "sibling_ids": ["conver-17"]         // same card in the other deck — matched by NAME (smith-08 Strength ↔ conver-11 La Force; smith-11 Justice ↔ conver-08 La Justice)
}
```
Source of truth for URLs and licence strings: `data/_sources/commons_verified.json` (fetched from the Commons API on 2026‑09‑12).
Never write "Rider-Waite" anywhere. Say "Smith 1909" / "Waite‑Smith line art".

### `data/elements.json` — ~35, two levels
```json
{
  "id": "water_falling",               // snake_case, stable
  "label": "Falling water",
  "gloss": "water poured or flowing downward",
  "parent_id": "water",                // null for the ~8 top-level groups
  "historical_prior": [0.0, 1.5, -2.0, 0.5, 1.0, 0.0, 0.0, 0.0],   // 8 floats in −3..3, axis order §1
  "prior_coded_by": "human" | "k2-drafted, human-approved",
  "attestations": [{"card_id": "smith-17", "source": "Waite 1911", "note": "…"}]
}
```
Top-level groups (parent_id null) are for grouping/filtering only. **The grammar regresses on leaf elements** (those that appear in `card_elements.json`). Parents may carry a prior (mean of children) but are never regressors.

### `data/card_elements.json` — list of tags
```json
{"card_id": "smith-17", "element_id": "water_falling", "visual_salience": 0.9, "tagged_by": "human" | "gemini"}
```
Every card has ≥ 3 tags. Salience 0..1 = how much of the visual attention the element takes.
The corpus is the experimental design: co-occurrence must vary across cards or the ridge cannot separate elements.

---

## 3. Engine package (`api/pixie/`) — pure numpy, no I/O except `data/` loaders

```python
# axes.py
AXES: list[tuple[str,str]]; N_AXES = 8; AXIS_MAX = 3.0
axes_to_words(vec: Sequence[float], k: int = 3) -> str

# metrics.py
RADIUS = 0.30; W_AXES = 0.6; W_EMBED = 0.4          # overridable via config dict
d_axes(a: array8, b: array8) -> float                    # ||a-b|| / (6*sqrt(8)), 0..1
d_embed(e1: array384, e2: array384) -> float             # (1-cos)/2, 0..1
d_total(a_i, a_r, e_i=None, e_r=None, cfg=None) -> dict  # {"d_axes","d_embed"|None,"d_total","inside_radius"}
maker_score(d_totals: list[float], cfg=None) -> dict     # {"points": 0|1|3|None, "f": float|None, "n": int, "needs": 3}
fidelity(d_totals: list[float]) -> float                 # 1 - mean

# verdict.py
polysemy_verdict(axes: array[N,8], v_lo=0.30, n_null=200, seed=0, cfg=None) -> dict
# n < 8  -> {"verdict":"collecting","n":n,"needed":8}
# else   -> {"verdict":"legible"|"polysemous"|"noisy","n","V","S","S_null95","k","P","noise",
#            "labels":[int]*N, "clusters":[{"centroid":[8],"n":int,"member_idx":[int]}]}
# AXES ONLY (x = axes/3). V = mean pairwise euclid / (2*sqrt(8)). S = max_k∈{2,3} silhouette(KMeans(k,n_init=10)).
# null = 200 draws of N isotropic Gaussian points rescaled to the same V; S_null95 = 95th pct of the null max-silhouette.
# Deterministic for a given seed.

# grammar.py
fit_grammar(X: array[N,E], Y: array[N,8], alpha=1.0, n_boot=200, seed=0) -> dict
# {"coef":[E][8], "ci_low":[E][8], "ci_high":[E][8], "intercept":[8], "n": N}
historical_support(coef_row: array8, prior: array8) -> float   # cosine, −1..1; 0.0 if either is all-zero

# geometry.py
class FrozenPCA:  fit(points: array[M,8]) -> self; transform(points) -> array[M,2]; to_dict(); from_dict()
# fit ONCE on seed intents + seed readings (axes, raw −3..3), stored by the server, reused for every round.

# embed.py
embed(texts: list[str]) -> array[n,384]; backend_name() -> "minilm" | "hash"
# minilm = sentence-transformers/all-MiniLM-L6-v2 if importable, else deterministic hashed bag-of-words → 384-d. Never Gemini.

# seeds.py
generate_seeds(cards, elements, card_elements, n=300, noise_sd=0.8, seed=0) -> dict
# {"intents":[Intent-like dicts], "readings":[Reading-like dicts, synthetic=True],
#  "planted": {"W_star": {element_id: [8]}, "polysemous_card_id": str, "noisy_card_id": str, "V_lo": float}}
# W* = historical priors of leaf elements. axes = clip(X @ W* + N(0, 0.8), -3, 3) per reading.
# One card planted polysemous (two intent modes, ~half the readings each), one planted noisy (isotropic scatter), matched V.
# V_lo = median V over cards with ≥ 8 seed readings.

# naming.py
name_cluster(texts: list[str], centroid: array8, top_elements: list[str]) -> dict   # {"label": str, "by": "k2"|"template"}
# K2 only when K2_ENDPOINT is set; 3 s timeout; template fallback = two strongest poles, e.g. "Willing ending".
```

Estimator test (`api/tests/test_estimator.py`): generate seeds from `data/*.json`, fit grammar, require
`corr(vec(W), vec(W*)) > 0.8`, planted polysemous card → "polysemous", planted noisy card → "noisy". Must pass in CI.

---

## 4. Records stored by the server (memory or Mongo — same shapes)

```
cards, elements, card_elements    — loaded from data/ at startup (upsert by id)
intents   {id, card_id, author_id, room_id|null, statement, axes[8], carriers[{element_id, weight}], embedding[384]|null, synthetic, created_at}
readings  {id, card_id, intent_id, reader_id, round_id, free_text|null, axes[8], embedding|null, latency_ms, synthetic, created_at, arrive_at?}
rooms     {see §5}
config    {w_axes, w_embed, radius, v_lo, alpha}
pca       FrozenPCA.to_dict()
```
`TransmissionEvent`, `Grammar`, `PolysemyVerdict` are **derived on read** (milliseconds at this size); the server may cache them.

---

## 5. Rooms — server‑authoritative state machine, polled every 1.5 s

Phases: `lobby → maker → reading → reveal → maker → …`. Transitions are **lazy**: any request touching the room first calls `tick(room)`, which moves `reading → reveal` when `now ≥ round_ends_at` or all readers have submitted. No background tasks, no websockets.

Room document:
```json
{
  "code": "ABCD", "host_id": "g_…", "created_at": "…", "phase": "lobby",
  "players": [{"guest_id":"g_…","nickname":"ana","joined_at":"…"}],
  "rotation_index": 0,
  "scores": {"g_…": 3},                       // Maker points only, die with the room
  "round": null | {
    "n": 1, "round_id": "r_…", "maker_id": "g_…", "card_id": "smith-17"|null, "intent_id": "i_…"|null,
    "started_at": "…", "round_ends_at": "…"|null, "duration_s": 60,
    "submitted_reader_ids": ["g_…"],
    "replay": false
  },
  "history": [{"n":1,"maker_id":"…","card_id":"…","intent_id":"…","points":3}]
}
```

`GET /api/rooms/{code}?guest_id=…` returns the room **filtered for that guest** plus:
```json
{ "server_time": "…", "you": {"guest_id":"…","role":"host"|"maker"|"reader"|"spectator","submitted": false},
  "reveal": {…} // only when phase == "reveal", see §6
}
```
During `maker` and `reading`, readers receive `round.card_id` but **never** the intent statement/axes/carriers.

Endpoints (all JSON; errors `{"detail": "…"}` with 4xx):

| Method & path | Body | Returns | Notes |
|---|---|---|---|
| `POST /api/rooms` | `{nickname, guest_id?}` | `{guest_id, room}` | creates 4-letter code (A–Z, no vowels to avoid words), caller = host |
| `POST /api/rooms/{code}/join` | `{nickname, guest_id?}` | `{guest_id, room}` | idempotent for a returning guest_id |
| `GET /api/rooms/{code}?guest_id=` | — | room (filtered) | the polling endpoint |
| `POST /api/rooms/{code}/start` | `{guest_id}` | room | host only; needs ≥ 2 players; phase → `maker`, maker = players[rotation_index] |
| `POST /api/rooms/{code}/intent` | `{guest_id, card_id, statement, axes[8], carriers[{element_id,weight}]}` | room | maker only; stores Intent (embedding computed); phase → `reading`, `round_ends_at = now + 60 s` |
| `POST /api/rooms/{code}/reading` | `{guest_id, axes[8], free_text?, latency_ms?}` | room | readers only, once per round; stores Reading (`synthetic:false`); when all readers submitted → reveal |
| `POST /api/rooms/{code}/next` | `{guest_id}` | room | host or maker; phase → `maker`, rotation_index += 1 (mod players) |
| `POST /api/rooms/{code}/replay` | `{guest_id}` | room | re-plays the last **completed real round of this room** (or, if none, the most recent real round of any room): copies its readings into a new round with `arrive_at` staggered over 10 s; `GET` shows them arriving; ends in `reveal`. Readings created by replay are stored with `synthetic: true`, `replay_of: <round_id>` so they never double-count in the grammar. |

Guest id: `g_` + 10 url-safe chars, minted by the server if absent; the web keeps it in `localStorage["pixie_guest"]` and a cookie.

---

## 6. Reveal payload (`room.reveal`, phase == reveal) — also `GET /api/rooms/{code}/reveal`

```json
{
  "card": {…card…},
  "intent": {"statement": "…", "axes": [8], "carriers": [...], "author_nickname": "…"},
  "readings": [
    {"reader_id":"g_…","nickname":"…","axes":[8],"free_text":"…"|null,
     "d_axes":0.21,"d_embed":0.33|null,"d_total":0.26,"inside_radius":true,"xy":[x,y],"synthetic":false}
  ],
  "intent_xy": [x, y], "radius": 0.30, "pca_note": "frozen on 300 seed intents+readings",
  "maker_score": {"points": 3, "f": 0.5, "n": 4, "needs": 3},
  "verdict": {…polysemy_verdict on ALL readings of this card, real + synthetic, with "clusters":[{…,"label":"Willing ending","label_by":"template"}]…},
  "grammar_strip": [ {"element_id":"…","label":"…","salience":0.9,"coef":[8],"ci_low":[8],"ci_high":[8],"n":312,"historical_support":0.71} ],
  "grammar_strip_before": [ same elements, fitted WITHOUT this round's readings ]   // so the UI can animate the band narrowing
}
```
Readers see their own `d_total` (highlighted). **No sorted list of readers anywhere.** Order readings by submission time.

---

## 7. Read-only endpoints

| Path | Returns |
|---|---|
| `GET /api/health` | `{ok, store:"memory"|"mongo", embed_backend, naming_backend, n_cards, n_readings, n_real, n_synthetic}` |
| `GET /api/cards` | `[{…card…, "elements":[{element_id,label,visual_salience,tagged_by}], "n_readings", "n_real"}]` |
| `GET /api/cards/{id}` | card + elements + `fidelity` + `verdict` (+ cluster labels) + `readings` (axes, free_text, synthetic, created_at) + `historical_support` per element |
| `GET /api/elements` | elements.json as stored |
| `GET /api/grammar?include_synthetic=true` | `{"axes":[[pole,pole]…], "n_readings","n_real","n_synthetic", "elements":[{element_id,label,parent_id,coef[8],ci_low[8],ci_high[8],n,historical_prior[8],historical_support,attestations}]}` |
| `GET /api/grammar/bandwidth` | `[{"n_elements": k, "mean_fidelity": f, "n_cards": c}]` real readings only (T2) |
| `GET /api/verdict/{card_id}` | polysemy_verdict + cluster labels |
| `GET /api/config` / `POST /api/config` | `{w_axes, w_embed, radius, v_lo, alpha}` (dev panel) |
| `GET /api/geometry` | `{"pca": …, "seed_points": [[x,y,is_intent]…]}` for backgrounds |

CORS: allow `*` (hackathon).

---

## 8. Web routes (`web/src/app`)

| Route | Screen |
|---|---|
| `/` | Join: nickname + "new room" / 4-letter code; QR is just `/r/CODE` |
| `/r/[code]` | Lobby → Maker → Reader → Reveal, one page switching on `phase`; polls every 1.5 s |
| `/grammar` | element × axis matrix with CI bands; toggles: synthetic on/off, "drifting from tradition" (historical_support < 0) |
| `/cards`, `/cards/[id]` | corpus grid with captions; card page (T2) |
| `/dev` | weights panel (reads/writes `/api/config`) |

Design: ink `#141414` on paper `#f4efe6`; accent (real data) `#c8361e`; synthetic `#9b9b93`; rule lines `#d9d2c3`. No gradients, no shadows. Serif display (Fraunces or system Georgia) + system sans. Every image has its caption under it.
