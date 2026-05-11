# ── Cell A2: Load and index FDC ───────────────────────────────
# Loads all four FDC sub-databases into fdc_index.pkl (full) and
# fdc_index_hq.pkl (high quality — no ALL CAPS branded entries).
# Applies serving size normalisation with multiplier cap to prevent
# impossible nutrient values from small-portion branded entries.
!pip install tqdm -q
import json, pickle, os
from tqdm.notebook import tqdm

BASE    = '/content/drive/MyDrive/NutrientKG'
FDC_DIR = f'{BASE}/fdc'
OUT_DIR = f'{BASE}/outputs'

NUTRIENT_IDS = {
    1093: 'sodium_mg',
    1092: 'potassium_mg',
    1091: 'phosphorus_mg',
    1003: 'protein_g',
}

HARD_LIMITS = {
    'sodium_mg':     40000,
    'potassium_mg':  20000,
    'phosphorus_mg':  5000,
    'protein_g':       100,
}

ANIMAL_GROUPS = {
    'Beef Products', 'Poultry Products', 'Pork Products',
    'Finfish and Shellfish Products', 'Dairy and Egg Products',
    'Sausages and Luncheon Meats', 'Lamb, Veal, and Game Products',
}
ADDITIVE_GROUPS = {
    'Fast Foods', 'Meals, Entrees, and Side Dishes', 'Restaurant Foods',
}
PLANT_GROUPS = {
    'Legumes and Legume Products', 'Cereal Grains and Pasta',
    'Nut and Seed Products', 'Vegetables and Vegetable Products',
    'Fruits and Fruit Juices', 'Baked Products',
}

def get_p_source(food_group):
    if food_group in ANIMAL_GROUPS:   return 'animal'
    if food_group in ADDITIVE_GROUPS: return 'additive'
    if food_group in PLANT_GROUPS:    return 'plant'
    return 'unknown'

def extract_nutrients(food_entry, serving_size=100, serving_unit='g'):
    nutrients = {}
    for fn in food_entry.get('foodNutrients', []):
        nid = fn.get('nutrient', {}).get('id') or fn.get('nutrientId')
        try:
            nid = int(nid)
        except (TypeError, ValueError):
            continue
        if nid not in NUTRIENT_IDS:
            continue
        val = fn.get('amount') or fn.get('value') or 0
        try:
            val = float(val)
        except:
            val = 0.0

        # Serving size normalisation
        # Only apply when unit is grams and serving differs from 100g
        if serving_unit == 'g' and serving_size and serving_size != 100:
            if 10 <= serving_size <= 500:
                multiplier = 100 / serving_size
                # Cap at 5x — beyond this the conversion is unreliable
                if multiplier <= 5:
                    val = val * multiplier
            # If serving_size < 10g (spice sachets) skip conversion
            # If serving_size > 500g skip conversion

        nutrients[NUTRIENT_IDS[nid]] = round(val, 2)

    # Reject entire entry if any nutrient is impossible
    for k, limit in HARD_LIMITS.items():
        if nutrients.get(k, 0) > limit:
            return {}

    return nutrients

def is_complete(nutrients):
    return {'sodium_mg', 'phosphorus_mg', 'protein_g'}.issubset(
        nutrients.keys())

def is_low_quality_branded(desc, priority):
    """ALL CAPS branded entries have unreliable serving size data."""
    if priority != 4:
        return False
    alpha = [c for c in desc if c.isalpha()]
    if alpha and all(c.isupper() for c in alpha):
        return True
    return False

FILE_CONFIG = [
    {
        'path':     f'{FDC_DIR}/FoodData_Central_foundation_food_json_2026-04-30.json',
        'root_key': 'FoundationFoods',
        'priority': 1
    },
    {
        'path':     f'{FDC_DIR}/FoodData_Central_sr_legacy_food_json_2018-04.json',
        'root_key': 'SRLegacyFoods',
        'priority': 2
    },
    {
        'path':     f'{FDC_DIR}/surveyDownload.json',
        'root_key': 'SurveyFoods',
        'priority': 3
    },
    {
        'path':     f'{FDC_DIR}/FoodData_Central_branded_food_json_2026-04-30.json',
        'root_key': 'BrandedFoods',
        'priority': 4
    },
]

fdc_entries      = []   # high quality entries
fdc_entries_lowq = []   # low quality ALL CAPS branded kept separately

for cfg in FILE_CONFIG:
    if not os.path.exists(cfg['path']):
        print(f"Not found: {cfg['path'].split('/')[-1]}")
        continue
    print(f"Loading {cfg['path'].split('/')[-1]}...")
    with open(cfg['path'], encoding='utf-8') as f:
        data = json.load(f)
    foods    = data.get(cfg['root_key'], [])
    skipped  = 0
    rejected = 0
    low_qual = 0
    print(f"  {len(foods):,} entries")

    for food in tqdm(foods, desc="  Processing"):
        if food is None:
            skipped += 1
            continue
        desc = food.get('description', '').strip()
        if not desc:
            skipped += 1
            continue

        fdc_id     = food.get('fdcId')
        food_group = (
            food.get('foodCategory', {}).get('description', '')
            if isinstance(food.get('foodCategory'), dict)
            else str(food.get('foodCategory', ''))
        )
        serving_size = food.get('servingSize', 100) or 100
        serving_unit = food.get('servingSizeUnit', 'g') or 'g'
        nutrients    = extract_nutrients(food, serving_size, serving_unit)

        if not nutrients:
            rejected += 1
            continue

        entry = {
            'fdc_id':     fdc_id,
            'desc':       desc,
            'desc_lower': desc.lower(),
            'food_group': food_group,
            'p_source':   get_p_source(food_group),
            'nutrients':  nutrients,
            'complete':   is_complete(nutrients),
            'priority':   cfg['priority'],
        }

        if is_low_quality_branded(desc, cfg['priority']):
            fdc_entries_lowq.append(entry)
            low_qual += 1
        else:
            fdc_entries.append(entry)

    print(f"  Skipped:   {skipped}")
    print(f"  Rejected:  {rejected}  (impossible nutrient values)")
    print(f"  Low qual:  {low_qual}  (ALL CAPS branded — kept separately)")

# Full index: high quality + low quality branded at the end
fdc_all = fdc_entries + fdc_entries_lowq

print(f"\nHigh quality entries: {len(fdc_entries):,}")
print(f"Low qual branded:     {len(fdc_entries_lowq):,}")
print(f"Total:                {len(fdc_all):,}")
print(f"Complete entries:     {sum(1 for e in fdc_all if e['complete']):,}")

with open(f'{OUT_DIR}/fdc_index.pkl', 'wb') as f:
    pickle.dump(fdc_all, f, protocol=4)
with open(f'{OUT_DIR}/fdc_index_hq.pkl', 'wb') as f:
    pickle.dump(fdc_entries, f, protocol=4)

print("Saved fdc_index.pkl and fdc_index_hq.pkl")
