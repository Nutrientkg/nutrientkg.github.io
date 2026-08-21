# NutrientKG

**A food-health knowledge graph for disease-aware recipe adaptation in Chronic Kidney Disease (CKD)**

NutrientKG integrates culinary knowledge, USDA nutritional data, validated ingredient substitution evidence from Recipe1MSubs, food ontology concepts, clinically reviewed kidney-friendly recipes, and CKD dietary constraints to support disease-aware recipe analysis and ingredient substitution.

**Website:** https://nutrientkg.github.io

---

## What is NutrientKG?

Chronic Kidney Disease (CKD) dietary management requires controlling nutrients such as sodium, potassium, phosphorus, and protein. These restrictions change as disease severity progresses, while standard food knowledge graphs generally focus on nutritional or culinary information without explicitly representing CKD-specific clinical constraints.

NutrientKG bridges this gap by integrating:

- **Recipe1M** — more than 1 million recipes and their ingredient lists
- **Recipe1MSubs** — 70,520 observed ingredient-substitution instances
- **USDA FoodData Central (FDC)** — nutrient composition data for sodium, potassium, phosphorus, and protein
- **FoodOn** — food ontology concepts used to provide semantic food classifications
- **KDIGO 2024 guidelines** — CKD-related dietary constraints represented across six CKD stages
- **SNOMED CT** — clinical concept alignment for CKD stages
- **National Kidney Foundation (NKF)** — 256 kidney-friendly recipes represented in the current graph
- **American Kidney Fund (AKF)** — 757 kidney-friendly recipes represented in the current graph

The current NutrientKG release therefore includes **1,013 kidney-focused recipes from NKF and AKF** in addition to the Recipe1M corpus.

---

## Graph Statistics

Statistics below correspond to the current `nutrientkg_v6_akf.nt` release.

| Metric | Value |
|--------|------:|
| Total triples | 26,551,240 |
| Recipes with ingredients | 1,029,544 |
| Ingredient nodes | 299,500 |
| Ingredient nodes with USDA mappings | 256,240 |
| Distinct USDA entries represented | 46,758 |
| Unique Recipe1M ingredient identifiers | 589,831 |
| Recipe ingredient identifiers mapped to USDA | 240,292 (40.74%) |
| Unique substitution-pair ingredients | 5,212 |
| Substitution-pair ingredients with complete Na/K/P/protein profiles | 2,136 (40.98%) |
| Unique substitution pairs | 30,769 |
| FoodOn concepts represented | 23,341 |
| NKF recipes | 256 |
| AKF recipes | 757 |
| CKD stages | 6 |
| SNOMED CT stage alignments | 6 |

### Recipe-Level Nutrient Mapping Coverage

| Coverage | Recipes | Percentage |
|----------|--------:|-----------:|
| Fully mapped | 408,308 | 39.66% |
| Partially mapped | 614,382 | 59.68% |
| Unmapped | 6,854 | 0.67% |

A recipe is considered **fully mapped** when every ingredient in the recipe resolves to at least one USDA nutrient record. A **partially mapped** recipe contains at least one mapped ingredient but also contains one or more unresolved ingredients. An **unmapped** recipe contains no ingredients that resolve to a USDA nutrient record.

### Ingredient Mapping Confidence

Among the 240,292 unique recipe ingredient identifiers with USDA mappings:

| Confidence tier | Ingredients | Percentage |
|-----------------|------------:|-----------:|
| High | 51,060 | 21.25% |
| Medium | 72,721 | 30.26% |
| Low | 116,511 | 48.49% |

High-confidence mappings correspond to a matching score of at least 85 or an alias-based match. Medium-confidence mappings have scores from 80--84, while low-confidence mappings have scores from 75--79.

---

## Knowledge Sources

### Recipe1M

NutrientKG represents **1,029,544 recipes with ingredient information** from the Recipe1M corpus.

Recipe ingredient strings are normalized and linked to canonical ingredient entities before downstream graph construction.

### Recipe1MSubs

Recipe1MSubs contributes **70,520 observed ingredient-substitution instances**. After processing and canonicalization, the current graph contains:

- **30,769 unique substitution pairs**
- **5,212 unique substitution-pair ingredients**
- **2,136 substitution-pair ingredients (40.98%)** with complete sodium, potassium, phosphorus, and protein profiles

Substitution evidence is represented directly in the graph so that culinary substitution evidence can be combined with nutritional and clinical constraints.

### USDA FoodData Central

NutrientKG represents **46,758 distinct USDA FoodData Central entries**.

A total of **256,240 ingredient nodes** have at least one USDA mapping.

Four CKD-relevant nutrients are currently represented:

- Sodium
- Potassium
- Phosphorus
- Protein

Nutrient values are represented on USDA entities and linked to ingredient nodes through NutrientKG relations.

### FoodOn

NutrientKG contains **23,341 distinct FoodOn concepts**, providing semantic food classifications for ingredient entities.

FoodOn is used as an ontological layer, while nutritional composition is obtained independently from USDA FoodData Central.

### Clinically Reviewed Kidney-Friendly Recipes

The current graph contains:

- **256 National Kidney Foundation (NKF) recipes**
- **757 American Kidney Fund (AKF) recipes**

for a total of **1,013 kidney-focused recipes**.

These resources provide clinically relevant recipe examples that complement the large-scale Recipe1M corpus.

### CKD Clinical Knowledge

NutrientKG represents six CKD stages:

1. Stage 1
2. Stage 2
3. Stage 3a
4. Stage 3b
5. Stage 4
6. Stage 5

Each stage is linked to the corresponding SNOMED CT clinical concept and is associated with the dietary constraints encoded in NutrientKG.

---

## Repository Structure

```text
nutrientkg.github.io/
├── README.md
├── data/
│   ├── README.md
│   ├── nutrientkg_sample.nt
│   ├── nkf_recipes_handcrafted.ttl
│   └── nkf_recipes_handcrafted.nt
└── code/
    ├── README.md
    ├── README_base_graph.md
    ├── data_integration.py
    ├── cell_a0_setup.py
    ├── ...
    ├── cell_a6_statistics.py
    ├── cell_nkf0_setup.py
    ├── ...
    └── cell_nkf5_merge.py
```

---

## Namespaces

| Prefix | URI |
|--------|-----|
| `nutrientkg:` | `http://nutrientkg.org/entity/` |
| `nkgp:` | `http://nutrientkg.org/property/` |

Standard RDF vocabularies used include:

- `rdf:`
- `rdfs:`
- `owl:`
- `dc:`
- `xsd:`

---

## Quick Start

### Load NutrientKG with RDFLib

```python
from rdflib import Graph

g = Graph()
g.parse("data/nutrientkg_sample.nt", format="nt")

print(f"Loaded {len(g):,} triples")
```

### Example SPARQL Query

The following query retrieves observed substitutes for butter together with their substitution frequencies:

```python
result = g.query("""
PREFIX nutrientkg: <http://nutrientkg.org/entity/>
PREFIX nkgp:       <http://nutrientkg.org/property/>
PREFIX xsd:        <http://www.w3.org/2001/XMLSchema#>

SELECT ?target ?frequency
WHERE {
    nutrientkg:ingredient_butter
        nkgp:substitutes_for ?target .

    ?subNode
        nkgp:substitution_source nutrientkg:ingredient_butter ;
        nkgp:substitution_target ?target ;
        nkgp:substitution_frequency ?frequency .
}
ORDER BY DESC(xsd:decimal(?frequency))
LIMIT 10
""")

for row in result:
    substitute = (
        str(row.target)
        .split("ingredient_")[-1]
        .replace("_", " ")
    )

    print(f"{substitute:<35} {row.frequency}")
```

---

## Loading the Full Graph

For large-scale querying, a dedicated RDF store such as Blazegraph is recommended.

```bash
java -server -Xmx16g -jar blazegraph.jar
```

After starting Blazegraph, load the full NutrientKG N-Triples file through the Blazegraph interface or bulk-loading utilities.

---

## CKD Stage Reference

The following per-meal thresholds are those currently encoded in NutrientKG.

| Stage | Sodium | Potassium | Phosphorus | Protein | Restrictions active |
|------|---------|-----------|------------|---------|---------------------|
| 1 | ≤767 mg | — | — | — | Na |
| 2 | ≤767 mg | — | — | — | Na |
| 3a | ≤500 mg | — | — | ≤19 g | Na, Protein |
| 3b | ≤500 mg | ≤667 mg | ≤233 mg (animal/additive) | ≤14 g | Na, Protein, K, P |
| 4 | ≤333 mg | ≤500 mg | ≤167 mg | ≤14 g | Na, Protein, K, P |
| 5 | ≤267 mg | ≤500 mg | ≤167 mg | ≤9 g | Na, Protein, K, P |

Values are represented per meal in NutrientKG.

Phosphorus is represented with source-aware bioavailability information. Animal-, plant-, and additive-derived phosphorus are distinguished because their estimated intestinal absorption differs.

Each CKD stage node is aligned with its corresponding SNOMED CT concept using `owl:sameAs`.

---

## What NutrientKG Supports

NutrientKG is designed to support several classes of queries and downstream tasks:

- nutrient lookup for recipe ingredients
- retrieval of observed ingredient substitutions
- CKD constraint checking
- identification of ingredients contributing to nutrient violations
- CKD-aware ingredient substitution
- progression-aware dietary analysis
- comparison of culinary validity and clinical appropriateness
- knowledge-graph-based machine learning and neuro-symbolic reasoning
- evaluation of food recommendation systems against explicit clinical constraints

---

## Availability

**Project website:** https://nutrientkg.github.io

The repository provides the NutrientKG resource, sample RDF data, construction code, and supporting materials for querying and reproducing the knowledge graph.
## Reproduce the Graph

See `code/README.md` for the full pipeline run order.

---
