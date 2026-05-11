# ── Cell NKF-2: Map NKF ingredients to graph nodes ────────────
# Maps each NKF ingredient string to an existing ingredient node
# in the graph using rapidfuzz token_sort_ratio at threshold 80.
# Manual overrides fix known bad fuzzy matches.
from rapidfuzz import process, fuzz, utils
import pickle, re

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

with open(f'{OUT_DIR}/usda_matched_full.pkl', 'rb') as f:
    match_data = pickle.load(f)
matched = match_data['matched']

def clean_nkf(name):
    name = name.lower()
    name = re.sub(r'[½¼¾⅓⅔]', '', name)
    name = re.sub(
        r'\b(fresh|dried|frozen|canned|chopped|sliced|diced|minced|'
        r'shredded|grated|cooked|raw|softened|melted|seeded|finely|'
        r'for garnish|low.sodium|unsweetened|lean|smoked|ground|'
        r'white|green|red|yellow|black|large|medium|small|'
        r'rinsed|drained|peeled|trimmed|halved|quartered|'
        r'divided|optional|to taste|non.dairy)\b',
        '', name)
    # Remove leading single characters left by quantity stripping
    name = re.sub(r'^\s*[a-z]\s+', '', name)
    return re.sub(r'\s+', ' ', name).strip()

matched_keys       = list(matched.keys())
matched_keys_clean = [utils.default_process(k) for k in matched_keys]

# ── Manual overrides for known bad matches and misses ─────────
MANUAL_OVERRIDES = {
    ('mexican_zucchini_and_corn',
     'Corn oil, for sautéing'):
        'ingredient:vegetable_oil',
    ('chili_wheat_treats',
     's spoon-size shredded wheat'):
        'ingredient:shredded_wheat',
    ('chicken_and_cabbage_mexican_skillet',
     'ground cumin'):
        'ingredient:cumin',
    ('mexican_rice_with_bell_peppers',
     'ground cumin'):
        'ingredient:cumin',
    ('chili_wheat_treats',
     'ground cumin'):
        'ingredient:cumin',
    ('mexican_rice_with_bell_peppers',
     'white rice'):
        'ingredient:rice',
}

nkf_ing_map = {}
hit_count   = 0
miss_count  = 0

# Apply manual overrides first
nkf_ing_map.update(MANUAL_OVERRIDES)
hit_count += len(MANUAL_OVERRIDES)

for recipe in NKF_RECIPES:
    slug = recipe['slug']
    print(f"\n{recipe['title']}")
    for qty_str, ing_str in recipe['ingredients']:

        # Skip if already in manual overrides
        if (slug, ing_str) in nkf_ing_map:
            print(f"  MANUAL {ing_str:<40} -> "
                  f"{nkf_ing_map[(slug, ing_str)]}")
            continue

        clean = clean_nkf(ing_str)
        if not clean:
            continue

        # Exact match
        if clean in matched:
            ing_id = f"ingredient:{clean.replace(' ', '_')}"
            nkf_ing_map[(slug, ing_str)] = ing_id
            hit_count += 1
            print(f"  EXACT  {ing_str:<40} -> {clean}")
            continue

        # Fuzzy match
        q = utils.default_process(clean)
        r = process.extractOne(
            q, matched_keys_clean,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=80
        )
        if r:
            desc, score, idx = r
            best_key = matched_keys[idx]
            ing_id   = f"ingredient:{best_key.replace(' ', '_')}"
            nkf_ing_map[(slug, ing_str)] = ing_id
            hit_count += 1
            print(f"  FUZZY  {ing_str:<40} -> {best_key}  ({score:.0f})")
        else:
            miss_count += 1
            print(f"  MISS   {ing_str:<40} -> no match")

total_ings = sum(len(r['ingredients']) for r in NKF_RECIPES)
print(f"\nMapped:    {len(nkf_ing_map):,} / {total_ings:,}")
print(f"Unmatched: {miss_count:,}")

# ── Diagnostic: verify all keys match ─────────────────────────
print(f"\nVerifying key lookup...")
for recipe in NKF_RECIPES:
    slug = recipe['slug']
    for qty_str, ing_str in recipe['ingredients']:
        found = (slug, ing_str) in nkf_ing_map
        if not found:
            print(f"  MISS KEY: ({slug[:20]}, '{ing_str}')")
print("Key verification complete")
