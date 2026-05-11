# NutrientKG

**A food-health knowledge graph for disease-aware recipe adaptation in Chronic Kidney Disease (CKD)**

NutrientKG integrates culinary knowledge, USDA nutritional data, validated ingredient substitution pairs from Recipe1M, and KDIGO 2024 clinical staging constraints to enable CKD-stage-aware dietary guidance.

**Website:** https://nutrientkg.github.io  
**Full graph (Zenodo):** *(update after publishing)*

---

## What is NutrientKG?

CKD patients must restrict specific nutrients depending on their disease stage — sodium from Stage 1, protein from Stage 3a, potassium and phosphorus from Stage 3b onwards. Standard food knowledge graphs do not encode these clinical constraints, making them unsuitable for patient-facing dietary tools.

NutrientKG bridges this gap by combining:

- **Recipe1M** — 1M+ recipes with ingredient lists and substitution history
- **USDA FoodData Central** — per-100g nutrient values for 289K matched ingredients
- **KDIGO 2024 guidelines** — per-meal thresholds for sodium, potassium, phosphorus, and protein across 6 CKD stages
- **SNOMED CT** — clinical concept alignment for the 6 CKD stages
- **FoodOn ontology** — food class hierarchy for RGCN message passing
- **NKF recipes** — 9 dietitian-verified CKD-safe recipes from the National Kidney Foundation

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
| NKF recipes integrated | 9 |
| SNOMED CT alignments | 6 |

---

## Repository Structure

```
nutrientkg.github.io/
├── README.md                      this file
├── data/
│   ├── README.md                  data download instructions
│   ├── nutrientkg_sample.nt       subset <100MB for immediate use
│   ├── nkf_recipes_handcrafted.ttl
│   └── nkf_recipes_handcrafted.nt
└── code/
    ├── README.md                  pipeline run instructions
    ├── README_base_graph.md       base graph prerequisites
    ├── data_integration.py        base graph from Recipe1M + FoodOn
    ├── cell_a0_setup.py           ... through cell_a6_statistics.py
    └── cell_nkf0_setup.py         ... through cell_nkf5_merge.py
```

---

## Namespaces

| Prefix | URI |
|--------|-----|
| `nutrientkg:` | `http://nutrientkg.org/entity/` |
| `nkgp:` | `http://nutrientkg.org/property/` |

Standard vocabularies: `rdf:`, `rdfs:`, `owl:`, `dc:`, `xsd:`

---

## Quick Start

**Load the sample graph and run a SPARQL query:**

```python
from rdflib import Graph
g = Graph()
g.parse('data/nutrientkg_sample.nt', format='nt')

result = g.query("""
PREFIX nutrientkg: <http://nutrientkg.org/entity/>
PREFIX nkgp:       <http://nutrientkg.org/property/>

SELECT ?substitute ?frequency
WHERE {
    nutrientkg:ingredient_butter nkgp:substitutes_for ?target .
    nutrientkg:ingredient_butter nkgp:safe_substitute_at_stage_3b ?target .
    ?subNode nkgp:substitution_source nutrientkg:ingredient_butter .
    ?subNode nkgp:substitution_target ?target .
    ?subNode nkgp:substitution_frequency ?frequency .
}
ORDER BY DESC(xsd:decimal(?frequency))
LIMIT 10
""")

for row in result:
    sub = str(row.target).split('ingredient_')[-1].replace('_', ' ')
    print(f"{sub:<35} {row.frequency}")
```

****Load into Blazegraph** (recommended for the full 28M triple graph):

```bash
java -server -Xmx16g -jar blazegraph.jar
# Navigate to localhost:9999 → Update tab → load nutrientkg_full.nt
```

---

## CKD Stage Reference

| Stage | Sodium | Potassium | Phosphorus | Protein | Restrictions active |
|-------|--------|-----------|------------|---------|---------------------|
| 1 | ≤767mg | — | — | — | Na only |
| 2 | ≤767mg | — | — | — | Na only |
| 3a | ≤500mg | — | — | ≤19g | Na, Pr |
| 3b | ≤500mg | ≤667mg | ≤233mg (animal/additive) | ≤14g | Na, Pr, K, P |
| 4 | ≤333mg | ≤500mg | ≤167mg (all sources) | ≤14g | Na, Pr, K, P |
| 5 | ≤267mg | ≤500mg | ≤167mg (all sources) | ≤9g | Na, Pr, K, P |

Values are per meal (daily KDIGO 2024 limits ÷ 3). Phosphorus restrictions at Stage 3b apply to animal and additive sources only; plant phosphorus is restricted from Stage 4 due to lower bioavailability (~30% vs ~50% animal, ~100% additive).

Each stage node carries a SNOMED CT `owl:sameAs` alignment to the corresponding CKD concept in the SNOMED International clinical finding hierarchy.

---

## Reproduce the Graph

See `code/README.md` for the full pipeline run order and input file download links.

---

## Citation

```bibtex
@misc{nutrientkg2026,
  title     = {NutrientKG: A Food-Health Knowledge Graph for
               Disease-Aware Recipe Adaptation},
  author    = {Koul, Vedantt and Anyanwu, Kemafor},
  year      = {2026},
  institution = {North Carolina State University}
}
```
