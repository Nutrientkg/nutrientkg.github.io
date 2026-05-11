# ── Cell NKF-3a: Scrape nutrition from NKF pages ─────────────
# Scrapes per-serving nutrient values from NKF recipe pages.
# Uses &nbsp; handling and range midpoint averaging.
# Mexican Rice with Bell Peppers has no nutrition panel —
# values are hardcoded from manual recording.
import requests, re, time

BASE    = '/content/drive/MyDrive/NutrientKG'
OUT_DIR = f'{BASE}/outputs'

def scrape_nkf_nutrition(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    # Replace &nbsp; with space before stripping tags
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&ndash;', '-').replace('–', '-')
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    def extract(patterns, text):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    val = m.group(1).strip().replace(',', '')
                    # Handle ranges like "300-350" — take midpoint
                    if '-' in val:
                        parts = val.split('-')
                        nums  = [float(p.strip())
                                 for p in parts
                                 if p.strip().replace('.', '').isdigit()]
                        if len(nums) == 2:
                            return round(sum(nums) / 2, 1)
                    return float(val)
                except:
                    continue
        return None

    sodium = extract([
        r'Sodium\s*:?\s*([\d,\.\-]+)\s*(?:to\s*[\d]+\s*)?mg',
        r'sodium\s*:?\s*([\d,\.\-]+)',
    ], text)

    potassium = extract([
        r'Potassium\s*:?\s*([\d,\.\-]+)\s*(?:to\s*[\d]+\s*)?mg',
        r'potassium\s*:?\s*([\d,\.\-]+)',
    ], text)

    phosphorus = extract([
        r'Phosphorus\s*:?\s*([\d,\.\-]+)\s*(?:to\s*[\d]+\s*)?mg',
        r'phosphorus\s*:?\s*([\d,\.\-]+)',
    ], text)

    protein = extract([
        r'Protein\s*:?\s*([\d,\.\-]+)\s*g',
        r'protein\s*:?\s*([\d,\.\-]+)',
    ], text)

    return {
        'sodium_mg':     sodium,
        'potassium_mg':  potassium,
        'phosphorus_mg': phosphorus,
        'protein_g':     protein,
    }

# ── Manual values for pages with no nutrition panel ───────────
MANUAL_NUTRITION = {
    'mexican_rice_with_bell_peppers': {
        'sodium_mg':     40.0,
        'potassium_mg':  140.0,
        'phosphorus_mg': 90.0,
        'protein_g':     4.0,
    },
}

# ── Scrape all verified recipes ───────────────────────────────
NKF_NUTRITION = {}

print(f"{'Recipe':<50} {'Na':>7} {'K':>7} {'P':>7} {'Pr':>5}  Source")
print("-" * 95)

for recipe in NKF_RECIPES:
    slug = recipe['slug']
    url  = recipe['url']

    if slug in MANUAL_NUTRITION:
        NKF_NUTRITION[slug] = MANUAL_NUTRITION[slug]
        nuts = MANUAL_NUTRITION[slug]
        print(f"  {recipe['title'][:48]:<50} "
              f"{nuts['sodium_mg']:>7} "
              f"{nuts['potassium_mg']:>7} "
              f"{nuts['phosphorus_mg']:>7} "
              f"{nuts['protein_g']:>5}  manual")
        continue

    result = scrape_nkf_nutrition(url)
    time.sleep(1)  # polite delay

    if result and any(v is not None for v in result.values()):
        NKF_NUTRITION[slug] = {
            k: v for k, v in result.items() if v is not None
        }
        na = result.get('sodium_mg',     '?')
        k  = result.get('potassium_mg',  '?')
        p  = result.get('phosphorus_mg', '?')
        pr = result.get('protein_g',     '?')
        src = 'NKF page'
    else:
        NKF_NUTRITION[slug] = None
        na = k = p = pr = '?'
        src = 'FAILED'

    print(f"  {recipe['title'][:48]:<50} "
          f"{str(na):>7} {str(k):>7} {str(p):>7} {str(pr):>5}  {src}")

# ── Fix known scraping artifacts ─────────────────────────────
# Chocolate Zucchini Brownies phosphorus has decimal artifact
if 'chocolate_zucchini_brownies' in NKF_NUTRITION \
        and NKF_NUTRITION['chocolate_zucchini_brownies']:
    NKF_NUTRITION['chocolate_zucchini_brownies']['phosphorus_mg'] = 95.0

# Chili Wheat Treats K=0 is verified correct from NKF page
if 'chili_wheat_treats' in NKF_NUTRITION \
        and NKF_NUTRITION['chili_wheat_treats']:
    k_val = NKF_NUTRITION['chili_wheat_treats'].get('potassium_mg', 0)
    if k_val == 0.0:
        print(f"\n  NOTE: Chili Wheat Treats K=0 — verified from NKF page")

print(f"\nScraped: {sum(1 for v in NKF_NUTRITION.values() if v)} "
      f"/ {len(NKF_RECIPES)}")

print(f"\nFinal NKF_NUTRITION:")
print(f"{'Recipe':<50} {'Na':>6} {'K':>6} {'P':>6} {'Pr':>5}")
print("-" * 75)
for slug, nuts in NKF_NUTRITION.items():
    title = next((r['title'] for r in NKF_RECIPES
                  if r['slug'] == slug), slug)
    if nuts:
        print(f"  {title[:48]:<50} "
              f"{nuts.get('sodium_mg', '?'):>6} "
              f"{nuts.get('potassium_mg', '?'):>6} "
              f"{nuts.get('phosphorus_mg', '?'):>6} "
              f"{nuts.get('protein_g', '?'):>5}")
    else:
        print(f"  {title[:48]:<50} FAILED")
