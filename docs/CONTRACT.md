# PIXIE v5 — build contract (platform)

The v5 spec (`docs/SPEC-v5.md`, pasted by the owner) is the source of truth for object names, fields,
states, roles, menus, flows and routes: **use its names verbatim**. This contract only fixes what the spec
leaves open — repo layout, module ownership, local fallbacks for services without keys, and the shapes
agents must agree on. Branch `v5`; `main` keeps the v4 hackathon relay.

## 0. Ground rules that never change
No votes anywhere. Makers approve editors, never edits. Readers are never scored. No model decides whether
a reading matches, a bet hit, a card landed, or how faithful an edit is — those are computed. No
"Rider-Waite" anywhere (say "Smith 1909"). Every model-produced value is labelled (`*_by`).

## 1. Layout (evolves the v4 repo; no monorepo rewrite)
```
api/
  main.py                 app factory: routers, CORS, /media static, lifespan (store, engine, worker)
  models.py               Pydantic models for every collection in spec §3 (names verbatim)
  auth.py                 guest tokens, dev magic link, optional Auth0 JWT verification, deck-scoped authz
  routers/                one file per spec §11 group: auth, base_decks, decks, members, symbols, cards,
                          versions, readings, sessions, forks, jobs, admin, notifications
  service/                domain services (pure functions over store + engine): decks.py, symbols.py,
                          cards.py, readings.py, sessions.py, forks.py, coherence.py, base_decks.py
  jobs.py                 Job docs + runner (thread pool in-process by default), SSE helpers
  storage.py              Storage interface: LocalStorage (api/storage/, served at /media/…) | S3Storage
  pixie/                  engine (v4 modules stay) + imaging/ (providers, prompts, fidelity, style, detect)
  worker.py               `python worker.py` runs the same job runner as a separate process (optional)
  tests/
data/
  base_decks/<slug>/manifest.json      spec §9 manifest (cards, structure_template, attestation_sources, rights)
  base_decks/<slug>/registry.json      curated symbol registry (spec §3.6 fields; exemplar crops via bbox)
  structures.json                      StructureTemplates (Appendix A)
  seeds/                               synthetic playground deck generator inputs
web/src/
  app/                    routes per spec §4 (see §6 below)
  lib/api.ts, lib/types.ts (TS mirrors of api/models.py), lib/i18n (next-intl, en + es)
  components/
docs/SPEC-v5.md, docs/CONTRACT.md (this), docs/DECISIONS.md (append v5 rows)
```

## 2. Services without keys → local fallbacks (all selected by env, all labelled in `/api/health`)
| Concern | With key | Fallback (always works) |
|---|---|---|
| Accounts | `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`: verify RS256 JWTs via JWKS | **Dev magic link**: `POST /auth/magic {email}` returns `{login_url}` directly (no mail); `GET /auth/magic/{token}` sets the session. Guest: `POST /auth/guest` → HMAC-signed token cookie `pixie_session`. |
| Object storage | `S3_ENDPOINT`, `S3_BUCKET`, `S3_KEY`, `S3_SECRET` (boto3) | `LocalStorage` under `api/storage/`, served at `/media/<key>`; private decks use signed URLs (`?sig=&exp=`) in both. |
| Image generation/edit | `GEMINI_API_KEY` → `GeminiImageProvider` (model id `GEMINI_IMAGE_MODEL`, default `gemini-2.5-flash-image`) ; `BFL_API_KEY` → FLUX Kontext; `OPENAI_API_KEY` → OpenAI edits | **`LocalCollageProvider`** (Pillow): generate = compose declared symbols' exemplars onto a paper card in the deck's palette/border (deterministic by seed); edit = paste/erase/replace the symbol's exemplar in the placement region with surround-fill; symbol = exemplar on white. It produces real images so every downstream metric runs. |
| Image embeddings (fidelity, style) | — | `clip-ViT-B-32` via sentence-transformers if the weights are present/downloadable, else a deterministic perceptual embedding (luminance grid + gradient histogram, 768-d). `/api/health.image_embed_backend`. |
| Vision tagger | `GEMINI_API_KEY` → JSON detection over the registry | declared symbols → `salience` from placement (`center 1.0, top/bottom 0.7, left/right 0.5, any 0.6`) flagged `declared_only` until a human confirms (`tagged_by: "human"`). |
| Naming | `K2_ENDPOINT`… | template label (two strongest poles). |
| Email | `RESEND_API_KEY` | none: links are returned in the API response and shown in the UI (dev banner). |

## 3. Auth and identity (spec §2)
- `User` with `guest_token` for guests. Session cookie `pixie_session` = `<user_id>.<exp>.<hmac>` signed with `PIXIE_SECRET`
  (dev default constant, warn in logs). `GET /me` returns the user + `is_guest`.
- Deck-scoped authorization: `require_role(deck, user, min_role)` with order reader < member < curator < owner; plus
  `is_maker(card, user)`, `is_approved_editor(card, deck, user)` (resolves `approved_editors` against
  `settings.default_editor_policy`). Every deck route calls one of these. Tests assert the spec §2.4 matrix.
- Guest → account upgrade: `POST /auth/upgrade` merges the guest user into the account (readings, memberships).

## 4. Store and ids
- `pixie/store.py` (v4) stays: memory + snapshot or Mongo. Collections named exactly as spec §3 objects in
  snake_case plural: `users, base_decks, base_cards, decks, memberships, invitations, structure_templates,
  symbols, symbol_proposals, cards, versions, readings, sessions, rounds, fork_snapshots, upstream_proposals,
  jobs, notifications, activities`. Derived (`transmission_events, edit_effects, verdicts, grammar`) are
  computed on read and cached in memory, never written by hand.
- ids: `<prefix>_<10 urlsafe>` — `u_ d_ bd_ bc_ sy_ sp_ c_ v_ r_ s_ rd_ j_ n_ a_ f_ up_ m_ i_`. Deck `slug` unique.
- Every deck-scoped doc has `deck_id`. Images are immutable per version; records store storage keys and the
  API returns absolute or relative URLs through `storage.url(key)` (relative `/media/...` by default; the web
  prefixes with the API host as in v4).

## 5. Jobs and SSE
- `jobs.enqueue(kind, payload, created_by, deck_id=None, idempotency_key=None) -> Job`; runner executes
  `HANDLERS[kind](job, ctx)` in a thread pool (`PIXIE_WORKER=thread` default, `inline` in tests, `external`
  when `worker.py` runs). Progress via `ctx.progress(0..1, note)`. Retries 3 with backoff. Result stored on the job.
- SSE endpoints stream `text/event-stream` with `event: <name>\ndata: <json>\n\n` (Appendix C names). The
  implementation polls the store every 500 ms and emits on change; heartbeat comment every 15 s. Clients fall
  back to polling the JSON endpoint every 1.5 s.

## 6. Web routes (spec §4) — file map
```
/                       app/page.tsx            Home (dashboard) — guest: landing with Join + Explore + Sign in
/explore                app/explore/page.tsx    base decks + public decks + search
/base/[slug]            app/base/[slug]/page.tsx
/decks/new              app/decks/new/page.tsx  wizard (5 steps)
/d/[slug]               app/d/[slug]/layout.tsx  workspace left nav (items by role) + pages:
  /d/[slug]             overview · /cards · /cards/[cid] (Card Studio tabs via ?tab=) · /symbols · /symbols/[sid]
  /play · /grammar (tabs grammar|coherence|transmission) · /history · /members · /settings · /read (queue)
/play                   join by code (+QR scan on mobile)      /s/[code]  session screens
/me                     profile                                 /admin     console (admin only)
/auth/magic/[token]     completes dev magic link
```
i18n: `next-intl`, messages in `web/messages/en.json` and `es.json`; locale from `User.locale` (cookie `NEXT_LOCALE`
for guests). All UI strings go through `t()`; both files complete for every slice.

## 7. Engine reuse from v4
`pixie/axes, metrics, verdict, grammar (weighted ridge), effects, geometry, embed, naming, relay` stay. Changes:
- Design matrix rows come from `Version.symbols_detected[].salience` over the deck's **active symbols** (not slots).
- Sessions (`sessions` + `rounds`) wrap `pixie/relay.py`: a `reading` session is a sequence of read rounds over
  chosen cards; a `relay` session is the v4 loop. Live edits call the imaging job with `generation_timer`.
- Seeds: the synthetic playground deck (spec §8.6) is created by `service/seeds.py` at boot when missing:
  slug `playground-synthetic`, visibility public, 60 cards, 300 readings, 40 paired edits, planted verdicts.

## 8. Imaging package (`pixie/imaging/`)
```
providers/base.py     ImageProvider protocol (spec §6.1) + ProviderResult {images: [bytes], provider, model, seed}
providers/local.py    LocalCollageProvider        providers/gemini.py   GeminiImageProvider (REST, JSON)
providers/flux.py, providers/openai.py            stubs raising ProviderUnavailable unless keyed
prompts.py            assemble_generate(...), assemble_edit(...) exactly as spec §6.2, denylist strip
fidelity.py           image_embed(img) -> np[768], embed_cos, ssim_out(base, cand, region), containment,
                      fidelity(...) per spec §6.4, diff_heatmap(base, cand) -> png bytes
style.py              style_centroid(refs) , style_score(img, centroid)
detect.py             detect_symbols(img, registry) -> [{symbol_id, present, salience, bbox}] (Gemini | fallback)
pipeline.py           run_generate(job), run_edit(job) (retries per §6.4), run_symbol(job), run_tag(job)
```
Regions: `{x, y, w, h}` in 0..1 of the image. Placement zones: center (0.24,0.30,0.52,0.40), top (0.30,0.04,0.40,0.22),
bottom (0.30,0.74,0.40,0.22), left (0.02,0.30,0.22,0.40), right (0.76,0.30,0.22,0.40), any → whole image.

## 9. Acceptance
Each slice's tests from spec §13 live in `api/tests/test_slice_<n>_*.py` and, for the web, a Playwright script
under `web/e2e/`. `PIXIE_EMBED=hash PIXIE_WORKER=inline pytest` must stay green on every slice.
