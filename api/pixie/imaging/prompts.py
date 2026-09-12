"""Prompt assembly exactly per spec §6.2, trademark/living-artist denylist, and how-text validation."""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

# trademarked deck names and a small living-artist list; matched case-insensitively as whole phrases
DENYLIST: tuple[str, ...] = (
    "rider-waite-smith", "rider waite smith", "rider-waite", "rider waite", "rider–waite", "rws deck", "rws",
    "u.s. games", "us games", "usgames", "thoth tarot", "wild unknown", "modern witch tarot", "light seer",
    "kim krans", "lisa sterle", "chris-anne", "yoshi yoshitani", "stasia burrington", "pamela colman smith style",
)

OP_SENTENCES = {
    "add": "add {symbol} ({gloss}) at {where}",
    "remove": "remove {symbol}; fill the area consistently with the surroundings",
    "replace": "replace {symbol} with {to} in the same place and scale",
    "emphasize": "make {symbol} more prominent (larger/more central/higher contrast) by one step",
    "deemphasize": "make {symbol} less prominent (smaller/less central/lower contrast) by one step",
    "reposition": "move {symbol} to {where}, keep its appearance",
    "cosmetic": "{how}",
}
EDIT_FRAME = ("Edit the provided card. Change only: {op}. Keep everything else identical: composition, figures, "
              "colors, line style, border, framing. Same size and aspect.")
GENERATE_TAIL = " Single card, full bleed inside border, no text."


def strip_denylist(text: Optional[str]) -> str:
    """Remove trademarked deck names and listed living artists; collapse whitespace."""
    out = text or ""
    for phrase in sorted(DENYLIST, key=len, reverse=True):
        out = re.sub(r"(?i)\b" + re.escape(phrase).replace(r"\ ", r"[\s\-–]+") + r"\b", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out


def _where(placement_or_region) -> str:
    if placement_or_region is None:
        return "its usual place"
    if isinstance(placement_or_region, str):
        return f"the {placement_or_region}" if placement_or_region != "any" else "a fitting place"
    r = placement_or_region
    try:
        return f"the region x={float(r['x']):.2f} y={float(r['y']):.2f} w={float(r['w']):.2f} h={float(r['h']):.2f}"
    except (KeyError, TypeError, ValueError):
        return "the indicated region"


def symbol_clause(symbol: dict) -> str:
    """'name — gloss' plus ' at {placement}' when the symbol has a fixed placement."""
    name = symbol.get("name") or symbol.get("key") or symbol.get("symbol_id") or "symbol"
    gloss = symbol.get("gloss") or ""
    s = f"{name} — {gloss}".rstrip(" —")
    placement = symbol.get("placement")
    if placement and placement != "any":
        s += f" at {placement}"
    return s


def assemble_generate(style_guide: dict, position_title: Optional[str], symbols: Sequence[dict], prompt_user: Optional[str]) -> str:
    """prompt_full (generate) = style.prompt_prefix + " Position: {title}." + " Symbols: " + join(...) + " " + prompt_user + tail."""
    prefix = (style_guide or {}).get("prompt_prefix") or ""
    parts = [prefix.strip()]
    if position_title:
        parts.append(f"Position: {position_title}.")
    if symbols:
        parts.append("Symbols: " + "; ".join(symbol_clause(s) for s in symbols) + ".")
    user = strip_denylist(prompt_user)
    if user:
        parts.append(user)
    return " ".join(p for p in parts if p) + GENERATE_TAIL


def op_sentence(op: str, symbol: Optional[dict] = None, to_symbol: Optional[dict] = None, placement_or_region=None,
                how_text: str = "") -> str:
    if op not in OP_SENTENCES:
        raise ValueError(f"unknown op {op!r}")
    name = (symbol or {}).get("name") or (symbol or {}).get("key") or "the symbol"
    gloss = (symbol or {}).get("gloss") or ""
    to = (to_symbol or {}).get("name") or (to_symbol or {}).get("key") or "the new symbol"
    return OP_SENTENCES[op].format(symbol=name, gloss=gloss, to=to, where=_where(placement_or_region),
                                   how=strip_denylist(how_text) or "cosmetic adjustment only")


def assemble_edit(op: str, symbol: Optional[dict] = None, to_symbol: Optional[dict] = None, placement_or_region=None,
                  how_text: str = "") -> str:
    """prompt_full (edit) = frame with the op sentence + (how text)."""
    sentence = op_sentence(op, symbol, to_symbol, placement_or_region, how_text)
    out = EDIT_FRAME.format(op=sentence)
    how = strip_denylist(how_text)
    if how and op != "cosmetic":
        out += " " + how
    return out


def validate_how_text(how_text: Optional[str], allowed_symbol_names: Iterable[str], registry_names: Iterable[str]) -> str:
    """Reject 'how' text that names a registry symbol not selected for this edit (style words only).
    Returns the denylist-stripped text."""
    text = strip_denylist(how_text)
    if not text:
        return ""
    allowed = {a.lower() for a in allowed_symbol_names if a}
    offending = []
    for name in registry_names:
        if not name or name.lower() in allowed:
            continue
        if re.search(r"(?i)(?<![\w-])" + re.escape(name) + r"(?![\w-])", text):
            offending.append(name)
    if offending:
        raise ValueError("the how-text names symbols that are not part of this edit: " + ", ".join(sorted(set(offending))))
    return text
