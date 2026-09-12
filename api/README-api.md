# PIXIE API (v5) — what is implemented, env vars, fallbacks

Run: `cd api && .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000` · tests: `PIXIE_EMBED=hash PIXIE_WORKER=inline .venv/bin/pytest -q`.
All routes are under `/api`. Errors: `{"detail": {"code": …, "detail": …}}` with the spec's codes.

## Routes (slices 1, 3, 4 — stream B1)
| Group | Routes |
|---|---|
| Auth | `POST /auth/guest` `{name?, locale?}` → `{token, user}` (sets cookie `pixie_session`; idempotent for an existing session) · `POST /auth/magic {email, name?}` → `{login_url, token, sent:false}` (dev link, no mail) · `GET /auth/magic/{token}?redirect=0|1` → `{token, user}` (single use) · `POST /auth/upgrade {email, name?}` (guest → account, keeps readings/memberships) · `POST /auth/logout` · `GET /me` → `{user, decks:[{deck_id, slug, name, role, visibility, stats}]}` · `PATCH /me {name, locale, avatar_url}` |
| Structures | `GET /structures` (tarot78 · majors22 · minors56 · lenormand36 · mantegna50 · free; `data/structures.json` overrides the built-ins) |
| Decks | `GET /decks?visibility=public|unlisted|private|mine&sort=recent|cards|forks|coherence` · `POST /decks` (wizard body below) · `GET /decks/{id|slug}?share_token=` · `PATCH /decks/{id}` (curators: `style_guide`, `structure_template_id`; owner: everything incl. `owner_id` transfer) · `DELETE /decks/{id}` (owner) · `POST /decks/{id}/fork {name?, visibility}` · `GET /decks/{id}/lineage` · `GET /decks/{id}/activity` · `POST /decks/{id}/sync-from-parent` (501 until slice 10) |
| Members | `GET /decks/{id}/members` · `POST /decks/{id}/members {user_id|email, role}` (owner; unknown email → invitation) · `PATCH /decks/{id}/members/{uid} {role}` (owner) · `DELETE /decks/{id}/members/{uid}` (owner or self) · `POST /decks/{id}/invitations {email?, role, expires_in_days}` (curator+) → `{…, accept_url}` · `GET /decks/{id}/invitations` · `POST /invitations/{token}/accept` |
| Symbols | `GET /decks/{id}/symbols?status=active|all|retired|merged` · `POST /decks/{id}/symbols` (curator; SymbolDraft) · `GET /symbols/{sid}` (+ `cards`, `proposals`) · `PATCH /symbols/{sid}` · `POST /symbols/{sid}/merge {into_symbol_id}` · `POST /symbols/{sid}/retire` · `POST /decks/{id}/symbols/import {base_deck_slug, symbol_keys?}` · `GET/POST /decks/{id}/symbol-proposals` · `PATCH /symbol-proposals/{pid} {action: approve|decline, decision_note?}` |
| Jobs | `GET /jobs/{jid}` · `GET /jobs/{jid}/events` (SSE: `job.progress`, `job.done`, `job.failed`, `: ping` heartbeat) · `POST /jobs/test {n, fail_times?, sleep?}` |
| Notifications | `GET /notifications?unread=` → `{unread, items}` · `PATCH /notifications/{nid} {read}` · `POST /notifications/read-all` |
| Media | `GET /media/{key}` (local storage; `private/…` keys need `?sig=&exp=`) · `GET /api/health` |

**Wizard body** (`POST /decks`): `{name, description?, visibility, origin:{kind: blank|base|fork, base_deck_id?, forked_from_deck_id?}, structure_template_id?, style_guide? | style_from_base_deck_id?, import_symbols?: [keys] (omit = all, [] = none), card_mode: inherit|reference, invites?: [{email, role}], settings?}`. Base + `inherit` fills every structure position that has a base card (matched by `position_key`, else by title) with a v0 whose `how = {kind:"generation", mode:"upload", provider:"base_deck", reference_image_url, base_card_id, caption}`; cards start `draft` (no intent yet); `symbols_declared` come from the base registry's `cards` mapping.

**Deck view** adds `your_role` (owner|curator|member|reader|guest|none) and `structure` (the template); `share_token` is only returned to curators/owners.

**Position keys** (structures): `major-00…major-21`, `wands-01…wands-10`, `wands-page|knight|queen|king` (same for cups, swords, pentacles), `len-01…len-36`, `mant-01…mant-50`.

**Base registry entries** (`base_symbols` collection, or `data/base_decks/<slug>/registry.json` as a fallback): `{id?, key, name, gloss, tags[], placement, attested_axes[8], attested_text?, attestations[{source, note}], exemplar:{image_url, bbox?, source_card}, cards:[position_key…]}`.

## Env vars and fallbacks
| Var | Effect | Without it |
|---|---|---|
| `PIXIE_SECRET` | signs sessions, magic tokens, private media URLs | dev secret (warned in logs) |
| `PIXIE_WEB_URL` | base of login/invite URLs | `http://localhost:3000` |
| `PIXIE_ADMIN_EMAILS` | comma list of admin accounts | no admins |
| `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` | accept Auth0 RS256 bearer tokens (JWKS) | dev magic link + guests only |
| `MONGODB_URI` (+`MONGODB_DB`) | Mongo store | memory store + `api/.pixie_state_v5.json` snapshot |
| `S3_BUCKET`, `S3_ENDPOINT`, `S3_KEY`, `S3_SECRET`, `S3_PUBLIC_URL` | S3 storage, presigned private URLs | `LocalStorage` under `api/storage/` at `/media/…` |
| `PIXIE_STORAGE_DIR`, `PIXIE_PUBLIC_URL` | local storage dir; absolute media URLs | relative `/media/…` |
| `PIXIE_WORKER` | `thread` (default) · `inline` (tests) · `external` (`python worker.py`) | thread pool in the API process |
| `PIXIE_SNAPSHOT`, `PIXIE_STRUCTURES`, `PIXIE_DATA_DIR` | file locations | defaults under `api/` and `data/` |
