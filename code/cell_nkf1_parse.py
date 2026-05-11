# ── Cell NKF-1: Parse NKF recipes from markdown ───────────────
# Reads nkf_recipe_ingredients_table.md from Drive and builds
# NKF_RECIPES list for the 9 verified recipes.
# Unverified recipes (no confirmed servings/tags from NKF pages)
# are skipped automatically.
import re

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'
MD_PATH = f'{BASE}/nkf_recipe_ingredients_table.md'

with open(MD_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

rows = []
for line in content.strip().split('\n'):
    line = line.strip()
    if not line.startswith('|'): continue
    if line.startswith('|---') or line.startswith('| #'): continue
    cells = [c.strip() for c in line.split('|')]
    cells = [c for c in cells if c]
    if len(cells) >= 4:
        rows.append(cells)

print(f"Found {len(rows)} rows in markdown")

def make_slug(title):
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s]', '', slug)
    slug = re.sub(r'\s+', '_', slug).strip('_')
    return slug

def parse_ingredients(ing_str):
    items = [i.strip() for i in ing_str.split(';') if i.strip()]
    result = []
    for item in items:
        item = item.strip()
        if not item: continue
        m = re.match(
            r'^([\d½¼¾⅓⅔\./\s]+)\s*'
            r'(cup|cups|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|'
            r'oz|ounce|ounces|lb|pound|pounds|g|gram|grams|kg|'
            r'clove|cloves|medium|large|small|'
            r'can|cans|jar|jars|pkg|package|bunch|bunches|'
            r'slice|slices|piece|pieces|sprig|sprigs)?\s*(.+)',
            item, re.IGNORECASE
        )
        if m:
            qty  = m.group(1).strip()
            unit = m.group(2).strip() if m.group(2) else ''
            name = m.group(3).strip()
            name = re.sub(r',.*$', '', name).strip()
            name = re.sub(r'\(.*?\)', '', name).strip()
            qty_str = f"{qty} {unit}".strip()
            result.append((qty_str, name))
        else:
            result.append(('1', item))
    return result

# ── Verified RECIPE_META ──────────────────────────────────────
# (servings, [nkf_tags]) confirmed from NKF recipe pages
# Only verified recipes are included — unverified are skipped
RECIPE_META = {
    'chicken_and_cabbage_mexican_skillet': (
        4, ['low-potassium', 'low-sodium']
    ),
    'chocolate_zucchini_brownies': (
        8, ['low-phosphorus', 'low-sodium']
    ),
    'zucchini_bread': (
        16, ['low-sodium', 'low-phosphorus', 'low-potassium']
    ),
    'mexican_zucchini_and_corn': (
        4, ['low-sodium']
    ),
    'onion_bagel_chips': (
        4, ['low-phosphorus', 'low-potassium', 'low-sodium']
    ),
    'mexican_rice_with_bell_peppers': (
        4, ['low-phosphorus', 'low-potassium']
    ),
    'pancakes': (
        4, ['low-sodium', 'low-phosphorus', 'low-potassium']
    ),
    'chili_wheat_treats': (
        8, ['low-phosphorus', 'low-potassium', 'low-sodium']
    ),
    'banana_berry_pancakes': (
        4, ['low-sodium', 'low-potassium']
    ),
}

VERIFIED_SLUGS = set(RECIPE_META.keys())
NKF_RECIPES   = []
skipped       = []

for cells in rows:
    title = cells[1].strip()
    url   = cells[2].strip()
    ings  = cells[3].strip()
    slug  = make_slug(title)

    if slug not in VERIFIED_SLUGS:
        skipped.append(title)
        continue

    servings, tags = RECIPE_META[slug]
    ingredients    = parse_ingredients(ings)

    NKF_RECIPES.append({
        'slug':        slug,
        'title':       title,
        'url':         url,
        'servings':    servings,
        'nkf_tags':    tags,
        'ingredients': ingredients,
    })

print(f"\nIncluded: {len(NKF_RECIPES)} verified recipes")
print(f"Skipped:  {len(skipped)} unverified recipes")

print(f"\n{'#':<4} {'Title':<55} {'Serv':>5}  Tags")
print("-" * 95)
for i, r in enumerate(NKF_RECIPES):
    print(f"{i+1:<4} {r['title'][:53]:<55} "
          f"{r['servings']:>5}  {', '.join(r['nkf_tags'])}")
    for qty, name in r['ingredients']:
        print(f"       {qty:<12} {name}")
    print()

if skipped:
    print(f"\nSkipped (need verification from NKF pages):")
    for t in skipped:
        print(f"  {t}")
