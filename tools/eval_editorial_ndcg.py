"""Editorial-playlist NDCG@10 for similar-song — reproducible standalone harness.

Replaces the drifted `backtest_v2.measure_full_accuracy` (which is tied to the
removed pillar architecture). Uses the committed editorial ground truth
(var/runtime/backtest/ground_truth/editorial_playlists_v1.json), the live
recommender, and the project's own ndcg_at_k. Reflects the CURRENT config
(AUDIO_BACKBONE + EMBEDDINGS_FILE).

Run: python -m tools.eval_editorial_ndcg
"""
from __future__ import annotations
import os, sys, statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from tools.backtest_v2.ground_truth.editorial import (
        build_query_gt_mapping, load_editorial_gt, GT_FILE)
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    from core.recommendation_engine import get_recommender
    import config as cfg

    playlists = load_editorial_gt(GT_FILE)
    gt = build_query_gt_mapping(playlists)
    print(f"[editorial-ndcg] backbone={cfg.AUDIO_BACKBONE}  lyrics={os.path.basename(cfg.EMBEDDINGS_FILE)}")
    print(f"[editorial-ndcg] {len(playlists)} playlists, {len(gt)} seed queries")

    rec = get_recommender()
    ndcgs = []
    for seed_idx, relevant_indices in gt.items():
        relevant = set(relevant_indices)
        if not relevant:
            continue
        try:
            df = rec.recommend_by_song(int(seed_idx), top_k=10)
            ranked = [int(i) for i in df["original_index"].tolist()]
        except Exception:
            ranked = []
        ndcgs.append(ndcg_at_k(ranked, relevant, 10))

    print(f"[editorial-ndcg] mean NDCG@10 = {statistics.mean(ndcgs):.4f}  (n={len(ndcgs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
