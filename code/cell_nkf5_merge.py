# ── Cell NKF-5: Merge NKF triples into main graph ─────────────
# Reads nkf_recipes_handcrafted.nt and merges into
# graph_triples_v2.json. Writes to /tmp first then copies to
# Drive to avoid sync corruption. After this rerun Cell A5
# to regenerate nutrientkg_full.nt and reload into Blazegraph.
import json, shutil, os
from rdflib import Graph as RGraph, URIRef, Literal

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

NKG_ENT  = "http://nutrientkg.org/entity/"
NKG_PROP = "http://nutrientkg.org/property/"

PRED_MAP = {
    'http://www.w3.org/1999/02/22-rdf-syntax-ns#type': 'rdf:type',
    'http://www.w3.org/2000/01/rdf-schema#label':       'rdfs:label',
    'http://www.w3.org/2002/07/owl#sameAs':             'owl:sameAs',
}

# Load main graph from /tmp if available else Drive
tmp_json = '/tmp/graph_triples_v2.json'
drv_json = f'{OUT_DIR}/graph_triples_v2.json'

if os.path.exists(tmp_json):
    print("Loading from /tmp...")
    src_path = tmp_json
else:
    print("Loading from Drive...")
    src_path = drv_json

with open(src_path) as f:
    main_triples = json.load(f)
print(f"Main graph: {len(main_triples):,} triples")

# Parse NKF NT file
nkf_g = RGraph()
nkf_g.parse(f'{BASE}/nkf_recipes_handcrafted.nt', format='nt')
print(f"NKF graph:  {len(nkf_g):,} triples")

# Convert NKF triples to JSON triple format
new_triples = []
for s, p, o in nkf_g:
    s_str = str(s).replace(NKG_ENT, '')
    p_str = PRED_MAP.get(str(p),
            str(p).replace(NKG_PROP, ''))
    if isinstance(o, URIRef):
        o_str = str(o).replace(NKG_ENT, '')
    else:
        o_str = str(o)
    new_triples.append([s_str, p_str, o_str])

all_triples = main_triples + new_triples
print(f"NKF triples added: {len(new_triples):,}")
print(f"Total:             {len(all_triples):,}")

# Write to /tmp first then copy to Drive
LOCAL_PATH = '/tmp/graph_triples_v2.json'
DRIVE_PATH = f'{OUT_DIR}/graph_triples_v2.json'

with open(LOCAL_PATH, 'w') as f:
    json.dump(all_triples, f)
local_size = os.path.getsize(LOCAL_PATH) / 1e9
print(f"Local write: {local_size:.2f} GB")

shutil.copy2(LOCAL_PATH, DRIVE_PATH)
drive_size = os.path.getsize(DRIVE_PATH) / 1e9
print(f"Drive copy:  {drive_size:.2f} GB")
print(f"Saved {DRIVE_PATH}")
print(f"\nNext: rerun Cell A5 then reload Blazegraph.")
