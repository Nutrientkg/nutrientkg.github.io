# ── Cell A4: Rebuild graph triples ────────────────────────────
# Loads base graph (FoodOn + Recipe1M structure) from
# graph_triples_with_foodon.json and adds:
# - USDA nutrient triples and CKD annotations
# - SNOMED CT owl:sameAs on stage nodes
# - KDIGO 2024 threshold triples on stage nodes
# - stage_order for SPARQL range queries
# - progresses_to chain
# - rdfs:label on ingredient nodes
# - confidence_tier and match provenance on ingredient nodes
# - canonical_name for SPARQL deduplication
# - Substitution edges with frequency counts
# - Safe substitute edges per stage
import json, pickle, re
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

def get_canonical(ing):
    name = ing.lower().strip()
    name = re.sub(r'^[\d/\.\s]+', '', name)
    name = re.sub(
        r'\b(fresh|dried|frozen|canned|chopped|sliced|diced|minced|'
        r'ground|whole|raw|cooked|large|small|medium|extra|fine|'
        r'shredded|grated|organic|reduced|sodium|low|fat|free|'
        r'softened|melted|c\.|pkg\.|jar|can|bottle|box|package)\b',
        '', name)
    return re.sub(r'\s+', ' ', name).strip()

# ── Load data ─────────────────────────────────────────────────
print("Loading matched data...")
with open(f'{OUT_DIR}/usda_matched_full.pkl', 'rb') as f:
    match_data = pickle.load(f)
matched   = match_data['matched']
unmatched = match_data['unmatched']
print(f"  Matched:   {len(matched):,}")
print(f"  Unmatched: {len(unmatched):,}")

print("Loading existing triples...")
with open(f'{BASE}/graph_triples_with_foodon.json') as f:
    triples = json.load(f)
print(f"  Existing: {len(triples):,}")

# ── Remove old predicates before rebuild ─────────────────────
OLD_PREDS = {
    'has_usda_entry', 'sodium_mg', 'potassium_mg',
    'phosphorus_mg', 'protein_g',
    'sodium_mg_per_100g', 'potassium_mg_per_100g',
    'phosphorus_mg_per_100g', 'protein_g_per_100g',
    'phosphorus_source_type', 'has_ckd_risk', 'risk_type',
    'restricted_at', 'safe_at',
    'match_source', 'match_score', 'confidence_tier',
    'at_stage', 'canonical_name', 'fdc_description',
    'substitutes_for', 'substitution_source',
    'substitution_target', 'substitution_frequency',
    'safe_substitute_at_stage_1', 'safe_substitute_at_stage_2',
    'safe_substitute_at_stage_3a', 'safe_substitute_at_stage_3b',
    'safe_substitute_at_stage_4', 'safe_substitute_at_stage_5',
    'owl:sameAs',
    'sodium_threshold_mg', 'potassium_threshold_mg',
    'phosphorus_threshold_mg', 'protein_threshold_g',
    'guideline_source', 'rdf:type', 'progresses_to',
    'stage_order', 'rdfs:label',
}

filtered      = []
noise_removed = 0
for t in triples:
    s, p, o = t
    if p in OLD_PREDS: continue
    if p == 'has_ingredient':
        ing = o.replace('ingredient:', '').replace('_', ' ').strip()
        if is_noise(ing) or len(ing) <= 1:
            noise_removed += 1
            continue
    filtered.append(t)

print(f"  After cleanup:       {len(filtered):,}")
print(f"  Noise edges removed: {noise_removed:,}")
triples = filtered

# ── KDIGO 2024 thresholds ─────────────────────────────────────
# Derived from KDIGO 2024 daily limits / 3 meals per day
# [sodium_mg, potassium_mg, phosphorus_mg, protein_g]
STAGE_THRESHOLDS = {
    'stage_1':  [767, 1567, 400, 23],
    'stage_2':  [767, 1567, 400, 23],
    'stage_3a': [500, 1000, 267, 19],
    'stage_3b': [500,  667, 233, 14],
    'stage_4':  [333,  500, 167, 14],
    'stage_5':  [267,  500, 167,  9],
}

STAGE_ACTIVE_RISKS = {
    'stage_1':  ['high_sodium'],
    'stage_2':  ['high_sodium'],
    'stage_3a': ['high_sodium', 'high_protein'],
    'stage_3b': ['high_sodium', 'high_protein', 'high_potassium',
                 'high_phosphorus_animal', 'high_phosphorus_additive'],
    'stage_4':  ['high_sodium', 'high_protein', 'high_potassium',
                 'high_phosphorus_animal', 'high_phosphorus_additive',
                 'high_phosphorus_plant'],
    'stage_5':  ['high_sodium', 'high_protein', 'high_potassium',
                 'high_phosphorus_animal', 'high_phosphorus_additive',
                 'high_phosphorus_plant'],
}

# SNOMED CT canonical CKD stage concept codes
# Generic stage codes without etiology qualifiers
# Source: SNOMED International clinical finding hierarchy
STAGE_SNOMED = {
    'stage_1':  '431855005',  # Chronic kidney disease stage 1
    'stage_2':  '431856006',  # Chronic kidney disease stage 2
    'stage_3a': '700378005',  # Chronic kidney disease stage 3A
    'stage_3b': '700379002',  # Chronic kidney disease stage 3B
    'stage_4':  '431857002',  # Chronic kidney disease stage 4
    'stage_5':  '433146000',  # Chronic kidney disease stage 5
}

# Numeric order for SPARQL range queries
# stage_3b=4 means FILTER(?ord >= 4) selects stage_3b onwards
STAGE_ORDER = {
    'stage_1': 1, 'stage_2': 2, 'stage_3a': 3,
    'stage_3b': 4, 'stage_4': 5, 'stage_5': 6
}

SNOMED_BASE = 'http://snomed.info/id/'

def get_violations(nutrients, p_source, stage):
    lim    = STAGE_THRESHOLDS[stage]
    active = STAGE_ACTIVE_RISKS[stage]
    na  = nutrients.get('sodium_mg',    0)
    k   = nutrients.get('potassium_mg', 0)
    p   = nutrients.get('phosphorus_mg',0)
    pr  = nutrients.get('protein_g',    0)
    v   = []
    if 'high_sodium'    in active and na > lim[0]:
        v.append('high_sodium')
    if 'high_protein'   in active and pr > lim[3]:
        v.append('high_protein')
    if 'high_potassium' in active and k  > lim[1]:
        v.append('high_potassium')
    if p_source == 'animal' and \
       'high_phosphorus_animal' in active and p > lim[2]:
        v.append('high_phosphorus_animal')
    if p_source == 'additive' and \
       'high_phosphorus_additive' in active and p > lim[2]:
        v.append('high_phosphorus_additive')
    if p_source == 'plant' and \
       'high_phosphorus_plant' in active and p > lim[2]:
        v.append('high_phosphorus_plant')
    return v

# ── Build new triples ─────────────────────────────────────────
new_triples   = []
risk_node_set = set()

# ── Stage metadata: type + SNOMED CT + KDIGO thresholds ───────
print("Adding stage metadata triples...")
for stage, snomed_id in STAGE_SNOMED.items():
    lim = STAGE_THRESHOLDS[stage]
    new_triples.append([stage, 'rdf:type',
                        'CKDStage'])
    new_triples.append([stage, 'owl:sameAs',
                        f"{SNOMED_BASE}{snomed_id}"])
    new_triples.append([stage, 'sodium_threshold_mg',
                        str(lim[0])])
    new_triples.append([stage, 'potassium_threshold_mg',
                        str(lim[1])])
    new_triples.append([stage, 'phosphorus_threshold_mg',
                        str(lim[2])])
    new_triples.append([stage, 'protein_threshold_g',
                        str(lim[3])])
    new_triples.append([stage, 'guideline_source',
                        'KDIGO_2024'])
    new_triples.append([stage, 'stage_order',
                        str(STAGE_ORDER[stage])])

# Stage progression chain
for s, t in [('stage_1',  'stage_2'),
             ('stage_2',  'stage_3a'),
             ('stage_3a', 'stage_3b'),
             ('stage_3b', 'stage_4'),
             ('stage_4',  'stage_5')]:
    new_triples.append([s, 'progresses_to', t])

stage_meta = len(STAGE_SNOMED) * 8 + 5
print(f"  Stage triples added: {stage_meta}")

# ── USDA + CKD annotation triples ────────────────────────────
print("Building USDA + CKD triples...")
for ing_name, match in tqdm(matched.items()):
    ing_id    = f"ingredient:{ing_name.replace(' ', '_')}"
    usda_id   = f"usda:{match['fdc_id']}"
    nutrients = match['nutrients']
    p_source  = match['p_source']

    # Link ingredient to USDA node
    new_triples.append([ing_id, 'has_usda_entry', usda_id])

    # Nutrient values on USDA node — properties of the food
    for k, val in nutrients.items():
        new_triples.append([usda_id, k, str(val)])

    # FDC description and phosphorus source on USDA node
    new_triples.append([usda_id, 'phosphorus_source_type', p_source])
    new_triples.append([usda_id, 'fdc_description',        match['desc']])

    # Match provenance on ingredient node
    # Stored on ing_id not usda_id to avoid multiple values
    # when multiple ingredient strings share the same FDC entry
    score = match.get('score', 100)
    src   = match.get('source', '')
    if src.startswith('alias') or \
       src in ('alias_refix', 'alias_fixed', 'normalised'):
        tier = 'high'
    elif score >= 85:
        tier = 'high'
    elif score >= 80:
        tier = 'medium'
    else:
        tier = 'low'

    new_triples.append([ing_id, 'match_source',    src])
    new_triples.append([ing_id, 'match_score',     str(score)])
    new_triples.append([ing_id, 'confidence_tier', tier])

    # Human-readable label for SPARQL label-based lookup
    new_triples.append([ing_id, 'rdfs:label', ing_name])

    # Canonical name for SPARQL deduplication
    canonical = get_canonical(ing_name)
    if canonical and canonical != ing_name.lower():
        new_triples.append([ing_id, 'canonical_name', canonical])

    # CKD stage annotations
    for stage in STAGE_THRESHOLDS:
        viols = get_violations(nutrients, p_source, stage)
        for vt in viols:
            rn = (f"risk:{ing_name.replace(' ', '_')}"
                  f"_{stage}_{vt}")
            if rn not in risk_node_set:
                new_triples.append([ing_id, 'has_ckd_risk', rn])
                new_triples.append([rn, 'risk_type', vt])
                new_triples.append([rn, 'at_stage',   stage])
                risk_node_set.add(rn)
            new_triples.append([ing_id, 'restricted_at', stage])
        if not viols:
            new_triples.append([ing_id, 'safe_at', stage])

# ── Substitution edges ────────────────────────────────────────
print("Building substitution edges...")
pair_freq = Counter()
for split in ['train', 'val', 'test']:
    with open(f'{BASE}/recipe1msubs/{split}_comments_subs.pkl',
              'rb') as f:
        subs = pickle.load(f)
    for entry in subs:
        s = entry.get('subs', [])
        if len(s) < 2: continue
        src = s[0].replace('_', ' ')
        tgt = s[1].replace('_', ' ')
        if is_noise(src) or is_noise(tgt): continue
        pair_freq[(src, tgt)] += 1

print(f"  Unique pairs: {len(pair_freq):,}")
print(f"  Total obs:    {sum(pair_freq.values()):,}")

sub_added = safe_sub_added = 0
for (src, tgt), freq in pair_freq.items():
    src_id   = f"ingredient:{src.replace(' ', '_')}"
    tgt_id   = f"ingredient:{tgt.replace(' ', '_')}"
    sub_node = (f"sub:{src.replace(' ', '_')}"
                f"_to_{tgt.replace(' ', '_')}")

    new_triples.append([src_id,   'substitutes_for',
                        tgt_id])
    new_triples.append([sub_node, 'rdf:type',
                        'SubstitutionPair'])
    new_triples.append([sub_node, 'substitution_source',
                        src_id])
    new_triples.append([sub_node, 'substitution_target',
                        tgt_id])
    new_triples.append([sub_node, 'substitution_frequency',
                        str(freq)])
    sub_added += 1

    tgt_match = matched.get(tgt)
    if tgt_match:
        for stage in STAGE_THRESHOLDS:
            viols = get_violations(
                tgt_match['nutrients'],
                tgt_match['p_source'],
                stage
            )
            if not viols:
                new_triples.append([
                    src_id,
                    f'safe_substitute_at_{stage}',
                    tgt_id
                ])
                safe_sub_added += 1

print(f"  Substitution pairs:   {sub_added:,}")
print(f"  Safe sub edges:       {safe_sub_added:,}")
print(f"  Risk nodes:           {len(risk_node_set):,}")

# ── Combine and save ──────────────────────────────────────────
import os, shutil

all_triples = triples + new_triples
print(f"\nTotal triples: {len(all_triples):,}")

# Write to /tmp first then copy to Drive to avoid sync corruption
LOCAL_PATH = '/tmp/graph_triples_v2.json'
DRIVE_PATH = f'{OUT_DIR}/graph_triples_v2.json'

import json as _json
print(f"Writing to local path...")
with open(LOCAL_PATH, 'w') as f:
    _json.dump(all_triples, f)
local_size = os.path.getsize(LOCAL_PATH) / 1e9
print(f"Local write complete: {local_size:.2f} GB")

print(f"Copying to Drive...")
shutil.copy2(LOCAL_PATH, DRIVE_PATH)
drive_size = os.path.getsize(DRIVE_PATH) / 1e9
print(f"Drive copy complete:  {drive_size:.2f} GB")
print(f"Saved {DRIVE_PATH}")
