# ── Cell A0: Mount and setup ──────────────────────────────────
from google.colab import drive
drive.mount('/content/drive')

BASE    = '/content/drive/MyDrive/NutrientKG'
FDC_DIR = f'{BASE}/fdc'
OUT_DIR = f'{BASE}/outputs'

import os
os.makedirs(FDC_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
print("Setup done")
print(f"  BASE:    {BASE}")
print(f"  FDC_DIR: {FDC_DIR}")
print(f"  OUT_DIR: {OUT_DIR}")
