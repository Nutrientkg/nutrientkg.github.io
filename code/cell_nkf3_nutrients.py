# ── Cell NKF-3: Per-serving nutrients + safe stages ───────────
# Uses NKF page scraped values as primary source.
# Applies KDIGO 2024 per-meal thresholds to determine safe stages.
# Run immediately after NKF-3a in the same session.

# ── Fix scraped values before computing stages ────────────────
NKF_NUTRITION['mexican_rice_with_bell_peppers'] = {
    'sodium_mg':     40.0,
    'potassium_mg':  140.0,
    'phosphorus_mg': 90.0,
    'protein_g':     4.0,
}
NKF_NUTRITION['chocolate_zucchini_brownies']['phosphorus_mg'] = 95.0

NUTRIENTS = ['sodium_mg', 'potassium_mg', 'phosphorus_mg', 'protein_g']

# KDIGO 2024 per-meal thresholds
KDIGO = {
    'stage_1':  {'sodium_mg': 767,  'potassium_mg': 1567,
                 'phosphorus_mg': 400,  'protein_g': 23},
    'stage_2':  {'sodium_mg': 767,  'potassium_mg': 1567,
                 'phosphorus_mg': 400,  'protein_g': 23},
    'stage_3a': {'sodium_mg': 500,  'potassium_mg': 1000,
                 'phosphorus_mg': 267,  'protein_g': 19},
    'stage_3b': {'sodium_mg': 500,  'potassium_mg': 667,
                 'phosphorus_mg': 233,  'protein_g': 14},
    'stage_4':  {'sodium_mg': 333,  'potassium_mg': 500,
                 'phosphorus_mg': 167,  'protein_g': 14},
    'stage_5':  {'sodium_mg': 267,  'potassium_mg': 500,
                 'phosphorus_mg': 167,  'protein_g': 9},
}

def safe_stages(per_serving):
    return [
        stage for stage, limits in KDIGO.items()
        if all(per_serving.get(n, 0) <= limits[n] for n in NUTRIENTS)
    ]

recipe_nutrients = {}
summary_rows     = []

for recipe in NKF_RECIPES:
    slug = recipe['slug']
    nuts = NKF_NUTRITION.get(slug)

    if nuts and all(k in nuts for k in NUTRIENTS):
        per_serving = {n: float(nuts[n]) for n in NUTRIENTS}
        source      = 'NKF page'
    elif nuts and any(k in nuts for k in NUTRIENTS):
        per_serving = {n: float(nuts.get(n, 0)) for n in NUTRIENTS}
        source      = 'NKF page (partial)'
    else:
        per_serving = {n: 0.0 for n in NUTRIENTS}
        source      = 'missing'

    stages = safe_stages(per_serving)
    recipe_nutrients[slug] = per_serving

    summary_rows.append({
        'title':  recipe['title'],
        'tags':   ', '.join(recipe['nkf_tags']),
        'na':     per_serving['sodium_mg'],
        'k':      per_serving['potassium_mg'],
        'p':      per_serving['phosphorus_mg'],
        'pr':     per_serving['protein_g'],
        'stages': ', '.join(stages) if stages else 'none',
        'source': source,
    })

    print(f"\n{recipe['title']}")
    print(f"  Source:      {source}")
    print(f"  Na={per_serving['sodium_mg']}mg  "
          f"K={per_serving['potassium_mg']}mg  "
          f"P={per_serving['phosphorus_mg']}mg  "
          f"Pr={per_serving['protein_g']}g")
    print(f"  Safe stages: {stages}")

print(f"\n{'='*125}")
print(f"{'Title':<45} {'Tags':<35} {'Na':>6} {'K':>6} "
      f"{'P':>6} {'Pr':>5}  {'Source':<20}  Safe stages")
print("-" * 125)
for r in summary_rows:
    print(f"  {r['title'][:43]:<45} {r['tags']:<35} "
          f"{r['na']:>6} {r['k']:>6} {r['p']:>6} "
          f"{r['pr']:>5}  {r['source']:<20}  {r['stages']}")
