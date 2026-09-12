# PIXIE

**A multiplayer relay where players build a tarot card one symbol at a time, bet on what each
symbol will do, and find out from the room. Every edit is an experiment; the accumulated
experiments are a shared symbol grammar — one per deck.**

HackCMU 2026 · Multiplayer track. A visual-communication research tool: the engine does not know
it is tarot — a deck of wayfinding icons is a deck with a different base library. No prediction
claims anywhere.

## The relay

1. **Compose.** The Maker writes a private intent (≤ 140 chars + eight bipolar scales) and places
   2–5 symbols from the deck's libraries into five fixed slots (center 1.0 · top/bottom 0.7 ·
   left/right 0.5 — the slot is the visual salience).
2. **Read.** Everyone else sees only the card: eight taps on a semantic differential (Osgood 1957),
   an optional phrase, sixty seconds on the server clock.
3. **Reveal.** Readings against the intent on a frozen PCA plane, the eight gaps, the Maker's
   score (3 / 1 / 0 for calibrated ambiguity / landed on arrival / obscure — computed from reports,
   never from anyone's choice).
4. **Edit.** The card passes to the next player, who sees the intent and the gaps, makes **exactly
   one** change (add / remove / swap / move), **bets** which axis will move, and writes a rationale.
5. **Read again** with ghost markers; **reveal** an arrow per reader, whether the bet landed (paired
   shift ≥ 0.5 in the gap's direction → +2), the change in fidelity, and the edited symbol's grammar
   coefficient moving (its band updates, and narrows as real readings accumulate). A card *lands* at fidelity ≥ 0.80 (+1 to every encoder) or closes after three edits.

Readers are never scored. Nobody votes. Makers may decide *who* edits their card, never *which*
edits land. No LLM judges anything: Gemini may draw a symbol (T2), MiniLM embeds text, K2 may
*name* a cluster or a landed card, and every such label says so.

What a deck keeps is the chain — every edit, who made it, their bet, their rationale, and what the
readers actually did. Across many edits that is a **grammar**: which symbols move which readings in
this community, with what confidence, and how far that drifts from the tradition the symbol was cut
from. A card with ≥ 8 readings gets a **verdict** — *legible*, *polysemous* (coherent camps: the
silhouette beats a null-calibrated threshold) or *noisy* (same variance, no structure) — which a
single agreement rate cannot tell apart.

## Run it

```bash
# API (Python 3.11, FastAPI). First boot seeds the Playground deck (60 cards, 620 flagged synthetic
# readings, 40 paired edits), freezes the PCA plane, and serves the symbol crops from api/static.
cd api && uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000

# Web (Next.js 15)
cd web && pnpm install && NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev

# or both (prints the LAN URL for phones on the same wifi):
./dev.sh
```

Phones: open `http://<your-laptop-ip>:3000`. The web app calls the API on whatever host it was opened
from, so no configuration is needed on the LAN; set `NEXT_PUBLIC_API_URL` only when the API lives elsewhere.

Tests — the §6.7 estimator test (planted grammar recovered, paired edit effects inside the CI,
both planted verdicts) plus the relay state machine and the HTTP relay end to end:

```bash
cd api && PIXIE_EMBED=hash .venv/bin/pytest -q      # 49 tests, ~4 s
```

Environment (all optional — the demo path works with every external service down):

| Variable | Effect |
|---|---|
| `MONGODB_URI` | use MongoDB Atlas; otherwise memory + `api/.pixie_state.json` snapshot |
| `K2_ENDPOINT`, `K2_API_KEY`, `K2_MODEL` | IFM K2 names clusters and landed cards; template fallback otherwise |
| `GEMINI_API_KEY` | symbol generation (T2 — not yet wired) |
| `PIXIE_PUBLIC_URL` | base URL the API prints in image links (default `http://localhost:8000`) |
| `PIXIE_EMBED=hash` | force the offline hashed embedder (no torch) |
| `NEXT_PUBLIC_API_URL` | where the web app finds the API |

## Layout

```
api/pixie/     engine: axes, slots, metrics (distances, gaps, paired shift, bet, landing), verdict (null-calibrated
               silhouette), grammar (ridge + bootstrap), effects (paired edit estimator), geometry (frozen PCA),
               seeds (planted-grammar estimator test), embed, naming, relay (state machine), store (memory/Atlas)
api/service.py derived payloads (reveal, chains, grammar per deck, replay script)      api/main.py routes
api/static/crops/<library>/<element>.png   symbol crops (built by api/scripts/build_crops.py)
data/libraries.json, data/libraries/<id>/elements.json   the element sheets: gloss, slot size, bbox, prior, attestation
web/           join · room (lobby / compose / read / reveal / edit / ended) · deck home with chains · grammar · dev
docs/CONTRACT.md   the shapes everything agrees on      docs/DECISIONS.md   deviations, kept honest for the Q&A
```

## Rights

All historical artwork is public domain. Smith 1909 crops: Wikimedia Commons scans, public domain.
Conver 1760: Wikimedia Commons, public-domain artwork, scan credited CC BY-SA 4.0 (text tiles until
crops are added). Attested meanings: Waite, *The Pictorial Key to the Tarot* (1911) and the Marseille
tradition. Composed cards are collages; we own the seams. The trademarked deck name is not used
anywhere in this project. See `data/README.md`.
