#!/usr/bin/env python3
"""
Read recipe skill levels (orange/yellow/green/grey) and sources for WoW: Forever professions from
seemeta.com's public profession pages, and write seemeta_skills.json keyed by crafted item ID.

  python3 fetch_seemeta_skills.py
"""
import gzip
import html
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
PAGES = {
    "Alchemy": "alchemy", "Blacksmithing": "blacksmithing", "Enchanting": "enchanting", "Engineering": "engineering",
    "Leatherworking": "leatherworking", "Tailoring": "tailoring", "Cooking": "cooking", "First Aid": "first-aid",
    "Fishing": "fishing", "Herbalism": "herbalism", "Mining": "mining", "Skinning": "skinning",
}
BASE = "https://seemeta.com/en/wow-forever/professions/"


def get(url, tries=4):
    for n in range(tries):
        try:
            return _get(url)
        except (urllib.error.URLError, OSError):
            if n == tries - 1:
                raise
            import time
            time.sleep(3 * (n + 1))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "forever-crafting-planner/1.0", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=90) as r:
        b = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            b = gzip.decompress(b)
        return b.decode("utf-8", "replace")


def text(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse(page):
    out = []
    # Each recipe: <a data-name href=".../item=ID"> ... <span data-t ...>Name</span> ... <p data-skill>4 spans</p><p data-src>...</p>
    for m in re.finditer(r'<a data-name href="[^"]*?(item|spell)=(\d+)"(.*?)<p data-skill>(.*?)</p>\s*<p data-src>(.*?)</p>', page, re.S):
        kind, oid, head, skill_html, src_html = m.groups()
        name = re.search(r"<span data-t[^>]*>(.*?)</span>", head, re.S)
        nums = [int(x) for x in re.findall(r"<span>\s*(\d+)\s*<!--", skill_html)]
        # Trainer recipes omit the first (learn/orange) value and show only yellow, green, grey.
        trainer_only = "Learned from a trainer" in skill_html and len(nums) == 3
        src = text(src_html)
        src = re.sub(r"^Source\s*", "", src)
        out.append({"kind": kind, "id": int(oid), "name": text(name.group(1)) if name else None,
                    "colors": ([None] + nums[:3]) if trainer_only else nums[:4],
                    "skill": None if trainer_only else (nums[0] if nums else None), "source": src})
    return out


def main():
    result, report = {}, []
    for prof, slug in PAGES.items():
        try:
            rows = parse(get(BASE + slug))
        except (urllib.error.URLError, OSError) as e:
            report.append(f"{prof}: failed ({e})")
            continue
        result[prof] = rows
        report.append(f"{prof}: {len(rows)} recipes")
    with open(os.path.join(DATA, "seemeta_skills.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": BASE, "professions": result}, fh, indent=1)
    print("; ".join(report))


if __name__ == "__main__":
    main()
