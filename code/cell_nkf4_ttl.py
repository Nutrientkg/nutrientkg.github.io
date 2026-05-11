# ── Cell NKF-4: Generate TTL and validate ─────────────────────
# Generates Turtle RDF for all 9 NKF recipes with:
# - rdf:type NKFRecipe and Recipe (dual typing)
# - per-serving nutrient values from NKF page
# - has_ingredient links to existing graph ingredient nodes
# - safe_at links to CKDStage nodes based on KDIGO evaluation
# - validatedBy NationalKidneyFoundation
# Validates with rdflib and serialises to NT.
from rdflib import Graph

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

def safe_stages(per_serving):
    return [
        stage for stage, limits in KDIGO.items()
        if all(per_serving.get(n, 0) <= limits[n] for n in NUTRIENTS)
    ]

ttl_lines = [
    '@prefix nutrientkg: <http://nutrientkg.org/entity/> .',
    '@prefix nkgp:       <http://nutrientkg.org/property/> .',
    '@prefix rdf:        <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .',
    '@prefix rdfs:       <http://www.w3.org/2000/01/rdf-schema#> .',
    '@prefix xsd:        <http://www.w3.org/2001/XMLSchema#> .',
    '',
    'nutrientkg:NationalKidneyFoundation',
    '    rdf:type       nutrientkg:Organization ;',
    '    rdfs:label     "National Kidney Foundation"@en ;',
    '    nkgp:sourceURL "https://www.kidney.org"^^xsd:anyURI .',
    '',
]

for recipe in NKF_RECIPES:
    slug        = recipe['slug']
    per_serving = recipe_nutrients[slug]
    stages      = safe_stages(per_serving)
    node        = f"nutrientkg:nkf_recipe_{slug}"

    props = []
    props.append(
        f"    rdf:type                     nutrientkg:NKFRecipe")
    props.append(
        f"    rdf:type                     nutrientkg:Recipe")
    props.append(
        f'    rdfs:label                   "{recipe["title"]}"@en')
    props.append(
        f'    nkgp:sourceURL               "{recipe["url"]}"^^xsd:anyURI')
    props.append(
        f'    nkgp:servings                '
        f'"{recipe["servings"]}"^^xsd:integer')
    props.append(
        f"    nkgp:validatedBy             "
        f"nutrientkg:NationalKidneyFoundation")

    for tag in recipe['nkf_tags']:
        props.append(
            f'    nkgp:hasDietaryLabel         "{tag}"@en')

    props.append(
        f'    nkgp:sodium_per_serving      '
        f'"{per_serving["sodium_mg"]}"^^xsd:decimal')
    props.append(
        f'    nkgp:potassium_per_serving   '
        f'"{per_serving["potassium_mg"]}"^^xsd:decimal')
    props.append(
        f'    nkgp:phosphorus_per_serving  '
        f'"{per_serving["phosphorus_mg"]}"^^xsd:decimal')
    props.append(
        f'    nkgp:protein_per_serving     '
        f'"{per_serving["protein_g"]}"^^xsd:decimal')

    # Link to matched ingredient nodes — deduplicated
    seen_ings = set()
    for _, ing_str in recipe['ingredients']:
        ing_id = nkf_ing_map.get((slug, ing_str))
        if ing_id and ing_id not in seen_ings:
            ing_uri = (f"nutrientkg:"
                       f"{ing_id.replace('ingredient:', 'ingredient_')}")
            props.append(
                f"    nkgp:has_ingredient          {ing_uri}")
            seen_ings.add(ing_id)

    for stage in stages:
        props.append(
            f"    nkgp:safe_at                 nutrientkg:{stage}")

    # Write block with correct ; and . punctuation
    ttl_lines.append(f"{node}")
    for i, prop in enumerate(props):
        if i < len(props) - 1:
            ttl_lines.append(f"{prop} ;")
        else:
            ttl_lines.append(f"{prop} .")
    ttl_lines.append('')

ttl_path = f'{BASE}/nkf_recipes_handcrafted.ttl'
nt_path  = f'{BASE}/nkf_recipes_handcrafted.nt'

with open(ttl_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(ttl_lines))

g = Graph()
g.parse(ttl_path, format='turtle')
print(f"Triples: {len(g)}")
g.serialize(nt_path, format='nt')
print(f"Saved: {ttl_path}")
print(f"Saved: {nt_path}")

# Summary
print(f"\n{'Title':<45} {'Stages':<50} {'Ings linked':>10}")
print("-" * 110)
for recipe in NKF_RECIPES:
    slug   = recipe['slug']
    stages = safe_stages(recipe_nutrients[slug])
    n_ings = len({nkf_ing_map.get((slug, ing_str))
                  for _, ing_str in recipe['ingredients']
                  if nkf_ing_map.get((slug, ing_str))})
    print(f"  {recipe['title'][:43]:<45} "
          f"{', '.join(stages) if stages else 'none':<50} "
          f"{n_ings:>10}")
