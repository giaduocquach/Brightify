"""Ground truth for recommend_by_colors() — V-A proximity of catalog songs to query color.

Validity: "engine-derived-color"

WARNING: V-A is an input to recommend_by_colors(), so this GT has tautology risk
similar to va_sanity_v1. Use it to detect catastrophic failures and to compare
pillar arms on the COLOR PATH — not as a standalone quality measure.

Intended tests:
  - Pillar C (RRF): does RRF improve color→song V-A alignment?
  - Pillar E (CLAP): does CLAP improve color→song V-A alignment?

Both pillars have vacuous PASS on editorial GT (song path CI=[0,0]).
This GT tests their actual target path (recommend_by_colors).

Protocol:
  1. 24 representative query hex colors spanning the full HSL space.
  2. For each color: color_to_valence_arousal() → target V-A.
  3. Relevant songs: those with V-A Euclidean distance <= VA_PROXIMITY_THRESHOLD.
  4. GT = {hex_color: [relevant_song_idx, ...]}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Representative query colors — 24 colors spanning the full HSL wheel
# ---------------------------------------------------------------------------

QUERY_COLORS: List[str] = [
    "#FF0000",  # Pure red         — angry/passionate
    "#FF4400",  # Red-orange       — energetic
    "#FF8800",  # Orange           — enthusiastic
    "#FFCC00",  # Amber            — cheerful
    "#FFFF00",  # Yellow           — happy/ecstatic
    "#AAFF00",  # Yellow-green     — hopeful
    "#00CC00",  # Green            — calm
    "#00FF88",  # Mint green       — fresh/calm
    "#00FFFF",  # Cyan             — peaceful
    "#0088FF",  # Sky blue         — calm/melancholic
    "#0000FF",  # Blue             — sad/melancholic
    "#4400CC",  # Blue-purple      — nostalgic
    "#8800CC",  # Purple           — nostalgic
    "#CC00FF",  # Violet           — romantic
    "#FF00CC",  # Magenta          — romantic/passionate
    "#FF0088",  # Hot pink         — romantic/tender
    "#FF88AA",  # Light pink       — tender/romantic
    "#884400",  # Brown/sepia      — nostalgic
    "#555555",  # Dark gray        — calm/sad
    "#AAAAAA",  # Light gray       — peaceful/neutral
    "#CC6600",  # Warm orange-brown — nostalgic/warm
    "#006644",  # Dark teal        — calm/meditative
    "#220066",  # Dark navy        — melancholic/deep
    "#660022",  # Dark crimson     — passionate/intense
]

# Proximity threshold: songs within this V-A Euclidean distance from the color's V-A.
# (√2 ≈ 1.41 is the maximum possible distance in [0,1]² space.)
VA_PROXIMITY_THRESHOLD = 0.25  # top ~25% closest V-A neighbors

GT_DIR  = "var/runtime/backtest/ground_truth"
GT_FILE = os.path.join(GT_DIR, "color_emotion_gt_v1.json")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_color_gt(
    catalog: Any,
    threshold: float = VA_PROXIMITY_THRESHOLD,
    save_path: Optional[str] = GT_FILE,
) -> Tuple[Dict[str, List[int]], Dict[str, Any]]:
    """Build engine-derived color GT.

    For each query color, maps to a (valence, arousal) centroid via the catalog's
    color_mapper, then collects all songs within V-A Euclidean distance <= threshold.

    Args:
        catalog:    Catalog instance (must have .rec.color_mapper and .song_va).
        threshold:  V-A Euclidean distance cutoff for "relevant" songs.
        save_path:  If given, writes GT JSON to this path.

    Returns:
        gt_mapping  — {hex_color: [relevant_song_idx, ...]}
        meta        — metadata dict describing how the GT was built.
    """
    color_mapper = catalog.rec.color_mapper
    song_va = catalog.song_va  # (n_songs, 2)

    gt_mapping: Dict[str, List[int]] = {}
    color_va_map: Dict[str, List[float]] = {}
    skipped: List[str] = []

    for hex_color in QUERY_COLORS:
        try:
            va_result = color_mapper.color_to_valence_arousal(hex_color)
            # color_to_valence_arousal returns (valence, arousal, confidence)
            valence = float(va_result[0])
            arousal = float(va_result[1])
        except Exception:
            skipped.append(hex_color)
            continue

        target_va = np.array([valence, arousal])
        dists = np.sqrt(np.sum((song_va - target_va) ** 2, axis=1))
        relevant = [int(i) for i in np.where(dists <= threshold)[0]]

        if relevant:
            gt_mapping[hex_color] = relevant
            color_va_map[hex_color] = [valence, arousal]

    meta = {
        "validity": "engine-derived-color",
        "warning": (
            "V-A is an input to recommend_by_colors. "
            "Tautology risk: cannot rank engine versions on this GT alone. "
            "Use ONLY to compare pillar arms on the color path (C/E) — "
            "not as a standalone quality measure."
        ),
        "va_proximity_threshold": threshold,
        "n_colors_sampled": len(QUERY_COLORS),
        "n_colors_with_relevant": len(gt_mapping),
        "n_colors_skipped": len(skipped),
        "skipped": skipped,
        "color_va_map": color_va_map,
    }

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        payload = {
            "meta": meta,
            "gt_mapping": gt_mapping,
        }
        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"[color_gt] Saved to {save_path}  ({len(gt_mapping)} color queries)")

    return gt_mapping, meta


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_color_gt(
    path: str = GT_FILE,
) -> Tuple[Dict[str, List[int]], Dict[str, Any]]:
    """Load previously saved color emotion GT."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    gt_mapping: Dict[str, List[int]] = d["gt_mapping"]
    return gt_mapping, d["meta"]
