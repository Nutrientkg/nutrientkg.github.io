# NutrientKG Pipeline

Construction pipeline for NutrientKG. All cells are written for Google Colab
with data on Google Drive at `MyDrive/NutrientKG/`.

---

## Run Order

```
A0  → Mount Drive and install dependencies
A1  → Unzip FDC bulk download files
A2  → Load FDC into indexed pkl files
A3  → Batch fuzzy matching (3-pass: HQ → complete → full index)
A3b → Priority fixes, normalisation, psource correction, manual refixes
A4  → Rebuild graph triples (USDA + CKD annotations + substitutions)
A5  → Serialise graph_triples_v2.json → nutrientkg_full.nt
A6  → Graph statistics

NKF0 → Install NKF dependencies
NKF1 → Parse nkf_recipe_ingredients_table.md from Drive
NKF2 → Map NKF ingredients to graph ingredient nodes
NKF3a → Scrape per-serving nutrition values from NKF pages
NKF3 → Assign safe stages using KDIGO thresholds
NKF4 → Generate TTL + validate with rdflib
NKF5 → Merge NKF triples into graph_triples_v2.json
A5  → Rerun → reload Blazegraph
```

---

## Required Input Files

Place these in `MyDrive/NutrientKG/`:

```
fdc/
  FoodData_Central_foundation_food_json_2026-04-30.json
  FoodData_Central_sr_legacy_food_json_2018-04.json
  surveyDownload.json
  FoodData_Central_branded_food_json_2026-04-30.json
graph_triples_with_foodon.json   (base graph with FoodOn links)
nkf_recipe_ingredients_table.md  (20 NKF recipes markdown table)
```

FDC bulk downloads are available at https://fdc.nal.usda.gov/download-data

---

## Output Files

All outputs written to `MyDrive/NutrientKG/outputs/`:

```
fdc_index.pkl              467,069 FDC entries (full index)
fdc_index_hq.pkl           High quality entries only (no ALL CAPS branded)
usda_matched_full.pkl      289,760 matched ingredients
graph_triples_v2.json      Complete graph as JSON list of triples
nutrientkg_full.nt         RDF N-Triples — primary serialisation artifact
```

---

## FDC Priority System

Matching searches sub-databases in priority order:

| Priority | Sub-database | Entries | Notes |
|---|---|---|---|
| 1 | Foundation Foods | 395 | Analytically measured, highest quality |
| 2 | SR Legacy | 7,793 | Common foods, complete panels |
| 3 | Survey (FNDDS) | 5,432 | NHANES dietary survey foods |
| 4 | Branded Foods | 455,458 | Manufacturer-reported values |

ALL CAPS branded entries are separated into `fdc_index.pkl` (full) and
`fdc_index_hq.pkl` (no ALL CAPS) to prevent Pass 1 from matching recipe
ingredients to branded products.

---

## Matching Pipeline (A3)

Three passes against different index subsets:

| Pass | Index | Threshold | Purpose |
|---|---|---|---|
| Pass 1 | fdc_index_hq.pkl | score ≥ 85 | High-quality matches only |
| Pass 2 | fdc_index.pkl (complete entries) | score ≥ 80 | Extend coverage |
| Pass 3 | fdc_index.pkl (full) | score ≥ 75 | Maximum coverage |

Confidence tiers:
- High: alias/refix match OR score ≥ 85 — 81,245 ingredients
- Medium: score 80-84 — 101,653 ingredients
- Low: score 75-79 — 106,762 ingredients

---

## KDIGO Violation Logic (A4)

For each matched ingredient and each stage, violations are computed by
checking active nutrient thresholds with phosphorus source awareness:

```python
def get_violations(nutrients, p_source, stage):
    lim    = STAGE_THRESHOLDS[stage]
    active = STAGE_ACTIVE_RISKS[stage]
    violations = []
    if 'high_sodium'    in active and sodium > lim[0]:
        violations.append('high_sodium')
    if 'high_protein'   in active and protein > lim[3]:
        violations.append('high_protein')
    if 'high_potassium' in active and potassium > lim[1]:
        violations.append('high_potassium')
    if p_source == 'animal' and 'high_phosphorus_animal' in active:
        if phosphorus > lim[2]:
            violations.append('high_phosphorus_animal')
    # ... similar for additive and plant
    return violations
```

Ingredients with no violations receive `nkgp:safe_at` to the stage node.
Ingredients with violations receive `nkgp:restricted_at` and a reified
`RiskProfile` node via `nkgp:has_ckd_risk`.

---

## NKF Integration Notes

- Only 9 of 20 recipes in the markdown table are integrated — the verified ones
- Servings and tags are confirmed from NKF page content
- Nutrient values are scraped from NKF page nutrition panels (dietitian-verified)
  not computed from USDA data
- Mexican Rice with Bell Peppers has no nutrition panel — values recorded manually
- Ingredient mapping uses rapidfuzz token_sort_ratio at threshold 80
- Manual overrides in NKF2 fix known bad fuzzy matches

---

## Dependencies

```
rdflib
ijson
tqdm
rapidfuzz
requests
```

Install: `pip install rdflib ijson tqdm rapidfuzz requests`
