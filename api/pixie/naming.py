"""Cluster naming (spec §6.6): K2 names, it never scores. Template fallback = two strongest poles."""
from __future__ import annotations

import os
import re
from typing import Optional, Sequence

from .axes import axes_to_words


def template_label(centroid: Sequence[float]) -> str:
    words = [w for w in axes_to_words(centroid, 2).split(" · ") if w]
    if not words:
        return "Neutral"
    return (words[0].capitalize() + (" " + words[1] if len(words) > 1 else ""))


def naming_backend() -> str:
    return "k2" if os.environ.get("K2_ENDPOINT") else "template"


def _k2_label(texts: Sequence[str], centroid: Sequence[float], top_elements: Sequence[str]) -> Optional[str]:
    endpoint = os.environ.get("K2_ENDPOINT")
    if not endpoint:
        return None
    import httpx  # local import: optional path

    url = endpoint.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("K2_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    quotes = [t.strip() for t in texts if isinstance(t, str) and t.strip()][:12]
    prompt = (
        "You label clusters of short reports about what people received from a symbolic image. "
        "Reply with ONLY a 2-4 word label in plain words, no quotes, no punctuation.\n\n"
        f"Axis centroid: {axes_to_words(centroid, 3) or 'neutral'}\n"
        f"Strongest visual elements: {', '.join(top_elements) or 'none'}\n"
        "Reports:\n" + ("\n".join(f"- {q}" for q in quotes) if quotes else "- (scales only)")
    )
    body = {
        "model": os.environ.get("K2_MODEL", "K2-Think"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16,
        "temperature": 0.2,
    }
    try:
        r = httpx.post(url, json=body, headers=headers, timeout=3.0)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = text.strip().strip('"\'`').strip().splitlines()[0] if text.strip() else ""
    text = re.sub(r"[^\w\s\-]", "", text).strip()
    words = text.split()
    if not (1 <= len(words) <= 6):
        return None
    return " ".join(words[:4])


def name_cluster(texts: Sequence[str], centroid: Sequence[float], top_elements: Sequence[str]) -> dict:
    label = _k2_label(texts, centroid, top_elements)
    if label:
        return {"label": label, "by": "k2"}
    return {"label": template_label(centroid), "by": "template"}
