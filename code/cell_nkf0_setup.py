# ── Cell NKF-0: Install dependencies ─────────────────────────
!pip install rapidfuzz rdflib tqdm requests -q

from rapidfuzz import process, fuzz, utils
from rdflib import Graph, URIRef, Literal, Namespace, XSD
from rdflib.namespace import OWL, RDF, RDFS, DC
import pickle, json, re, os, shutil

print("Libraries loaded:")
import rapidfuzz, rdflib
print(f"  rapidfuzz: {rapidfuzz.__version__}")
print(f"  rdflib:    {rdflib.__version__}")

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'
TMP_DIR = '/tmp'

print(f"\nPaths:")
print(f"  BASE:    {BASE}")
print(f"  OUT_DIR: {OUT_DIR}")
print(f"  TMP_DIR: {TMP_DIR}")

print(f"\nChecking required files:")
required = [
    f'{BASE}/nkf_recipe_ingredients_table.md',
    f'{OUT_DIR}/usda_matched_full.pkl',
    f'{OUT_DIR}/graph_triples_v2.json',
]
for path in required:
    exists = os.path.exists(path)
    size   = os.path.getsize(path) / 1e6 if exists else 0
    status = f"OK ({size:.1f} MB)" if exists else "MISSING"
    print(f"  {'OK' if exists else 'XX'}  "
          f"{path.split('/')[-1]:<45} {status}")
