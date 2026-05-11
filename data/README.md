# NutrientKG Data

---

## Full Knowledge Graph

The complete NutrientKG graph (28,047,658 triples, ~4GB) is hosted on Zenodo:

**Zenodo DOI:** *(update after publishing)*  
**Download:** `nutrientkg_full.nt` (N-Triples format)

---

## Files in this directory

### `nutrientkg_sample.nt`

A representative subset of the full graph for immediate exploration, under 100MB. Contains:

- All 6 CKD stage nodes with SNOMED CT `owl:sameAs` links and KDIGO 2024 threshold triples
- All 9 NKF recipe nodes with `has_ingredient`, `safe_at`, and per-serving nutrient triples
- 5,000 high-confidence ingredient nodes (match score ≥ 85) with full USDA nutrient values, CKD annotations, and substitution edges
- FoodOn class hierarchy (`subclass_of` edges)

Load into Blazegraph or rdflib for SPARQL queries.

### `nkf_recipes_handcrafted.ttl`

Turtle RDF for the 9 NKF-verified CKD-safe recipes. Each recipe node includes:
- `rdf:type nutrientkg:NKFRecipe` and `rdf:type nutrientkg:Recipe`
- Per-serving sodium, potassium, phosphorus, and protein values scraped from kidney.org
- `nkgp:has_ingredient` links to graph ingredient nodes
- `nkgp:safe_at` links to CKD stage nodes based on KDIGO 2024 thresholds
- `nkgp:validatedBy nutrientkg:NationalKidneyFoundation`
- NKF dietary labels (low-sodium, low-potassium, low-phosphorus)

### `nkf_recipes_handcrafted.nt`

Same content as the TTL file in N-Triples format. Use this for loading into Blazegraph alongside the full graph.

---

## Namespaces

| Prefix | URI |
|--------|-----|
| `nutrientkg:` | `http://nutrientkg.org/entity/` |
| `nkgp:` | `http://nutrientkg.org/property/` |

---

## Loading into Blazegraph

1. Download and run Blazegraph: `java -server -Xmx16g -jar blazegraph.jar`
2. Navigate to `localhost:9999`
3. Go to the **Update** tab
4. Load `nutrientkg_full.nt` (or `nutrientkg_sample.nt` for the subset)
5. Run SPARQL queries from the **Query** tab

---

## Loading into rdflib

```python
from rdflib import Graph

g = Graph()
g.parse('nutrientkg_sample.nt', format='nt')
print(f"Loaded {len(g):,} triples")
```

---

## Graph Statistics

| Metric | Value |
|--------|-------|
| Total triples | 28,047,658 |
| Unique predicates | 32 |
| Recipes | 1,029,568 |
| Unique ingredients | 675,940 |
| Matched to FDC | 289,760 (42.9%) |
| Substitution observations | 70,520 |
| Unique substitution pairs | 30,782 |
| Safe substitution edges | 116,786 |
| Clinical risk nodes | 1,009,042 |
| FoodOn classes used | 10,383 |
| NKF recipes | 9 |
| SNOMED CT alignments | 6 |

---

## Citation

If you use NutrientKG please cite:

```bibtex
@misc{nutrientkg2026,
  title     = {NutrientKG: A Food-Health Knowledge Graph for
               Disease-Aware Recipe Adaptation},
  author    = {Koul, Vedantt and Anyanwu, Kemafor},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {UPDATE_AFTER_PUBLISHING}
}
```
