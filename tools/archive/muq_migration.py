"""Option 1 — migrate audio backbone MERT→MuQ for similar-song + colour-coherence, with
re-optimization; ADOPT only if MuQ ≥ MERT on the end metric (editorial NDCG / colour-TE).

MuQ is SOTA on MARBLE (Zhang 2025, arXiv 2501.01108: beats MERT/MusicFM). This tests whether
that benchmark edge transfers to OUR VN end-metrics after re-tuning, before any migration.

B1 similar-song: editorial NDCG@10 under MERT vs MuQ backbone, each over an audio-weight grid
   (lite re-optimization; SLSQP landed ~0.82 for MERT).
B2 colour-coherence: colour-TE under MERT-centered (α=0.45) vs MuQ-centered over an α grid.

Run: python -m tools.muq_migration
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.color_eval_rigor import ICEAS_COLS, euclidean_te


def _aligned_muq(rec):
    M = np.load("data/muq_embeddings.npy"); meta = json.load(open("data/muq_metadata.json"))
    order = meta.get("done_track_ids") or meta.get("track_ids")
    tids = rec.df["track_id"].astype(str).tolist()
    idx = {str(t): i for i, t in enumerate(order)}
    M = np.array([M[idx[t]] if t in idx else np.full(M.shape[1], np.nan) for t in tids])
    n = (M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)).astype(np.float32)
    c = M - np.nanmean(M, axis=0, keepdims=True)
    c = (c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-9)).astype(np.float32)
    return n, c


def main() -> int:
    from core.recommendation_engine import get_recommender
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.editorial import build_query_gt_mapping
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    rec = get_recommender(); cat = Catalog(rec)
    mert_n, mert_c = rec.mert_matrix, rec.mert_centered
    muq_n, muq_c = _aligned_muq(rec)
    playlists = json.load(open("var/runtime/backtest/ground_truth/editorial_playlists_v1.json"))
    gt = build_query_gt_mapping(playlists)
    seeds = list(gt.keys())
    print(f"[migration] editorial seeds={len(seeds)}")

    def ndcg_for(weights):
        tot = 0.0
        for s in seeds:
            ranked = cat.recommend_by_song(s, top_k=10, weights=weights)
            tot += ndcg_at_k(ranked, gt[s], k=10) if ranked else 0.0
        return tot / max(len(seeds), 1)

    # ── B1: similar-song NDCG, MERT vs MuQ, audio-weight grid (re-opt lite) ──
    print("\n=== B1 similar-song: editorial NDCG@10 (higher=better) ===")
    res_b1 = {}
    for tag, A in [("MERT", mert_n), ("MuQ", muq_n)]:
        rec.mert_matrix = A
        best = (-1, None)
        for mw in (0.76, 0.82, 0.88):           # audio weight; va:lyrics keep 2:1
            rest = 1 - mw; w = [0, 0, 0, rest/3, 2*rest/3, 0, 0, mw]
            nd = ndcg_for(w)
            if nd > best[0]: best = (nd, mw)
            print(f"  {tag:5} mert_w={mw:.2f}  NDCG@10={nd:.4f}")
        res_b1[tag] = best
        print(f"  → {tag} best NDCG={best[0]:.4f} @ mert_w={best[1]}")
    rec.mert_matrix = mert_n

    # ── B2: colour-coherence TE, MERT-centered(α=0.45) vs MuQ-centered (α grid) ──
    import core.recommendation_engine as RE
    match_va = rec.song_va_match
    def color_te(alpha):
        RE.COLOR_COHERENCE_ALPHA = alpha
        tes = []
        for hx, _ in ICEAS_COLS:
            cv, ca = rec.color_mapper.hsl_to_va(hx); tgt = rec._color_target_quantile([cv, ca])
            df = rec.recommend_by_colors(hx, top_k=12)
            idx = df["original_index"].tolist() if df is not None and not df.empty else []
            if len(idx) >= 2: tes.append(euclidean_te(idx, match_va, np.array(tgt)))
        return float(np.mean(tes))
    print("\n=== B2 colour-coherence: colour-TE (lower=better) ===")
    rec.mert_centered = mert_c
    te_mert = color_te(0.45); print(f"  MERT-centered α=0.45  TE={te_mert:.4f}")
    rec.mert_centered = muq_c
    best_muq = (9.9, None)
    for a in (0.45, 0.35, 0.55):
        te = color_te(a); print(f"  MuQ-centered  α={a:.2f}  TE={te:.4f}")
        if te < best_muq[0]: best_muq = (te, a)
    rec.mert_centered = mert_c; RE.COLOR_COHERENCE_ALPHA = 0.45

    # ── verdicts ──
    print("\n=== ADOPT DECISIONS (adopt MuQ only if ≥ MERT) ===")
    nd_m, nd_q = res_b1["MERT"][0], res_b1["MuQ"][0]
    print(f"  B1 similar-song: MERT NDCG={nd_m:.4f} vs MuQ NDCG={nd_q:.4f}"
          f"  → {'ADOPT MuQ' if nd_q > nd_m + 0.002 else 'KEEP MERT'}")
    print(f"  B2 colour: MERT TE={te_mert:.4f} vs MuQ best TE={best_muq[0]:.4f} (α={best_muq[1]})"
          f"  → {'ADOPT MuQ' if best_muq[0] < te_mert - 0.001 else 'KEEP MERT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
