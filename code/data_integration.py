"""
CKD Data Integration Pipeline
==============================

Organises all datasets into a unified graph-ready structure before
the graph is actually built.  This module handles:

  Food side
  ---------
  Recipe1M        → Recipe nodes + raw ingredient strings
  FoodKG (RDF)    → existing ingredient→FoodOn + ingredient→USDA links
  USDA SR Legacy  → nutrient values per 100g
  Recipe1MSubs    → substitution pairs (.pkl)

  Disease side
  ------------
  KDIGO 2024      → CKD stage thresholds → ingredient risk profiles

  Alignment
  ---------
  Normalised ingredient names → FlavorGraph vocabulary
  FoodOn URIs ←skos:closeMatch→ USDA FDC IDs
  Recipe1MSubs ingredient names → normalised vocabulary

HOW TO RUN
----------
First run (test with 500 recipes — fast):
    python data_integration.py

Full run (all 1M recipes — slow, ~20-40 min):
    python data_integration.py --full

Outputs written to:
    outputs/coverage_report.txt
    outputs/unmatched_ingredients.txt
    outputs/graph_triples.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

# ── inline copies of pipeline functions so this file is self-contained ────────
# (if you have pipeline.py in the same folder, you can replace these with:
#   from pipeline import parse_amount_to_grams, normalize_ingredient_name, ...)

UNIT_TO_GRAMS: dict[str, float] = {
    "cup": 240, "cups": 240,
    "tbsp": 15, "tablespoon": 15, "tablespoons": 15,
    "tsp": 5,   "teaspoon": 5,   "teaspoons": 5,
    "oz": 28.35,"ounce": 28.35,  "ounces": 28.35,
    "lb": 453.6,"pound": 453.6,  "pounds": 453.6,
    "g": 1,     "gram": 1,       "grams": 1,
    "kg": 1000,
    "ml": 1,    "l": 1000,
    "pinch": 0.3, "dash": 0.6,
    "slice": 30, "slices": 30,
    "clove": 5,  "cloves": 5,
    "bunch": 100,"piece": 50, "pieces": 50,
    "can": 400,  "cans": 400,
    "fillet": 150, "fillets": 150,
    "stalk": 40, "stalks": 40,
    "sprig": 3,  "sprigs": 3,
    "head": 600, "heads": 600,
    "packet": 30,"packets": 30,
}
_SORTED_UNITS = sorted(UNIT_TO_GRAMS, key=len, reverse=True)

UNMEASURABLE = {
    "to taste", "as needed", "as desired", "as required",
    "optional", "for garnish", "garnish", "a handful",
    "handful", "to serve", "for serving", "for topping",
}

UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3",
    "¼": "1/4", "¾": "3/4", "⅛": "1/8",
    "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
    "⅙": "1/6", "⅚": "5/6", "⅕": "1/5",
    "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
}

PREP_MODIFIERS = {
    "finely chopped", "coarsely chopped", "roughly chopped", "chopped",
    "minced", "diced", "sliced", "thinly sliced", "thickly sliced",
    "julienned", "grated", "shredded", "torn", "crushed", "crumbled",
    "mashed", "toasted", "roasted", "grilled", "fried", "sautéed",
    "steamed", "blanched", "boiled", "poached", "smoked", "cured",
    "frozen", "thawed", "dried", "dehydrated", "reconstituted",
    "fresh", "canned", "jarred", "pickled", "marinated", "fermented",
    "peeled", "seeded", "pitted", "trimmed", "cored", "deveined",
    "halved", "quartered", "cubed", "ground", "whole", "boneless",
    "skinless", "lean", "extra-lean", "low-fat", "fat-free", "reduced-fat",
    "unsalted", "salted", "sweetened", "unsweetened",
    "at room temperature", "softened", "melted", "room temperature",
    "packed", "lightly packed", "firmly packed",
    "heaping", "level", "scant", "large", "small", "medium",
}
_SORTED_MODS = sorted(PREP_MODIFIERS, key=len, reverse=True)


def parse_amount_to_grams(raw: str) -> Optional[float]:
    """Extract the leading amount from a Recipe1M ingredient string → grams."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if any(u in s for u in UNMEASURABLE):
        return None
    for uc, asc in UNICODE_FRACTIONS.items():
        s = s.replace(uc, asc)
    s = re.sub(r"\(.*?\)", "", s).strip()

    _num = (
        r"(?:"
        r"(\d+)\s+(\d+)\s*/\s*(\d+)"
        r"|(\d+)\s*/\s*(\d+)"
        r"|([\d.]+)\s*[-–]\s*([\d.]+)"
        r"|([\d.]+)"
        r")"
    )
    _unit = r"(?:\s*(" + "|".join(re.escape(u) for u in _SORTED_UNITS) + r"))?"
    m = re.match(r"^\s*" + _num + _unit, s, re.IGNORECASE)
    if not m:
        return None

    (mw, mn, md, fn, fd, rlo, rhi, plain, unit_word) = m.groups()
    if mw is not None:
        den = int(md)
        if den == 0: return None
        numeric = int(mw) + int(mn) / den
    elif fn is not None:
        den = int(fd)
        if den == 0: return None
        numeric = int(fn) / den
    elif rlo is not None:
        numeric = (float(rlo) + float(rhi)) / 2
    elif plain is not None:
        try: numeric = float(plain)
        except ValueError: return None
    else:
        return None

    unit_grams = UNIT_TO_GRAMS.get((unit_word or "").strip().lower(), 100.0)
    return round(numeric * unit_grams, 3)


def normalize_ingredient_name(raw: str) -> str:
    """Strip amount, unit, modifiers from a Recipe1M ingredient string."""
    s = raw.lower().strip()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(
        r"^[\d\s/½¼¾⅓⅔⅛⅜⅝⅞.]+\s*"
        r"(?:(?:" + "|".join(re.escape(u) for u in _SORTED_UNITS) + r")\s*)?",
        "", s,
    )
    s = s.split(",")[0]
    for mod in _SORTED_MODS:
        s = re.sub(r"\b" + re.escape(mod) + r"\b", "", s)
    for unit in UNIT_TO_GRAMS:
        s = re.sub(r"\b" + re.escape(unit) + r"\b", "", s)
    trailing = ["to taste", "as needed", "as desired", "as required",
                "for garnish", "for serving", "to serve"]
    for t in trailing:
        if s.endswith(t):
            s = s[: -len(t)].strip()

    # strip "to 1/2", "to 3" etc. left by range parsing like "1 to 1/2 tsp"
    s = re.sub(r"^to\s+[\d/½¼¾⅓⅔]+", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


# ── simple n-gram semantic matcher (no external deps) ──────────────────────────

class _SemanticMatcher:
    def __init__(self, corpus: list[str]):
        self._corpus = corpus
        self._vocab: dict[str, int] = {}
        self._matrix = self._build(corpus)

    def _ngrams(self, t: str, n: int = 3) -> list[str]:
        p = f"  {t}  "
        return [p[i:i+n] for i in range(len(p) - n + 1)]

    def _build(self, texts: list[str]) -> np.ndarray:
        for text in texts:
            for ng in self._ngrams(text.lower()):
                if ng not in self._vocab:
                    self._vocab[ng] = len(self._vocab)
        mat = np.zeros((len(texts), len(self._vocab)), dtype=np.float32)
        for i, text in enumerate(texts):
            for ng in self._ngrams(text.lower()):
                if ng in self._vocab:
                    mat[i, self._vocab[ng]] += 1
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return mat / norms

    def _encode(self, text: str) -> np.ndarray:
        if not self._vocab:
            return np.zeros(1, dtype=np.float32)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        for ng in self._ngrams(text.lower()):
            if ng in self._vocab:
                vec[self._vocab[ng]] += 1
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def top1(self, query: str) -> tuple[int, float]:
        qvec = self._encode(query)
        if self._matrix.shape[1] != qvec.shape[0]:
            return 0, 0.0
        scores = self._matrix @ qvec
        idx = int(np.argmax(scores))
        return idx, float(scores[idx])


@dataclass
class USDAEntry:
    usda_id:       str
    description:   str
    sodium_mg:     float
    potassium_mg:  float
    phosphorus_mg: float
    protein_g:     float


class USDAMatcher:
    def __init__(self, entries: list[USDAEntry], threshold: float = 0.72):
        self._entries      = entries
        self._threshold    = threshold
        self._cache:       dict[str, dict] = {}
        self._skip_ngram   = False   # set True for full runs to skip slow n-gram tier

        self._by_desc = {e.description.lower(): e for e in entries}

        self._first_word: dict[str, list[USDAEntry]] = {}
        for e in entries:
            first = e.description.lower().split(",")[0].strip()
            self._first_word.setdefault(first, []).append(e)

        self._sem = _SemanticMatcher([e.description for e in entries])
        log.info("USDAMatcher: %d entries, threshold=%.2f", len(entries), threshold)

    def match(self, raw: str) -> dict:
        norm = normalize_ingredient_name(raw)
        if not norm:
            return {"status": "incomplete", "reason": f"empty after normalisation: {raw!r}"}

        if norm in self._cache:
            return {**self._cache[norm], "method": "cache"}

        if norm in self._by_desc:
            r = {"status": "matched", "entry": self._by_desc[norm],
                 "method": "exact", "score": 1.0}
            self._cache[norm] = r
            return r

        first_word = norm.split()[0] if norm.split() else norm
        candidates = self._first_word.get(first_word, [])
        if candidates:
            norm_words = set(norm.split())
            best_entry, best_score = None, 0.0
            for cand in candidates:
                desc_words = set(cand.description.lower().replace(",", " ").split())
                overlap = len(norm_words & desc_words) / max(len(norm_words), 1)
                if overlap > best_score:
                    best_score = overlap
                    best_entry = cand
            if best_entry and best_score >= 0.5:
                r = {"status": "matched", "entry": best_entry,
                     "method": "first_word", "score": best_score}
                self._cache[norm] = r
                return r

        # N-gram semantic fallback — skipped for full runs (slow)
        if not self._skip_ngram:
            ngram_threshold = min(self._threshold, 0.42)
            idx, score = self._sem.top1(norm)
            if score >= ngram_threshold:
                r = {"status": "matched", "entry": self._entries[idx],
                     "method": "semantic", "score": score}
                self._cache[norm] = r
                return r

        return {"status": "incomplete",
                "reason": f"no match for '{norm}'"}


# ════════════════════════════════════════════════════════════════
# SECTION 1 — GRAPH NODE & EDGE TYPES
# ════════════════════════════════════════════════════════════════

@dataclass
class RecipeNode:
    recipe_id:   str
    title:       str
    ingredients: list[str]
    source:      str = "recipe1m"


@dataclass
class IngredientNode:
    name:           str
    raw_name:       str
    flavorgraph_id: Optional[str]
    foodon_uri:     Optional[str]
    usda_fdc_id:    Optional[str]
    match_method:   Optional[str]


@dataclass
class NutrientNode:
    fdc_id:        str
    description:   str
    sodium_mg:     float
    potassium_mg:  float
    phosphorus_mg: float
    protein_g:     float
    p_source_type: str = "unknown"


@dataclass
class RecipeIngredientEdge:
    recipe_id:  str
    ingredient: str
    grams:      Optional[float]
    raw_string: str


@dataclass
class SubstitutionEdge:
    """Raw substitution pair from Recipe1MSubs — direction: source → target."""
    source:    str
    target:    str
    recipe_id: str
    direction: str = "source_to_target"


@dataclass
class SafeSubstitutionEdge:
    """
    A substitution that has been validated as safe at a specific CKD stage.

    A substitution source → target is safe at stage X if and only if:
      1. The target has a USDA match (its nutrients are known)
      2. The target has no HIGH or MODERATE severity risks at stage X
         from the active risk types for that stage

    LOW severity risks (e.g. low_potassium_bioavailable) are acceptable —
    they are informational flags, not restrictions.

    This is the core change from the previous pipeline where substitutions
    were stage-agnostic. Now a substitution is only recommended if the
    replacement ingredient is clinically safe for the patient's specific stage.
    """
    source:    str
    target:    str
    recipe_id: str
    stage:     str
    reason:    str    # why the target is safe at this stage


# ════════════════════════════════════════════════════════════════
# SECTION 2 — KDIGO 2024 CKD RULES
# ════════════════════════════════════════════════════════════════

class RiskType(str, Enum):
    HIGH_PROTEIN        = "high_protein"
    HIGH_SODIUM         = "high_sodium"
    HIGH_K_BIOAVAILABLE = "high_potassium_bioavailable"
    LOW_K_BIOAVAILABLE  = "low_potassium_bioavailable"
    HIGH_P_ADDITIVE     = "high_phosphorus_additive"
    HIGH_P_ANIMAL       = "high_phosphorus_animal"
    HIGH_P_PLANT        = "high_phosphorus_plant"


STAGE_ACTIVE_RISKS: dict[str, set[RiskType]] = {
    "stage_1":  {RiskType.HIGH_SODIUM},
    "stage_2":  {RiskType.HIGH_SODIUM},
    "stage_3a": {RiskType.HIGH_SODIUM, RiskType.HIGH_PROTEIN},
    "stage_3b": {RiskType.HIGH_SODIUM, RiskType.HIGH_PROTEIN,
                 RiskType.HIGH_K_BIOAVAILABLE,
                 RiskType.HIGH_P_ADDITIVE, RiskType.HIGH_P_ANIMAL},
    "stage_4":  {RiskType.HIGH_SODIUM, RiskType.HIGH_PROTEIN,
                 RiskType.HIGH_K_BIOAVAILABLE,
                 RiskType.HIGH_P_ADDITIVE, RiskType.HIGH_P_ANIMAL,
                 RiskType.HIGH_P_PLANT},
    "stage_5":  {RiskType.HIGH_SODIUM, RiskType.HIGH_PROTEIN,
                 RiskType.HIGH_K_BIOAVAILABLE,
                 RiskType.HIGH_P_ADDITIVE, RiskType.HIGH_P_ANIMAL,
                 RiskType.HIGH_P_PLANT},
}

# Only protein and sodium have hard thresholds in KDIGO 2024
HARD_THRESHOLDS: dict[str, dict[str, float]] = {
    "stage_1":  {"sodium_mg": 2000, "protein_g_per_kg": 1.3},
    "stage_2":  {"sodium_mg": 2000, "protein_g_per_kg": 1.3},
    "stage_3a": {"sodium_mg": 2000, "protein_g_per_kg": 0.8},
    "stage_3b": {"sodium_mg": 2000, "protein_g_per_kg": 0.8},
    "stage_4":  {"sodium_mg": 2000, "protein_g_per_kg": 0.8},
    "stage_5":  {"sodium_mg": 2000, "protein_g_per_kg": 0.8},
}

INGREDIENT_RISK_THRESHOLDS = {
    "sodium_mg_per_100g":    200,
    "protein_g_per_100g":     15,
    "potassium_mg_per_100g": 200,
}

PHOSPHATE_ADDITIVE_KEYWORDS = {
    "processed", "cheese spread", "american cheese", "velveeta",
    "instant", "fast food", "cola", "processed meat",
    "hot dog", "deli meat", "lunch meat", "canned soup",
    "packaged", "frozen dinner", "ready meal",
}

PLANT_POTASSIUM_SOURCES = {
    "spinach", "kale", "broccoli", "sweet potato", "banana",
    "orange", "tomato", "avocado", "potato", "beans", "lentils",
    "peas", "mushroom", "squash", "beet", "carrot",
}


@dataclass
class CKDRiskProfile:
    ingredient_name: str
    risks:           list[dict]
    hard_violations: list[dict]


def classify_phosphorus_source(name: str) -> str:
    n = name.lower()
    if any(kw in n for kw in PHOSPHATE_ADDITIVE_KEYWORDS):
        return "additive"
    if any(kw in n for kw in ["chicken", "beef", "pork", "fish", "salmon",
                               "tuna", "turkey", "shrimp", "cheese",
                               "milk", "egg", "dairy", "meat"]):
        return "animal"
    if any(kw in n for kw in ["bean", "lentil", "pea", "grain", "wheat",
                               "oat", "rice", "corn", "soy", "nut",
                               "seed", "bran", "legume"]):
        return "plant"
    return "unknown"


def build_ckd_risk_profile(name: str,
                            nutrient: NutrientNode) -> CKDRiskProfile:
    p_source   = classify_phosphorus_source(name)
    is_plant_k = any(kw in name.lower() for kw in PLANT_POTASSIUM_SOURCES)
    risks: list[dict] = []

    for stage, active in STAGE_ACTIVE_RISKS.items():
        if (RiskType.HIGH_SODIUM in active and
                nutrient.sodium_mg > INGREDIENT_RISK_THRESHOLDS["sodium_mg_per_100g"]):
            sev = "high" if nutrient.sodium_mg > 500 else "moderate"
            risks.append({"stage": stage, "risk_type": RiskType.HIGH_SODIUM.value,
                          "severity": sev,
                          "note": f"{nutrient.sodium_mg:.0f}mg Na/100g"})

        if (RiskType.HIGH_PROTEIN in active and
                nutrient.protein_g > INGREDIENT_RISK_THRESHOLDS["protein_g_per_100g"]):
            sev = "high" if nutrient.protein_g > 25 else "moderate"
            risks.append({"stage": stage, "risk_type": RiskType.HIGH_PROTEIN.value,
                          "severity": sev,
                          "note": f"{nutrient.protein_g:.1f}g protein/100g"})

        if (RiskType.HIGH_K_BIOAVAILABLE in active and
                nutrient.potassium_mg > INGREDIENT_RISK_THRESHOLDS["potassium_mg_per_100g"]):
            rt  = RiskType.LOW_K_BIOAVAILABLE if is_plant_k else RiskType.HIGH_K_BIOAVAILABLE
            sev = "low" if is_plant_k else "moderate"
            note = ("plant K — KDIGO 2024 does not restrict"
                    if is_plant_k else
                    "non-plant K — restrict if serum K+ elevated")
            risks.append({"stage": stage, "risk_type": rt.value,
                          "severity": sev,
                          "note": f"{nutrient.potassium_mg:.0f}mg K/100g — {note}"})

        if nutrient.phosphorus_mg > 100:
            if p_source == "additive" and RiskType.HIGH_P_ADDITIVE in active:
                risks.append({"stage": stage, "risk_type": RiskType.HIGH_P_ADDITIVE.value,
                              "severity": "high",
                              "note": f"{nutrient.phosphorus_mg:.0f}mg P/100g additive (~100% absorbed)"})
            elif p_source == "animal" and RiskType.HIGH_P_ANIMAL in active:
                risks.append({"stage": stage, "risk_type": RiskType.HIGH_P_ANIMAL.value,
                              "severity": "moderate",
                              "note": f"{nutrient.phosphorus_mg:.0f}mg P/100g animal (~50% absorbed)"})
            elif p_source == "plant" and RiskType.HIGH_P_PLANT in active:
                risks.append({"stage": stage, "risk_type": RiskType.HIGH_P_PLANT.value,
                              "severity": "low",
                              "note": f"{nutrient.phosphorus_mg:.0f}mg P/100g plant (~30% absorbed)"})

    return CKDRiskProfile(ingredient_name=name, risks=risks, hard_violations=[])


# ════════════════════════════════════════════════════════════════
# STAGE-AWARE SUBSTITUTION LOGIC
# ════════════════════════════════════════════════════════════════

def is_ingredient_safe_at_stage(
    ingredient_name: str,
    stage:           str,
    risk_profiles:   dict,
) -> bool:
    """
    An ingredient is safe at a stage if and only if:
      1. It has USDA data (risk profile exists)
      2. It has ZERO active risk flags at that stage

    No severity gradation. No exceptions for informational flags.
    Any risk flag at this stage = not safe = not a valid substitute.

    Ingredients with no USDA data are always excluded — we cannot
    recommend something we have no nutritional data for.
    """
    if ingredient_name not in risk_profiles:
        return False
    profile = risk_profiles[ingredient_name]
    return not any(r["stage"] == stage for r in profile.risks)


def build_safe_substitutions(
    raw_subs:      list["SubstitutionEdge"],
    risk_profiles: dict,
) -> dict[str, list["SafeSubstitutionEdge"]]:
    """
    For each raw substitution pair and each CKD stage, include the pair
    only if the target ingredient has zero risk flags at that stage.

    That is the only criterion — no severity levels, no partial credit.
    """
    safe_by_stage: dict[str, list] = {stage: [] for stage in HARD_THRESHOLDS}

    for edge in raw_subs:
        for stage in HARD_THRESHOLDS:
            if is_ingredient_safe_at_stage(edge.target, stage, risk_profiles):
                safe_by_stage[stage].append(SafeSubstitutionEdge(
                    source=    edge.source,
                    target=    edge.target,
                    recipe_id= edge.recipe_id,
                    stage=     stage,
                    reason=    f"target '{edge.target}' has no risk flags at {stage}",
                ))

    return safe_by_stage


# ════════════════════════════════════════════════════════════════
# SECTION 3 — DATA PATHS
# ════════════════════════════════════════════════════════════════

class DataPaths:
    """
    All file paths in one place.
    Edit the PATH constants below to match your local file locations.

    FoodKG NOTE: FoodKG is excluded from the final pipeline. It does not
    provide a downloadable RDF dump — it must be built from Recipe1M using
    their Python 3.7 build scripts. The USDA links it would provide are
    already covered by our three-tier matcher. FoodOn ontology links are
    deferred to future work.
    """

    RECIPE1M_PATH      = Path(r"C:\Users\Vedantt\NSAI Data\recipe1M_layers\layer1.json")
    USDA_PATH          = Path(r"C:\Users\Vedantt\NSAI Data\usda\usda_sr_legacy.json")
    RECIPE1MSUBS_PATH  = Path(r"C:\Users\Vedantt\NSAI Data\recipe1msubs\subs.pkl")  # loader checks parent folder for split files

    def __init__(self, base: str = "."):
        b = Path(base)
        self.recipe1m          = self.RECIPE1M_PATH
        self.usda_json         = self.USDA_PATH
        self.recipe1msubs      = self.RECIPE1MSUBS_PATH
        self.foodkg_triples    = b / "data/foodkg/foodkg_triples.nt"   # excluded — see note above
        self.flavorgraph_vocab = b / "data/flavorgraph/ingredient_vocab.json"  # used at GNN step, not here
        self.outputs           = b / "outputs"
        self.outputs.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# SECTION 4 — DATA LOADERS
# ════════════════════════════════════════════════════════════════

def load_recipe1m(path: Path,
                  max_recipes: Optional[int] = None) -> list[RecipeNode]:
    """
    Load Recipe1M layer1.json.
    Ingredients are dicts with a 'text' key: {"text": "6 ounces penne"}.
    """
    if not path.exists():
        log.warning("Recipe1M not found at %s — using mock data", path)
        return _mock_recipe1m()

    log.info("Loading Recipe1M from %s", path)
    log.info("Reading file into memory (this may take 20-30 seconds)...")
    t0 = time.time()
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    log.info("File loaded in %.1fs — %d total recipes", time.time() - t0, len(raw))

    limit = max_recipes or len(raw)
    recipes: list[RecipeNode] = []
    log_every = max(1, limit // 10)     # log progress every 10%

    for i, r in enumerate(raw):
        if i >= limit:
            break
        if i > 0 and i % log_every == 0:
            pct = i / limit * 100
            log.info("  Loaded %d / %d recipes (%.0f%%)", i, limit, pct)

        ingredients = []
        for ing in r.get("ingredients", []):
            if isinstance(ing, dict):
                text = ing.get("text", "").strip()
            else:
                text = str(ing).strip()
            if text:
                ingredients.append(text)

        recipes.append(RecipeNode(
            recipe_id=   str(r["id"]),
            title=       r.get("title", ""),
            ingredients= ingredients,
        ))

    log.info("Loaded %d recipes", len(recipes))
    return recipes


def load_recipe1msubs(path: Path) -> list[SubstitutionEdge]:
    """
    Load Recipe1MSubs substitution pairs.

    The dataset is split into three files hosted at:
      https://dl.fbaipublicfiles.com/gismo/train_comments_subs.pkl
      https://dl.fbaipublicfiles.com/gismo/val_comments_subs.pkl
      https://dl.fbaipublicfiles.com/gismo/test_comments_subs.pkl

    Place all three under data/recipe1msubs/ and they will be loaded
    and combined automatically. Falls back to mock data if none found.

    Each pkl is a list of dicts with keys:
        'substitutions': [{'source': str, 'target': str}, ...]
        'recipe_id': str  (or similar — exact key varies by split)
    """
    import pickle

    # Look for the three split files
    split_files = [
        path.parent / "train_comments_subs.pkl",
        path.parent / "val_comments_subs.pkl",
        path.parent / "test_comments_subs.pkl",
    ]
    found = [f for f in split_files if f.exists()]

    # Also try the old single-file path for backward compatibility
    if not found and path.exists():
        found = [path]

    if not found:
        log.warning("Recipe1MSubs not found — using mock data. "
                    "Download from https://dl.fbaipublicfiles.com/gismo/")
        return _mock_recipe1msubs()

    log.info("Loading Recipe1MSubs from %d split file(s)", len(found))
    edges: list[SubstitutionEdge] = []

    for fpath in found:
        with open(fpath, "rb") as f:
            data = pickle.load(f)

        before = len(edges)

        # GISMo format — list of dicts:
        # {
        #   'id': '00004320bb',
        #   'ingredients': [['boiling_water'], ['cool_whip', ...], ...],
        #   'subs': ('seedless_watermelon', 'lime')
        # }
        if isinstance(data, list):
            for entry in data:
                rid = str(entry.get("id", ""))
                subs = entry.get("subs")
                if not subs or len(subs) < 2:
                    continue
                src = normalize_ingredient_name(str(subs[0]).replace("_", " "))
                tgt = normalize_ingredient_name(str(subs[1]).replace("_", " "))
                if src and tgt:
                    edges.append(SubstitutionEdge(source=src, target=tgt, recipe_id=rid))

        # Fallback: DataFrame format
        elif hasattr(data, "iterrows"):
            for _, row in data.iterrows():
                src = normalize_ingredient_name(str(row.get("source", "")))
                tgt = normalize_ingredient_name(str(row.get("target", "")))
                rid = str(row.get("recipe_id", ""))
                if src and tgt:
                    edges.append(SubstitutionEdge(source=src, target=tgt, recipe_id=rid))

        log.info("  %s: +%d pairs", fpath.name, len(edges) - before)

    log.info("Recipe1MSubs: %d substitution pairs loaded", len(edges))
    return edges


def load_foodkg_links(path: Path) -> dict[str, dict]:
    """Parse FoodKG N-Triples for ingredient→FoodOn and ingredient→USDA links."""
    if not path.exists():
        log.warning("FoodKG not found at %s — skipping", path)
        return {}

    log.info("Parsing FoodKG triples from %s", path)
    links: dict[str, dict] = defaultdict(lambda: {"foodon_uri": None, "usda_id": None})
    pat = re.compile(r'<([^>]+)>\s+<([^>]+)>\s+(?:<([^>]+)>|"([^"]+)")\s*\.')

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = pat.match(line)
            if not m:
                continue
            subject, predicate, obj_uri, obj_lit = m.groups()
            if "ingredient" in subject:
                ing = subject.split("/")[-1].replace("_", " ")
                if "usda" in predicate.lower():
                    links[ing]["usda_id"] = obj_lit or obj_uri
                if "foodon" in (obj_uri or "") or "type" in predicate:
                    links[ing]["foodon_uri"] = obj_uri

    log.info("FoodKG: %d ingredient links", len(links))
    return dict(links)


def load_usda(path: Path) -> list[USDAEntry]:
    """
    Load USDA SR Legacy JSON from FoodData Central.

    File structure (FoodData_Central_sr_legacy_food_json_2018-04.json):
    {
      "SRLegacyFoods": [
        {
          "fdcId": 747447,
          "description": "Spinach, raw",
          "foodNutrients": [
            {"nutrient": {"name": "Sodium, Na", "unitName": "mg"}, "amount": 79.0},
            ...
          ]
        }
      ]
    }
    """
    if not path.exists():
        log.warning("USDA not found at %s — using mock data", path)
        return _mock_usda()

    log.info("Loading USDA from %s", path)
    log.info("Reading USDA file (may take a few seconds)...")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # handle whichever top-level key the file uses
    foods = (raw.get("SRLegacyFoods")
             or raw.get("Foods")
             or raw.get("foods")
             or [])

    if not foods:
        log.warning("Could not find food list in USDA JSON — falling back to mock")
        return _mock_usda()

    name_map = {
        "Sodium, Na":    "sodium_mg",
        "Potassium, K":  "potassium_mg",
        "Phosphorus, P": "phosphorus_mg",
        "Protein":       "protein_g",
    }

    entries: list[USDAEntry] = []
    for food in foods:
        nutrients = {v: 0.0 for v in name_map.values()}
        for fn in food.get("foodNutrients", []):
            # nutrient name is nested under a "nutrient" object
            n = fn.get("nutrient", {}).get("name", "")
            if n in name_map:
                try:
                    nutrients[name_map[n]] = float(fn.get("amount", 0) or 0)
                except (ValueError, TypeError):
                    pass
        entries.append(USDAEntry(
            usda_id=       str(food.get("fdcId", "")),
            description=   food.get("description", ""),
            sodium_mg=     nutrients["sodium_mg"],
            potassium_mg=  nutrients["potassium_mg"],
            phosphorus_mg= nutrients["phosphorus_mg"],
            protein_g=     nutrients["protein_g"],
        ))

    log.info("USDA: %d entries loaded", len(entries))
    return entries


def load_flavorgraph_vocab(path: Path) -> dict[str, str]:
    """Load FlavorGraph ingredient vocabulary {name: node_id}."""
    if not path.exists():
        log.warning("FlavorGraph vocab not found at %s — alignment disabled", path)
        return {}
    log.info("Loading FlavorGraph vocab from %s", path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k.replace("_", " "): v for k, v in raw.items()}


# ════════════════════════════════════════════════════════════════
# SECTION 5 — ALIGNMENT
# ════════════════════════════════════════════════════════════════

def align_to_flavorgraph(name: str, vocab: dict[str, str]) -> Optional[str]:
    """Map normalised ingredient name to FlavorGraph node ID."""
    if name in vocab:
        return vocab[name]
    parts = name.split()
    for i in range(1, len(parts)):
        shorter = " ".join(parts[i:])
        if shorter in vocab:
            return vocab[shorter]
    return None


def align_substitution_vocab(
    subs: list[SubstitutionEdge],
    known: set[str],
) -> tuple[list[SubstitutionEdge], list[SubstitutionEdge]]:
    aligned, unresolved = [], []
    for e in subs:
        if e.source in known and e.target in known:
            aligned.append(e)
        else:
            unresolved.append(e)
    return aligned, unresolved


# ════════════════════════════════════════════════════════════════
# SECTION 6 — INTEGRATED GRAPH
# ════════════════════════════════════════════════════════════════

@dataclass
class IntegratedGraph:
    recipes:                    dict[str, RecipeNode]                   = field(default_factory=dict)
    ingredients:                dict[str, IngredientNode]               = field(default_factory=dict)
    nutrients:                  dict[str, NutrientNode]                 = field(default_factory=dict)
    ckd_stages:                 dict[str, dict]                        = field(default_factory=dict)
    recipe_ingredients:         list[RecipeIngredientEdge]              = field(default_factory=list)
    # Raw substitutions from Recipe1MSubs — stage-agnostic source of truth
    substitutions:              list[SubstitutionEdge]                  = field(default_factory=list)
    unresolved_subs:            list[SubstitutionEdge]                  = field(default_factory=list)
    # Stage-qualified safe substitutions — the clinically valid recommendations
    # Key change: a substitution is only here if the target is safe at that stage
    safe_substitutions_by_stage: dict[str, list[SafeSubstitutionEdge]] = field(default_factory=dict)
    ckd_risk_profiles:          dict[str, CKDRiskProfile]              = field(default_factory=dict)

    def coverage_report(self) -> str:
        te  = len(self.recipe_ingredients)
        wg  = sum(1 for e in self.recipe_ingredients if e.grams is not None)
        iu  = sum(1 for i in self.ingredients.values() if i.usda_fdc_id)
        ifo = sum(1 for i in self.ingredients.values() if i.foodon_uri)
        ifg = sum(1 for i in self.ingredients.values() if i.flavorgraph_id)
        ni  = len(self.ingredients)
        total_raw_subs  = len(self.substitutions)

        lines = [
            "═" * 55,
            "  INTEGRATION COVERAGE REPORT",
            "═" * 55,
            f"  Recipes:                    {len(self.recipes):>8,}",
            f"  Unique ingredients:         {ni:>8,}",
            f"  Nutrient entries (USDA):    {len(self.nutrients):>8,}",
            f"  Recipe-ingredient edges:    {te:>8,}",
            f"    with parsed amounts:      {wg:>8,}  ({wg/max(te,1):.0%})",
            f"",
            f"  Ingredient coverage:",
            f"    USDA matched:       {iu:>6,} / {ni}  ({iu/max(ni,1):.0%})",
            f"    FoodOn linked:      {ifo:>6,} / {ni}  ({ifo/max(ni,1):.0%})",
            f"    FlavorGraph mapped: {ifg:>6,} / {ni}  ({ifg/max(ni,1):.0%})",
            f"",
            f"  Substitution pairs (raw):   {total_raw_subs:>8,}",
            f"    unresolved:               {len(self.unresolved_subs):>8,}",
            f"  Safe substitutions by stage (target must be safe at that stage):",
        ]
        for stage in sorted(self.safe_substitutions_by_stage):
            n = len(self.safe_substitutions_by_stage[stage])
            pct = n / max(total_raw_subs, 1)
            lines.append(f"    {stage:10}  {n:>6,}  ({pct:.0%} of raw pairs qualify)")
        lines += [
            f"",
            f"  CKD risk profiles:          {len(self.ckd_risk_profiles):>8,}  ingredients",
            "═" * 55,
        ]
        return "\n".join(lines)

    def unmatched_ingredients(self) -> list[str]:
        """All ingredient names that have no USDA match — for improving the matcher."""
        return sorted(
            name for name, ing in self.ingredients.items()
            if ing.usda_fdc_id is None
        )

    def export_graph_triples(self) -> list[tuple[str, str, str]]:
        """Export all nodes and edges as (subject, predicate, object) triples."""
        triples: list[tuple[str, str, str]] = []

        for stage in self.ckd_stages:
            triples.append((stage, "rdf:type", "CKDStage"))

        for rid, r in self.recipes.items():
            triples.append((f"recipe:{rid}", "rdf:type", "Recipe"))
            triples.append((f"recipe:{rid}", "dc:title", r.title))

        for name, ing in self.ingredients.items():
            sn = name.replace(" ", "_")
            triples.append((f"ingredient:{sn}", "rdf:type", "Ingredient"))
            if ing.foodon_uri:
                triples.append((f"ingredient:{sn}", "skos:closeMatch", ing.foodon_uri))
            if ing.usda_fdc_id:
                triples.append((f"ingredient:{sn}", "has_usda_entry", f"usda:{ing.usda_fdc_id}"))
            if ing.flavorgraph_id:
                triples.append((f"ingredient:{sn}", "fg:node_id", ing.flavorgraph_id))

        for e in self.recipe_ingredients:
            si = e.ingredient.replace(" ", "_")
            triples.append((f"recipe:{e.recipe_id}", "has_ingredient", f"ingredient:{si}"))
            if e.grams:
                triples.append((f"recipe:{e.recipe_id}___{si}", "has_amount_grams", str(e.grams)))

        for fdc_id, nut in self.nutrients.items():
            triples.append((f"usda:{fdc_id}", "rdf:type", "NutrientEntry"))
            triples.append((f"usda:{fdc_id}", "sodium_mg_per_100g",     str(nut.sodium_mg)))
            triples.append((f"usda:{fdc_id}", "potassium_mg_per_100g",  str(nut.potassium_mg)))
            triples.append((f"usda:{fdc_id}", "phosphorus_mg_per_100g", str(nut.phosphorus_mg)))
            triples.append((f"usda:{fdc_id}", "protein_g_per_100g",     str(nut.protein_g)))
            triples.append((f"usda:{fdc_id}", "phosphorus_source_type", nut.p_source_type))

        # Stage-qualified safe substitution edges
        # These replace the old stage-agnostic substitutes_for edges.
        # Each triple encodes: ingredient A is a safe substitute for B at stage X.
        # This is the only substitution information the GNN and reasoner should use.
        safe_sub_count = 0
        for stage, edges in self.safe_substitutions_by_stage.items():
            for e in edges:
                s = e.source.replace(" ", "_")
                t = e.target.replace(" ", "_")
                # The edge is: target safe_substitute_at stage → source
                # i.e. "target can safely replace source at this stage"
                triples.append((
                    f"ingredient:{t}",
                    f"safe_substitute_at_{stage}",
                    f"ingredient:{s}",
                ))
                triples.append((
                    f"ingredient:{t}__sub__{stage}__{s}",
                    "reason",
                    e.reason,
                ))
                safe_sub_count += 1

        # Also keep raw substitutes_for edges for completeness
        for e in self.substitutions:
            s = e.source.replace(" ", "_")
            t = e.target.replace(" ", "_")
            triples.append((f"ingredient:{s}", "substitutes_for", f"ingredient:{t}"))

        for ing_name, profile in self.ckd_risk_profiles.items():
            sn = ing_name.replace(" ", "_")
            for risk in profile.risks:
                rnode = f"risk:{sn}_{risk['stage']}_{risk['risk_type']}"
                triples.append((f"ingredient:{sn}", "has_ckd_risk", rnode))
                triples.append((rnode, "risk_type",     risk["risk_type"]))
                triples.append((rnode, "severity",      risk["severity"]))
                triples.append((rnode, "risk_at_stage", risk["stage"]))
                triples.append((rnode, "note",          risk["note"]))

        return triples


# ════════════════════════════════════════════════════════════════
# SECTION 7 — MASTER BUILD FUNCTION
# ════════════════════════════════════════════════════════════════

def build_integrated_graph(
    paths:       DataPaths,
    matcher:     USDAMatcher,
    max_recipes: Optional[int] = None,
) -> IntegratedGraph:

    graph = IntegratedGraph()

    # 0. CKD stage nodes
    for stage, thresholds in HARD_THRESHOLDS.items():
        graph.ckd_stages[stage] = {
            "thresholds":   thresholds,
            "active_risks": [r.value for r in STAGE_ACTIVE_RISKS[stage]],
        }

    # 1. USDA nutrient nodes
    usda_entries = load_usda(paths.usda_json)
    for e in usda_entries:
        p_src = classify_phosphorus_source(e.description)
        graph.nutrients[e.usda_id] = NutrientNode(
            fdc_id=        e.usda_id,
            description=   e.description,
            sodium_mg=     e.sodium_mg,
            potassium_mg=  e.potassium_mg,
            phosphorus_mg= e.phosphorus_mg,
            protein_g=     e.protein_g,
            p_source_type= p_src,
        )
    log.info("Nutrient nodes: %d", len(graph.nutrients))

    # 2. FoodKG links
    foodkg = load_foodkg_links(paths.foodkg_triples)

    # 3. FlavorGraph vocab
    fg_vocab = load_flavorgraph_vocab(paths.flavorgraph_vocab)

    # 4. Recipes → ingredient edges
    # Two-pass approach for full runs:
    #   Pass 1: iterate recipes, build edges, collect unique ingredient strings
    #   Pass 2: batch-match all unique strings against USDA (with progress)
    # This gives visibility into the matching phase and avoids redundant work.

    recipes = load_recipe1m(paths.recipe1m, max_recipes=max_recipes)
    is_full_run = max_recipes is None

    norm_cache: dict[str, str] = {}

    log.info("Pass 1: building recipe-ingredient edges (%d recipes)...", len(recipes))
    unique_raw_ingredients: set[str] = set()

    for i, recipe in enumerate(recipes):
        if i > 0 and i % 100000 == 0:
            log.info("  Edge pass: %d / %d recipes (%.0f%%)",
                     i, len(recipes), i/len(recipes)*100)

        graph.recipes[recipe.recipe_id] = recipe
        for raw in recipe.ingredients:
            norm = norm_cache.get(raw)
            if norm is None:
                norm = normalize_ingredient_name(raw)
                norm_cache[raw] = norm
            if not norm:
                continue

            grams = parse_amount_to_grams(raw)
            graph.recipe_ingredients.append(RecipeIngredientEdge(
                recipe_id=  recipe.recipe_id,
                ingredient= norm,
                grams=      grams,
                raw_string= raw,
            ))
            unique_raw_ingredients.add(raw)

    log.info("Pass 1 done: %d edges, %d unique raw strings",
             len(graph.recipe_ingredients), len(unique_raw_ingredients))

    # Pass 2: match each unique ingredient string to USDA exactly once.
    # For full runs, skip the slow n-gram tier — cache + exact + first-word
    # already cover ~65-70% and are fast. N-gram adds ~2% but takes 10x longer.
    if is_full_run:
        log.info("Pass 2: USDA matching (full run — skipping n-gram tier for speed)...")
        matcher._skip_ngram = True
    else:
        log.info("Pass 2: USDA matching (%d unique strings)...", len(unique_raw_ingredients))
        matcher._skip_ngram = False

    unique_list = sorted(unique_raw_ingredients)
    log_every   = max(1, len(unique_list) // 20)   # log every 5%

    for i, raw in enumerate(unique_list):
        if i > 0 and i % log_every == 0:
            matched_so_far = sum(1 for v in graph.ingredients.values() if v.usda_fdc_id)
            log.info("  Matching: %d / %d strings (%.0f%%) — %d matched so far",
                     i, len(unique_list), i/len(unique_list)*100, matched_so_far)

        norm = norm_cache.get(raw, normalize_ingredient_name(raw))
        if not norm or norm in graph.ingredients:
            continue

        m = matcher.match(raw)
        usda_id, method = None, None
        if m["status"] == "matched":
            usda_id = m["entry"].usda_id
            method  = m["method"]

        fkg = foodkg.get(norm, {})
        if fkg.get("usda_id"):
            usda_id = fkg["usda_id"]
            method  = "foodkg"

        fg_id = align_to_flavorgraph(norm, fg_vocab)

        graph.ingredients[norm] = IngredientNode(
            name=           norm,
            raw_name=       raw,
            flavorgraph_id= fg_id,
            foodon_uri=     fkg.get("foodon_uri"),
            usda_fdc_id=    usda_id,
            match_method=   method,
        )

    log.info("Ingredients: %d  |  Edges: %d",
             len(graph.ingredients), len(graph.recipe_ingredients))

    # 5. CKD risk profiles
    profiled = 0
    for name, ing in graph.ingredients.items():
        if ing.usda_fdc_id and ing.usda_fdc_id in graph.nutrients:
            graph.ckd_risk_profiles[name] = build_ckd_risk_profile(
                name, graph.nutrients[ing.usda_fdc_id])
            profiled += 1
    log.info("CKD risk profiles: %d", profiled)

    # 6. Recipe1MSubs substitutions
    raw_subs = load_recipe1msubs(paths.recipe1msubs)

    # Register any substitution ingredients not already in the vocabulary.
    # Even ingredients not seen in the 500-recipe sample need USDA data
    # so their safety can be evaluated for the substitution logic.
    for edge in raw_subs:
        for name in [edge.source, edge.target]:
            if name and name not in graph.ingredients:
                m = matcher.match(name)
                usda_id, method = None, None
                if m["status"] == "matched":
                    usda_id = m["entry"].usda_id
                    method  = m["method"]
                fg_id = align_to_flavorgraph(name, fg_vocab)
                graph.ingredients[name] = IngredientNode(
                    name=name, raw_name=name,
                    flavorgraph_id=fg_id,
                    foodon_uri=None,
                    usda_fdc_id=usda_id,
                    match_method=method,
                )
                if usda_id and usda_id in graph.nutrients:
                    graph.ckd_risk_profiles[name] = build_ckd_risk_profile(
                        name, graph.nutrients[usda_id])

    known = set(graph.ingredients)
    graph.substitutions, graph.unresolved_subs = align_substitution_vocab(raw_subs, known)
    log.info("Raw substitutions: %d aligned, %d unresolved",
             len(graph.substitutions), len(graph.unresolved_subs))

    # Build stage-qualified safe substitutions.
    # For each (source → target) pair and each CKD stage, check whether the
    # target ingredient is safe at that stage. Only include pairs where the
    # target passes the safety check — no moderate or high severity risks
    # at that stage from the active risk types.
    graph.safe_substitutions_by_stage = build_safe_substitutions(
        graph.substitutions, graph.ckd_risk_profiles
    )
    for stage, safe_edges in graph.safe_substitutions_by_stage.items():
        log.info("Safe substitutions at %s: %d / %d pairs qualify",
                 stage, len(safe_edges), len(graph.substitutions))

    return graph


# ════════════════════════════════════════════════════════════════
# SECTION 8 — MOCK DATA (fallback when files not present)
# ════════════════════════════════════════════════════════════════

def _mock_usda() -> list[USDAEntry]:
    """
    Extended mock USDA covering the most common Recipe1M ingredients.
    Values are per 100g from USDA SR Legacy.
    Replace this entire function with load_usda() once you have the real file.
    """
    return [
        # ── Vegetables ──────────────────────────────────────────────────
        USDAEntry("11457", "spinach, raw",                 70,  558,  49,  2.9),
        USDAEntry("11090", "broccoli, raw",                33,  316,  67,  2.8),
        USDAEntry("11352", "potato, flesh and skin raw",   17,  379,  44,  2.0),
        USDAEntry("11960", "sweet potato, raw",            55,  337,  54,  1.6),
        USDAEntry("11282", "onions, raw",                   4,  146,  29,  1.1),
        USDAEntry("11215", "garlic, raw",                   5,  401, 153,  6.4),
        USDAEntry("11529", "tomatoes, raw",                 5,  237,  24,  0.9),
        USDAEntry("11124", "carrots, raw",                 69,  320,  35,  0.9),
        USDAEntry("11143", "celery, raw",                  80,  260,  24,  0.7),
        USDAEntry("11209", "eggplant, raw",                 2,  229,  24,  1.0),
        USDAEntry("11135", "cauliflower, raw",             30,  299,  44,  1.9),
        USDAEntry("11233", "kale, raw",                    53,  491,  92,  4.3),
        USDAEntry("11250", "lettuce, romaine",              8,  247,  29,  1.2),
        USDAEntry("11304", "peas, green, raw",              5,  244,  108, 5.4),
        USDAEntry("11313", "peppers, sweet, red, raw",     4,  211,  26,  1.0),
        USDAEntry("11951", "peppers, sweet, green, raw",   4,  175,  20,  0.9),
        USDAEntry("11355", "pumpkin, raw",                  1,  340,  44,  1.0),
        USDAEntry("11587", "zucchini, raw",                 8,  261,  38,  1.2),
        USDAEntry("11003", "asparagus, raw",                2,  202,  52,  2.2),
        USDAEntry("11011", "broccoli rabe, raw",           33,  196,  74,  3.2),
        USDAEntry("11260", "mushrooms, raw",                5,  318,  86,  3.1),
        USDAEntry("11352", "russet potato",                17,  379,  44,  2.0),
        USDAEntry("11216", "ginger root, raw",              13,  415,  34,  1.8),
        USDAEntry("11567", "tomato paste, canned",         59,  1014, 84,  3.8),
        # ── Fruits ──────────────────────────────────────────────────────
        USDAEntry("09003", "apple, raw",                    1,  107,  11,  0.3),
        USDAEntry("09040", "banana, raw",                   1,  358,  22,  1.1),
        USDAEntry("09070", "blueberries, raw",               1,   77,  12,  0.7),
        USDAEntry("09150", "lemon, raw",                    2,  138,  16,  1.1),
        USDAEntry("09206", "orange juice, raw",              1,  200,  17,  0.7),
        USDAEntry("09302", "strawberries, raw",              1,  153,  24,  0.7),
        USDAEntry("09132", "grapes, red, raw",               2,  191,  20,  0.6),
        USDAEntry("09181", "mango, raw",                    1,  168,  14,  0.8),
        # ── Proteins ────────────────────────────────────────────────────
        USDAEntry("05062", "chicken breast, raw",           74,  256, 220, 23.1),
        USDAEntry("05064", "chicken thigh, raw",            82,  218, 158, 17.9),
        USDAEntry("07055", "ground beef, 80% lean",         72,  270, 158, 17.2),
        USDAEntry("10006", "pork chop, raw",                62,  323, 185, 19.0),
        USDAEntry("15236", "salmon, raw",                   59,  363, 274, 20.4),
        USDAEntry("15261", "tilapia, raw",                  52,  302, 170, 26.2),
        USDAEntry("15027", "cod, raw",                      58,  413, 203, 17.8),
        USDAEntry("15270", "shrimp, raw",                  119,  264, 237, 20.9),
        USDAEntry("15167", "tuna, canned in water",        337,  237, 267, 25.5),
        USDAEntry("10179", "bacon, raw",                   672,  253, 137, 13.5),
        USDAEntry("07935", "sausage, pork",                 749, 204, 114, 12.0),
        USDAEntry("16057", "tofu, raw",                    121,  121, 97,   8.1),
        USDAEntry("16087", "tempeh",                         9,  401, 266, 18.5),
        # ── Dairy & Eggs ────────────────────────────────────────────────
        USDAEntry("01123", "egg, whole, raw",              142,  138, 198, 12.6),
        USDAEntry("01085", "milk, whole, 3.25% fat",        43,  150,  84,  3.2),
        USDAEntry("01077", "milk, reduced fat, 2%",         47,  156,  96,  3.3),
        USDAEntry("01001", "butter, salted",               714,   24,  24,  0.9),
        USDAEntry("01002", "butter, unsalted",             714,   24,  24,  0.9),
        USDAEntry("01009", "cheddar cheese",               621,   98, 512, 24.9),
        USDAEntry("01032", "parmesan cheese, hard",       1529,  125, 694, 35.7),
        USDAEntry("01017", "cream cheese",                 321,   97, 101,  5.9),
        USDAEntry("01116", "yogurt, plain, whole milk",     46,  141, 105,  3.5),
        USDAEntry("01049", "mozzarella cheese, whole milk",486,   76, 354, 22.2),
        USDAEntry("01035", "provolone cheese",             876,  138, 448, 25.6),
        USDAEntry("01056", "sour cream",                    70,  136,  61,  1.8),
        USDAEntry("01053", "heavy cream",                   38,  122,  62,  2.1),
        USDAEntry("01070", "half and half",                 41,  130,  95,  3.0),
        # ── Grains & Bread ──────────────────────────────────────────────
        USDAEntry("20081", "rice, white, long-grain",        5,  115,  43,  7.1),
        USDAEntry("20035", "rice, brown, long-grain",        5,  154,  83,  2.6),
        USDAEntry("20082", "pasta, dry, enriched",           6,  184,  76, 12.8),
        USDAEntry("20100", "flour, all-purpose",             2,  107, 108, 10.3),
        USDAEntry("20063", "flour, whole-wheat",             2,  405, 346, 13.2),
        USDAEntry("20011", "cornmeal",                       1,  142,  99,  7.1),
        USDAEntry("18069", "bread, whole-wheat",           400,  248, 212, 13.4),
        USDAEntry("18350", "bread, white",                 491,  115,  91,  7.6),
        USDAEntry("20001", "amaranth grain, cooked",         9,  135,  148, 3.8),
        USDAEntry("20006", "barley, cooked",                 3,   93,  54,  2.3),
        USDAEntry("20014", "quinoa, cooked",                 7,  172,  152, 4.4),
        USDAEntry("20025", "oats, rolled, dry",              6,  429, 523, 16.9),
        USDAEntry("18069", "breadcrumbs, dry",             732,  196, 106, 14.1),
        # ── Oils, Condiments, Sauces ────────────────────────────────────
        USDAEntry("04053", "olive oil",                      0,    0,   0,  0.0),
        USDAEntry("04518", "vegetable oil",                  0,    0,   0,  0.0),
        USDAEntry("04042", "canola oil",                     0,    0,   0,  0.0),
        USDAEntry("02047", "salt, table",               38758,    8,   0,  0.0),
        USDAEntry("02009", "pepper, black",                 20, 1329, 158, 10.4),
        USDAEntry("02003", "allspice, ground",               7,  684, 113,  6.1),
        USDAEntry("02010", "cinnamon, ground",               7,  431,  64,  4.0),
        USDAEntry("02014", "cumin, ground",                 168, 1788, 481, 17.8),
        USDAEntry("02028", "paprika",                       68, 2280, 314, 14.1),
        USDAEntry("02031", "chili powder",                  76, 1010, 173, 13.5),
        USDAEntry("02020", "garlic powder",                 26, 1227, 243, 16.6),
        USDAEntry("02025", "onion powder",                  52, 1130, 149, 10.4),
        USDAEntry("02042", "thyme, dried",                  55, 814,  201, 10.2),
        USDAEntry("02044", "vanilla extract",                9,   72,   6,  0.1),
        USDAEntry("11935", "soy sauce",                   5493,  435,  130, 10.5),
        USDAEntry("11549", "tomato sauce, canned",         390,  340,  29,  1.7),
        USDAEntry("02037", "red pepper, crushed",          131, 1523, 234, 12.6),
        USDAEntry("04120", "mayonnaise",                   486,   30,  21,  1.1),
        USDAEntry("11935", "worcestershire sauce",         980,  180,  37,  1.1),
        USDAEntry("02004", "bay leaf",                      23, 529,   67,  7.6),
        USDAEntry("02027", "oregano, dried",                25, 1260, 200, 11.0),
        USDAEntry("02023", "nutmeg, ground",                16,  350,  213, 5.8),
        # ── Legumes & Nuts ──────────────────────────────────────────────
        USDAEntry("16069", "lentils, raw",                   6,  677, 281, 25.8),
        USDAEntry("16015", "black beans, cooked",           240, 355, 140,  8.9),
        USDAEntry("16043", "kidney beans, cooked",          239, 403, 142,  8.7),
        USDAEntry("16086", "chickpeas, cooked",             282, 291, 168,  8.9),
        USDAEntry("16108", "white beans, cooked",           146, 561, 160,  9.7),
        USDAEntry("12061", "almonds",                         1,  733, 481, 21.2),
        USDAEntry("12155", "walnuts",                         2,  441, 346, 15.2),
        USDAEntry("12174", "cashews, raw",                   12, 660, 593, 18.2),
        USDAEntry("16087", "peanut butter",                 429,  558, 358, 25.1),
        # ── Liquids & Stock ─────────────────────────────────────────────
        USDAEntry("14429", "water",                          0,    0,   0,  0.0),
        USDAEntry("06172", "chicken broth, canned",        554,   82,  24,  1.3),
        USDAEntry("06169", "beef broth, canned",           372,  176,  40,  2.7),
        USDAEntry("06615", "vegetable broth",              430,   59,  16,  0.2),
        USDAEntry("14084", "white wine",                     9,   71,  18,  0.1),
        USDAEntry("14096", "red wine",                       5,  127,  23,  0.1),
        USDAEntry("14400", "lemon juice, raw",               1,  103,  11,  0.4),
        USDAEntry("09152", "lime juice, raw",                1,  117,  18,  0.3),
        USDAEntry("19904", "baking soda",                27360, 0,    0,    0.0),
        USDAEntry("18372", "baking powder",               10600, 40, 7700,  0.0),
        # ── Sweeteners ──────────────────────────────────────────────────
        USDAEntry("19335", "sugar, granulated",              1,    2,   0,  0.0),
        USDAEntry("19904", "brown sugar",                   28,   91,   4,  0.0),
        USDAEntry("19296", "honey",                          4,   52,   4,  0.3),
        USDAEntry("19903", "maple syrup",                    9,  212,   2,  0.0),
        USDAEntry("11167", "corn, sweet, yellow, raw",       1,  270,  89,  3.3),
    ]


def _mock_usda_cache(entries: list[USDAEntry]) -> dict[str, dict]:
    """
    Alias cache: maps normalised Recipe1M ingredient names directly to
    USDA entries, bypassing the semantic matcher.

    Uses DESCRIPTION-based lookup (not FDC ID) so it works regardless of
    which USDA release you have loaded — FoodData Central SR Legacy uses
    different fdcId values than the old NDB numbers.

    To add more entries: look up the USDA description for the ingredient
    (search at fdc.nal.usda.gov) and add a line below.
    """
    by_desc = {e.description.lower(): e for e in entries}

    def find(usda_description: str) -> Optional[dict]:
        """Exact match on USDA description (case-insensitive)."""
        e = by_desc.get(usda_description.lower())
        if e is None:
            return None
        return {"status": "matched", "entry": e, "method": "cache", "score": 1.0}

    # Format: "normalised Recipe1M name": "exact USDA SR Legacy description"
    # Find descriptions at: https://fdc.nal.usda.gov (filter: SR Legacy)
    mappings: dict[str, str] = {
        # ── Vegetables ───────────────────────────────────────────────────
        "spinach":              "Spinach, raw",
        "baby spinach":         "Spinach, raw",
        "broccoli":             "Broccoli, raw",
        "broccoli florets":     "Broccoli, raw",
        "potato":               "Potatoes, flesh and skin, raw",
        "potatoes":             "Potatoes, flesh and skin, raw",
        "russet potato":        "Potatoes, flesh and skin, raw",
        "sweet potato":         "Sweet potato, raw, unprepared",
        "yam":                  "Sweet potato, raw, unprepared",
        "onion":                "Onions, raw",
        "onions":               "Onions, raw",
        "yellow onion":         "Onions, raw",
        "red onion":            "Onions, raw",
        "white onion":          "Onions, raw",
        "shallot":              "Shallots, raw",
        "shallots":             "Shallots, raw",
        "garlic":               "Garlic, raw",
        "garlic clove":         "Garlic, raw",
        "garlic cloves":        "Garlic, raw",
        "tomato":               "Tomatoes, red, ripe, raw, year round average",
        "tomatoes":             "Tomatoes, red, ripe, raw, year round average",
        "cherry tomatoes":      "Tomatoes, red, ripe, raw, year round average",
        "carrot":               "Carrots, raw",
        "carrots":              "Carrots, raw",
        "celery":               "Celery, raw",
        "celery stalk":         "Celery, raw",
        "eggplant":             "Eggplant, raw",
        "cauliflower":          "Cauliflower, raw",
        "kale":                 "Kale, raw",
        "lettuce":              "Lettuce, romaine, raw",
        "romaine":              "Lettuce, romaine, raw",
        "romaine lettuce":      "Lettuce, romaine, raw",
        "peas":                 "Peas, green, raw",
        "green peas":           "Peas, green, raw",
        "red pepper":           "Peppers, sweet, red, raw",
        "bell pepper":          "Peppers, sweet, red, raw",
        "red bell pepper":      "Peppers, sweet, red, raw",
        "green pepper":         "Peppers, sweet, green, raw",
        "green bell pepper":    "Peppers, sweet, green, raw",
        "zucchini":             "Squash, summer, zucchini, includes skin, raw",
        "courgette":            "Squash, summer, zucchini, includes skin, raw",
        "asparagus":            "Asparagus, raw",
        "mushroom":             "Mushrooms, white, raw",
        "mushrooms":            "Mushrooms, white, raw",
        "ginger":               "Ginger root, raw",
        "fresh ginger":         "Ginger root, raw",
        "corn":                 "Corn, sweet, yellow, raw",
        "cilantro":             "Coriander (cilantro) leaves, raw",
        "fresh cilantro":       "Coriander (cilantro) leaves, raw",
        "parsley":              "Parsley, fresh",
        "fresh parsley":        "Parsley, fresh",
        "basil":                "Basil, fresh",
        "fresh basil":          "Basil, fresh",
        "scallion":             "Onions, spring or scallions (includes tops and bulb), raw",
        "scallions":            "Onions, spring or scallions (includes tops and bulb), raw",
        "green onion":          "Onions, spring or scallions (includes tops and bulb), raw",
        "green onions":         "Onions, spring or scallions (includes tops and bulb), raw",
        "pumpkin":              "Pumpkin, raw",
        "jalapeño":             "Peppers, hot chili, red, raw",
        "jalapeno":             "Peppers, hot chili, red, raw",
        "cucumber":             "Cucumber, with peel, raw",
        "radish":               "Radishes, raw",
        # ── Fruits ───────────────────────────────────────────────────────
        "apple":                "Apples, raw, with skin",
        "apples":               "Apples, raw, with skin",
        "banana":               "Bananas, raw",
        "bananas":              "Bananas, raw",
        "blueberries":          "Blueberries, raw",
        "blueberry":            "Blueberries, raw",
        "lemon":                "Lemons, raw, without peel",
        "lime":                 "Limes, raw",
        "strawberries":         "Strawberries, raw",
        "strawberry":           "Strawberries, raw",
        "grapes":               "Grapes, red or green (European type, such as Thompson seedless), raw",
        "mango":                "Mangos, raw",
        "peach":                "Peaches, raw",
        "pear":                 "Pears, raw",
        "pineapple":            "Pineapple, raw, all varieties",
        "avocado":              "Avocados, raw, all commercial varieties",
        "raspberry":            "Raspberries, raw",
        "raspberries":          "Raspberries, raw",
        "cranberries":          "Cranberries, raw",
        # ── Proteins ─────────────────────────────────────────────────────
        "chicken breast":       "Chicken, broilers or fryers, breast, meat only, raw",
        "chicken":              "Chicken, broilers or fryers, breast, meat only, raw",
        "chicken thigh":        "Chicken, broilers or fryers, thigh, meat only, raw",
        "chicken thighs":       "Chicken, broilers or fryers, thigh, meat only, raw",
        "ground beef":          "Beef, ground, 80% lean meat / 20% fat, raw",
        "beef":                 "Beef, ground, 80% lean meat / 20% fat, raw",
        "ground turkey":        "Turkey, ground, 93% lean, 7% fat, raw",
        "turkey":               "Turkey, ground, 93% lean, 7% fat, raw",
        "pork":                 "Pork, fresh, loin, whole, separable lean and fat, raw",
        "pork chop":            "Pork, fresh, loin, whole, separable lean and fat, raw",
        "salmon":               "Fish, salmon, Atlantic, wild, raw",
        "salmon fillet":        "Fish, salmon, Atlantic, wild, raw",
        "tilapia":              "Fish, tilapia, raw",
        "cod":                  "Fish, cod, Atlantic, raw",
        "shrimp":               "Crustaceans, shrimp, mixed species, raw",
        "prawns":               "Crustaceans, shrimp, mixed species, raw",
        "tuna":                 "Fish, tuna, light, canned in water, drained solids",
        "canned tuna":          "Fish, tuna, light, canned in water, drained solids",
        "bacon":                "Pork, cured, bacon, raw",
        "tofu":                 "Tofu, raw, firm, prepared with calcium sulfate",
        "firm tofu":            "Tofu, raw, firm, prepared with calcium sulfate",
        "sausage":              "Pork, fresh, ground, raw",
        "lamb":                 "Lamb, domestic, composite of trimmed retail cuts, separable lean and fat, raw",
        # ── Dairy & Eggs ─────────────────────────────────────────────────
        "egg":                  "Egg, whole, raw, fresh",
        "eggs":                 "Egg, whole, raw, fresh",
        "egg yolk":             "Egg, yolk, raw, fresh",
        "egg white":            "Egg, white, raw, fresh",
        "milk":                 "Milk, whole, 3.25% milkfat, with added vitamin D",
        "whole milk":           "Milk, whole, 3.25% milkfat, with added vitamin D",
        "butter":               "Butter, salted",
        "unsalted butter":      "Butter, without salt",
        "cheddar":              "Cheese, cheddar",
        "cheddar cheese":       "Cheese, cheddar",
        "parmesan":             "Cheese, parmesan, hard",
        "parmesan cheese":      "Cheese, parmesan, hard",
        "mozzarella":           "Cheese, mozzarella, whole milk",
        "mozzarella cheese":    "Cheese, mozzarella, whole milk",
        "cream cheese":         "Cheese, cream",
        "feta":                 "Cheese, feta",
        "feta cheese":          "Cheese, feta",
        "gruyere":              "Cheese, gruyere",
        "gruyere cheese":       "Cheese, gruyere",
        "swiss cheese":         "Cheese, swiss",
        "ricotta":              "Cheese, ricotta, whole milk",
        "ricotta cheese":       "Cheese, ricotta, whole milk",
        "sour cream":           "Cream, sour, cultured",
        "heavy cream":          "Cream, fluid, heavy whipping",
        "heavy whipping cream": "Cream, fluid, heavy whipping",
        "half and half":        "Cream, half and half",
        "yogurt":               "Yogurt, plain, whole milk, 8 grams protein per 8 ounce",
        "greek yogurt":         "Yogurt, Greek, plain, whole milk",
        # ── Grains & Bread ───────────────────────────────────────────────
        "rice":                 "Rice, white, long-grain, regular, raw, unenriched",
        "white rice":           "Rice, white, long-grain, regular, raw, unenriched",
        "brown rice":           "Rice, brown, long-grain, raw",
        "pasta":                "Pasta, dry, unenriched",
        "penne":                "Pasta, dry, unenriched",
        "spaghetti":            "Pasta, dry, unenriched",
        "linguine":             "Pasta, dry, unenriched",
        "flour":                "Wheat flour, white (all-purpose), unenriched",
        "all-purpose flour":    "Wheat flour, white (all-purpose), unenriched",
        "whole wheat flour":    "Wheat flour, whole-grain",
        "cornmeal":             "Cornmeal, whole-grain, yellow",
        "cornstarch":           "Cornstarch",
        "bread":                "Bread, white, commercially prepared (includes soft bread crumbs)",
        "white bread":          "Bread, white, commercially prepared (includes soft bread crumbs)",
        "whole wheat bread":    "Bread, whole-wheat, commercially prepared",
        "breadcrumbs":          "Bread, white, commercially prepared (includes soft bread crumbs)",
        "quinoa":               "Quinoa, cooked",
        "oats":                 "Cereals, oatmeal, regular and quick, not fortified, dry",
        "rolled oats":          "Cereals, oatmeal, regular and quick, not fortified, dry",
        "oatmeal":              "Cereals, oatmeal, regular and quick, not fortified, dry",
        "barley":               "Barley, pearled, raw",
        "noodles":              "Noodles, egg, dry, unenriched",
        "tortilla":             "Tortillas, ready-to-bake or -fry, flour, shelf stable",
        "flour tortilla":       "Tortillas, ready-to-bake or -fry, flour, shelf stable",
        "panko":                "Bread, white, commercially prepared (includes soft bread crumbs)",
        # ── Oils & Fats ──────────────────────────────────────────────────
        "olive oil":            "Oil, olive, salad or cooking",
        "extra-virgin olive oil":"Oil, olive, salad or cooking",
        "vegetable oil":        "Oil, industrial, soy (partially hydrogenated), all purpose",
        "canola oil":           "Oil, canola",
        "coconut oil":          "Oil, coconut",
        "sesame oil":           "Oil, sesame, salad or cooking",
        "butter oil":           "Butter, salted",
        # ── Salt, Spices & Seasonings ─────────────────────────────────────
        "salt":                 "Salt, table",
        "sea salt":             "Salt, table",
        "kosher salt":          "Salt, table",
        "salt and pepper":      "Salt, table",
        "pepper":               "Spices, pepper, black",
        "black pepper":         "Spices, pepper, black",
        "white pepper":         "Spices, pepper, white",
        "red pepper flakes":    "Spices, pepper, red or cayenne",
        "cayenne":              "Spices, pepper, red or cayenne",
        "cayenne pepper":       "Spices, pepper, red or cayenne",
        "cinnamon":             "Spices, cinnamon, ground",
        "cumin":                "Spices, cumin seed",
        "paprika":              "Spices, paprika",
        "chili powder":         "Spices, chili powder",
        "garlic powder":        "Spices, garlic powder",
        "onion powder":         "Spices, onion powder",
        "thyme":                "Spices, thyme, dried",
        "dried thyme":          "Spices, thyme, dried",
        "oregano":              "Spices, oregano, dried",
        "dried oregano":        "Spices, oregano, dried",
        "bay leaf":             "Spices, bay leaf",
        "bay leaves":           "Spices, bay leaf",
        "nutmeg":               "Spices, nutmeg, ground",
        "allspice":             "Spices, allspice, ground",
        "turmeric":             "Spices, turmeric, ground",
        "curry powder":         "Spices, curry powder",
        "ginger powder":        "Spices, ginger, ground",
        "rosemary":             "Spices, rosemary, dried",
        "dried rosemary":       "Spices, rosemary, dried",
        "sage":                 "Spices, sage, ground",
        "vanilla":              "Vanilla extract",
        "vanilla extract":      "Vanilla extract",
        "baking soda":          "Leavening agents, baking soda",
        "baking powder":        "Leavening agents, baking powder, double-acting, sodium aluminum sulfate",
        # ── Condiments & Sauces ──────────────────────────────────────────
        "soy sauce":            "Sauce, ready-to-serve, hoisin",
        "tomato sauce":         "Sauce, tomato, canned",
        "mayonnaise":           "Mayonnaise dressing, no cholesterol",
        "ketchup":              "Catsup",
        "mustard":              "Mustard, prepared, yellow",
        "hot sauce":            "Sauce, ready-to-serve, pepper, TABASCO",
        "worcestershire sauce": "Sauce, worcestershire",
        "fish sauce":           "Fish sauce, ready-to-serve",
        "oyster sauce":         "Sauce, oyster, ready-to-serve",
        "salsa":                "Sauce, salsa, ready-to-serve",
        "vinegar":              "Vinegar, distilled",
        "white vinegar":        "Vinegar, distilled",
        "apple cider vinegar":  "Vinegar, cider",
        "red wine vinegar":     "Vinegar, red wine",
        "balsamic vinegar":     "Vinegar, balsamic",
        "tomato paste":         "Tomato products, canned, paste, without salt added",
        "crushed tomatoes":     "Tomatoes, crushed, canned",
        "diced tomatoes":       "Tomatoes, red, ripe, canned, packed in tomato juice",
        # ── Legumes & Nuts ────────────────────────────────────────────────
        "lentils":              "Lentils, raw",
        "lentil":               "Lentils, raw",
        "red lentils":          "Lentils, raw",
        "black beans":          "Beans, black, mature seeds, raw",
        "kidney beans":         "Beans, kidney, red, mature seeds, raw",
        "chickpeas":            "Chickpeas (garbanzo beans, bengal gram), mature seeds, raw",
        "garbanzo beans":       "Chickpeas (garbanzo beans, bengal gram), mature seeds, raw",
        "white beans":          "Beans, white, mature seeds, raw",
        "cannellini beans":     "Beans, white, mature seeds, raw",
        "pinto beans":          "Beans, pinto, mature seeds, raw",
        "almonds":              "Nuts, almonds",
        "walnuts":              "Nuts, walnuts, english",
        "cashews":              "Nuts, cashew nuts, raw",
        "pecans":               "Nuts, pecans",
        "peanuts":              "Peanuts, all types, raw",
        "peanut butter":        "Peanut butter, smooth style, with salt",
        "pine nuts":            "Nuts, pine nuts, dried",
        "sesame seeds":         "Seeds, sesame seeds, whole, dried",
        # ── Stock & Liquids ───────────────────────────────────────────────
        "water":                "Water, bottled, generic",
        "chicken broth":        "Soup, chicken broth, canned, condensed",
        "chicken stock":        "Soup, chicken broth, canned, condensed",
        "beef broth":           "Soup, beef broth or bouillon canned, ready-to-serve",
        "beef stock":           "Soup, beef broth or bouillon canned, ready-to-serve",
        "vegetable broth":      "Soup, vegetable beef, canned, condensed",
        "vegetable stock":      "Soup, vegetable beef, canned, condensed",
        "white wine":           "Alcoholic beverage, wine, table, white",
        "red wine":             "Alcoholic beverage, wine, table, red",
        "lemon juice":          "Lemon juice, raw",
        "lime juice":           "Lime juice, raw",
        "orange juice":         "Orange juice, raw",
        # ── Sweeteners ───────────────────────────────────────────────────
        "sugar":                "Sugars, granulated",
        "granulated sugar":     "Sugars, granulated",
        "brown sugar":          "Sugars, brown",
        "powdered sugar":       "Sugars, powdered",
        "honey":                "Honey",
        "maple syrup":          "Syrups, maple",
        "molasses":             "Molasses",
        # ── Other common ─────────────────────────────────────────────────
        "chocolate chips":      "Candies, chocolate chips, semi-sweet",
        "cocoa powder":         "Cocoa, dry powder, unsweetened",
        "vanilla ice cream":    "Ice creams, vanilla",
        "cream of tartar":      "Leavening agents, cream of tartar",
        "gelatin":              "Gelatin desserts, dry mix",
    }

    result: dict[str, dict] = {}
    for ingredient_name, usda_desc in mappings.items():
        match = find(usda_desc)
        if match is not None:
            result[ingredient_name] = match
        # if USDA description not found, just skip — semantic matcher will handle it

    matched_count = len(result)
    log.info("Alias cache: %d / %d mappings resolved from USDA",
             matched_count, len(mappings))
    return result



def _mock_recipe1m() -> list[RecipeNode]:
    return [
        RecipeNode("r001", "Baked Salmon with Broccoli", [
            "150g salmon fillet", "1 cup broccoli florets",
            "1 tbsp olive oil", "salt and pepper to taste", "1 clove garlic, minced",
        ]),
        RecipeNode("r002", "Parmesan Chicken with Potato", [
            "200g chicken breast", "200g potato, diced",
            "50g parmesan cheese, grated", "1 tsp salt", "1 tbsp olive oil",
        ]),
        RecipeNode("r003", "Lentil and Sweet Potato Soup", [
            "1 cup lentils, dried", "1 medium sweet potato, cubed",
            "1 tbsp olive oil", "1/2 tsp black pepper",
        ]),
        RecipeNode("r004", "Egg and Spinach Scramble", [
            "2 eggs", "1 cup fresh spinach", "1 tbsp butter", "1/4 tsp salt",
        ]),
    ]


def _mock_recipe1msubs() -> list[SubstitutionEdge]:
    return [
        SubstitutionEdge("salmon",          "tilapia",      "r001"),
        SubstitutionEdge("parmesan cheese", "eggplant",     "r002"),
        SubstitutionEdge("chicken breast",  "tofu",         "r002"),
        SubstitutionEdge("butter",          "olive oil",    "r004"),
        SubstitutionEdge("lentils",         "white rice",   "r003"),
        SubstitutionEdge("potato",          "sweet potato", "r002"),
    ]


# ════════════════════════════════════════════════════════════════
# SECTION 9 — MAIN
# ════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("data_integration")


def main():
    parser = argparse.ArgumentParser(description="CKD Data Integration Pipeline")
    parser.add_argument("--full", action="store_true",
                        help="Run on all recipes (slow). Default: 500 recipes.")
    parser.add_argument("--limit", type=int, default=500,
                        help="Number of recipes to process (default: 500)")
    args = parser.parse_args()

    max_recipes = None if args.full else args.limit

    print("=" * 55)
    print("  CKD DATA INTEGRATION PIPELINE")
    if max_recipes:
        print(f"  Mode: test run ({max_recipes:,} recipes)")
    else:
        print("  Mode: FULL RUN (all recipes — this will take a while)")
    print("=" * 55)

    # ── build USDA matcher
    paths = DataPaths()
    usda_entries = load_usda(paths.usda_json)
    matcher = USDAMatcher(usda_entries, threshold=0.50)   # n-gram similarity; raise to 0.72 when using real sentence-transformers

    # seed alias cache (works for both mock and real USDA)
    matcher._cache = _mock_usda_cache(
        _mock_usda() if not paths.usda_json.exists() else usda_entries
    )

    # ── run integration
    t0 = time.time()
    graph = build_integrated_graph(paths, matcher, max_recipes=max_recipes)
    elapsed = time.time() - t0

    # ── print coverage report
    print()
    print(graph.coverage_report())
    print(f"\n  Completed in {elapsed:.1f}s")

    # ── save outputs
    report_path = paths.outputs / "coverage_report.txt"
    report_path.write_text(graph.coverage_report(), encoding="utf-8")
    log.info("Coverage report → %s", report_path)

    unmatched = graph.unmatched_ingredients()
    unmatched_path = paths.outputs / "unmatched_ingredients.txt"
    unmatched_path.write_text("\n".join(unmatched), encoding="utf-8")
    log.info("Unmatched ingredients (%d) → %s", len(unmatched), unmatched_path)

    triples_path = paths.outputs / "graph_triples.json"
    triples = graph.export_graph_triples()
    with open(triples_path, "w", encoding="utf-8") as f:
        json.dump(triples, f)
    log.info("Graph triples (%d) → %s", len(triples), triples_path)

    print(f"\n  Outputs saved to: {paths.outputs}/")
    print(f"    coverage_report.txt      ← check USDA match rate first")
    print(f"    unmatched_ingredients.txt← use to improve matcher")
    print(f"    graph_triples.json       ← handoff for graph construction")
    print()

    # ── quick summary of CKD profiles on real data
    if len(graph.ckd_risk_profiles) > 0:
        print("  Sample CKD risk profiles:")
        sample = list(graph.ckd_risk_profiles.items())[:5]
        for name, profile in sample:
            risk_stages = {r["stage"] for r in profile.risks
                           if r["severity"] in ("high","moderate")}
            print(f"    {name:30} unsafe at: {', '.join(sorted(risk_stages)) or 'none'}")

    # ── show safe substitution breakdown
    if graph.safe_substitutions_by_stage:
        print("\n  Safe substitutions per stage (target must be safe at that stage):")
        for stage in sorted(graph.safe_substitutions_by_stage):
            edges = graph.safe_substitutions_by_stage[stage]
            total = len(graph.substitutions)
            print(f"    {stage:10}  {len(edges):>4} / {total} pairs qualify")

        # Show a few concrete examples at stage_3b
        stage_3b_subs = graph.safe_substitutions_by_stage.get("stage_3b", [])
        if stage_3b_subs:
            print("\n  Example safe substitutions at Stage 3b:")
            for e in stage_3b_subs[:5]:
                print(f"    {e.source:25} → {e.target:25}  [{e.reason}]")


if __name__ == "__main__":
    main()
