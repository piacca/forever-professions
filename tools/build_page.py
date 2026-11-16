#!/usr/bin/env python3
"""
Rebuild index.html's embedded data from forever_data.json and the ah-snapshot-house*.json files,
and write a skeleton-free copy for publishing (artifact.html).

  python3 build_page.py [--houses 113 114 120 124] [--artifact-out PATH]
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


def fit(points):
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    b = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, _ in points)
    return my - b * mx, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--houses", nargs="*", type=int, default=[113, 114, 120, 124])
    ap.add_argument("--artifact-out", default=os.path.join(ROOT, "artifact.html"))
    a = ap.parse_args()

    fd = json.load(open(os.path.join(DATA, "forever_data.json"), encoding="utf-8"))
    ilvl = {i["name"]: i.get("ilvl") for i in fd["items"]}
    import statistics

    def known_skill(r):
        return ((r.get("learn") or {}).get("skill") or (r.get("trainer") or {}).get("skill")
                or (r.get("wowhead") or {}).get("skill"))

    def load(name, key):
        p = os.path.join(DATA, name)
        return json.load(open(p, encoding="utf-8"))[key] if os.path.exists(p) else {}

    seemeta_rows = load("seemeta_skills.json", "professions")
    seemeta_id = {prof: {row["id"]: row for row in rows if row["kind"] == "item"} for prof, rows in seemeta_rows.items()}
    seemeta_name = {prof: {row["name"]: row for row in rows if row["name"]} for prof, rows in seemeta_rows.items()}
    classic = load("classic_skills.json", "skills")

    def sm_row(r):
        return ((seemeta_id.get(r["prof"]) or {}).get(r["output_id"]) if r["output_id"] else None) \
            or (seemeta_name.get(r["prof"]) or {}).get(r["name"])

    def exact(r):
        sm = sm_row(r)
        return known_skill(r) or (sm and sm["skill"])

    def classic_skill(r):
        return (classic.get(str(r["output_id"])) or {}).get(r["prof"]) if r["output_id"] else None

    # Per profession, decide how far Classic data can be trusted: compare it with recipes whose Forever skill is exact.
    # Many agree exactly ("classic"); some professions were rescaled ("converted" via a learned Classic->Forever map).
    strategy, conv, gap, models, report = {}, {}, {}, {}, []
    for prof in sorted({r["prof"] for r in fd["recipes"]}):
        rs = [r for r in fd["recipes"] if r["prof"] == prof]
        pairs = [(classic_skill(r), exact(r)) for r in rs if classic_skill(r) and exact(r)]
        same = sum(1 for c, e in pairs if c == e)
        m = {}
        for c, e in pairs:
            m.setdefault(c, []).append(e)
        conv[prof] = {c: statistics.median(v) for c, v in m.items()}
        if len(pairs) >= 5 and same / len(pairs) >= 0.8:
            strategy[prof] = "classic"
        elif len(pairs) >= 30:
            strategy[prof] = "converted"
        # typical gap between learn skill (orange) and yellow, from rows where all four values are known
        g = [row["colors"][1] - row["colors"][0] for row in seemeta_rows.get(prof, [])
             if row["colors"] and len(row["colors"]) == 4 and row["colors"][0] is not None]
        if g:
            gap[prof] = statistics.median(g)
        pts = [(ilvl[r["output"]], exact(r)) for r in rs if exact(r) and r["output"] and ilvl.get(r["output"])]
        if len(pts) > 30:
            models[prof] = fit(pts)
        report.append(f"{prof}: Classic agrees {same}/{len(pairs)} -> {strategy.get(prof, 'not used')}")

    def convert(prof, c):
        m = conv.get(prof) or {}
        if not m:
            return None
        if c in m:
            return m[c]
        ks = sorted(m)
        lo = [k for k in ks if k < c]
        hi = [k for k in ks if k > c]
        if lo and hi:
            a_, b_ = lo[-1], hi[0]
            return m[a_] + (m[b_] - m[a_]) * (c - a_) / (b_ - a_)
        return m[lo[-1]] if lo else m[hi[0]]

    def r5(v):
        return max(1, int(round(v / 5.0) * 5))

    def resolve(r):
        """[skill, kind, colors, auto]; kind = exact | classic | converted | yellow | ilvl | None."""
        sm = sm_row(r)
        colors = (r.get("trainer") or {}).get("colors") or (sm["colors"] if sm and len(sm["colors"]) == 4 else None)
        auto = bool(sm and sm["source"].startswith("Learned automatically"))
        k = exact(r)
        if k:
            return [k, "exact", colors, auto]
        yellow = colors[1] if colors else None
        cap = (lambda v: min(v, yellow) if yellow else v)
        c = classic_skill(r)
        st = strategy.get(r["prof"])
        if c and st == "classic":
            return [cap(c), "classic", colors, auto]
        if c and st == "converted":
            v = convert(r["prof"], c)
            if v is not None:
                return [r5(cap(v)), "converted", colors, auto]
        if yellow and r["prof"] in gap:
            return [r5(max(1, yellow - gap[r["prof"]])), "yellow", colors, auto]
        if r["prof"] in models and r["output"] and ilvl.get(r["output"]):
            a0, b0 = models[r["prof"]]
            return [min(300, r5(cap(a0 + b0 * ilvl[r["output"]]))), "ilvl", colors, auto]
        return [None, None, colors, auto]

    data = {
        "patch": fd["patch"],
        "items": [[i["id"], i["name"], i["type"], i["vbuy"], i["vsell"], i.get("q", 1), i.get("tt") or []] for i in fd["items"]],
        "recipes": [[
            r["name"], r["prof"], r["cat"], r["req"], r["output"], r["yield"],
            [[x["qty"], x["item"]] for x in r["reagents"]],
            [r["learn"]["item"], r["learn"]["skill"], r["learn"]["vbuy"]] if r.get("learn") else None,
            [r["trainer"]["skill"], r["trainer"]["colors"], r["trainer"]["source"], r["trainer"].get("trainers", [])]
            if r.get("trainer") else None,
            [r["wowhead"]["skill"], r["wowhead"]["source"]] if r.get("wowhead") else None,
            resolve(r),
        ] for r in fd["recipes"]],
    }

    markets = []
    for h in a.houses:
        p = os.path.join(DATA, f"ah-snapshot-house{h}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        markets.append({
            "listings": d.get("listings_total"),
            "house": d["house"], "ruleset": d["ruleset"], "region": d["region"], "generated": d["generated"],
            "no_listings": d["no_listings"],
            "prices": {k: {"low": v["low"], "median": v["median"], "min": v["min"], "q": v["quantity"]}
                       for k, v in d["prices"].items()},
        })

    page = os.path.join(ROOT, "index.html")
    s = open(page, encoding="utf-8").read()
    s = re.sub(r"const FOREVER_DATA=\{.*?\};\n",
               lambda m: "const FOREVER_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n", s, count=1, flags=re.S)
    s = re.sub(r"const MARKETS=\[.*?\];\n",
               lambda m: "const MARKETS=" + json.dumps(markets, separators=(",", ":")) + ";\n", s, count=1, flags=re.S)
    open(page, "w", encoding="utf-8").write(s)

    art = (s.replace('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                     '<meta name="viewport" content="width=device-width, initial-scale=1">\n', "")
            .replace("</head>\n<body>\n", "").replace("</body>\n</html>\n", ""))
    open(a.artifact_out, "w", encoding="utf-8").write(art)
    from collections import Counter
    kinds = Counter((r[1], r[10][1]) for r in data["recipes"])
    print("Skill sources:", dict(sorted(kinds.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))))
    print("\n".join(report))
    print(f"Built: {len(data['recipes'])} recipes, {len(data['items'])} items, {len(markets)} markets, {len(s)//1024} KB.")


if __name__ == "__main__":
    main()
