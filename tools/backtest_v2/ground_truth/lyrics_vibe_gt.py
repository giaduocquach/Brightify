"""GT-1 — Lyrics / Vibe search ground-truth (2026-05-30).

Builds ~120 (query, relevant-songs) pairs for evaluating the lyrics/vibe search
feature (F3 / recommend_by_lyrics_keywords).

Method (semi-automated, not pure-weak-annotation):
  For each natural-language query, retrieve candidates via PhoBERT semantic
  similarity (the same signal the search uses), then KEEP only songs whose
  cosine similarity to the query exceeds a calibrated threshold AND whose
  fused_emotion label matches the query intent.  This creates pairs that are
  both semantically close AND emotionally coherent — harder to game than a
  purely keyword-based or emotion-label-only GT.

Validity note: this GT is SEMI-INDEPENDENT (it uses the same embedding model
  as the system under test), so NDCG on it cannot prove absolute quality.
  It is suitable for relative A/B comparison (e.g. with vs without emotion
  term, with vs without centroid-γ) but should be labeled "semi-independent"
  in reports.  For a fully-independent GT, human annotation is required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

GT1_FILE = "var/runtime/backtest/ground_truth/lyrics_vibe_gt_v1.json"

# ------------------------------------------------------------------
# Query definitions: (query_text, target_emotions, min_relevant)
# target_emotions: list of fused_emotion labels that are *relevant* to this query.
# A song is relevant if cosine(query, song_emb) >= SEMANTIC_THRESHOLD
# AND its fused_emotion is in target_emotions.
# ------------------------------------------------------------------
QUERIES: List[Tuple[str, List[str], int]] = [
    # --- sad / melancholic ---
    ("đêm mưa buồn nhớ người yêu cũ",        ["sad", "melancholic"],  8),
    ("tình yêu đầu tan vỡ nước mắt cô đơn",   ["sad", "melancholic"],  8),
    ("buồn bã u sầu không ai hiểu mình",       ["sad", "melancholic"],  8),
    ("xa nhau mãi mãi chia tay đau lòng",      ["sad", "melancholic"],  8),
    ("nhớ thương người cũ ngày xưa hoài niệm", ["sad", "melancholic"],  8),
    # --- happy / excited ---
    ("vui vẻ hạnh phúc yêu đời nhảy múa",     ["happy", "excited"],    8),
    ("tiệc tùng sôi động phấn khích bạn bè",   ["happy", "excited"],    8),
    ("tình yêu mới ngọt ngào hạnh phúc",       ["happy", "excited"],    8),
    ("năng lượng tích cực mỗi ngày tươi sáng", ["happy", "excited"],    8),
    ("mùa hè nắng vàng biển xanh vui chơi",    ["happy", "excited"],    8),
    # --- peaceful / calm ---
    ("bình yên thư giãn nhẹ nhàng nghỉ ngơi",  ["peaceful", "calm"],   6),
    ("sáng sớm cà phê yên tĩnh thiên nhiên",   ["peaceful", "calm"],   6),
    ("acoustic nhẹ nhàng tĩnh lặng tâm hồn",   ["peaceful", "calm"],   6),
    # --- angry / tense ---
    ("tức giận bực bội căng thẳng nổi loạn",   ["angry", "tense"],     5),
    ("phản kháng mạnh mẽ không sợ hãi",        ["angry", "tense"],     5),
    # --- mixed / thematic ---
    ("quê hương gia đình mẹ cha nhớ nhà",      ["sad", "melancholic", "peaceful"], 8),
    ("tuổi trẻ ước mơ thanh xuân cố gắng",    ["happy", "excited"],    8),
    ("cô đơn một mình đêm khuya suy nghĩ",     ["sad", "melancholic"],  8),
    ("tình bạn gắn kết bên nhau mãi mãi",      ["happy", "peaceful"],   8),
    ("vượt qua khó khăn mạnh mẽ đứng dậy",    ["happy", "excited"],    6),
]

SEMANTIC_THRESHOLD = 0.80   # cosine similarity floor — requires strong semantic match
MAX_RELEVANT = 60           # cap per query to avoid trivial majority-class flooding
MIN_RELEVANT = 10           # drop query if fewer relevant songs found


def build_lyrics_vibe_gt(
    catalog: "Catalog",
    save_path: str = GT1_FILE,
) -> Tuple[Dict[str, List[int]], dict]:
    """Build the GT-1 query→relevant mapping and save to JSON.

    Args:
        catalog: backtest Catalog instance (has .df, .embeddings_normalized,
                 .emotion_analyzer).
        save_path: where to write the JSON.

    Returns:
        (gt_mapping, meta) where gt_mapping = {query_str: [catalog_idx, ...]}.
    """
    from core.emotion_analysis import get_emotion_analyzer

    df = catalog.df
    emb = catalog.embeddings_normalized   # (n_songs, 768) L2-normed
    if emb is None:
        raise RuntimeError("GT-1 needs lyrics embeddings (embeddings_normalized).")

    _, classifier, _ = get_emotion_analyzer()  # get_emotion_analyzer returns (lexicon, classifier, fusion)

    gt_mapping: Dict[str, List[int]] = {}
    stats: List[dict] = []

    for query_text, target_emotions, min_req in QUERIES:
        # Encode query with PhoBERT (same path as recommend_by_lyrics_keywords)
        q_emb = classifier.encode_lyrics(query_text)
        if q_emb is None or np.linalg.norm(q_emb) < 1e-9:
            print(f"[GT-1] SKIP '{query_text}' — encoder returned empty vector")
            continue
        q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

        # Cosine similarity to all songs
        sims = emb @ q_norm                        # [-1, 1]
        sims_01 = (sims + 1.0) / 2.0              # → [0, 1]

        # Emotion mask
        emo_mask = df["fused_emotion"].isin(target_emotions).to_numpy()

        # Relevant = high semantic sim AND matching emotion
        combined = sims_01 * emo_mask.astype(float)
        above = (sims_01 >= SEMANTIC_THRESHOLD) & emo_mask

        # Take the top-MAX_RELEVANT by cosine (among those passing threshold+emotion)
        if above.sum() > MAX_RELEVANT:
            scores_masked = np.where(above, sims_01, -1.0)
            top_idx = np.argsort(scores_masked)[::-1][:MAX_RELEVANT]
            relevant_idx = [int(i) for i in top_idx if above[i]]
        else:
            relevant_idx = np.where(above)[0].tolist()

        if len(relevant_idx) < min_req:
            # Relax: take top-N by cosine within emotion filter, even if < threshold
            emo_scores = np.where(emo_mask, sims_01, -1.0)
            top = np.argsort(emo_scores)[::-1][:MAX_RELEVANT]
            relevant_idx = [int(i) for i in top if sims_01[i] >= 0.72]

        if len(relevant_idx) < MIN_RELEVANT:
            print(f"[GT-1] SKIP '{query_text}' — only {len(relevant_idx)} relevant (< {MIN_RELEVANT})")
            continue

        gt_mapping[query_text] = [int(i) for i in relevant_idx]
        stats.append({
            "query": query_text,
            "target_emotions": target_emotions,
            "n_relevant": len(relevant_idx),
            "mean_cosine": float(np.mean(sims_01[relevant_idx])),
        })
        print(f"[GT-1] '{query_text[:45]}' → {len(relevant_idx)} relevant  "
              f"(mean_cos={float(np.mean(sims_01[relevant_idx])):.3f})")

    meta = {
        "n_queries": len(gt_mapping),
        "total_relevant_pairs": sum(len(v) for v in gt_mapping.values()),
        "semantic_threshold": SEMANTIC_THRESHOLD,
        "validity": "semi-independent",
        "note": (
            "Uses the same PhoBERT embeddings as the system under test — valid "
            "for relative A/B comparison, NOT absolute quality claims."
        ),
        "query_stats": stats,
    }

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    payload = {
        "queries": [
            {"query": q, "relevant_catalog_ids": ids}
            for q, ids in gt_mapping.items()
        ],
        "meta": meta,
    }
    with open(save_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\n[GT-1] Saved {meta['n_queries']} queries, "
          f"{meta['total_relevant_pairs']} relevant pairs → {save_path}")
    return gt_mapping, meta


def load_lyrics_vibe_gt(path: str = GT1_FILE) -> Tuple[Dict[str, List[int]], dict]:
    """Load GT-1 from JSON. Returns (gt_mapping, meta)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    gt = {item["query"]: item["relevant_catalog_ids"] for item in d["queries"]}
    return gt, d.get("meta", {})
