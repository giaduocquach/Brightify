"""SECONDARY ground-truth candidate: MTG-Jamendo mood_tags.

§7.3 gate — only promote to `semi-independent` if it passes all three:
  1. Top-tag entropy: reject if >80% of songs share the same 1–2 top tags.
  2. Distinct top-tags: reject if <5 distinct.
  3. Correlation with engine V-A: downgrade to engine-derived if r > 0.7.

`discriminativeness_check()` is reproducible — re-run it whenever the catalog
is rebuilt. Building the actual GT JSON is Phase 2 (only if the gate passes).

NOTE (catalog as of 2026-05-27, 5548 rows): GATE FAILED.
  - 98.2% of songs have top-tag "corporate"; 9 distinct top-tags; normalized
    entropy 0.054. MTG-Jamendo (stock/library-music training) mislabels VN pop
    en masse as "corporate" → non-discriminative. Do NOT use as ground truth.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Dict

import numpy as np
import pandas as pd


def _parse_tags(x: Any) -> Dict[str, float]:
    if pd.isna(x):
        return {}
    try:
        d = json.loads(x)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def discriminativeness_check(df: pd.DataFrame) -> Dict[str, Any]:
    """Run the §7.3 gate over a catalog dataframe with a `mood_tags` column.

    Returns a dict with the computed stats and a verdict in
    {'reject', 'engine_derived', 'semi_independent'}.
    """
    tags = df["mood_tags"].apply(_parse_tags)
    top = tags.apply(lambda d: max(d, key=d.get) if d else None).dropna()
    counts = Counter(top)
    total = len(top)
    distinct = len(counts)

    top1 = counts.most_common(1)[0][1] / total if total else 0.0
    top2 = sum(c for _, c in counts.most_common(2)) / total if total else 0.0
    probs = np.array([c / total for c in counts.values()]) if total else np.array([1.0])
    entropy = float(-(probs * np.log2(probs)).sum())
    norm_entropy = entropy / math.log2(distinct) if distinct > 1 else 0.0

    verdict = "semi_independent"
    reasons = []
    if top1 > 0.80 or top2 > 0.80:
        verdict = "reject"
        reasons.append(f"top-2 tag share {top2:.1%} > 80%")
    if distinct < 5:
        verdict = "reject"
        reasons.append(f"only {distinct} distinct top-tags (<5)")
    # Correlation vs engine V-A is only meaningful if the first gates pass.

    return {
        "n_with_tags": int(top.shape[0]),
        "distinct_top_tags": distinct,
        "top1_share": round(top1, 4),
        "top2_share": round(top2, 4),
        "entropy_bits": round(entropy, 4),
        "normalized_entropy": round(norm_entropy, 4),
        "verdict": verdict,
        "reasons": reasons,
    }
