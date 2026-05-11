# ── Cell A3b: Priority matching + normalisation + fixes ───────
# Extends usda_matched_full.pkl with:
# - Extended alias cache for common unmatched ingredients
# - Normalisation dictionary for informal names
# - Phosphorus source reclassification
# - Category mismatch removal
# - Manual refixes for known bad FDC matches
!pip install rapidfuzz tqdm -q
import pickle, re
from rapidfuzz import process, fuzz, utils
from collections import Counter
from tqdm.notebook import tqdm

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

NOISE_STRINGS = {
    '.', '-58', '-78', '-13', '-18', '-23', '-33', '-43', '-53',
    '-63', '-68', '-73', '-83', '-88', '-93', '-98',
    'c.', 'filling:', 'filling', 'topping:', 'topping', 'crust:',
    'crust', 'frosting:', 'frosting', 'of', 'x', 'skewers',
    'toothpicks', 'toothpick', 'firm', 'bone-in', 'or', '-',
    'drained', 'skinned', 'skin-on', 'whl', 'fl', 'cloth',
    'skewer', 'hot', 'on-the-go', 'dairy-free', 'essence',
    'veg-all', 'borax', 'and', 'the', 'a', 'an', 'some',
    'sauce:', 'marinade:', 'dressing:', 'glaze:', 'base:',
    'coating:', 'breading:', 'syrup:', 'rub:', 'batter:',
    'garnish:', 'for serving', 'to serve', 'optional',
    'as needed', 'to taste', 'or more', 'plus more',
}

NOISE_PATTERNS = [
    r'or_possibly', r'\bor_\d+_', r'_or_more$', r'^c\._',
    r'_if_desired$', r'_to_taste$', r'_as_needed$',
    r'_for_garnish$', r'_for_serving$', r'_optional$',
    r'_divided$', r'_plus_more$',
]

def is_noise(ing):
    ing_l = ing.lower()
    if ing_l in NOISE_STRINGS: return True
    if len(ing.split()) > 8:   return True
    if any(re.search(pat, ing_l) for pat in NOISE_PATTERNS): return True
    return False

NORMALISATION_DICT = {
    'active dry yeast': 'yeast', 'dry yeast': 'yeast',
    'dry active yeast': 'yeast',
    'kosher salt': 'salt', 'seasoning salt': 'salt',
    'season salt': 'salt', 'rock salt': 'salt',
    'fleur de sel': 'salt', 'canning salt': 'salt',
    'salt substitute': 'salt', 'salt/pepper': 'salt',
    'baking cocoa': 'cocoa powder', 'cocoa': 'cocoa powder',
    'cacao': 'cocoa powder',
    'dutch process cocoa': 'cocoa powder',
    'dutch processed cocoa powder': 'cocoa powder',
    'red pepper flakes': 'crushed red pepper',
    'cilantro leaves': 'cilantro',
    'coriander powder': 'coriander',
    'cardamom powder': 'cardamom',
    'aniseed': 'anise seed', 'mixed spice': 'allspice',
    'lemon pepper seasoning': 'lemon pepper',
    'creole seasoning': 'cajun seasoning',
    'adobo seasoning': 'garlic powder',
    'chili seasoning mix': 'chili powder',
    'mild chili powder': 'chili powder',
    'mexican chili powder': 'chili powder',
    'new mexico chile powder': 'chili powder',
    'allspice berry': 'allspice',
    'parmigiano-reggiano': 'parmesan cheese',
    'pecorino': 'romano cheese', 'gruyere': 'swiss cheese',
    'mild cheddar cheese': 'cheddar cheese',
    'old cheddar cheese': 'cheddar cheese',
    'pizza cheese': 'mozzarella cheese',
    'bocconcini': 'mozzarella cheese',
    'jalapeno jack cheese': 'pepper jack cheese',
    'anchovy': 'anchovies',
    'anchovy paste': 'anchovies in oil',
    'monkfish': 'white fish fillet',
    'pork shoulder': 'pork roast',
    'cooked bacon': 'bacon',
    'streaky bacon': 'bacon', 'bacon fat': 'lard',
    'ham bone': 'ham', 'brisket': 'beef brisket',
    'rump steak': 'beef round steak',
    'rump roast': 'beef round roast',
    'tasso': 'smoked ham', 'suet': 'beef fat',
    'quail': 'game bird', 'serrano ham': 'prosciutto',
    'chicken bouillon cube': 'chicken broth',
    'chicken bouillon': 'chicken broth',
    'chicken bouillon granule': 'chicken broth',
    'instant chicken bouillon': 'chicken broth',
    'beef bouillon cube': 'beef broth',
    'beef bouillon powder': 'beef broth',
    'instant beef bouillon': 'beef broth',
    'vegetable bouillon cube': 'vegetable broth',
    'bouillon': 'chicken broth', 'beef base': 'beef broth',
    'demi-glace': 'beef broth',
    'unflavored gelatin': 'gelatin',
    'gelatin powder': 'gelatin',
    'instant coffee': 'coffee',
    'instant coffee powder': 'coffee',
    'self raising flour': 'all purpose flour',
    'sage leaf': 'sage', 'lemongrass': 'lemon grass',
    'seedless watermelon': 'watermelon',
    'pepitas': 'pumpkin seeds',
    'sushi rice': 'short grain white rice',
    'butternut pumpkin': 'butternut squash',
    'capsicum': 'bell pepper',
    'aubergines': 'eggplant', 'swede': 'rutabaga',
    'daikon': 'radish', 'rocket': 'arugula',
    'mesclun': 'mixed salad greens', 'ramps': 'wild leeks',
    'maui onion': 'sweet onion',
    'porcini': 'dried mushrooms',
    'black sesame seed': 'sesame seeds',
    'nori': 'dried seaweed', 'kombu': 'dried seaweed',
    'mango powder': 'dried mango', 'habanero': 'hot pepper',
    'ruby port': 'port wine', 'tawny port': 'port wine',
    'merlot': 'red wine', 'chardonnay': 'white wine',
    'ginger ale': 'ginger beer', 'lemonade': 'lemon juice',
    'prosecco': 'sparkling wine', 'madeira': 'dry sherry',
    'cognac': 'brandy', 'cachaca': 'rum',
    'shoyu': 'soy sauce', 'chili paste': 'chili garlic sauce',
    'thai red curry paste': 'red curry paste',
    'asian chili sauce': 'chili sauce', 'sambal': 'chili sauce',
    'galangal': 'fresh ginger', 'kinako': 'soy flour',
    'aonori': 'dried seaweed flakes',
    'umeboshi': 'pickled plum',
    'shiro-dashi': 'dashi broth', 'ra-yu': 'chili oil',
    'matcha green tea powder': 'green tea powder',
    'vegemite': 'yeast extract spread',
    'splenda': 'sucralose sweetener',
    'sucanat': 'raw cane sugar',
    'instant nonfat dry milk powder': 'nonfat dry milk',
    'protein powder': 'whey protein powder',
    'vanilla powder': 'vanilla extract',
    'meringue powder': 'dried egg white',
    'brown rice vinegar': 'rice vinegar',
    'oreos': 'chocolate sandwich cookies',
    'half-and-half': 'half and half cream',
    'mirin': 'mirin rice wine', 'veal': 'veal meat',
    'ricotta': 'ricotta cheese', 'evoo': 'olive oil',
    'prawns': 'shrimp', 'tabasco': 'hot pepper sauce',
    'trout': 'rainbow trout', 'sultanas': 'raisins',
    'sultana': 'raisins', 'sumac': 'sumac spice',
    'duck': 'duck meat', 'sweetcorn': 'corn',
    'vermouth': 'dry vermouth',
    'fenugreek': 'fenugreek seed',
    'ponzu': 'ponzu sauce',
    'doubanjiang': 'chili bean sauce',
    'mentsuyu': 'japanese noodle broth',
    'plums': 'fresh plums', 'herbs': 'mixed herbs',
    'seitan': 'vital wheat gluten',
}

EXTRA_ALIASES = {
    'olive oil': 171413, 'chicken broth': 172234,
    'sour cream': 170857, 'vegetable oil': 172336,
    'green onion': 170000, 'ground beef': 174036,
    'heavy cream': 170859, 'brown sugar': 168878,
    'garlic powder': 169231, 'lemon juice': 167747,
    'tomato sauce': 170909, 'canola oil': 172336,
    'ground turkey': 171506, 'green pepper': 170108,
    'chicken stock': 172234, 'garlic salt': 169231,
    'beef broth': 172233, 'all purpose flour': 169761,
    'onion powder': 170932, 'diced tomato': 170457,
    'coconut oil': 172336, 'vegetable broth': 172234,
    'cayenne pepper': 170931, 'whole wheat flour': 169762,
    'cream cheese': 171252, 'vanilla extract': 169109,
    'white wine': 174824, 'red onion': 170000,
    'chocolate chip': 170272, 'red pepper': 170108,
    'nutmeg': 170931, 'half and half': 170857,
    'ricotta cheese': 170851, 'evoo': 171413,
    'prawns': 175180, 'tabasco': 170930,
    'trout': 175167, 'sultanas': 168155,
    'sultana': 168155, 'duck': 171491,
    'sweetcorn': 170416, 'cognac': 174823,
    'katakuriko': 169720,
    'cooked bacon': 167712,
    'cocoa powder': 169593,
    'cream of tartar': 175029,
    'mustard seed': 170930,
    'anchovies': 175167,
    'kosher salt': 746768,
    'salmon': 175167,
}

ANIMAL_KW = [
    'beef','pork','chicken','turkey','lamb','veal','duck','fish',
    'salmon','tuna','cod','tilapia','shrimp','prawn','crab',
    'lobster','scallop','oyster','clam','anchovy','sardine',
    'herring','trout','cheese','milk','cream','butter','yogurt',
    'whey','casein','egg','bacon','ham','sausage','pepperoni',
    'salami','prosciutto','gelatin','lard','suet','tallow','ghee',
    'collagen','meat','poultry','seafood','deli','rotisserie',
]
PLANT_KW = [
    'bean','lentil','pea','chickpea','soy','tofu','tempeh',
    'edamame','grain','wheat','oat','barley','rye','corn','rice',
    'quinoa','millet','nut','almond','walnut','cashew','pecan',
    'pistachio','hazelnut','seed','flaxseed','chia','sesame',
    'sunflower','pumpkin','fruit','vegetable','spinach','kale',
    'broccoli','carrot','potato','sweet potato','yam','squash',
    'zucchini','onion','scallion','leek','chive','garlic','ginger',
    'pepper','tomato','lettuce','cabbage','celery','cucumber',
    'mushroom','eggplant','coconut','avocado','olive','hummus',
    'bread','pasta','noodle','cracker','cereal','flour','tortilla',
    'chocolate','cocoa','coffee','tea','herb','spice','sauce',
    'salsa','vinegar','juice','berry','apple','banana','orange',
    'lemon','lime','mango','seitan','gluten',
]
ADDITIVE_KW = [
    'processed','velveeta','american cheese slice','instant',
    'reconstituted','artificial','imitation','fast food',
    'ready meal','microwave','frozen dinner','canned soup',
    'bouillon cube','stock cube',
]

def classify_psource(ing_name, desc):
    combined = f"{ing_name} {desc}".lower()
    if any(k in combined for k in ADDITIVE_KW): return 'additive'
    if any(k in combined for k in ANIMAL_KW):   return 'animal'
    if any(k in combined for k in PLANT_KW):    return 'plant'
    return 'unknown'

def clean(name):
    name = name.replace('_', ' ').lower()
    name = re.sub(
        r'\b(fresh|dried|frozen|canned|chopped|sliced|diced|minced|'
        r'ground|whole|raw|cooked|large|small|medium|extra|fine|'
        r'shredded|grated|crumbled|softened|melted|divided|optional)\b',
        '', name)
    return re.sub(r'\s+', ' ', name).strip()

print("Loading data...")
with open(f'{OUT_DIR}/usda_matched_full.pkl', 'rb') as f:
    match_data = pickle.load(f)
matched   = match_data['matched']
unmatched = list(match_data['unmatched'])

with open(f'{OUT_DIR}/fdc_index.pkl', 'rb') as f:
    fdc_entries = pickle.load(f)

fdc_by_id        = {e['fdc_id']: e for e in fdc_entries}
complete_entries  = [e for e in fdc_entries if e['complete']]
all_descs_c      = [utils.default_process(e['desc'])
                    for e in complete_entries]
all_descs_all    = [utils.default_process(e['desc'])
                    for e in fdc_entries]

print(f"Currently matched:   {len(matched):,}")
print(f"Currently unmatched: {len(unmatched):,}")

# Pass 1: Extended alias cache
print("\nPass 1: Extended alias cache...")
still_unmatched = []
alias_matched   = 0
for ing in unmatched:
    if is_noise(ing): continue
    key    = ing.lower().strip()
    fdc_id = EXTRA_ALIASES.get(key)
    if fdc_id and fdc_id in fdc_by_id:
        e = fdc_by_id[fdc_id]
        if e['nutrients']:
            matched[ing] = {
                'source': 'alias_ext', 'fdc_id': e['fdc_id'],
                'desc': e['desc'], 'p_source': e['p_source'],
                'nutrients': e['nutrients'], 'score': 100,
            }
            alias_matched += 1
            continue
    still_unmatched.append(ing)

print(f"  Matched by alias: {alias_matched:,}")
print(f"  Remaining:        {len(still_unmatched):,}")
unmatched = still_unmatched

# Pass 2: Normalisation dictionary
print("\nPass 2: Normalisation dictionary...")
still_unmatched = []
norm_matched    = 0
noise_removed   = 0

for ing in tqdm(unmatched, desc="Normalising"):
    if is_noise(ing):
        noise_removed += 1
        continue
    ing_l     = ing.lower().strip()
    canonical = NORMALISATION_DICT.get(ing_l)
    if canonical:
        q = utils.default_process(canonical)
        r = process.extractOne(q, all_descs_c,
                               scorer=fuzz.token_sort_ratio,
                               score_cutoff=80)
        if not r:
            r = process.extractOne(q, all_descs_all,
                                   scorer=fuzz.token_sort_ratio,
                                   score_cutoff=75)
        if r:
            desc, score, idx = r
            e = complete_entries[idx] \
                if score >= 80 and idx < len(complete_entries) \
                else fdc_entries[idx]
            matched[ing] = {
                'source': 'normalised', 'canonical': canonical,
                'fdc_id': e['fdc_id'], 'desc': e['desc'],
                'p_source': e['p_source'], 'nutrients': e['nutrients'],
                'score': score,
            }
            norm_matched += 1
            continue
    still_unmatched.append(ing)

print(f"  Noise removed:    {noise_removed:,}")
print(f"  Matched by norm:  {norm_matched:,}")
print(f"  Remaining:        {len(still_unmatched):,}")
unmatched = still_unmatched

# Pass 3: Priority fuzzy for substitution ingredients (batch)
print("\nPass 3: Priority fuzzy for substitution ingredients (batch)...")
all_pairs = []
for split in ['train', 'val', 'test']:
    with open(f'{BASE}/recipe1msubs/{split}_comments_subs.pkl', 'rb') as f:
        data = pickle.load(f)
    for entry in data:
        s = entry.get('subs', [])
        if len(s) >= 2:
            all_pairs.append((
                s[0].replace('_', ' '),
                s[1].replace('_', ' ')
            ))

matched_set        = set(matched.keys())
priority_unmatched = [
    ing for ing in unmatched
    if any(ing == src or ing == tgt for src, tgt in all_pairs)
    and not is_noise(ing)
]

print(f"  Priority ingredients: {len(priority_unmatched):,}")

if priority_unmatched:
    queries = [clean(ing) for ing in priority_unmatched]
    valid   = [(n, q) for n, q in zip(priority_unmatched, queries) if q]
    if valid:
        names_v, queries_v = zip(*valid)
        fuzzy_matched = 0
        BATCH = 500
        for batch_start in tqdm(range(0, len(names_v), BATCH),
                                desc="  Batch priority"):
            batch_end     = min(batch_start + BATCH, len(names_v))
            batch_names   = names_v[batch_start:batch_end]
            batch_queries = queries_v[batch_start:batch_end]
            scores = process.cdist(
                batch_queries, all_descs_c,
                scorer=fuzz.token_sort_ratio, workers=-1)
            for i, ing_name in enumerate(batch_names):
                best_score = scores[i].max()
                if best_score >= 75:
                    best_idx = scores[i].argmax()
                    e = complete_entries[best_idx]
                    matched[ing_name] = {
                        'source':    'fdc_fuzzy_priority',
                        'fdc_id':    e['fdc_id'],
                        'desc':      e['desc'],
                        'p_source':  e['p_source'],
                        'nutrients': e['nutrients'],
                        'score':     int(best_score),
                    }
                    fuzzy_matched += 1
        print(f"  Fuzzy matched: {fuzzy_matched:,}")

# Phosphorus source reclassification
print("\nReclassifying phosphorus sources...")
reclassified = 0
for ing, m in matched.items():
    old = m['p_source']
    new = classify_psource(ing, m.get('desc', ''))
    if new != old:
        m['p_source'] = new
        reclassified += 1

print(f"  Reclassified: {reclassified:,}")
dist = Counter(m['p_source'] for m in matched.values())
print(f"  animal: {dist['animal']:,}  plant: {dist['plant']:,}"
      f"  additive: {dist['additive']:,}  unknown: {dist['unknown']:,}")

# Category mismatch removal
print("\nRemoving category mismatches...")
MISMATCH_RULES = [
    ('chicken',    'chickpea',    'chicken->chickpea'),
    ('coconut',    'chocolate',   'coconut->chocolate'),
    ('cardamom',   'cacao',       'cardamom->cacao'),
    ('cardamom',   'cocoa',       'cardamom->cocoa'),
    ('ampalaya',   'jambalaya',   'ampalaya->jambalaya'),
    ('flaxseed',   'flaxseed oil','flaxseed milk->flaxseed oil'),
    ('coconut milk','chocolate',  'coconut milk->chocolate milk'),
]
BAD_MATCHES = {
    'chicken drumstick', 'extra lemon wedges',
    'drops_maple_oil', '._garlic_chives',
    'breadcrumbs:', 'iced', 'lemon_batter', 'ampalaya',
}

removed_mismatch = []
for ing in list(matched.keys()):
    ing_l  = ing.lower()
    desc_l = matched[ing].get('desc', '').lower()
    if ing in BAD_MATCHES:
        del matched[ing]
        unmatched.append(ing)
        removed_mismatch.append((ing, 'known bad match'))
        continue
    for ing_kw, bad_kw, label in MISMATCH_RULES:
        if ing_kw in ing_l and bad_kw in desc_l \
                and ing_kw not in desc_l:
            del matched[ing]
            unmatched.append(ing)
            removed_mismatch.append((ing, label))
            break

print(f"  Removed {len(removed_mismatch)} mismatches")

# Manual refixes — verified SR Legacy entries for known bad matches
print("\nApplying manual refixes...")
REFIXES = {
    'salmon': {
        'fdc_id': 175167,
        'desc': 'Fish, salmon, Atlantic, wild, raw',
        'p_source': 'animal', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 44.0, 'potassium_mg': 490.0,
                      'phosphorus_mg': 371.0, 'protein_g': 19.8}
    },
    'allspice': {
        'fdc_id': 170931,
        'desc': 'Spices, allspice, ground',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 77.0, 'potassium_mg': 1044.0,
                      'phosphorus_mg': 113.0, 'protein_g': 6.1}
    },
    'cooked bacon': {
        'fdc_id': 167712,
        'desc': 'Pork, cured, bacon, cooked, broiled, pan-fried',
        'p_source': 'animal', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 1030.0, 'potassium_mg': 533.0,
                      'phosphorus_mg': 533.0, 'protein_g': 37.0}
    },
    'canned chicken': {
        'fdc_id': 331960,
        'desc': 'Chicken, broilers or fryers, breast, '
                'meat only, cooked, roasted',
        'p_source': 'animal', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 175.0, 'potassium_mg': 239.0,
                      'phosphorus_mg': 196.0, 'protein_g': 31.0}
    },
    'cashews': {
        'fdc_id': 12087,
        'desc': 'Nuts, cashew nuts, raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 12.0, 'potassium_mg': 565.0,
                      'phosphorus_mg': 490.0, 'protein_g': 18.2}
    },
    'cashew nuts': {
        'fdc_id': 12087,
        'desc': 'Nuts, cashew nuts, raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 12.0, 'potassium_mg': 565.0,
                      'phosphorus_mg': 490.0, 'protein_g': 18.2}
    },
    'turkey': {
        'fdc_id': 171506,
        'desc': 'Turkey, all classes, breast, '
                'meat only, cooked, roasted',
        'p_source': 'animal', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 70.0, 'potassium_mg': 298.0,
                      'phosphorus_mg': 224.0, 'protein_g': 29.0}
    },
    'cooked chicken': {
        'fdc_id': 331960,
        'desc': 'Chicken, broilers or fryers, breast, '
                'meat only, cooked, roasted',
        'p_source': 'animal', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 175.0, 'potassium_mg': 239.0,
                      'phosphorus_mg': 196.0, 'protein_g': 31.0}
    },
    'apple rings': {
        'fdc_id': 171688,
        'desc': 'Apples, raw, with skin',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 1.0, 'potassium_mg': 107.0,
                      'phosphorus_mg': 11.0, 'protein_g': 0.3}
    },
    'scallion': {
        'fdc_id': 170000,
        'desc': 'Onions, spring or scallions '
                '(includes tops and bulb), raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 16.0, 'potassium_mg': 276.0,
                      'phosphorus_mg': 37.0, 'protein_g': 1.8}
    },
    'scallions': {
        'fdc_id': 170000,
        'desc': 'Onions, spring or scallions '
                '(includes tops and bulb), raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 16.0, 'potassium_mg': 276.0,
                      'phosphorus_mg': 37.0, 'protein_g': 1.8}
    },
    'green onion': {
        'fdc_id': 170000,
        'desc': 'Onions, spring or scallions '
                '(includes tops and bulb), raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 16.0, 'potassium_mg': 276.0,
                      'phosphorus_mg': 37.0, 'protein_g': 1.8}
    },
    'green onions': {
        'fdc_id': 170000,
        'desc': 'Onions, spring or scallions '
                '(includes tops and bulb), raw',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 16.0, 'potassium_mg': 276.0,
                      'phosphorus_mg': 37.0, 'protein_g': 1.8}
    },
    'hulled sunflower seeds': {
        'fdc_id': 12036,
        'desc': 'Seeds, sunflower seed kernels, dried',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 9.0, 'potassium_mg': 645.0,
                      'phosphorus_mg': 660.0, 'protein_g': 20.8}
    },
    'seitan': {
        'fdc_id': 174276,
        'desc': 'Vital wheat gluten',
        'p_source': 'plant', 'source': 'alias_fixed', 'score': 100,
        'nutrients': {'sodium_mg': 0.0, 'potassium_mg': 135.0,
                      'phosphorus_mg': 260.0, 'protein_g': 75.0}
    },
}

for ing, fix in REFIXES.items():
    matched[ing] = fix
    print(f"  Fixed: {ing}")

# Final save
matched_set_new = set(matched.keys())
new_unmatched   = [u for u in unmatched if u not in matched_set_new]

with open(f'{OUT_DIR}/usda_matched_full.pkl', 'wb') as f:
    pickle.dump({'matched': matched,
                 'unmatched': new_unmatched}, f, protocol=4)

print(f"\nFinal:")
print(f"  Total matched:   {len(matched):,}")
print(f"  Total unmatched: {len(new_unmatched):,}")
both = sum(1 for src, tgt in all_pairs
           if src in matched_set_new and tgt in matched_set_new)
print(f"  Sub pair coverage: {both:,} / {len(all_pairs):,}"
      f" ({both/len(all_pairs)*100:.1f}%)")
