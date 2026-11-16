#!/usr/bin/env python3
"""
Download WoW: Forever Alchemy, First Aid and Herbalism recipes plus item data
(vendor prices, item types) from Blizzard's Game Data API and write
forever_data.json for the Alchemy Profit Planner and fetch_ah_prices.py.

Run again after a game patch. Uses the same credentials as fetch_ah_prices.py.
  python3 fetch_forever_recipes.py [--region us|eu] [--include-sod]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import fetch_ah_prices as f

PROFESSIONS = ["Alchemy", "Blacksmithing", "Enchanting", "Engineering", "Leatherworking", "Tailoring",
               "Cooking", "First Aid", "Fishing", "Herbalism", "Mining", "Skinning"]
# Professions whose recipes may create no item (enchants are applied to gear directly).
NO_ITEM_OK = {"Enchanting"}
# Items a vendor actually sells. The API gives every item a purchase price, so it can't tell us this.
VENDOR_ITEMS = {
    "Empty Vial", "Leaded Vial", "Crystal Vial", "Imbued Vial", "Mild Spices", "Hot Spices", "Soothing Spices",
    "Simple Wood", "Fine Thread", "Silken Thread", "Heavy Silken Thread", "Refreshing Spring Water",
    "Thunder Ale", "Bottle of Dalaran Noir", "Skin of Dwarven Stout", "Flagon of Dwarven Honeymead",
    # Tailoring and Blacksmithing trade supplies
    "Coarse Thread", "Rune Thread", "Bleach", "Gray Dye", "Red Dye", "Pink Dye", "Blue Dye", "Green Dye",
    "Black Dye", "Orange Dye", "Purple Dye", "Yellow Dye", "Weak Flux", "Strong Flux", "Coal",
}
SKIP_CATEGORIES = {"SEASON OF DISCOVERY"}


def outputs_names(recipes):
    """Crafted items aren't vendor reagents even if Classic sold them (keeps profit math honest)."""
    return {r["output"] for r in recipes if r["output"]}


QUALITY = {"POOR": 0, "COMMON": 1, "UNCOMMON": 2, "RARE": 3, "EPIC": 4, "LEGENDARY": 5, "ARTIFACT": 6}


def tooltip(it):
    """Compact in-game style tooltip lines: [text, style] or [text, style, right-aligned text].
    Styles: w white, g green (Equip/Use), y yellow (flavor/teaches), m muted, s sell price (copper in text)."""
    pv = it.get("preview_item") or {}
    L = []
    if pv.get("binding"):
        L.append([pv["binding"]["name"], "w"])
    if pv.get("unique_equipped"):
        L.append([pv["unique_equipped"] if isinstance(pv["unique_equipped"], str) else "Unique", "w"])
    inv = (pv.get("inventory_type") or {}).get("name")
    sub = (pv.get("item_subclass") or {}).get("name")
    if pv.get("is_equippable") or (inv and inv not in ("Non-equippable", "Bag")):
        L.append([inv or "", "w", "" if pv.get("is_subclass_hidden") else (sub or "")])
    if pv.get("container_slots"):
        L.append([pv["container_slots"]["display_string"], "w"])
    w = pv.get("weapon")
    if w:
        L.append([w["damage"]["display_string"], "w", (w.get("attack_speed") or {}).get("display_string", "")])
        if w.get("dps"):
            L.append([w["dps"]["display_string"], "w"])
    if pv.get("armor"):
        L.append([pv["armor"]["display"]["display_string"], "w"])
    for st in pv.get("stats") or []:
        d = (st.get("display") or {}).get("display_string")
        if d:
            L.append([d, "g" if st.get("is_equip_bonus") else "w"])
    if pv.get("durability"):
        L.append([pv["durability"]["display_string"], "w"])
    req = pv.get("requirements") or {}
    for k in ("playable_classes", "level", "skill", "reputation"):
        if req.get(k, {}).get("display_string"):
            L.append([req[k]["display_string"], "w"])
    for sp in pv.get("spells") or []:
        if sp.get("description"):
            L.append([sp["description"], "g"])
    if pv.get("set"):
        L.append([(pv["set"].get("display_string") or pv["set"].get("item_set", {}).get("name") or ""), "y"])
    if pv.get("description"):
        L.append([pv["description"], "y"])
    rec = pv.get("recipe")
    if rec and rec.get("reagents_display_string"):
        L.append(["Requires " + rec["reagents_display_string"], "w"])
    if it.get("sell_price"):
        L.append([str(it["sell_price"]), "s"])
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="us", choices=["us", "eu"])
    ap.add_argument("--include-sod", action="store_true", help="keep the 'Season of Discovery' category")
    ap.add_argument("--out", default=os.path.join(f.DATA, "forever_data.json"))
    a = ap.parse_args()
    api, ns = f"https://{a.region}.api.blizzard.com", f"static-forever-{a.region}"
    tok = f.get_token("https://oauth.battle.net/token", *f.load_credentials())

    def g(path):
        try:
            return f.http_json(f"{api}{path}?namespace={ns}&locale=en_US", token=tok)[0]
        except f.ApiError:
            return None

    idx = g("/data/wow/profession/index") or sys.exit("Couldn't read the profession index.")
    todo = []
    for p in idx["professions"]:
        if p["name"] not in PROFESSIONS:
            continue
        prof = g(f"/data/wow/profession/{p['id']}")
        for t in prof.get("skill_tiers", []):
            tier = g(f"/data/wow/profession/{p['id']}/skill-tier/{t['id']}") or {}
            for c in tier.get("categories", []):
                if c["name"] in SKIP_CATEGORIES and not a.include_sod:
                    continue
                for r in c.get("recipes", []):
                    todo.append((p["name"], c["name"].title() if c["name"].isupper() else c["name"], r["id"]))
    print(f"{len(todo)} recipes; downloading details...")
    with ThreadPoolExecutor(8) as ex:
        details = list(ex.map(lambda x: g(f"/data/wow/recipe/{x[2]}"), todo))

    item_ids = set()
    for d in details:
        if d:
            if d.get("crafted_item"):
                item_ids.add(d["crafted_item"]["id"])
            item_ids.update(r["reagent"]["id"] for r in d.get("reagents", []))
    ids = sorted(item_ids)
    print(f"{len(ids)} items; downloading details...")
    with ThreadPoolExecutor(8) as ex:
        items = dict(zip(ids, ex.map(lambda i: g(f"/data/wow/item/{i}"), ids)))

    # Recipe items ("Recipe: X", "Manual: X") carry the skill needed to learn them.
    learn = {}  # crafted item id -> recipe-item info
    recipe_item_ids = set()
    for sub in range(1, 10):  # item class 9 (Recipe): 1 LW, 2 Tailoring, 3 Eng, 4 BS, 5 Cooking, 6 Alchemy, 7 First Aid, 8 Enchanting, 9 Fishing
        page = 1
        while True:
            try:
                j = f.http_json(f"{api}/data/wow/search/item?namespace={ns}&item_class.id=9&item_subclass.id={sub}"
                                f"&orderby=id&_pageSize=1000&_page={page}", token=tok)[0]
            except f.ApiError:
                break
            recipe_item_ids.update(r["data"]["id"] for r in j.get("results", []))
            if page >= j.get("pageCount", 1):
                break
            page += 1
    with ThreadPoolExecutor(8) as ex:
        ritems = list(ex.map(lambda i: g(f"/data/wow/item/{i}"), sorted(recipe_item_ids)))
    learn_by_name = {}
    for ri in ritems:
        pv = (ri or {}).get("preview_item") or {}
        made = (((pv.get("recipe") or {}).get("item") or {}).get("item") or {}).get("id")
        sk = ((pv.get("requirements") or {}).get("skill") or {})
        if made:
            learn[made] = {"item": ri["name"], "item_id": ri["id"], "skill": sk.get("level"),
                           "profession": (sk.get("profession") or {}).get("name"),
                           "vbuy": ri.get("purchase_price") or None, "vsell": ri.get("sell_price") or None,
                           "quality": (ri.get("quality") or {}).get("name")}
        if ri and ": " in ri["name"] and sk.get("level"):
            # "Formula: Enchant Bracer - Minor Health" teaches the recipe "Enchant Bracer - Minor Health"
            learn_by_name[ri["name"].split(": ", 1)[1]] = {
                "item": ri["name"], "item_id": ri["id"], "skill": sk.get("level"),
                "profession": (sk.get("profession") or {}).get("name"),
                "vbuy": ri.get("purchase_price") or None, "vsell": ri.get("sell_price") or None,
                "quality": (ri.get("quality") or {}).get("name")}
    print(f"{len(learn)} recipe items with skill requirements")

    # Trainer skill levels aren't in Blizzard's API. wowhead_skills.json holds them (copied from Wowhead's
    # Forever trainer pages): {"recipes": {name: {"skill", "colors": [orange, yellow, green, grey], "source"}}}
    trainer_skills = {}
    ws = os.path.join(f.DATA, "wowhead_skills.json")
    if os.path.exists(ws):
        with open(ws, encoding="utf-8") as fh:
            trainer_skills = json.load(fh).get("recipes", {})

    wowhead_sources = {}
    wsrc = os.path.join(f.DATA, "wowhead_sources.json")
    if os.path.exists(wsrc):
        with open(wsrc, encoding="utf-8") as fh:
            wowhead_sources = json.load(fh).get("recipes", {})

    recipes, skipped = [], []
    for (prof, cat, rid), d in zip(todo, details):
        ci = (d or {}).get("crafted_item")
        reag_ok = d and all(items.get(r["reagent"]["id"]) for r in d.get("reagents", []))
        no_item = bool(d) and not ci and prof in NO_ITEM_OK and reag_ok and d.get("reagents")
        if not no_item and (not ci or not items.get(ci["id"])):
            skipped.append((d or {}).get("name", rid))
            continue
        out = items[ci["id"]] if ci else None
        recipes.append({
            "id": rid, "name": d["name"], "prof": prof, "cat": cat,
            "output": out["name"] if out else None, "output_id": ci["id"] if ci else None,
            "yield": (d.get("crafted_quantity") or {}).get("value", 1),
            "req": (out or {}).get("required_level") or 0,
            "learn": (learn.get(ci["id"]) if ci else None) or learn_by_name.get(d["name"]),
            "trainer": trainer_skills.get(d["name"]),
            "wowhead": wowhead_sources.get(d["name"]),
            "reagents": [{"qty": r["quantity"], "item": r["reagent"]["name"], "id": r["reagent"]["id"]}
                         for r in d.get("reagents", [])],
        })
    outputs = {r["output_id"] for r in recipes if r["output_id"]}
    vendor_names = set(VENDOR_ITEMS)
    cv = os.path.join(f.DATA, "classic_vendor_items.json")
    if os.path.exists(cv):
        with open(cv, encoding="utf-8") as fh:
            vendor_names |= set(json.load(fh)["items"])
    vendor_names -= outputs_names(recipes)
    out_items = []
    for i, it in items.items():
        if not it:
            continue
        sub = (it.get("item_subclass") or {}).get("name", "")
        name = it["name"]
        typ = ("herb" if sub == "Herb" else "vendor" if name in vendor_names
               else "product" if i in outputs else "reagent")
        pq = it.get("purchase_quantity") or 1
        out_items.append({
            "id": i, "name": name, "type": typ, "class": sub,
            "vbuy": round(it["purchase_price"] / pq) if name in vendor_names and it.get("purchase_price") else None,
            "vsell": it.get("sell_price") or None,
            "ilvl": it.get("level"),
            "q": QUALITY.get((it.get("quality") or {}).get("type"), 1),
            "tt": tooltip(it),
        })
    ritem_by_id = {ri["id"]: ri for ri in ritems if ri}
    for lv in learn.values():
        if lv["item_id"] in {r["learn"]["item_id"] for r in recipes if r["learn"]}:
            out_items.append({"id": lv["item_id"], "name": lv["item"], "type": "recipe", "class": "Recipe",
                              "vbuy": None, "vsell": lv["vsell"],
                              "q": QUALITY.get(((ritem_by_id.get(lv["item_id"]) or {}).get("quality") or {}).get("type"), 1),
                              "tt": tooltip(ritem_by_id.get(lv["item_id"]) or {})})
    data = {"source": "Blizzard Game Data API", "namespace": ns, "patch": (idx["_links"]["self"]["href"].split("namespace=static-")[-1]),
            "recipes": recipes, "items": sorted(out_items, key=lambda x: x["name"]), "skipped": skipped}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    print(f"Wrote {a.out}: {len(recipes)} recipes, {len(out_items)} items. Skipped (item not in Forever): {', '.join(map(str, skipped)) or 'none'}")


if __name__ == "__main__":
    main()
