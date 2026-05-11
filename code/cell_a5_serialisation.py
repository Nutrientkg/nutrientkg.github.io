# ── Cell A5: RDF serialisation ────────────────────────────────
# Reads graph_triples_v2.json and serialises to N-Triples.
# Reads from /tmp if available (avoids Drive sync corruption).
# Uses chunked writing to stay within Colab RAM limits.
# Standard predicates (rdf:type, owl:sameAs, rdfs:label, dc:title)
# use their correct vocabulary URIs not the NKGP namespace.
!pip install rdflib ijson tqdm -q
from rdflib import Graph, URIRef, Literal, Namespace, XSD
from rdflib.namespace import OWL, RDF, RDFS, DC
from tqdm.notebook import tqdm
import ijson, os, re

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'
TMP_DIR = '/tmp'

# ── Namespaces ────────────────────────────────────────────────
NUTRIENTKG = Namespace("http://nutrientkg.org/entity/")
NKGP       = Namespace("http://nutrientkg.org/property/")

# ── Standard predicate mapping ────────────────────────────────
# These must use their correct vocabulary URIs not NKGP
STANDARD_PREDS = {
    'owl:sameAs':  OWL.sameAs,
    'rdf:type':    RDF.type,
    'rdfs:label':  RDFS.label,
    'dc:title':    DC.title,
}

# ── Predicates whose objects are literals not URIs ────────────
LITERAL_PREDS = {
    'sodium_mg', 'potassium_mg', 'phosphorus_mg', 'protein_g',
    'match_score', 'match_source', 'phosphorus_source_type',
    'risk_type', 'at_stage', 'dc:title', 'has_amount_grams',
    'reason', 'severity', 'note', 'substitution_frequency',
    'canonical_name', 'confidence_tier', 'fdc_description',
    'sodium_threshold_mg', 'potassium_threshold_mg',
    'phosphorus_threshold_mg', 'protein_threshold_g',
    'guideline_source', 'rdfs:label', 'stage_order',
    'sodium_per_serving', 'potassium_per_serving',
    'phosphorus_per_serving', 'protein_per_serving',
    'servings', 'hasDietaryLabel', 'sourceURL',
}

# ── URI prefix patterns for object nodes ─────────────────────
URI_PREFIXES = (
    'ingredient:', 'usda:', 'recipe:', 'risk:', 'sub:',
    'stage_', 'foodon:', 'category:', 'SubstitutionPair',
    'CKDStage', 'http://snomed.info/',
    'nkf_recipe_', 'NKFRecipe', 'Recipe', 'Organization',
    'nutrientkg:', 'NationalKidneyFoundation',
)

def make_uri(val):
    # Full URIs pass through directly
    if str(val).startswith('http://') or str(val).startswith('https://'):
        return URIRef(str(val))
    clean = str(val)
    clean = re.sub(r'^[\d/\.\s]+', '', clean)
    clean = clean.replace('"', '').replace("'", '')
    clean = clean.replace('<', '').replace('>', '')
    clean = clean.replace('{', '').replace('}', '')
    clean = clean.replace('(', '').replace(')', '')
    clean = clean.replace('[', '').replace(']', '')
    clean = clean.replace('`', '')
    clean = clean.replace('/', '_or_')
    clean = clean.replace('\\', '').replace('|', '')
    clean = clean.replace('&', '_and_').replace('%', '_pct_')
    clean = clean.replace('@', '_at_').replace('#', '')
    clean = clean.replace('!', '').replace('?', '')
    clean = clean.replace(',', '').replace(';', '')
    clean = clean.replace('+', '_plus_')
    clean = clean.replace('~', '').replace('^', '')
    clean = clean.replace(' ', '_').replace(':', '_')
    clean = re.sub(r'_+', '_', clean)
    clean = clean.strip('_')
    # Remove any remaining non-URI-safe characters
    clean = re.sub(r'[^\w\-\.]', '', clean)
    return URIRef(NUTRIENTKG[clean])

def make_pred(p):
    # Standard vocabulary predicates use their correct namespace
    if p in STANDARD_PREDS:
        return STANDARD_PREDS[p]
    # All custom predicates use NKGP namespace
    return URIRef(NKGP[p.replace(' ', '_').replace(':', '_')])

def make_obj(o, p):
    o_str = str(o)
    # owl:sameAs object is always a full external URI
    if p == 'owl:sameAs':
        return URIRef(o_str)
    # Known entity references become URIs
    if p not in LITERAL_PREDS and any(o_str.startswith(px)
                                      for px in URI_PREFIXES):
        return make_uri(o)
    # Numeric values become xsd:decimal literals
    try:
        float(o)
        return Literal(o, datatype=XSD.decimal)
    except:
        return Literal(str(o))

CHUNK_SIZE = 250000

# ── Determine JSON source ─────────────────────────────────────
tmp_json = f'{TMP_DIR}/graph_triples_v2.json'
drv_json = f'{OUT_DIR}/graph_triples_v2.json'

if os.path.exists(tmp_json):
    tmp_size = os.path.getsize(tmp_json) / 1e9
    print(f"Found /tmp file: {tmp_size:.2f} GB — using this")
    JSON_PATH = tmp_json
else:
    drv_size = os.path.getsize(drv_json) / 1e9
    print(f"/tmp not found — using Drive file: {drv_size:.2f} GB")
    JSON_PATH = drv_json

# ── Count triples ─────────────────────────────────────────────
print("\nCounting triples...")
total = 0
with open(JSON_PATH, 'rb') as f:
    for _ in ijson.items(f, 'item'):
        total += 1
print(f"Total: {total:,}")

if total < 28_000_000:
    print("WARNING: triple count lower than expected.")
    print("         Rerun Cell A4 before proceeding.")
    raise SystemExit("Stopping — rerun A4 first.")
else:
    print("Triple count looks correct — proceeding.")

# ── Write NT ──────────────────────────────────────────────────
print("\nSerialising to NT...")
nt_path = f'{OUT_DIR}/nutrientkg_full.nt'
written = 0
skipped = 0

with open(nt_path, 'w', encoding='utf-8') as out_f:
    g_chunk = Graph()
    g_chunk.bind("nutrientkg", NUTRIENTKG)
    g_chunk.bind("nkgp",       NKGP)

    with open(JSON_PATH, 'rb') as f:
        for triple in tqdm(ijson.items(f, 'item'), total=total):
            s, p, o = triple
            try:
                subj = make_uri(s)
                pred = make_pred(p)
                obj  = make_obj(o, p)
                g_chunk.add((subj, pred, obj))
                written += 1
            except Exception:
                skipped += 1
                continue

            if len(g_chunk) >= CHUNK_SIZE:
                out_f.write(g_chunk.serialize(format='nt'))
                g_chunk = Graph()

    if len(g_chunk) > 0:
        out_f.write(g_chunk.serialize(format='nt'))
        del g_chunk

nt_size = os.path.getsize(nt_path) / 1e9
print(f"\nNT written:  {written:,} triples  ({nt_size:.2f} GB)")
print(f"Skipped:     {skipped:,} (invalid URIs)")
print(f"Saved:       {nt_path}")
print(f"\nNamespaces:")
print(f"  Entity:   http://nutrientkg.org/entity/   (prefix: nutrientkg)")
print(f"  Property: http://nutrientkg.org/property/ (prefix: nkgp)")
