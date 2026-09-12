# PIXIE corpus data

Everything in this directory is committed JSON. The engine loads it at startup; the front end
reads it through the API. There is no tag-correction UI — corrections are edits to these files.

## Files

| File | What | Produced by |
|---|---|---|
| `cards.json` | 44 Major Arcana: 22 Smith 1909 + 22 Conver 1760, with image URLs, captions, rights and sibling links | `api/scripts/build_cards.py` from `_sources/commons_verified.json` |
| `elements.json` | the shared symbol vocabulary: 8 top-level groups + 43 leaf elements, each with an 8-axis historical prior and attestations | `api/scripts/build_vocab.py` (tables are hand-drafted in the script) |
| `card_elements.json` | visual tags: which leaf elements are visible on which card, with salience 0..1 | `api/scripts/build_vocab.py` (`tagged_by: "human"`); optionally merged with Gemini output |
| `card_elements.gemini.json` | raw Gemini tagging output (not committed until a pass has been run) | `api/scripts/tag_with_gemini.py` |
| `_sources/commons_verified.json` | Wikimedia Commons API response for all 44 files (URL, size, licence, uploader), fetched 2026‑09‑12 | one-off fetch |
| `_cache/gemini/` | per-card Gemini responses, so re-runs are free | `tag_with_gemini.py` |

Validate after any edit:

```
api/.venv/bin/python api/scripts/validate_data.py
```

It checks schemas, sibling symmetry, ≥3 tags per card, every leaf on ≥2 cards, prior ranges and
rank, and prints the design-matrix rank plus any element pairs that always co-occur (those share
one wide confidence band in the grammar — the corpus is the experimental design).

## Rights

| Deck | Artist / printer | Year | Source | Licence | Caption used |
|---|---|---|---|---|---|
| Smith 1909 (Waite‑Smith line art) | Pamela Colman Smith | 1909 (first printed Dec 1909, dated 1910 on some scans) | Wikimedia Commons `File:RWS Tarot NN Name.jpg` | Public domain (author died 1951; US publication 1909) | "Pamela Colman Smith, 1909 · public domain" |
| Conver 1760 (Tarot de Marseille) | Nicolas Conver, Marseille | 1760 | Wikimedia Commons `File:<NUMERAL NAME> Nicolas Conver Tarot 1760.jpg`, uploaded by "Tarot World Project" | Artwork public domain; the scan is tagged CC BY‑SA 4.0 by its uploader, so the uploader is credited in `rights_note` | "Nicolas Conver, Marseille, 1760 · public-domain artwork · scan CC BY-SA 4.0 via Wikimedia Commons" |

Rules:

- **Never** use the 1971 U.S. Games recolored edition (copyrighted).
- **Never** write "Rider‑Waite" in a title, tag, caption or note — it is a live trademark. Say
  "Smith 1909" or "Waite‑Smith line art". The validator fails on the trademarked forms.
- Every rendered image carries its `caption` (artist, year · rights).
- Historical meanings (the priors) paraphrase Waite's *Pictorial Key to the Tarot* (1911, public
  domain, Wikisource) and standard Tarot de Marseille readings; each leaf element cites ≥1 card
  where the tradition attests that reading.

## Axis convention (must match `docs/CONTRACT.md` §1)

Eight bipolar scales, values −3..+3, **negative = first pole**:
`active/passive · beginning/ending · giving/withholding · inward/outward · gain/loss · willing/compelled · certain/uncertain · singular/collective`.

## Re-running the Gemini tagging pass

```
GEMINI_API_KEY=… api/.venv/bin/python api/scripts/tag_with_gemini.py          # writes card_elements.gemini.json
GEMINI_API_KEY=… api/.venv/bin/python api/scripts/tag_with_gemini.py --apply  # merges; human rows win
api/.venv/bin/python api/scripts/validate_data.py
```

One request per card (44 total), `gemini-2.5-flash`, JSON-schema output, three retries with
backoff, responses cached. Nothing external runs at demo time — the tags are a file.

## Seed-card suggestions (for `pixie/seeds.py`)

Planted **polysemous** card: `smith-06` (The Lovers) — the tradition itself splits it between
*choice/trial* and *union*, so two coherent reading modes are believable.
Planted **noisy** card: `conver-10` (La Roue de Fortune) — a wheel with three animal figures and
no landscape; a card that plausibly scatters.
Both have a sibling in the other deck that is NOT planted, so the sibling remains a clean control.

## v4 — symbol libraries (`data/libraries.json`, `data/libraries/<id>/elements.json`)

In v4 a card is **composed** from symbol crops placed in five slots, so each base library is an
element sheet whose placeable entries carry `size_class`, `origin`, `source_card`, `bbox`, `image_url`
and a `caption`. Groups (`parent_id: null`) stay in the sheet for grouping only.

| Library | Placeable | Crops | Source scans | Rights |
|---|---|---|---|---|
| `smith1909` | 43 (14 large, 29 small) | 43 rectangular crops | Wikimedia Commons `File:RWS Tarot NN *.jpg` (1909 Rider edition, tagged public domain) | public domain; captions "cut from *Card*, Smith 1909, public domain" |
| `conver1760` | 42 (14 large, 28 small) | 0 (all text tiles, crops pending) | Wikimedia Commons `File:* Nicolas Conver Tarot 1760.jpg` | public-domain artwork; the scans carry a CC BY-SA 4.0 uploader credit |

Crop provenance: `bbox` is a normalised rectangle `[x0, y0, x1, y1]` on the source card image
(`data/cards.json` → `image_url`, cached in `data/_cache/images/`). `api/scripts/build_crops.py`
cuts the rectangle with Pillow, pads it on white to the slot aspect (small 1:1, large 3:4), caps the
longest side at 400 px and writes `api/static/crops/<library>/<id>.png`. No masking, no recolouring,
no redrawing — the crops are honest rectangles of public-domain scans, seams included. Every Smith
crop was checked by eye against the source card. Elements with `bbox: null` render as text tiles
(`origin: "tile"`) and can be cropped later by adding a bbox and re-running the script.

Priors and attestations are carried over unchanged from the v2 vocabulary (Waite 1911 for Smith,
the Marseille tradition for Conver); Conver ids are prefixed `m_` so both libraries can share one
design matrix in a deck. Generated symbols (T2) are stored only in the database, in a deck's
community library, with `origin: "generated"`, no prior and the caption "generated · no attestation".

Rebuild and check:

```bash
api/.venv/bin/python api/scripts/build_crops.py --library smith1909
api/.venv/bin/python api/scripts/build_crops.py --library conver1760
api/.venv/bin/python api/scripts/validate_libraries.py
```
