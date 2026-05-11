# ── Cell A3: Batch fuzzy matching ─────────────────────────────
# Three-pass matching pipeline:
# Pass 1: High quality entries only (no ALL CAPS branded) at threshold 80
# Pass 2: All complete entries at threshold 75
# Pass 3: Full index including low quality branded at threshold 75 (last resort)
!pip install rapidfuzz tqdm -q
import pickle, re, os
from rapidfuzz import process, fuzz, utils
from tqdm.notebook import tqdm

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

print("Loading inputs...")
with open(f'{OUT_DIR}/fdc_index.pkl', 'rb') as f:
    fdc_all = pickle.load(f)
with open(f'{OUT_DIR}/fdc_index_hq.pkl', 'rb') as f:
    fdc_hq = pickle.load(f)
with open(f'{BASE}/node_mappings.pkl', 'rb') as f:
    mappings = pickle.load(f)

iv               = mappings['ingredient_vocab']
ingredient_names = list(iv.keys())
fdc_by_id        = {e['fdc_id']: e for e in fdc_all}

hq_complete      = [e for e in fdc_hq  if e['complete']]
all_complete     = [e for e in fdc_all if e['complete']]

all_descs_hq_c   = [utils.default_process(e['desc']) for e in hq_complete]
all_descs_all_c  = [utils.default_process(e['desc']) for e in all_complete]
all_descs_full   = [utils.default_process(e['desc']) for e in fdc_all]

print(f"Ingredients:        {len(ingredient_names):,}")
print(f"HQ complete:        {len(hq_complete):,}")
print(f"All complete:       {len(all_complete):,}")
print(f"Full index:         {len(fdc_all):,}")

def clean(name):
    name = name.replace('_', ' ').lower()
    name = re.sub(
        r'\b(fresh|dried|frozen|canned|chopped|sliced|diced|minced|'
        r'ground|whole|raw|cooked|large|small|medium|extra|fine|'
        r'shredded|grated|crumbled|softened|melted|divided|optional|'
        r'or more|to taste|plus more|as needed|approximately)\b',
        '', name)
    return re.sub(r'\s+', ' ', name).strip()

ALIAS_CACHE = {
    'flour': 169761, 'sugar': 169655, 'butter': 173410,
    'egg': 748967, 'eggs': 748967, 'milk': 746782,
    'salt': 746768, 'olive oil': 748608, 'water': 174227,
    'onion': 170000, 'onions': 170000, 'garlic': 169230,
    'tomato': 170457, 'tomatoes': 170457, 'chicken': 331960,
    'beef': 174036, 'rice': 169756, 'pasta': 169734,
    'cheese': 173414, 'cream': 170859, 'yogurt': 171284,
    'lemon': 167747, 'lemons': 167747, 'pepper': 170931,
    'oil': 748608, 'baking powder': 175029, 'baking soda': 175028,
    'vanilla': 169109, 'cinnamon': 171320,
    'parmesan': 170848, 'parmesan cheese': 170848,
    'mozzarella': 170845, 'mozzarella cheese': 170845,
    'cheddar': 173414, 'cheddar cheese': 173414,
    'soy sauce': 175055, 'honey': 169640,
    'maple syrup': 168875, 'tofu': 172476,
    'all purpose flour': 169761, 'all-purpose flour': 169761,
    'brown sugar': 168878, 'powdered sugar': 169659,
    'cornstarch': 169720, 'corn starch': 169720,
    'cocoa powder': 169593, 'spinach': 168462,
    'broccoli': 170379, 'carrot': 170393, 'carrots': 170393,
    'celery': 169988, 'mushroom': 169251, 'mushrooms': 169251,
    'potato': 170026, 'potatoes': 170026,
    'sweet potato': 168482, 'apple': 171688, 'apples': 171688,
    'banana': 173944, 'bananas': 173944,
    'lemon juice': 167747, 'lime juice': 167751,
    'orange juice': 169098, 'sour cream': 170857,
    'mayonnaise': 172339, 'mustard': 172340,
    'ketchup': 172341, 'hot sauce': 170930,
    'worcestershire sauce': 172345, 'tahini': 168594,
    'peanut butter': 172470, 'tomato paste': 170908,
    'tomato sauce': 170909, 'heavy cream': 170859,
    'cream cheese': 171252, 'bacon': 168318,
    'chicken broth': 172234, 'beef broth': 172233,
    'bread crumbs': 174986, 'breadcrumbs': 174986,
    'vegetable oil': 172336, 'canola oil': 172336,
    'coconut oil': 172336, 'sesame oil': 172348,
}

matched    = {}
CKPT       = f'{OUT_DIR}/matched_checkpoint.pkl'
BATCH_SIZE = 1000
SAVE_EVERY = 50000

if os.path.exists(CKPT):
    print("Loading checkpoint...")
    with open(CKPT, 'rb') as f:
        ckpt = pickle.load(f)
    matched   = ckpt['matched']
    remaining = ckpt['remaining']
    print(f"  Resumed: {len(matched):,} matched, "
          f"{len(remaining):,} remaining")
else:
    remaining = ingredient_names[:]

# ── Layer 1: Alias cache ──────────────────────────────────────
print("\nLayer 1: Alias cache...")
still_remaining = []
for ing in remaining:
    key    = ing.replace('_', ' ').lower()
    fdc_id = ALIAS_CACHE.get(key)
    if fdc_id and fdc_id in fdc_by_id:
        e = fdc_by_id[fdc_id]
        if e['nutrients']:
            matched[ing] = {
                'source':    'alias',
                'fdc_id':    e['fdc_id'],
                'desc':      e['desc'],
                'p_source':  e['p_source'],
                'nutrients': e['nutrients'],
                'score':     100,
            }
        else:
            still_remaining.append(ing)
    else:
        still_remaining.append(ing)
remaining = still_remaining
print(f"  Matched: {len(matched):,}  Remaining: {len(remaining):,}")

# ── Layer 2: Batch fuzzy matching ────────────────────────────
print("\nLayer 2: Batch fuzzy matching...")
queries_cleaned = [clean(ing) for ing in remaining]

# Pass 1 — HQ entries only at threshold 80
print(f"  Pass 1: HQ entries threshold 80 ({len(remaining):,})...")
still_remaining = []
for batch_start in tqdm(range(0, len(remaining), BATCH_SIZE)):
    batch_end     = min(batch_start + BATCH_SIZE, len(remaining))
    batch_names   = remaining[batch_start:batch_end]
    batch_queries = queries_cleaned[batch_start:batch_end]
    valid = [(n, q) for n, q in zip(batch_names, batch_queries) if q]
    if not valid:
        still_remaining.extend(batch_names)
        continue
    names_v, queries_v = zip(*valid)
    scores = process.cdist(queries_v, all_descs_hq_c,
                           scorer=fuzz.token_sort_ratio, workers=-1)
    for i, ing_name in enumerate(names_v):
        best_score = scores[i].max()
        if best_score >= 80:
            best_idx = scores[i].argmax()
            e = hq_complete[best_idx]
            matched[ing_name] = {
                'source':    'fdc_fuzzy',
                'fdc_id':    e['fdc_id'],
                'desc':      e['desc'],
                'p_source':  e['p_source'],
                'nutrients': e['nutrients'],
                'score':     int(best_score),
            }
        else:
            still_remaining.append(ing_name)
    processed = batch_start + len(batch_names)
    if processed % SAVE_EVERY < BATCH_SIZE:
        with open(CKPT, 'wb') as f:
            pickle.dump({'matched':   matched,
                         'remaining': still_remaining}, f, protocol=4)

print(f"  After Pass 1: matched={len(matched):,} "
      f"remaining={len(still_remaining):,}")

# Pass 2 — all complete entries at threshold 75
remaining2       = still_remaining
still_remaining  = []
queries_cleaned2 = [clean(ing) for ing in remaining2]

print(f"  Pass 2: All complete entries threshold 75 "
      f"({len(remaining2):,})...")
for batch_start in tqdm(range(0, len(remaining2), BATCH_SIZE)):
    batch_end     = min(batch_start + BATCH_SIZE, len(remaining2))
    batch_names   = remaining2[batch_start:batch_end]
    batch_queries = queries_cleaned2[batch_start:batch_end]
    valid = [(n, q) for n, q in zip(batch_names, batch_queries) if q]
    if not valid:
        still_remaining.extend(batch_names)
        continue
    names_v, queries_v = zip(*valid)
    scores = process.cdist(queries_v, all_descs_all_c,
                           scorer=fuzz.token_sort_ratio, workers=-1)
    for i, ing_name in enumerate(names_v):
        best_score = scores[i].max()
        if best_score >= 75:
            best_idx = scores[i].argmax()
            e = all_complete[best_idx]
            matched[ing_name] = {
                'source':    'fdc_fuzzy',
                'fdc_id':    e['fdc_id'],
                'desc':      e['desc'],
                'p_source':  e['p_source'],
                'nutrients': e['nutrients'],
                'score':     int(best_score),
            }
        else:
            still_remaining.append(ing_name)

print(f"  After Pass 2: matched={len(matched):,} "
      f"remaining={len(still_remaining):,}")

# Pass 3 — full index including low quality branded as last resort
remaining3       = still_remaining
still_remaining  = []
queries_cleaned3 = [clean(ing) for ing in remaining3]

print(f"  Pass 3: Full index including branded threshold 75 "
      f"({len(remaining3):,})...")
for batch_start in tqdm(range(0, len(remaining3), BATCH_SIZE)):
    batch_end     = min(batch_start + BATCH_SIZE, len(remaining3))
    batch_names   = remaining3[batch_start:batch_end]
    batch_queries = queries_cleaned3[batch_start:batch_end]
    valid = [(n, q) for n, q in zip(batch_names, batch_queries) if q]
    if not valid:
        still_remaining.extend(batch_names)
        continue
    names_v, queries_v = zip(*valid)
    scores = process.cdist(queries_v, all_descs_full,
                           scorer=fuzz.token_sort_ratio, workers=-1)
    for i, ing_name in enumerate(names_v):
        best_score = scores[i].max()
        if best_score >= 75:
            best_idx = scores[i].argmax()
            e = fdc_all[best_idx]
            matched[ing_name] = {
                'source':    'fdc_fuzzy',
                'fdc_id':    e['fdc_id'],
                'desc':      e['desc'],
                'p_source':  e['p_source'],
                'nutrients': e['nutrients'],
                'score':     int(best_score),
            }
        else:
            still_remaining.append(ing_name)

print(f"  After Pass 3: matched={len(matched):,} "
      f"remaining={len(still_remaining):,}")

# ── Save ──────────────────────────────────────────────────────
with open(f'{OUT_DIR}/usda_matched_full.pkl', 'wb') as f:
    pickle.dump({'matched':   matched,
                 'unmatched': still_remaining}, f, protocol=4)

if os.path.exists(CKPT):
    os.remove(CKPT)

print(f"\nFinal:")
print(f"  Matched:   {len(matched):,}"
      f" ({len(matched)/len(ingredient_names)*100:.1f}%)")
print(f"  Unmatched: {len(still_remaining):,}")

from collections import Counter
src_dist = Counter(m['source'] for m in matched.values())
print(f"\nMatch source breakdown:")
for src, count in src_dist.most_common():
    print(f"  {src:<25} {count:,}")
