# ── Cell A6: Graph statistics ─────────────────────────────────
import ijson, pickle, json
from collections import Counter, defaultdict
from tqdm.notebook import tqdm

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

# Load matched data for coverage stats
with open(f'{OUT_DIR}/usda_matched_full.pkl', 'rb') as f:
    match_data = pickle.load(f)
matched   = match_data['matched']
unmatched = match_data['unmatched']

REQUIRED  = ['sodium_mg', 'potassium_mg', 'phosphorus_mg', 'protein_g']
matched_set       = set(matched.keys())
fully_connected   = {ing for ing, m in matched.items()
                     if all(m['nutrients'].get(k, 0) > 0
                            for k in REQUIRED)}

# Stream graph for statistics
print("Streaming graph...")
tmp_json = '/tmp/graph_triples_v2.json'
drv_json = f'{OUT_DIR}/graph_triples_v2.json'
JSON_PATH = tmp_json if __import__('os').path.exists(tmp_json) else drv_json

pred_counts = Counter()
recipe_ings = defaultdict(set)
stage_safe  = Counter()
stage_restr = Counter()
sub_edges   = Counter()

with open(JSON_PATH, 'rb') as f:
    for triple in tqdm(ijson.items(f, 'item')):
        s, p, o = triple
        pred_counts[p] += 1
        if p == 'has_ingredient':
            recipe_ings[s.replace('recipe:', '')].add(
                o.replace('ingredient:', '').replace('_', ' '))
        if p == 'safe_at':       stage_safe[o]  += 1
        if p == 'restricted_at': stage_restr[o] += 1
        if p == 'substitutes_for': sub_edges['total'] += 1
        if p.startswith('safe_substitute_at_'):
            sub_edges[p.replace('safe_substitute_at_', '')] += 1

total     = len(recipe_ings)
fully     = sum(1 for v in recipe_ings.values()
                if all(i in matched_set for i in v))
partial   = sum(1 for v in recipe_ings.values()
                if any(i in matched_set for i in v)
                and not all(i in matched_set for i in v))
zero      = sum(1 for v in recipe_ings.values()
                if not any(i in matched_set for i in v))
fully_4   = sum(1 for v in recipe_ings.values()
                if all(i in fully_connected for i in v) and len(v) > 0)
avg_ings  = sum(len(v) for v in recipe_ings.values()) / total
avg_mat   = sum(sum(1 for i in v if i in matched_set)
                for v in recipe_ings.values()) / total

total_ings = len(matched) + len(unmatched)

print(f"\n{'='*60}")
print(f"NUTRIENTKG FINAL STATISTICS")
print(f"{'='*60}")
print(f"\nGraph:              {sum(pred_counts.values()):,} triples"
      f", {len(pred_counts)} predicates")
print(f"\nIngredients:")
print(f"  Total unique:     {total_ings:,}")
print(f"  Matched:          {len(matched):,}"
      f" ({len(matched)/total_ings*100:.1f}%)")
print(f"  All 4 nutrients:  {len(fully_connected):,}"
      f" ({len(fully_connected)/total_ings*100:.1f}%)")
print(f"\nRecipes:")
print(f"  Total:            {total:,}")
print(f"  Fully mapped:     {fully:,} ({fully/total*100:.1f}%)")
print(f"  Partially mapped: {partial:,} ({partial/total*100:.1f}%)")
print(f"  Zero mapped:      {zero:,} ({zero/total*100:.1f}%)")
print(f"  Avg ings/recipe:  {avg_ings:.1f}")
print(f"  Avg matched/rec:  {avg_mat:.1f} ({avg_mat/avg_ings*100:.1f}%)")
print(f"\nSubstitution edges: {sub_edges['total']:,}")
print(f"Safe sub per stage:")
for stage in ['stage_1', 'stage_2', 'stage_3a',
              'stage_3b', 'stage_4', 'stage_5']:
    print(f"  {stage}: safe_at={stage_safe[stage]:,} "
          f"restricted_at={stage_restr[stage]:,} "
          f"safe_sub={sub_edges[stage]:,}")
print(f"\nClinical risk nodes: {pred_counts.get('risk_type', 0):,}")
print(f"\nAll predicates:")
for pred, count in pred_counts.most_common():
    print(f"  {pred:<42} {count:,}")

with open(f'{OUT_DIR}/nutrientkg_stats.json', 'w') as f:
    json.dump({
        'total_triples':          sum(pred_counts.values()),
        'total_ingredients':      total_ings,
        'matched':                len(matched),
        'fully_connected':        len(fully_connected),
        'total_recipes':          total,
        'fully_mapped':           fully,
        'partially_mapped':       partial,
        'zero_mapped':            zero,
        'avg_ings_per_recipe':    round(avg_ings, 2),
        'avg_matched_per_recipe': round(avg_mat, 2),
        'sub_edges':              dict(sub_edges),
        'stage_safe':             dict(stage_safe),
        'stage_restr':            dict(stage_restr),
        'predicate_counts':       dict(pred_counts.most_common()),
    }, f, indent=2)
print(f"\nSaved nutrientkg_stats.json")
