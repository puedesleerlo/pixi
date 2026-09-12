# PIXIE

**Communities build decks together. Every deck has its own symbols, its own style, and its own
evidence of what its cards actually communicate.**

Two branches:

- **`v5`** (this branch) — the platform: accounts and deck roles, a catalog of public-domain base decks,
  a deck wizard with structure and style guide, a deck-level symbol registry with proposals, card
  generation and **one-operation edits with computed fidelity**, async reading queues and live
  sessions, a per-deck measured symbol grammar, a coherence dashboard, forks with lineage and
  upstream proposals, export and print. Spec: `docs/SPEC-v5.md`. Contract: `docs/CONTRACT.md`.
- **`main`** — the HackCMU 2026 relay (v4): one deck, composed cards from symbol crops, the live relay.

## Run it (v5)

```bash
cd api && uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
PIXIE_WORKER=thread .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000     # API + in-process worker
cd web && pnpm install && pnpm dev                                              # http://localhost:3000
cd api && PIXIE_EMBED=hash PIXIE_WORKER=inline .venv/bin/pytest -q             # ~100 tests
```

Everything works with no external service: sign in with the **dev magic link** (the link is shown in
the UI), images live under `api/storage/`, cards are generated and edited by the **local collage
provider** (Pillow compositing of symbol exemplars — region-confined, so every fidelity metric is
real), image embeddings use CLIP ViT-B/32 when the weights are present, symbol detection is
declared-only. `GET /api/health` and the Admin console name every backend in use. Keys that unlock the
real services: `GEMINI_API_KEY` (image generation/edits + vision tagging), `BFL_API_KEY` / `OPENAI_API_KEY`
(alternate image providers), `K2_ENDPOINT` + `K2_API_KEY` (naming), `MONGODB_URI` (Atlas), `S3_*`
(object storage), `AUTH0_DOMAIN` + `AUTH0_AUDIENCE` (+ `AUTH0_CLIENT_ID`), `RESEND_API_KEY` (mail),
`PIXIE_ADMIN_EMAILS` (admin console).

## What the measurement is

Readers report on eight bipolar scales (Osgood 1957) and an optional phrase; the distance to the
maker's intent is computed, never judged. A version's fidelity is one minus the mean distance; a card
lands at 0.80. Each edit is one operation with a bet on an axis; the paired shift of readers who read
both versions decides the bet. A version with eight readings gets a verdict — legible, polysemous
(silhouette above a null-calibrated threshold) or noisy. The deck's grammar is a ridge regression of
readings on detected symbol salience with bootstrap bands, a paired edit-effect estimator beside it,
priors from attestations (base decks) or the parent's grammar (forks), and a coherence index from how
consistently each symbol acts across cards. A synthetic playground deck plants the tradition's priors
and the estimator test recovers them.

## Layout (v5)

```
api/main.py, routers/*, service/*, models.py, auth.py, jobs.py, storage.py     FastAPI + in-process worker
api/pixie/                engine (axes, metrics, verdict, grammar, effects, geometry, embed, naming, relay, store)
api/pixie/imaging/        providers (local, gemini, flux, openai), prompts, fidelity, style, detect, pipeline
data/base_decks/<slug>/   manifest.json (verified Commons cards + rights) and registry.json (symbols, priors, attestations)
web/src/app/              home, explore, base/[slug], decks/new, d/[slug]/* workspace, s/[code] sessions, me, play, admin
docs/SPEC-v5.md · docs/CONTRACT.md · docs/DECISIONS.md · docs/archive/
```

## Rights

Base artwork is public domain (Smith 1909: 78 cards verified on Wikimedia Commons; Conver 1760: 24
verified, scans credited CC BY-SA 4.0). Attested meanings from Waite (1911) and the Marseille tradition.
Generated symbols carry no attestation and no copyright claim; prompts strip trademarked deck names and
living artists. The trademarked deck name is not used anywhere. See `data/README.md`.
