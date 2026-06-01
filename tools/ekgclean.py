"""E-KG-CLEAN — KG (kg_sim, w0.08) is 50% MERT + 50% degenerate Essentia tags
(mood_tags/instrument_tags, 99% corporate/trumpet). Question: does kg_sim help, and is
the tag-half hurting? Compare on the editorial GT (cluster-paired bootstrap CI):
  A) KG-off  (kg_matrix=None) vs current tag-KG
  B) pure-MERT KG vs current tag-KG   [if data/kg_embeddings_mertonly.npy exists]
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.backtest_v2.catalog import Catalog
from tools.backtest_v2.ground_truth.editorial import (
    GT_FILE, load_editorial_gt, build_query_gt_mapping, build_cluster_seeds)
from tools.backtest_v2.stats import cluster_paired_bootstrap
from tools.backtest_v2.metrics.accuracy import ndcg_at_k

cat = Catalog.load()
pls = load_editorial_gt(GT_FILE)
gt = build_query_gt_mapping(pls)
clusters = build_cluster_seeds(pls)
seeds = list(gt.keys())
print(f"[E-KG-CLEAN] {len(seeds)} queries")


def eval_ndcg():
    out = {}
    for s in seeds:
        r = cat.recommend_by_song(s, top_k=10)
        out[s] = ndcg_at_k(r, set(gt[s]), 10) if r is not None and len(r) else 0.0
    return out


# --- baseline: current tag-KG ---
sc_base = eval_ndcg()
print(f"  KG-on (tag-KG)  mean NDCG@10 = {np.mean(list(sc_base.values())):.5f}")

# --- A) KG off ---
kg_backup = cat.rec.kg_matrix
cat.rec.kg_matrix = None
sc_off = eval_ndcg()
cat.rec.kg_matrix = kg_backup
print(f"  KG-off          mean NDCG@10 = {np.mean(list(sc_off.values())):.5f}")
d, lo, hi = cluster_paired_bootstrap(sc_base, sc_off, clusters)   # off - base
print(f"  Δ(off-base) = {d:+.5f}  CI95=[{lo:+.5f},{hi:+.5f}]  "
      f"→ {'DROP KG safe/better' if lo >= 0 else 'KG helps, keep (try pure-MERT)'}")

# --- B) pure-MERT KG (if built) ---
mert_only = "data/kg_embeddings_mertonly.npy"
if os.path.exists(mert_only):
    kg2 = np.load(mert_only)
    kg2 = kg2 / (np.linalg.norm(kg2, axis=1, keepdims=True) + 1e-9)
    cat.rec.kg_matrix = kg2.astype(np.float32)
    sc_pure = eval_ndcg()
    cat.rec.kg_matrix = kg_backup
    print(f"  KG pure-MERT    mean NDCG@10 = {np.mean(list(sc_pure.values())):.5f}")
    d2, lo2, hi2 = cluster_paired_bootstrap(sc_base, sc_pure, clusters)
    print(f"  Δ(pureMERT-base) = {d2:+.5f}  CI95=[{lo2:+.5f},{hi2:+.5f}]")
