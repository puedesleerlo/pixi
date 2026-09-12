"""Verify Wikimedia Commons file titles and record URL, size and licence metadata.

Usage: python api/scripts/verify_commons.py OUT.json "File:A.jpg" "File:B.jpg" ...
       python api/scripts/verify_commons.py OUT.json --from-file titles.txt
Never guess a URL: a manifest only lists files this script has resolved.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "pixie-hackcmu/0.1 (datos@corlide.org)"}
API = "https://commons.wikimedia.org/w/api.php?"


def verify(titles: list[str], thumb_width: int = 640) -> dict:
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        qs = urllib.parse.urlencode({"action": "query", "titles": "|".join(chunk), "prop": "imageinfo",
                                     "iiprop": "url|extmetadata|size|mime", "iiurlwidth": str(thumb_width), "format": "json"})
        req = urllib.request.Request(API + qs, headers=UA)
        d = json.load(urllib.request.urlopen(req, timeout=60))
        normalized = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for page in d["query"]["pages"].values():
            t = page["title"]
            key = normalized.get(t, t)
            if "missing" in page or "imageinfo" not in page:
                out[key] = {"missing": True}
                continue
            ii = page["imageinfo"][0]
            em = ii.get("extmetadata", {})
            out[key] = {
                "title": t, "url": ii["url"], "thumb": ii.get("thumburl"), "width": ii["width"], "height": ii["height"],
                "mime": ii.get("mime"), "license": em.get("LicenseShortName", {}).get("value"),
                "license_url": em.get("LicenseUrl", {}).get("value"), "artist": em.get("Artist", {}).get("value", "")[:120],
                "date": em.get("DateTimeOriginal", {}).get("value", "")[:40],
                "description_page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(t.replace(' ', '_'))}",
            }
    return out


def main(argv: list[str]) -> None:
    out_path, args = argv[0], argv[1:]
    if args and args[0] == "--from-file":
        titles = [l.strip() for l in open(args[1]) if l.strip()]
    else:
        titles = args
    res = verify(titles)
    json.dump(res, open(out_path, "w"), indent=1, ensure_ascii=False)
    for t, v in res.items():
        print(("MISSING " if v.get("missing") else "ok      ") + t, v.get("license"), v.get("width"), "x", v.get("height"))


if __name__ == "__main__":
    main(sys.argv[1:])
