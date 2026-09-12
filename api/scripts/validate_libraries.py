#!/usr/bin/env python
"""Validate data/libraries.json and every data/libraries/<id>/elements.json (v4 sheets).

Checks: unique element ids across libraries; every placeable element has size_class/origin/caption/
source_card; bbox (when set) in [0,1] with x0<x1, y0<y1; image files exist when image_url is set;
priors are 8 floats in [-3,3]; parents exist; leaf-prior matrix has rank 8 per library. Exit 1 on error.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
errors, warnings = [], []


def err(m):
    errors.append(m)


libs = json.load(open(os.path.join(DATA, "libraries.json")))
seen = {}
for lib in libs:
    for k in ("id", "name", "kind", "source_deck", "source_year", "rights_note"):
        if k not in lib:
            err(f"library {lib.get('id')}: missing {k}")
    path = os.path.join(DATA, "libraries", lib["id"], "elements.json")
    if not os.path.exists(path):
        err(f"library {lib['id']}: no elements.json")
        continue
    els = json.load(open(path))
    ids = {e["id"] for e in els}
    placeable = [e for e in els if e.get("size_class")]
    groups = [e for e in els if not e.get("size_class")]
    n_cut = n_tile = 0
    priors = []
    for e in els:
        if e["id"] in seen:
            err(f"{lib['id']}/{e['id']}: id already used in {seen[e['id']]}")
        seen[e["id"]] = lib["id"]
        if e.get("library_id") != lib["id"]:
            err(f"{lib['id']}/{e['id']}: library_id mismatch")
        if e.get("parent_id") and e["parent_id"] not in ids:
            err(f"{lib['id']}/{e['id']}: unknown parent {e['parent_id']}")
        hp = e.get("historical_prior")
        if hp is not None:
            if len(hp) != 8 or any((not isinstance(v, (int, float))) or v < -3 or v > 3 for v in hp):
                err(f"{lib['id']}/{e['id']}: bad historical_prior")
            elif e.get("size_class"):
                priors.append(hp)
        if not e.get("size_class"):
            continue
        if e["size_class"] not in ("large", "small"):
            err(f"{lib['id']}/{e['id']}: size_class must be large|small")
        if e.get("origin") not in ("cut", "tile", "generated"):
            err(f"{lib['id']}/{e['id']}: origin must be cut|tile|generated")
        for k in ("caption", "source_card"):
            if not e.get(k):
                err(f"{lib['id']}/{e['id']}: missing {k}")
        if "Rider" in json.dumps(e):
            err(f"{lib['id']}/{e['id']}: trademarked deck name present")
        bbox = e.get("bbox")
        if bbox is not None:
            ok = len(bbox) == 4 and all(0 <= v <= 1 for v in bbox) and bbox[0] < bbox[2] and bbox[1] < bbox[3]
            if not ok:
                err(f"{lib['id']}/{e['id']}: bad bbox {bbox}")
        url = e.get("image_url")
        if url:
            if not os.path.exists(os.path.join(ROOT, "api", url.lstrip("/"))):
                err(f"{lib['id']}/{e['id']}: image file missing for {url}")
            if e.get("origin") == "tile":
                err(f"{lib['id']}/{e['id']}: tile with an image_url")
            n_cut += 1
        else:
            if e.get("origin") == "cut":
                err(f"{lib['id']}/{e['id']}: origin cut without image_url (run build_crops.py)")
            n_tile += 1
    rank = int(np.linalg.matrix_rank(np.array(priors))) if priors else 0
    if priors and rank < 8:
        warnings.append(f"{lib['id']}: leaf-prior matrix rank {rank} < 8")
    large = sum(1 for e in placeable if e["size_class"] == "large")
    print(f"{lib['id']:12s} placeable={len(placeable):3d} (large {large}, small {len(placeable)-large})  groups={len(groups)}  crops={n_cut}  tiles={n_tile}  prior rank={rank}")
print(f"total placeable ids: {sum(1 for k in seen)} (unique across libraries: {'yes' if len(seen)==len(set(seen)) else 'no'})")
for w in warnings:
    print("WARN", w)
for e in errors:
    print("ERROR", e)
print("OK" if not errors else f"{len(errors)} error(s)")
sys.exit(1 if errors else 0)
