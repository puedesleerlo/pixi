"""Loaders for the committed corpus (data/*.json) and the design matrix."""
from __future__ import annotations

import json
import os
from typing import Sequence

import numpy as np

from .axes import N_AXES

DEFAULT_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))


def _read(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_corpus(data_dir: str = DEFAULT_DATA_DIR) -> tuple[list, list, list]:
    """→ (cards, elements, card_elements) from cards.json, elements.json, card_elements.json."""
    cards = _read(os.path.join(data_dir, "cards.json"))
    elements = _read(os.path.join(data_dir, "elements.json"))
    card_elements = _read(os.path.join(data_dir, "card_elements.json"))
    return cards, elements, card_elements


def corpus_exists(data_dir: str = DEFAULT_DATA_DIR) -> bool:
    return all(os.path.exists(os.path.join(data_dir, f)) for f in ("cards.json", "elements.json", "card_elements.json"))


def leaf_element_ids(elements: Sequence[dict], card_elements: Sequence[dict]) -> list[str]:
    """Regressors = elements that appear in card_elements (sorted by id). Unknown ids are dropped."""
    known = {e["id"] for e in elements}
    return sorted({ce["element_id"] for ce in card_elements if ce["element_id"] in known})


def design_matrix(cards: Sequence[dict], elements: Sequence[dict], card_elements: Sequence[dict]):
    """→ (X_cards (C, E), leaf_ids, card_index {card_id: row}). X = visual salience, max over duplicate tags."""
    leaf = leaf_element_ids(elements, card_elements)
    eidx = {e: j for j, e in enumerate(leaf)}
    card_index = {c["id"]: i for i, c in enumerate(cards)}
    X = np.zeros((len(cards), len(leaf)), dtype=float)
    for ce in card_elements:
        i = card_index.get(ce["card_id"])
        j = eidx.get(ce["element_id"])
        if i is None or j is None:
            continue
        X[i, j] = max(X[i, j], float(ce.get("visual_salience", 0.0)))
    return X, leaf, card_index


def element_priors(elements: Sequence[dict], leaf_ids: Sequence[str]) -> np.ndarray:
    """(E, 8) historical priors in leaf order; zeros when missing."""
    by_id = {e["id"]: e for e in elements}
    P = np.zeros((len(leaf_ids), N_AXES), dtype=float)
    for j, eid in enumerate(leaf_ids):
        pr = by_id.get(eid, {}).get("historical_prior")
        if pr is not None and len(pr) == N_AXES:
            P[j] = np.asarray(pr, dtype=float)
    return P


def elements_by_id(elements: Sequence[dict]) -> dict:
    return {e["id"]: e for e in elements}


# ----------------------------------------------------------------------------- v4: libraries of placeable symbols
LIBRARIES_FILE = "libraries.json"
LIBRARIES_DIR = "libraries"
FIGURE_GROUPS = {"figure", "posture"}  # fallback size_class = large for these groups


def libraries_exist(data_dir: str = DEFAULT_DATA_DIR) -> bool:
    return os.path.exists(os.path.join(data_dir, LIBRARIES_FILE)) and os.path.isdir(os.path.join(data_dir, LIBRARIES_DIR))


def _fallback_smith_library(data_dir: str) -> tuple[list, list]:
    """Before data/libraries/ exists: one Smith 1909 library built from the v2 element sheet, all text tiles."""
    lib = {
        "id": "smith1909", "name": "Smith 1909", "kind": "base", "source_deck": "Smith 1909", "source_year": 1909,
        "rights_note": "Pamela Colman Smith line art, 1909, public domain (text tiles until crops are built)",
    }
    elements = []
    for e in _read(os.path.join(data_dir, "elements.json")):
        e = dict(e)
        e["library_id"] = "smith1909"
        if e.get("parent_id"):
            e.setdefault("size_class", "large" if e["parent_id"] in FIGURE_GROUPS else "small")
            e.setdefault("origin", "tile")
            e.setdefault("image_url", None)
            e.setdefault("bbox", None)
            src = next((a.get("card_id") for a in e.get("attestations", []) if a.get("card_id")), None)
            e.setdefault("source_card", src)
            e.setdefault("caption", f"{e['label']} · Smith 1909 · text tile")
        else:
            e.setdefault("size_class", None)
            e.setdefault("origin", None)
            e.setdefault("image_url", None)
        elements.append(e)
    return [lib], elements


def load_libraries(data_dir: str = DEFAULT_DATA_DIR) -> tuple[list, list]:
    """→ (libraries, elements) from data/libraries.json + data/libraries/<id>/elements.json.
    Falls back to a tile-only Smith library from data/elements.json when the v4 files are absent."""
    if not libraries_exist(data_dir):
        return _fallback_smith_library(data_dir)
    libraries = _read(os.path.join(data_dir, LIBRARIES_FILE))
    elements: list = []
    seen: set[str] = set()
    for lib in libraries:
        path = os.path.join(data_dir, LIBRARIES_DIR, lib["id"], "elements.json")
        if not os.path.exists(path):
            continue
        for e in _read(path):
            e = dict(e)
            e.setdefault("library_id", lib["id"])
            if e.get("parent_id"):
                e.setdefault("size_class", "small")
                e.setdefault("origin", "cut" if e.get("image_url") else "tile")
                e.setdefault("image_url", None)
            else:
                e.setdefault("size_class", None)
            if e["id"] in seen:
                raise ValueError(f"duplicate element id across libraries: {e['id']}")
            seen.add(e["id"])
            elements.append(e)
    return libraries, elements


def placeable(elements: Sequence[dict]) -> list[dict]:
    """Elements that can sit in a slot (groups have no size_class)."""
    return [e for e in elements if e.get("size_class") in ("large", "small")]


def placeable_ids(elements: Sequence[dict]) -> list[str]:
    return sorted(e["id"] for e in placeable(elements))


def design_matrix_versions(versions: Sequence[dict], leaf_ids: Sequence[str]) -> np.ndarray:
    """(len(versions), E) rows of slot salience; each version is {elements: [{element_id, slot}]}."""
    from .slots import design_row

    pos = {eid: j for j, eid in enumerate(leaf_ids)}
    E = len(leaf_ids)
    if not versions:
        return np.zeros((0, E), dtype=float)
    return np.stack([design_row(v["elements"], pos, E) for v in versions])
