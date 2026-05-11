# Base Graph Construction Pipeline

This pipeline (`data_integration.py`) is the upstream step that runs
**before** the main NutrientKG pipeline (A0-A6). It produces
`graph_triples.json` which feeds into the main pipeline as the base
graph containing FoodOn links and initial ingredient-recipe structure.

---

## Role in the Full Pipeline

```
data_integration.py          ← THIS FILE
        ↓
graph_triples.json           (base graph — FoodOn + Recipe1M + initial USDA)
        ↓
graph_triples_with_foodon.json  (saved to Drive — input to Cell A4)
        ↓
A2 → A3 → A3b → A4 → A5     (main NutrientKG pipeline)
        ↓
graph_triples_v2.json
        ↓
nutrientkg_full.nt           (final RDF artifact)
```

The base graph handles Recipe1M loading, initial USDA matching via a
three-tier matcher, FoodOn ontology links, and stage-agnostic
substitution pair loading. The main pipeline replaces the USDA matching
with the higher-quality A2/A3 FDC pipeline and rebuilds all clinical
annotations from scratch using KDIGO 2024 thresholds.

---

## What This Pipeline Does

**Food side**
- Recipe1M → Recipe nodes and raw ingredient strings
- USDA SR Legacy → nutrient values per 100g via three-tier matcher
- Recipe1MSubs → substitution pairs from train/val/test pkl splits
- FoodOn ontology → ingredient class links via FoodKG N-Triples

**Disease side**
- KDIGO 2024 thresholds → CKD stage nodes
- Per-ingredient risk profiles at each stage
- Stage-qualified safe substitution edges

**Alignment**
- Normalised ingredient names → FlavorGraph vocabulary
- FoodOn URIs ↔ USDA FDC IDs via FoodKG links
- Recipe1MSubs ingredient names → normalised vocabulary

---

## Input Files Required

```
C:\Users\Vedantt\NSAI Data\recipe1M_layers\layer1.json
C:\Users\Vedantt\NSAI Data\usda\usda_sr_legacy.json
C:\Users\Vedantt\NSAI Data\recipe1msubs\train_comments_subs.pkl
C:\Users\Vedantt\NSAI Data\recipe1msubs\val_comments_subs.pkl
C:\Users\Vedantt\NSAI Data\recipe1msubs\test_comments_subs.pkl
```

Recipe1MSubs split files available at:
```
https://dl.fbaipublicfiles.com/gismo/train_comments_subs.pkl
https://dl.fbaipublicfiles.com/gismo/val_comments_subs.pkl
https://dl.fbaipublicfiles.com/gismo/test_comments_subs.pkl
```

USDA SR Legacy JSON available at:
```
https://fdc.nal.usda.gov/download-data
```

---

## How to Run

Test run (500 recipes — fast):
```bash
python data_integration.py
```

Custom limit:
```bash
python data_integration.py --limit 10000
```

Full run (all 1M+ recipes — 20-40 minutes):
```bash
python data_integration.py --full
```

---

## Output Files

All outputs written to `outputs/`:

```
outputs/
  coverage_report.txt         USDA match rate and coverage statistics
  unmatched_ingredients.txt   Ingredient strings with no USDA match
  graph_triples.json          Base graph as list of (s, p, o) triples
```

`graph_triples.json` is renamed to `graph_triples_with_foodon.json`
and placed in `MyDrive/NutrientKG/` before running the main pipeline.

---

## USDA Matching — Three-Tier System

| Tier | Method | Notes |
|---|---|---|
| 1 | Alias cache | ~600 hand-mapped ingredient → USDA description pairs |
| 2a | Exact description match | Lowercased exact string match |
| 2b | First-word index | Overlap score on words starting with same token |
| 3 | N-gram semantic fallback | Trigram cosine similarity, threshold 0.42 |

This is superseded by the A2/A3 FDC pipeline in the main pipeline which
uses RapidFuzz token_sort_ratio across 467,069 FDC entries with priority
ordering across four sub-databases.

---

## Key Design Decisions

**FoodKG excluded from final pipeline.** FoodKG does not provide a
downloadable RDF dump — it must be built from Recipe1M using Python 3.7
build scripts. The USDA links it provides are covered by the A2/A3
matcher. FoodOn links from this base graph are preserved in
`graph_triples_with_foodon.json` and passed through to the main pipeline
where they serve RGCN message passing only and are isolated from the
clinical reasoning layer.

**Stage-qualified substitutions.** A substitution source → target is
included at stage X only if the target has zero active risk flags at that
stage. No severity gradation — any risk flag at that stage excludes the
pair. This is stricter than the main pipeline's `safe_substitute_at_stage_X`
edges which use the same logic via the KDIGO violation check in Cell A4.

**Mock data fallback.** If any input file is missing the pipeline falls
back to mock data covering ~100 common ingredients and 4 sample recipes.
This allows the pipeline to run without the full datasets for testing.

---

## Dependencies

```
numpy
```

No external NLP or embedding libraries required. The n-gram semantic
matcher is implemented from scratch using numpy. For production use,
replace `_SemanticMatcher` with a sentence-transformers model for higher
match quality.

Install:
```bash
pip install numpy
```

Optional for pandas-format Recipe1MSubs files:
```bash
pip install pandas
```
