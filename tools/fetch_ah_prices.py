#!/usr/bin/env python3
"""
Fetch WoW: Forever Auction House prices and write ah-snapshot.json for the
Alchemy Profit Planner (index.html -> Paste / Import -> Import AH snapshot).

Uses the UNOFFICIAL Forever routes found by the community at launch:
  /data/wow/ruleset/{rulesetId}/auctions/index
  /data/wow/ruleset/{rulesetId}/auctions/{houseId}
  /data/wow/ruleset/{rulesetId}/auctions/{houseId}/commodities
with namespace dynamic-forever-{region}. Blizzard may change these.

Credentials (never commit or share these):
  - env vars BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET, or
  - a blizzard_credentials.json in the project folder:
      {"client_id": "...", "client_secret": "..."}
  Create them at https://develop.battle.net/access/clients

Usage:
  python3 fetch_ah_prices.py                       # US, PvP ruleset, Horde
  python3 fetch_ah_prices.py --list-houses         # show house IDs
  python3 fetch_ah_prices.py --house 113           # pick a specific house
  python3 fetch_ah_prices.py --region eu --ruleset normal --faction alliance
  python3 fetch_ah_prices.py --items alchemy-backup.json   # include your custom items

Only the Python standard library is used.
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RULESETS = {"pvp": 1, "normal": 2, "rp": 3, "roleplay": 3, "rppvp": 15, "roleplay-pvp": 15}
UA = "forever-alchemy-planner/1.0"

# Items the planner ships with. Your own items are added with --items <backup.json>.
DEFAULT_ITEMS = [
    "Peacebloom", "Silverleaf", "Earthroot", "Mageroyal", "Briarthorn", "Swiftthistle", "Stranglekelp",
    "Bruiseweed", "Wild Steelbloom", "Grave Moss", "Kingsblood", "Liferoot", "Fadeleaf", "Goldthorn",
    "Khadgar's Whisker", "Wintersbite", "Firebloom", "Purple Lotus", "Wildvine", "Arthas' Tears", "Sungrass",
    "Blindweed", "Ghost Mushroom", "Gromsblood", "Golden Sansam", "Dreamfoil", "Mountain Silversage",
    "Plaguebloom", "Icecap", "Black Lotus", "Demonsage", "Marefoil", "Death Lotus", "Frilled Lichen",
    "Rosecap", "Stranglevine", "Empty Vial", "Leaded Vial", "Crystal Vial", "Imbued Vial",
    "Blackmouth Oil", "Stonescale Oil", "Fire Oil", "Elemental Earth", "Elemental Fire", "Thorium Bar",
    "Arcane Crystal", "Arcanite Bar", "Oily Blackmouth", "Stonescale Eel", "Firefin Snapper",
    "Minor Healing Potion", "Elixir of Lion's Strength", "Elixir of Minor Defense", "Weak Troll's Blood Potion",
    "Minor Mana Potion", "Minor Rejuvenation Potion", "Elixir of Minor Fortitude", "Elixir of Minor Agility",
    "Lesser Healing Potion", "Swiftness Potion", "Elixir of Wisdom", "Elixir of Water Breathing",
    "Healing Potion", "Lesser Mana Potion", "Strong Troll's Blood Potion", "Elixir of Firepower",
    "Elixir of Ogre's Strength", "Free Action Potion", "Greater Healing Potion", "Mana Potion",
    "Lesser Invisibility Potion", "Shadow Oil", "Elixir of Frost Power", "Frost Oil", "Greater Mana Potion",
    "Restorative Potion", "Superior Healing Potion", "Wildvine Potion", "Dreamless Sleep Potion",
    "Elixir of Greater Intellect", "Invisibility Potion", "Elixir of Greater Agility", "Elixir of Giants",
    "Elixir of Shadow Power", "Elixir of Demonslaying", "Limited Invulnerability Potion", "Mighty Rage Potion",
    "Superior Mana Potion", "Elixir of Superior Defense", "Major Healing Potion", "Elixir of Brute Force",
    "Elixir of the Mongoose", "Greater Stoneshield Potion", "Greater Arcane Elixir", "Purification Potion",
    "Greater Fire Protection Potion", "Major Mana Potion", "Flask of the Titans", "Flask of Supreme Power",
    "Flask of Distilled Wisdom", "Flask of Chromatic Resistance", "Flask of Petrification",
]

# Known Classic item IDs. Each is checked against Forever's item database (static-forever-{region})
# before use, which also gives the item's Forever name. Unknown names fall back to item search.
FALLBACK_IDS = {
    "Peacebloom": 2447, "Silverleaf": 765, "Earthroot": 2449, "Mageroyal": 785, "Briarthorn": 2450,
    "Swiftthistle": 2452, "Bruiseweed": 2453, "Stranglekelp": 3820, "Wild Steelbloom": 3355,
    "Grave Moss": 3369, "Kingsblood": 3356, "Liferoot": 3357, "Fadeleaf": 3818, "Goldthorn": 3821,
    "Khadgar's Whisker": 3358, "Wintersbite": 3819, "Firebloom": 4625, "Purple Lotus": 8831,
    "Wildvine": 8153, "Arthas' Tears": 8836, "Sungrass": 8838, "Blindweed": 8839, "Ghost Mushroom": 8845,
    "Gromsblood": 8846, "Golden Sansam": 13464, "Dreamfoil": 13463, "Mountain Silversage": 13465,
    "Plaguebloom": 13466, "Icecap": 13467, "Black Lotus": 13468,
    "Empty Vial": 3371, "Leaded Vial": 3372, "Crystal Vial": 8925, "Imbued Vial": 18256,
    "Minor Healing Potion": 118, "Lesser Healing Potion": 858, "Healing Potion": 929,
    "Greater Healing Potion": 1710, "Superior Healing Potion": 3928, "Major Healing Potion": 13446,
    "Minor Mana Potion": 2455, "Lesser Mana Potion": 3385, "Mana Potion": 3827,
    "Greater Mana Potion": 6149, "Superior Mana Potion": 13443, "Major Mana Potion": 13444,
    "Thorium Bar": 12359, "Arcanite Bar": 12360, "Arcane Crystal": 12363, "Stonescale Oil": 13423,
    "Flask of the Titans": 13510, "Flask of Distilled Wisdom": 13511, "Flask of Supreme Power": 13512,
    "Flask of Chromatic Resistance": 13513, "Flask of Petrification": 13506,
    # verified against static-forever-us on 2026-11-16 (several are renamed in Forever)
    "Elixir of Demonslaying": 9224, "Elixir of Firepower": 6373, "Elixir of Giants": 9206,
    "Elixir of Lion's Strength": 2454, "Elixir of Ogre's Strength": 3391, "Elixir of Water Breathing": 5996,
    "Strong Troll's Blood Potion": 3388, "Weak Troll's Blood Potion": 3382, "Wildvine Potion": 9144,
    "Dreamless Sleep Potion": 12190, "Elixir of Shadow Power": 9264, "Elixir of Superior Defense": 13445,
    "Greater Arcane Elixir": 13454, "Greater Fire Protection Potion": 13457, "Greater Stoneshield Potion": 13455,
    "Invisibility Potion": 9172, "Mighty Rage Potion": 13442, "Purification Potion": 13462,
}


class ApiError(Exception):
    pass


def http_json(url, token=None, basic=None, data=None):
    headers = {"Accept-Encoding": "gzip", "User-Agent": UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if basic:
        headers["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read()
            if r.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            return json.loads(body), dict(r.headers)
    except urllib.error.HTTPError as e:
        snippet = e.read()[:300].decode("utf-8", "replace")
        raise ApiError(f"HTTP {e.code} for {redact(url)}: {snippet}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"Network error for {redact(url)}: {e.reason}") from None


def redact(url):
    return url.split("access_token=")[0]


def load_credentials():
    cid, sec = os.environ.get("BLIZZARD_CLIENT_ID"), os.environ.get("BLIZZARD_CLIENT_SECRET")
    path = os.path.join(ROOT, "blizzard_credentials.json")
    if (not cid or not sec) and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        cid, sec = c.get("client_id"), c.get("client_secret")
    if not cid or not sec:
        sys.exit("No credentials. Set BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET, or create "
                 "blizzard_credentials.json in the project folder (see the top of this file).")
    return cid, sec


def get_token(oauth_url, cid, sec):
    j, _ = http_json(oauth_url, basic=f"{cid}:{sec}", data={"grant_type": "client_credentials"})
    if "access_token" not in j:
        raise ApiError("Token response had no access_token")
    return j["access_token"]


def find_houses(index_json):
    """Return [{'id','name','href'}] from an auctions/index response, whatever its top-level key."""
    houses = []

    def walk(o):
        if isinstance(o, dict):
            if "id" in o and isinstance(o.get("key"), dict) and "href" in o["key"]:
                name = o.get("name")
                if isinstance(name, dict):
                    name = name.get("en_US") or next(iter(name.values()), "")
                houses.append({"id": o["id"], "name": name or "", "href": o["key"]["href"]})
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(index_json)
    return houses


def rebase(href, api_base):
    """Follow an API href but keep our chosen host (so --api-base works for testing)."""
    p = urllib.parse.urlparse(href)
    return api_base.rstrip("/") + p.path + ("?" + p.query if p.query else "")


def with_ns(url, ns):
    p = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(p.query))
    q.setdefault("namespace", ns)
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q)))


def collect_listings(auctions_json, kind, out):
    for a in auctions_json.get("auctions") or []:
        item_id = (a.get("item") or {}).get("id")
        qty = a.get("quantity") or 0
        if not item_id or qty <= 0:
            continue
        if kind == "commodity":
            unit = a.get("unit_price")
        else:
            unit = a.get("unit_price")
            if unit is None and a.get("buyout") is not None:
                unit = a["buyout"] / qty
        if unit is None:  # bid-only listing: no usable asking price
            continue
        out.setdefault(item_id, []).append((float(unit), int(qty)))


def weighted_pct(listings, pct):
    """Unit price at which `pct` of the listed quantity is available (listings sorted by price)."""
    total = sum(q for _, q in listings)
    target = total * pct
    run = 0
    for price, q in listings:
        run += q
        if run >= target:
            return price
    return listings[-1][0]


def item_name(api, region, item_id, token):
    """Forever name for an item id, or None if Forever's item database doesn't have it."""
    try:
        j, _ = http_json(f"{api}/data/wow/item/{item_id}?namespace=static-forever-{region}", token=token)
    except ApiError:
        return None
    n = j.get("name")
    return n.get("en_US") if isinstance(n, dict) else n


def search_id(api, region, name, token):
    """Exact-name match via item search. Search is fuzzy and capped, so this is only a fallback."""
    for ns in (f"static-forever-{region}", f"static-classic1x-{region}"):
        url = (f"{api}/data/wow/search/item?" +
               urllib.parse.urlencode({"namespace": ns, "name.en_US": name, "orderby": "id", "_pageSize": 1000}))
        try:
            j, _ = http_json(url, token=token)
        except ApiError:
            continue
        for r in j.get("results", []):
            d = r.get("data", {})
            n = d.get("name", {})
            n = n.get("en_US") if isinstance(n, dict) else n
            if n and n.lower() == name.lower():
                return d.get("id")
    return None


def resolve_ids(names, api, region, token, cache_path, refresh):
    cache = {}
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    changed = False
    for name in names:
        hit = cache.get(name)
        if hit and hit.get("forever_name"):
            continue
        found = None
        candidates = [(FALLBACK_IDS[name], "known id")] if name in FALLBACK_IDS else []
        sid = search_id(api, region, name, token) if not candidates else None
        if sid:
            candidates.append((sid, "search"))
        for cid, how in candidates:
            fname = item_name(api, region, cid, token)
            if fname:
                found = {"id": cid, "source": how, "forever_name": fname}
                break
        cache[name] = found
        changed = True
    if changed:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
    return cache


def main():
    ap = argparse.ArgumentParser(description="Fetch WoW: Forever AH prices for the Alchemy Profit Planner.")
    ap.add_argument("--region", default="us", choices=["us", "eu"])
    ap.add_argument("--ruleset", default="pvp", help="pvp | normal | rp | rppvp, or a numeric ruleset id")
    ap.add_argument("--faction", default="horde", choices=["horde", "alliance", "blackwater", "neutral"])
    ap.add_argument("--house", type=int, help="auction house id (see --list-houses)")
    ap.add_argument("--list-houses", action="store_true")
    ap.add_argument("--items", help="planner backup JSON; its item names are priced too")
    ap.add_argument("--out", help="output file (default: data/ah-snapshot-house<ID>.json)")
    ap.add_argument("--refresh-ids", action="store_true", help="re-resolve item names to ids")
    ap.add_argument("--api-base", help=argparse.SUPPRESS)   # testing
    ap.add_argument("--oauth-url", default="https://oauth.battle.net/token", help=argparse.SUPPRESS)
    a = ap.parse_args()

    rs = int(a.ruleset) if str(a.ruleset).isdigit() else RULESETS.get(a.ruleset.lower())
    if rs is None:
        sys.exit(f"Unknown ruleset {a.ruleset!r}. Use pvp, normal, rp, rppvp or a number.")
    api = (a.api_base or f"https://{a.region}.api.blizzard.com").rstrip("/")
    ns = f"dynamic-forever-{a.region}"

    try:
        token = get_token(a.oauth_url, *load_credentials())
        idx, _ = http_json(f"{api}/data/wow/ruleset/{rs}/auctions/index?namespace={ns}", token=token)
        houses = find_houses(idx)
        if not houses:
            raise ApiError("auctions/index returned no houses")

        if a.list_houses:
            print(f"Auction houses under ruleset {rs} ({a.region.upper()}):")
            for h in sorted(houses, key=lambda h: h["id"]):
                print(f"  {h['id']:>5}  {h['name']}")
            return

        if a.house:
            house = next((h for h in houses if h["id"] == a.house), None)
            if not house:
                raise ApiError(f"House {a.house} isn't in the ruleset {rs} index. Try --list-houses.")
        else:
            word = "blackwater" if a.faction in ("blackwater", "neutral") else a.faction
            cands = sorted([h for h in houses if word in h["name"].lower()], key=lambda h: h["id"])
            if word == "blackwater" and not cands:
                cands = sorted([h for h in houses if "neutral" in h["name"].lower()], key=lambda h: h["id"])
            if not cands:
                raise ApiError(f"No {a.faction} house found. Use --list-houses and --house.")
            house = cands[0]
            if len(cands) > 1:
                print(f"Note: {len(cands)} {a.faction} houses listed ({', '.join(str(h['id']) for h in cands)}); "
                      f"using {house['id']}. Use --house to choose another.", file=sys.stderr)

        url = with_ns(rebase(house["href"], api), ns)
        print(f"Downloading house {house['id']} ({house['name']}), ruleset {rs}, {a.region.upper()}...")
        main_json, hdr = http_json(url, token=token)
        listings = {}
        collect_listings(main_json, "auction", listings)
        n_reg = sum(len(v) for v in listings.values())
        com_href = (main_json.get("commodities") or {}).get("href")
        n_com = 0
        if com_href:
            cj, _ = http_json(with_ns(rebase(com_href, api), ns), token=token)
            before = sum(len(v) for v in listings.values())
            collect_listings(cj, "commodity", listings)
            n_com = sum(len(v) for v in listings.values()) - before
        print(f"  {n_reg:,} regular + {n_com:,} commodity listings, {len(listings):,} distinct items")

        # Item ids come from forever_data.json (written by fetch_forever_recipes.py).
        known = {}
        fd = os.path.join(DATA, "forever_data.json")
        if os.path.exists(fd):
            with open(fd, encoding="utf-8") as fh:
                known = {it["name"]: it["id"] for it in json.load(fh)["items"]}
        else:
            print("forever_data.json not found; using the built-in item list.", file=sys.stderr)
        names = list(known) or list(DEFAULT_ITEMS)
        if a.items:
            with open(a.items, encoding="utf-8") as fh:
                backup = json.load(fh)
            for it in (backup.get("items") or {}).values():
                if it.get("name") and it["name"] not in names:
                    names.append(it["name"])
                    if it.get("id"):
                        known[it["name"]] = it["id"]
        ids = {n: {"id": i, "source": "forever_data", "forever_name": n} for n, i in known.items()}
        rest = [n for n in names if n not in ids]
        if rest:
            print(f"Resolving {len(rest)} item names to ids (cached after the first run)...")
            ids.update(resolve_ids(rest, api, a.region, token, os.path.join(DATA, "item_ids.json"), a.refresh_ids))

        prices, missing, unresolved = {}, [], []
        for name in names:
            info = ids.get(name)
            if not info or not info.get("id"):
                unresolved.append(name)
                continue
            ls = sorted(listings.get(info["id"], []))
            if not ls:
                missing.append(name)
                continue
            prices[name] = {
                "item_id": info["id"],
                "id_source": info["source"],
                "forever_name": info.get("forever_name"),
                "min": round(ls[0][0]),
                "low": round(weighted_pct(ls, 0.10)),
                "median": round(weighted_pct(ls, 0.50)),
                "quantity": sum(q for _, q in ls),
                "listings": len(ls),
            }

        snap = {
            "source": "wow-forever-ah",
            "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "last_modified": hdr.get("Last-Modified"),
            "region": a.region, "ruleset": rs, "house": {"id": house["id"], "name": house["name"]},
            "listings_total": n_reg + n_com,
            "prices": prices, "no_listings": missing, "unresolved": unresolved,
        }
        out_path = a.out or os.path.join(DATA, f"ah-snapshot-house{house['id']}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1)
        print(f"Priced {len(prices)} items; {len(missing)} had no listings; {len(unresolved)} names unresolved.")
        if unresolved:
            print("  Unresolved: " + ", ".join(unresolved))
        print(f"Wrote {out_path}. Run tools/build_page.py to put it on the page.")
    except ApiError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
