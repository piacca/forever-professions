# Forever Crafting Planner

A fan-made profit planner for **World of Warcraft: Forever**. Pick a profession, and it shows what each recipe costs to craft (reagents from vendors or the Auction House) against what the finished item sells for. You can also see how each recipe is learned and at what skill.

![Forever Crafting Planner](docs/screenshot.png)

## Use it

Open `index.html` in a browser. Everything is in that one file, and nothing to install. If the repo has GitHub Pages turned on, the same page is live at the Pages URL.

- **All 12 professions:** Alchemy, Blacksmithing, Enchanting, Engineering, Leatherworking, Tailoring, Cooking, First Aid, Fishing, Herbalism, Mining and Skinning (2,123 recipes)
- **Enchants** show the reagent cost of each enchant, which is what to charge for it, since enchants don't make an item you can sell
- **Auction House:** choose a market (US Horde houses) and a price: *low market* (the price of the cheapest 10% of what's listed), *median*, or *lowest listing*
- **Skill-ups:** the orange, yellow, green and grey skill levels for every recipe, for planning your leveling
- **Learned from:** how you get each recipe (trainer, automatic, vendor, reputation with faction and standing, Merchant's Favor cost, boss or world drop, quest), plus whether the recipe item is **BoP** or **BoE** (tradeable, so you can buy it on the AH)
- **Click a recipe** to see each reagent's cost and where the price comes from (AH, vendor, or cheaper to craft), how to learn the recipe, and its skill-up colors
- **Click an item name** to open its Wowhead Forever page in a new tab
- **Hover an item** for an in-game style tooltip with its stats, effects, sell price, current AH price, and how many are listed
- **Thin markets** are flagged when 3 or fewer of an item are listed, since one listing can make a profit look much bigger than it is
- **Settings:** AH cut, "I gather my own herbs", and backup

Prices are a snapshot taken when the page was built. See below to refresh them.

## Refresh the data

You need Python 3 (no extra packages) and a free Blizzard API client.

1. Create a client at <https://develop.battle.net/access/clients>.
2. Save its keys in `blizzard_credentials.json` in this folder. `.gitignore` keeps this file out of the repo:
   ```json
   {"client_id": "YOUR_CLIENT_ID", "client_secret": "YOUR_CLIENT_SECRET"}
   ```
3. Run the scripts you need:

```bash
python3 tools/fetch_ah_prices.py --house 113   # AH prices for one house -> data/ah-snapshot-house113.json
python3 tools/fetch_ah_prices.py --list-houses # show all house IDs
python3 tools/fetch_forever_recipes.py         # recipes, items, vendor prices, tooltips (run after a patch)
python3 tools/fetch_seemeta_skills.py          # skill-up colors and sources
python3 tools/build_page.py                    # put the data into index.html
```

`fetch_ah_prices.py` takes `--region us|eu`, `--ruleset pvp|normal|rp|rppvp` and `--faction horde|alliance|blackwater`. `build_page.py --houses 113 114 120 124` chooses which snapshots appear in the market picker.

## Where the data comes from

| Data | Source |
|---|---|
| Recipes, reagents, items, tooltips, vendor prices | Blizzard Game Data API, `static-forever-*` namespace |
| Auction House listings | Blizzard Game Data API, `dynamic-forever-*`, `/data/wow/ruleset/{id}/auctions/{house}` (community-discovered, unofficial) |
| Skill from patterns, plans and recipe items | Blizzard Game Data API (the recipe item's "Requires …" line) |
| Skill-up colors, "learned automatically" | seemeta.com Forever profession pages |
| Alchemy trainer skills and recipe sources | Wowhead Forever pages, copied in by hand (`data/wowhead_*.json`) |
| Classic skill levels used for estimates, and which reagents vendors sell | `wow-classic-items` npm package (`data/classic_skills.json`, `data/classic_vendor_items.json`) |

### How accurate is it?

**About 1,700 of 2,123 recipes have their exact Forever skill.** The skill comes from the recipe item, from seemeta, or from Wowhead. For the rest, mostly trainer-taught recipes, the planner shows an estimate marked **≈**, and hovering it says how it was made. Tested on recipes whose skill is known:

| Estimate | Used for | Exactly right | Within 5 points |
|---|---|---|---|
| Classic skill, unchanged | Alchemy, Cooking, Engineering, First Aid | 98–99% | 98–99% |
| Classic skill converted to Forever's scale (capped at the exact yellow skill-up) | Blacksmithing | 90% | 90% |
| | Leatherworking | 72% | 82% |
| | Tailoring | 55% | 66% |
| Exact yellow skill-up minus the profession's typical gap | Enchanting, Mining and anything without Classic data | 40–60% | 60–70% |

Other limits:

- **Training costs** aren't in any source this project can read, so they're blank.
- **Recipe sources:** BoP/BoE and reputation requirements come from Forever's own item data and are exact. Vendor, drop and quest sources come from Classic data, and are marked as such. Merchant's Favor and reputation unlocks are only known for Alchemy (from Wowhead). About 700 recipe items are new in Forever, and nothing this project can read says where they come from, so they're labelled "New in Forever".
- **AH prices are asking prices, not sales.** Gear with random bonuses ("of the Bear") is pooled per item, and "only N listed" marks thin markets.
- **Which house is which server type isn't published.** The API exposes 5 markets (each an Alliance, Horde and Blackwater house) but doesn't say which ruleset each belongs to.

## Project layout

```
index.html        the planner (data embedded; open it directly)
data/             recipe, item, skill and AH snapshot data
tools/            Python scripts that fetch data and rebuild index.html
docs/             screenshot
```

## Disclaimer

Fan-made and unofficial. Not affiliated with or endorsed by Blizzard Entertainment. World of Warcraft and Blizzard Entertainment are trademarks or registered trademarks of Blizzard Entertainment, Inc. Game data is from Blizzard's public Game Data API and is subject to Blizzard's API terms.
