"""GT-COLOR — Evidence-grounded color→music ground truth (2026-05-30).

No human annotation required. Uses multi-signal proxy V-A for songs + Whiteford
2018 structural HSL→V-A formula for query colors.

SONG V-A PROXY (3-signal fusion, grounded in literature):
  Arousal: 60% Essentia audio (energy/tempo/arousal — R²≈0.69 in-domain)
           + 40% CLAP Russell centroid arousal
  Valence: 40% PhoBERT lyric-emotion cosine (valence from lyrics, arXiv:2302.13321)
           + 30% CLAP Russell centroid valence
           + 30% Essentia audio valence (weaker signal, R²≈0.40)
  QC:      high-confidence = CLAP quadrant matches computed quadrant

QUERY COLOR V-A (Whiteford 2018, PMC6240980):
  arousal = 0.40×sat + 0.35×hue_warmth + 0.25×(1−lightness)   [r_s=0.720]
  valence = 0.45×lightness + 0.35×hue_YB + 0.20×(1−sat)       [r_s=0.484]

GT: song S relevant for color C if d(VA_proxy_S, VA_color_C) < θ (default 0.25)

VALIDITY: "semi-independent proxy GT" — not human-annotated.
  - Arousal proxy: Essentia+CLAP, expected R²≈0.55–0.70 for VN music (arousal
    correlates with audio energy/tempo, more culturally universal).
  - Valence proxy: PhoBERT lyrics provide cultural-specific valence; weaker
    for instrumental songs. Expected R²≈0.30–0.50 for VN music.
  - Circular bias reduced vs engine-derived (3 different signal types),
    but not fully eliminated. Label results as "proxy GT, not gold standard".

REFERENCES:
  Whiteford et al. 2018, i-Perception (PMC6240980) — HSL→V-A formulas
  Palmer et al. 2013, PNAS — emotion mediates color-music link (r=0.89–0.99)
  arXiv:2302.13321 — lyrics improve valence over audio alone
  Memo2496 arXiv:2512.13998 — θ=0.25 expert consistency threshold
  MMVA arXiv:2501.01094 — Recall@K + soft scoring for cross-modal GT
  Eerola & Anderson ACM CSUR 2026 — arousal R²=0.81 > valence R²=0.67
"""

from __future__ import annotations

import colorsys
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

GT_COLOR_FILE = "var/runtime/backtest/ground_truth/color_va_gt_v1.json"

# ------------------------------------------------------------------
# Russell Circumplex centroids for the 8 CLAP emotion labels
# (canonical positions from Russell 1980 + subsequent literature;
#  used to derive a categorical V-A prior from existing CLAP labels)
# ------------------------------------------------------------------
RUSSELL_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "happy":       ( 0.80,  0.50),   # high V, moderate A
    "excited":     ( 0.60,  0.80),   # high V, high A
    "peaceful":    ( 0.55, -0.60),   # moderate V, low A   [normalized -1..1]
    "calm":        ( 0.45, -0.70),   # moderate V, low A
    "melancholic": (-0.40, -0.30),   # low V, low-mod A
    "sad":         (-0.70, -0.40),   # low V, low A
    "tense":       (-0.30,  0.70),   # low V, high A
    "angry":       (-0.70,  0.80),   # low V, high A
}

# ------------------------------------------------------------------
# Whiteford 2018 (PMC6240980) — structural HSL → V-A
# Saturation→Arousal r_s=0.720; Lightness→Valence r_s=0.484
# ------------------------------------------------------------------
def _hsl_to_va(hex_color: str) -> Tuple[float, float]:
    """Map a hex color to (valence, arousal) in [0, 1]² via Whiteford 2018.

    Structural formula (physical properties of light → V-A), culturally
    portable unlike named-color lookups (Jonauskaite uses 30 countries;
    Vietnam is not in the sample; red = festive in VN ≠ global mean).

    Whiteford regressions (Spearman):
      Arousal = 0.40×S + 0.35×hue_warmth + 0.25×(1−L)
      Valence = 0.45×L + 0.35×hue_yellow_bias + 0.20×(1−S)

    Returns (valence, arousal) both in [0, 1].
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16)/255, int(hex_color[2:4], 16)/255, int(hex_color[4:6], 16)/255
    h, l, s = colorsys.rgb_to_hls(r, g, b)   # h in [0,1], l in [0,1], s in [0,1]
    h_deg = h * 360

    # Hue warmth: warm (red/orange/yellow) = high arousal, high valence
    # Cool (blue/green) = lower arousal. Maps hue to [0, 1] warmth proxy.
    # Warm zone: 0–60° and 330–360° (red→yellow); cold zone: 180–300° (blue→purple)
    if h_deg <= 60 or h_deg >= 330:
        hue_warmth = 1.0
    elif h_deg <= 120:
        hue_warmth = 1.0 - (h_deg - 60) / 60
    elif h_deg <= 180:
        hue_warmth = 0.0
    elif h_deg <= 240:
        hue_warmth = 0.0
    elif h_deg <= 300:
        hue_warmth = (h_deg - 240) / 60 * 0.5
    else:
        hue_warmth = 0.5 + (h_deg - 300) / 30 * 0.5

    # Yellow bias for valence: yellow=high V, blue=low V
    # Yellow: ~55–70°, Blue: ~220–250°
    if 40 <= h_deg <= 80:
        hue_yb = 1.0
    elif 200 <= h_deg <= 260:
        hue_yb = 0.0
    else:
        hue_yb = 0.5

    arousal = 0.40 * s + 0.35 * hue_warmth + 0.25 * (1.0 - l)
    valence = 0.45 * l + 0.35 * hue_yb + 0.20 * (1.0 - s)
    return float(np.clip(valence, 0.0, 1.0)), float(np.clip(arousal, 0.0, 1.0))


# ------------------------------------------------------------------
# Song V-A proxy — multi-signal fusion (all from existing system)
# ------------------------------------------------------------------
def _song_va_proxy(catalog: "Catalog") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (valence, arousal, confidence) arrays over the catalog.

    Three signals, each grounded:
    Arousal (more reliable — arXiv:2302.13321; Eerola 2026):
        60% Essentia audio (energy/tempo/arousal col, R²≈0.69)
        40% CLAP Russell centroid arousal
    Valence (needs lyrics — arXiv:2302.13321):
        40% PhoBERT cosine to valence-anchor embeddings
        30% CLAP Russell centroid valence
        30% Essentia audio valence estimate
    Confidence: high = CLAP quadrant matches computed quadrant
    """
    df = catalog.df
    n = len(df)

    # ── CLAP Russell V-A centroids ──────────────────────────────────
    def _clap_va():
        emo = df["fused_emotion"].fillna("happy").str.lower().values
        clap_v = np.array([RUSSELL_CENTROIDS.get(e, (0.0, 0.0))[0] for e in emo])
        clap_a = np.array([RUSSELL_CENTROIDS.get(e, (0.0, 0.0))[1] for e in emo])
        # Normalize from [-1, 1] → [0, 1]
        clap_v = (clap_v + 1.0) / 2.0
        clap_a = (clap_a + 1.0) / 2.0
        return clap_v, clap_a

    clap_v, clap_a = _clap_va()

    # ── Essentia audio signals ────────────────────────────────────────
    def _ess(col, default=0.5):
        if col in df.columns:
            vals = df[col].fillna(default).astype(float).values
            # Normalize to [0, 1]
            mn, mx = vals.min(), vals.max()
            if mx - mn > 1e-6:
                return (vals - mn) / (mx - mn)
        return np.full(n, default)

    # Arousal-related audio: energy (primary), arousal col if present, tempo
    ess_arousal = (
        0.50 * _ess("energy") +
        0.30 * _ess("arousal", 0.5) +
        0.20 * _ess("tempo", 0.5)
    )
    # Valence from audio: very weak but non-zero signal
    ess_valence = _ess("valence_estimated", 0.5)

    # ── PhoBERT lyrics → valence anchor ──────────────────────────────
    # Compute cosine similarity to high-valence / low-valence anchor centroids
    # built from songs already labeled happy vs sad (CLAP ground truth).
    pho_valence = np.full(n, 0.5)
    if catalog.embeddings_normalized is not None:
        happy_mask = np.isin(df["fused_emotion"].values, ["happy", "excited"])
        sad_mask = np.isin(df["fused_emotion"].values, ["sad", "melancholic"])
        if happy_mask.sum() >= 5 and sad_mask.sum() >= 5:
            pos_anchor = catalog.embeddings_normalized[happy_mask].mean(axis=0)
            neg_anchor = catalog.embeddings_normalized[sad_mask].mean(axis=0)
            pos_anchor /= (np.linalg.norm(pos_anchor) + 1e-9)
            neg_anchor /= (np.linalg.norm(neg_anchor) + 1e-9)
            # Valence proxy: how much song leans toward happy vs sad in lyrics space
            pos_sim = catalog.embeddings_normalized @ pos_anchor
            neg_sim = catalog.embeddings_normalized @ neg_anchor
            pho_valence = (pos_sim - neg_sim + 2.0) / 4.0   # → [0, 1] approx
            pho_valence = np.clip(pho_valence, 0.0, 1.0)

    # ── Fuse ─────────────────────────────────────────────────────────
    # Arousal: 60% Essentia audio (culturally stable) + 40% CLAP Russell
    arousal = 0.60 * ess_arousal + 0.40 * clap_a

    # Valence: 40% PhoBERT lyrics (strongest for VN text) + 30% CLAP + 30% Essentia
    valence = 0.40 * pho_valence + 0.30 * clap_v + 0.30 * ess_valence

    arousal = np.clip(arousal, 0.0, 1.0)
    valence = np.clip(valence, 0.0, 1.0)

    # ── Confidence: quadrant agreement between CLAP and proxy ────────
    def _quadrant(v, a):
        return (v >= 0.5).astype(int) * 2 + (a >= 0.5).astype(int)

    clap_q = _quadrant(clap_v, clap_a)
    proxy_q = _quadrant(valence, arousal)
    confidence = (clap_q == proxy_q).astype(float)   # 1.0 = high confidence

    return valence, arousal, confidence


# ------------------------------------------------------------------
# GT builder
# ------------------------------------------------------------------
def build_color_va_gt(
    catalog: "Catalog",
    color_queries: Optional[List[str]] = None,
    theta: float = 0.25,
    soft_sigma: Optional[float] = None,
    min_relevant: int = 5,
    save_path: str = GT_COLOR_FILE,
) -> Tuple[Dict[str, List[int]], dict]:
    """Build color→music GT using proxy V-A.

    Args:
        catalog: Catalog instance.
        color_queries: list of hex colors. Defaults to a curated diverse set.
        theta: hard relevance threshold (Euclidean V-A distance). Default 0.25
               (Memo2496 expert consistency standard).
        soft_sigma: if set, also compute soft scores S=exp(-d/sigma) for NDCG.
        min_relevant: skip query if fewer relevant songs found.
        save_path: where to write JSON.
    """
    if color_queries is None:
        # 24 diverse colors spanning V-A quadrants, including Vietnamese-relevant
        color_queries = [
            "#FF0000",  # Red (high A; VN = festive)
            "#FF6600",  # Orange
            "#FFCC00",  # Yellow (high V, high A)
            "#99FF00",  # Yellow-green
            "#00FF00",  # Green
            "#00FFCC",  # Cyan-green
            "#0099FF",  # Sky blue (calm)
            "#0000FF",  # Blue (low A, mid V)
            "#6600FF",  # Indigo
            "#CC00FF",  # Purple
            "#FF00CC",  # Magenta
            "#FF6699",  # Pink
            "#FF9999",  # Light pink (peaceful-happy)
            "#99CCFF",  # Light blue (calm, low A)
            "#FFFF99",  # Light yellow (happy)
            "#99FF99",  # Light green
            "#CCCCCC",  # Grey (neutral-low)
            "#FFFFFF",  # White
            "#000000",  # Black
            "#333333",  # Dark grey (low V, moderate A)
            "#8B4513",  # Brown (nostalgic)
            "#FF4444",  # Bright red (angry/excited)
            "#4444FF",  # Bright blue (sad/calm)
            "#44FF44",  # Bright green (energetic/happy)
        ]

    val_proxy, aro_proxy, confidence = _song_va_proxy(catalog)
    song_va = np.stack([val_proxy, aro_proxy], axis=1)   # (n, 2)

    gt_mapping: Dict[str, List[int]] = {}
    soft_scores: Dict[str, List[Tuple[int, float]]] = {}
    stats: List[dict] = []

    for color in color_queries:
        try:
            cv, ca = _hsl_to_va(color)
        except Exception:
            print(f"[GT-COLOR] SKIP '{color}' — invalid hex")
            continue

        color_va = np.array([cv, ca])
        dists = np.linalg.norm(song_va - color_va, axis=1)
        above = dists <= theta

        # Limit to high-confidence songs where signal agreement is good
        above_hc = above & (confidence > 0.5)
        relevant_idx = np.where(above_hc)[0].tolist()

        if len(relevant_idx) < min_relevant:
            # Relax confidence gate
            relevant_idx = np.where(above)[0].tolist()

        if len(relevant_idx) < min_relevant:
            print(f"[GT-COLOR] SKIP '{color}' (V={cv:.2f},A={ca:.2f}) — only {len(relevant_idx)} relevant")
            continue

        gt_mapping[color] = relevant_idx

        if soft_sigma is not None:
            # Soft relevance for top-50 (sorted by distance)
            top_idx = np.argsort(dists)[:50].tolist()
            soft_scores[color] = [(int(i), float(np.exp(-dists[i]**2 / (2*soft_sigma**2)))) for i in top_idx]

        hc_frac = confidence[relevant_idx].mean() if relevant_idx else 0.0
        stats.append({
            "color": color,
            "query_va": {"valence": round(cv, 3), "arousal": round(ca, 3)},
            "n_relevant": len(relevant_idx),
            "n_high_conf": int(above_hc.sum()),
            "mean_dist": round(float(dists[relevant_idx].mean()), 4),
            "high_conf_fraction": round(float(hc_frac), 3),
        })
        print(f"[GT-COLOR] '{color}' VA=({cv:.2f},{ca:.2f}) → {len(relevant_idx)} relevant "
              f"(hc={int(above_hc.sum())}  mean_d={dists[relevant_idx].mean():.3f})")

    meta = {
        "n_queries": len(gt_mapping),
        "total_relevant": sum(len(v) for v in gt_mapping.values()),
        "theta": theta,
        "soft_sigma": soft_sigma,
        "validity": "proxy-multi-signal",
        "note": (
            "Song V-A: Arousal=60%Essentia+40%CLAP-Russell; "
            "Valence=40%PhoBERT+30%CLAP+30%Essentia. "
            "Query V-A: Whiteford 2018 HSL structural formula. "
            "Not human-annotated. Arousal more reliable than valence. "
            "Interpret at quadrant level. "
            "Cultural caveat: formula is more portable than Jonauskaite "
            "named-color lookup (Vietnam not in Jonauskaite 30-country sample)."
        ),
        "signals": {
            "arousal": "60% Essentia(energy/arousal/tempo) + 40% CLAP-Russell",
            "valence": "40% PhoBERT-lyrics + 30% CLAP-Russell + 30% Essentia",
            "confidence": "quadrant agreement CLAP vs proxy",
            "query_color": "Whiteford 2018 HSL formula (PMC6240980)",
        },
        "query_stats": stats,
    }

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    payload = {
        "gt_mapping": {c: ids for c, ids in gt_mapping.items()},
        "soft_scores": soft_scores,
        "meta": meta,
    }
    with open(save_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\n[GT-COLOR] Saved {meta['n_queries']} queries, "
          f"{meta['total_relevant']} relevant pairs → {save_path}")
    return gt_mapping, meta


def load_color_va_gt(path: str = GT_COLOR_FILE):
    """Load GT from JSON. Returns (gt_mapping, meta)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d["gt_mapping"], d.get("meta", {})


# ------------------------------------------------------------------
# Evaluation helpers
# ------------------------------------------------------------------
def color_recall_at_k(
    recommender: "MusicRecommender",
    gt_mapping: Dict[str, List[int]],
    k: int = 10,
) -> Dict[str, float]:
    """Compute Recall@K and mAP@K for color→music retrieval.

    Standard metric for cross-modal retrieval (IMEMNet/MMVA, arXiv:2501.01094).
    """
    recalls, aps, n = [], [], 0
    for color, relevant in gt_mapping.items():
        if not relevant:
            continue
        rel_set = set(relevant)
        results = recommender.recommend_by_colors([color], top_k=k)
        if len(results) == 0:
            recalls.append(0.0)
            aps.append(0.0)
            n += 1
            continue
        retrieved = results.index.tolist()
        hits = [1 if idx in rel_set else 0 for idx in retrieved[:k]]
        recall = sum(hits) / len(rel_set) if rel_set else 0.0
        # Average Precision
        ap, hit_count = 0.0, 0
        for rank_i, h in enumerate(hits, 1):
            if h:
                hit_count += 1
                ap += hit_count / rank_i
        ap /= min(k, len(rel_set)) if rel_set else 1
        recalls.append(recall)
        aps.append(ap)
        n += 1

    return {
        f"Recall@{k}": round(float(np.mean(recalls)), 4) if recalls else 0.0,
        f"mAP@{k}":    round(float(np.mean(aps)), 4)     if aps else 0.0,
        "n_queries":   n,
    }
