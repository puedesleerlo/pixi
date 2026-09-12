"""Five fixed slots (spec v4 §5, contract §2). A card version is 2–5 elements, one per slot.

Salience of an element on a version is its slot's value. `large` elements may go anywhere,
`small` ones never in `center`. Auto-assignment: pick order; the first `large` takes `center`,
the rest fill top, bottom, left, right; with no `large` picked, `center` stays empty (max 4).
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

SLOTS: dict[str, float] = {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5}
SLOT_ORDER: list[str] = ["center", "top", "bottom", "left", "right"]
FILL_ORDER: list[str] = ["top", "bottom", "left", "right"]
MIN_ELEMENTS = 2
MAX_ELEMENTS = 5
MOVE_TYPES = ("add", "remove", "swap", "move")


def may_occupy(size_class: str | None, slot: str) -> bool:
    return slot != "center" or size_class == "large"


def salience(slot: str) -> float:
    return SLOTS[slot]


def auto_assign(elements: Sequence[Mapping]) -> list[dict]:
    """elements: dicts with `id` and `size_class`, in pick order → [{element_id, slot}]."""
    out: list[dict] = []
    center_taken = False
    fill = iter(FILL_ORDER)
    for e in elements:
        eid = e.get("id") or e.get("element_id")
        if not center_taken and e.get("size_class") == "large":
            out.append({"element_id": eid, "slot": "center"})
            center_taken = True
            continue
        slot = next(fill, None)
        if slot is None:
            raise ValueError("too many elements: without a large element in the center a card holds at most 4")
        out.append({"element_id": eid, "slot": slot})
    return out


def validate_version(elements: Sequence[Mapping], elem_by_id: Mapping[str, Mapping]) -> None:
    """Raise ValueError with a human message when a version breaks the slot rules."""
    n = len(elements)
    if n < MIN_ELEMENTS:
        raise ValueError(f"a card needs at least {MIN_ELEMENTS} elements (got {n})")
    if n > MAX_ELEMENTS:
        raise ValueError(f"a card holds at most {MAX_ELEMENTS} elements (got {n})")
    seen_e: set[str] = set()
    seen_s: set[str] = set()
    for item in elements:
        eid, slot = item.get("element_id"), item.get("slot")
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot!r}")
        if eid not in elem_by_id:
            raise ValueError(f"unknown element {eid!r}")
        e = elem_by_id[eid]
        if not e.get("size_class"):
            raise ValueError(f"{e.get('label', eid)} is a group, not a placeable symbol")
        if eid in seen_e:
            raise ValueError(f"{e.get('label', eid)} is already on the card")
        if slot in seen_s:
            raise ValueError(f"slot {slot} is used twice")
        if not may_occupy(e.get("size_class"), slot):
            raise ValueError(f"{e.get('label', eid)} is a small symbol and cannot take the center")
        seen_e.add(eid)
        seen_s.add(slot)


def design_row(version_elements: Sequence[Mapping], leaf_pos: Mapping[str, int], E: int) -> np.ndarray:
    row = np.zeros(int(E), dtype=float)
    for item in version_elements:
        j = leaf_pos.get(item["element_id"])
        if j is not None:
            row[j] = SLOTS[item["slot"]]
    return row


def free_slots(version_elements: Sequence[Mapping]) -> list[str]:
    used = {it["slot"] for it in version_elements}
    return [s for s in SLOT_ORDER if s not in used]


def apply_move(version_elements: Sequence[Mapping], move: Mapping, elem_by_id: Mapping[str, Mapping]) -> list[dict]:
    """One move → the next version's elements. Exactly one element changes. Raises ValueError otherwise."""
    kind = move.get("type")
    if kind not in MOVE_TYPES:
        raise ValueError(f"move type must be one of {MOVE_TYPES}")
    cur = [{"element_id": it["element_id"], "slot": it["slot"]} for it in version_elements]
    by_eid = {it["element_id"]: it for it in cur}
    eid = move.get("element_id")
    if eid not in elem_by_id:
        raise ValueError(f"unknown element {eid!r}")
    e = elem_by_id[eid]
    label = e.get("label", eid)

    if kind == "add":
        if eid in by_eid:
            raise ValueError(f"{label} is already on the card")
        if len(cur) >= MAX_ELEMENTS:
            raise ValueError("the card is full; remove or swap instead")
        to_slot = move.get("to_slot")
        free = free_slots(cur)
        if to_slot is None:
            cands = [s for s in free if may_occupy(e.get("size_class"), s)]
            if not cands:
                raise ValueError(f"no free slot can take {label}")
            to_slot = cands[0]
        elif to_slot not in SLOTS:
            raise ValueError(f"unknown slot {to_slot!r}")
        elif to_slot not in free:
            raise ValueError(f"slot {to_slot} is taken")
        cur.append({"element_id": eid, "slot": to_slot})

    elif kind == "remove":
        if eid not in by_eid:
            raise ValueError(f"{label} is not on the card")
        if len(cur) <= MIN_ELEMENTS:
            raise ValueError(f"a card keeps at least {MIN_ELEMENTS} elements; swap instead")
        cur = [it for it in cur if it["element_id"] != eid]

    elif kind == "swap":
        to = move.get("to_element_id")
        if eid not in by_eid:
            raise ValueError(f"{label} is not on the card")
        if to not in elem_by_id:
            raise ValueError(f"unknown element {to!r}")
        if to in by_eid:
            raise ValueError(f"{elem_by_id[to].get('label', to)} is already on the card")
        if to == eid:
            raise ValueError("swap needs a different element")
        slot = by_eid[eid]["slot"]
        for it in cur:
            if it["element_id"] == eid:
                it["element_id"] = to

    elif kind == "move":
        to_slot = move.get("to_slot")
        if eid not in by_eid:
            raise ValueError(f"{label} is not on the card")
        if to_slot not in SLOTS:
            raise ValueError(f"unknown slot {to_slot!r}")
        if to_slot == by_eid[eid]["slot"]:
            raise ValueError(f"{label} is already in {to_slot}")
        if to_slot not in free_slots(cur):
            raise ValueError(f"slot {to_slot} is taken")
        for it in cur:
            if it["element_id"] == eid:
                it["slot"] = to_slot

    validate_version(cur, elem_by_id)
    return cur


def describe_move(move: Mapping, elem_by_id: Mapping[str, Mapping]) -> str:
    lab = lambda x: elem_by_id.get(x, {}).get("label", x)  # noqa: E731
    k = move.get("type")
    if k == "add":
        return f"add {lab(move.get('element_id'))}" + (f" ({move['to_slot']})" if move.get("to_slot") else "")
    if k == "remove":
        return f"remove {lab(move.get('element_id'))}"
    if k == "swap":
        return f"swap {lab(move.get('element_id'))} → {lab(move.get('to_element_id'))}"
    if k == "move":
        return f"move {lab(move.get('element_id'))} to {move.get('to_slot')}"
    return str(dict(move))
