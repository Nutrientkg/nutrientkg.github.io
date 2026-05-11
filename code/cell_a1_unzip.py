# ── Cell A1: Unzip FDC files ──────────────────────────────────
import zipfile, os

BASE    = '/content/drive/MyDrive/NutrientKG'
FDC_DIR = f'{BASE}/fdc'

ZIPS = [
    f'{BASE}/FoodData_Central_foundation_food_json_2026-04-30.zip',
    f'{BASE}/FoodData_Central_sr_legacy_food_json_2018-04.zip',
    f'{BASE}/FoodData_Central_survey_food_json_2024-10-31.zip',
    f'{BASE}/FoodData_Central_branded_food_json_2026-04-30.zip',
]

for zpath in ZIPS:
    fname = zpath.split('/')[-1]
    if not os.path.exists(zpath):
        print(f"NOT FOUND: {fname}")
        continue
    size = os.path.getsize(zpath)
    if size < 1000:
        print(f"WARNING: {fname} is only {size} bytes")
        continue
    print(f"Extracting {fname} ({size/1e6:.0f} MB)...")
    with zipfile.ZipFile(zpath, 'r') as z:
        z.extractall(FDC_DIR)
    print(f"  Done")

print("\nFDC folder contents:")
for f in sorted(os.listdir(FDC_DIR)):
    size = os.path.getsize(f'{FDC_DIR}/{f}') / 1e6
    print(f"  {f}  ({size:.0f} MB)")
