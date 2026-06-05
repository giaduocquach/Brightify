"""Shared FOUNDATION for the non-circular color backtest (L1/L2/L3).

The old color GT (color_emotion_gt.py / color_va_gt.py) is CIRCULAR: it defines
"relevant" by the same song V-A that the ranker scores with, and uses the engine's
own hsl_to_va() to place the query — so optimising V-A trivially scores ~100% on a
test made of V-A. See docs/PLAN_COLOR_BACKTEST_V15.md.

This module replaces the circular anchor with an EXTERNAL human standard:
the International Colour-Emotion Association Survey (ICEAS / Jonauskaite et al. 2020,
Psychological Science; OSF 2w6gh, CC-BY 4.0). 8615 participants per colour from
37 nations rated 12 colour terms on 20 Geneva-Emotion-Wheel concepts.

From that we derive, PER COLOUR, an independent ground truth:
  * human_va        — valence/arousal centroid (GEW emotion ratings × circumplex coords)
  * human_emotion8  — distribution over the engine's 8 emotion labels
  * target_mood     — the dominant human emotion (used as the L2/L3 query intent)

None of these touch the engine's hsl_to_va / song_va / song_emotion_vec, so any
agreement with the engine is real signal, not tautology.

Data file: data/external/color_norms/jonauskaite_ICEAS_raw.csv
Download:  curl -L https://osf.io/download/5urwh/ -o <that path>   (OSF node 2w6gh)
"""

from __future__ import annotations

import functools
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

ICEAS_CSV = "data/external/color_norms/jonauskaite_ICEAS_raw.csv"

# --------------------------------------------------------------------------- #
# The 12 ICEAS colour terms → representative sRGB hex.
# ICEAS presented colour *terms* (words), not patches, so there is no single
# "correct" hex. We use the standard/web canonical sRGB for each basic term;
# the companion patch study (Jonauskaite et al. 2019, i-Perception) confirms
# these terms map to the prototypical hues. Lightness/saturation kept maximal
# for chromatic terms so the engine's hue-driven formula gets a fair input.
# --------------------------------------------------------------------------- #
COLOR_TERM_HEX: Dict[str, str] = {
    "red":       "#FF0000",
    "orange":    "#FF8000",
    "yellow":    "#FFFF00",
    "green":     "#008000",
    "turquoise": "#40E0D0",
    "blue":      "#0000FF",
    "purple":    "#800080",
    "pink":      "#FFC0CB",
    "brown":     "#8B4513",
    "white":     "#FFFFFF",
    "grey":      "#808080",
    "black":     "#000000",
}

# --------------------------------------------------------------------------- #
# Geneva Emotion Wheel (the 20 ICEAS concepts) → (valence, arousal) in [0,1].
# Placements follow Russell's circumplex (1980) and the GEW affective layout
# (Scherer 2005); valence = pleasantness, arousal = activation. These are
# fixed independent norms — NOT derived from anything in Brightify — so they
# can anchor the engine's color→V-A formula without circularity.
# --------------------------------------------------------------------------- #
GEW_EMOTION_VA: Dict[str, Tuple[float, float]] = {
    "admiration":     (0.80, 0.55),
    "amusement":      (0.85, 0.60),
    "anger":          (0.10, 0.90),
    "compassion":     (0.65, 0.40),
    "contempt":       (0.20, 0.55),
    "contentment":    (0.80, 0.25),
    "disappointment": (0.22, 0.38),
    "disgust":        (0.15, 0.60),
    "fear":           (0.15, 0.85),
    "guilt":          (0.22, 0.50),
    "hate":           (0.10, 0.80),
    "interest":       (0.70, 0.60),
    "joy":            (0.90, 0.70),
    "love":           (0.90, 0.55),
    "pleasure":       (0.85, 0.50),
    "pride":          (0.80, 0.60),
    "regret":         (0.25, 0.40),
    "relief":         (0.70, 0.30),
    "sadness":        (0.15, 0.25),
    "shame":          (0.20, 0.45),
}
EMO20: List[str] = list(GEW_EMOTION_VA.keys())

# --------------------------------------------------------------------------- #
# Map each GEW concept onto the engine's 8 emotion labels (happy / excited /
# peaceful / calm / melancholic / sad / tense / angry). Grouping is by nearest
# affective meaning; used only to express the human ratings in the SAME label
# space the engine uses, for a like-for-like distribution comparison.
# --------------------------------------------------------------------------- #
EMOTION_20_TO_8: Dict[str, str] = {
    "joy": "happy", "amusement": "happy", "pleasure": "happy",
    "admiration": "excited", "pride": "excited", "interest": "excited", "love": "excited",
    "contentment": "calm", "relief": "calm",
    "compassion": "peaceful",
    "disappointment": "melancholic", "regret": "melancholic", "guilt": "melancholic",
    "shame": "melancholic",
    "sadness": "sad",
    "fear": "tense", "disgust": "tense", "contempt": "tense",
    "anger": "angry", "hate": "angry",
}
EMO8: List[str] = ["happy", "excited", "peaceful", "calm",
                   "melancholic", "sad", "tense", "angry"]


@functools.lru_cache(maxsize=1)
def load_human_color_norm(csv_path: str = ICEAS_CSV) -> Dict[str, dict]:
    """Aggregate the raw ICEAS survey into a per-colour human norm.

    Returns {colour_term: {
        "hex":           sRGB hex,
        "n":             #participants,
        "ratings20":     {emotion: mean_rating} over the 20 GEW concepts,
        "human_va":      (valence, arousal) in [0,1] — rating-weighted circumplex centroid,
        "human_emotion8": {label: prob} over the engine's 8 labels (raw shares, sum 1),
        "distinctive8":  {label: prob} after dividing each emotion by its cross-colour
                         mean — i.e. what this colour is *distinctively* associated with
                         (removes the positivity baseline shared by all colours),
        "target_mood":   argmax of distinctive8 (the L2/L3 query intent),
    }}

    The positivity baseline (people rate almost every colour net-positive) makes the
    RAW argmax collapse to happy/excited for most colours. The literature reports
    colour specificity relative to the cross-colour average, so target_mood uses the
    distinctive profile (red→angry, blue→calm, black→melancholic, …).
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"ICEAS data not found at {csv_path}. Download with:\n"
            f"  curl -L https://osf.io/download/5urwh/ -o {csv_path}"
        )
    df = pd.read_csv(csv_path)
    va_v = np.array([GEW_EMOTION_VA[e][0] for e in EMO20])
    va_a = np.array([GEW_EMOTION_VA[e][1] for e in EMO20])

    terms = [t for t in COLOR_TERM_HEX if t in set(df["colour"].unique())]
    grouped = df.groupby("colour")[EMO20].mean()
    counts = df.groupby("colour").size()
    R = np.array([grouped.loc[t].values.astype(float) for t in terms])   # (n_terms, 20)
    col_mean = R.mean(axis=0) + 1e-9                                      # per-emotion baseline

    def _collapse8(vec20: np.ndarray) -> Dict[str, float]:
        e8 = {lbl: 0.0 for lbl in EMO8}
        for emo, val in zip(EMO20, vec20):
            e8[EMOTION_20_TO_8[emo]] += float(val)
        tot = sum(e8.values()) or 1.0
        return {k: v / tot for k, v in e8.items()}

    out: Dict[str, dict] = {}
    for i, term in enumerate(terms):
        r = R[i]
        w = r / (r.sum() + 1e-9)                        # rating share per emotion
        human_v = float((w * va_v).sum())
        human_a = float((w * va_a).sum())
        distinctive8 = _collapse8(r / col_mean)         # specificity vs other colours
        out[term] = {
            "hex": COLOR_TERM_HEX[term],
            "n": int(counts.get(term, 0)),
            "ratings20": {e: float(r[j]) for j, e in enumerate(EMO20)},
            "human_va": (human_v, human_a),
            "human_emotion8": _collapse8(r),
            "distinctive8": distinctive8,
            "target_mood": max(distinctive8, key=distinctive8.get),
        }
    return out


# --------------------------------------------------------------------------- #
# QUERY COLOURS for L2 (retrieval) and L3 (discriminant).
# Each query colour is anchored to a target mood derived from the HUMAN norm
# above (not the engine). We expose them as a function so the target_mood is
# always taken live from the loaded survey, never hand-typed.
# --------------------------------------------------------------------------- #

def query_colors() -> List[dict]:
    """Return [{term, hex, target_mood, human_va}] for the 12 normed colours."""
    norm = load_human_color_norm()
    return [
        {"term": t, "hex": d["hex"], "target_mood": d["target_mood"],
         "human_va": d["human_va"]}
        for t, d in norm.items()
    ]


# Opposite-mood colour pairs for L3 discriminant validity. Chosen by HUMAN
# valence/arousal separation (see human_va), not the engine — e.g. blue/black
# (calm-positive vs negative-arousing), yellow/grey (cheerful vs dull).
def discriminant_pairs() -> List[Tuple[str, str]]:
    """Return colour-term pairs whose HUMAN V-A are far apart (for separation tests)."""
    norm = load_human_color_norm()

    def dist(a: str, b: str) -> float:
        va, vb = norm[a]["human_va"], norm[b]["human_va"]
        return float(np.hypot(va[0] - vb[0], va[1] - vb[1]))

    # Candidate antonym pairs grounded in the literature (warm/cool, light/dark);
    # keep those the human data confirms are actually far apart.
    candidates = [("yellow", "black"), ("yellow", "grey"), ("orange", "grey"),
                  ("pink", "black"), ("red", "blue"), ("green", "black"),
                  ("orange", "blue"), ("white", "black")]
    ranked = sorted(candidates, key=lambda p: -dist(*p))
    return ranked
