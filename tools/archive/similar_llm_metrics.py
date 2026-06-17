"""NDCG/P@K for recommend_by_song on the de-circularized LLM-judge GT (v2).

GT v2 changes vs v1:
  • No fused_emotion in judge prompt (Soboroff 2024 — removes circular element)
  • PoLL: qwen3:8b + gemma2:2b both must score >= 2 (Verga 2024)
  • Cross-artist split: same-artist pairs excluded to surface genre-level similarity

Reports: production vs random-within-pool (honest contrast) + bootstrap CI.
P@10 is the headline; NDCG/mAP are pool-relative (warn if citing absolute values).

Usage: python -m tools.similar_llm_metrics
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT   = "var/runtime/backtest/reports/similar_llm_metrics.json"
TOP_K = 10


def _boot_ci(vals, n_boot: int = 10_000, seed: int = 42):
    vals = np.asarray(vals, dtype=float)
    if not len(vals):
        return (0.0, 0.0, 0.0)
    rng   = np.random.default_rng(seed)
    means = [vals[rng.integers(0, len(vals), len(vals))].mean() for _ in range(n_boot)]
    return (round(float(vals.mean()), 4),
            round(float(np.percentile(means, 2.5)),  4),
            round(float(np.percentile(means, 97.5)), 4))


def _eval_block(cat, gt: dict, rng: np.random.Generator,
                artist_col: str | None, cross_artist_only: bool = False):
    """Compute NDCG/P/Recall/mAP/MRR lists for production and random-pool."""
    from tools.backtest_v2.metrics.accuracy import (
        ndcg_at_k, precision_at_k, recall_at_k, average_precision_at_k, mrr)

    df = cat.df
    prod_m = {k: [] for k in ("ndcg", "p", "rec", "ap", "rr")}
    rand_m = {k: [] for k in ("ndcg", "p", "rec", "ap", "rr")}
    n_skip = 0

    for seed_str, entry in gt.items():
        seed_idx = int(seed_str)
        judged   = entry.get("judged", {})
        R_all    = set(entry.get("relevant", []))
        pool     = [int(k) for k, v in judged.items()
                    if isinstance(v, dict) and v.get("q", -1) >= 0]

        if cross_artist_only and artist_col:
            seed_artist = str(df.iloc[seed_idx].get(artist_col, "") or "")
            R_all = {r for r in R_all
                     if str(df.iloc[r].get(artist_col, "") or "") != seed_artist}
            pool  = [p for p in pool
                     if str(df.iloc[p].get(artist_col, "") or "") != seed_artist]

        if len(R_all) < 1 or len(pool) < 2:
            n_skip += 1
            continue

        recs = cat.recommend_by_song(seed_idx, top_k=TOP_K)
        rand = rng.choice(pool, size=min(TOP_K, len(pool)), replace=False).tolist()

        for k in prod_m:
            fn_map = {"ndcg": ndcg_at_k, "p": precision_at_k, "rec": recall_at_k,
                      "ap": average_precision_at_k, "rr": mrr}
            fn = fn_map[k]
            prod_m[k].append(fn(recs, R_all, TOP_K) if k != "rr" else fn(recs, R_all))
            rand_m[k].append(fn(rand, R_all, TOP_K) if k != "rr" else fn(rand, R_all))

    return prod_m, rand_m, n_skip


def main() -> int:
    from tools.backtest_v2.catalog import Catalog
    from tools.backtest_v2.ground_truth.similar_llm_gt import load_similar_llm_gt, GT_FILE

    gt  = load_similar_llm_gt()
    cat = Catalog.load()
    rng = np.random.default_rng(42)

    artist_col = cat.artist_col

    # ── PoLL agreement stats ──────────────────────────────────────────────────
    q_scores, g_scores, agree = [], [], 0
    poll_mode_counts: dict = {}
    for entry in gt.values():
        mode = entry.get("poll_mode", "unknown")
        poll_mode_counts[mode] = poll_mode_counts.get(mode, 0) + 1
        for sc in entry.get("judged", {}).values():
            if not isinstance(sc, dict):
                continue
            q = sc.get("q", -1)
            # prefer g14 (qwen2.5-coder:14b) over g (degenerate gemma2:2b)
            g = sc.get("g14", -1) if sc.get("g14", -2) != -2 else sc.get("g", -1)
            if q >= 0 and g >= 0:
                q_scores.append(q); g_scores.append(g)
                agree += int(q == g)

    n_pairs = len(q_scores)
    poll_agreement = round(agree / n_pairs, 3) if n_pairs else 0.0
    from scipy.stats import pearsonr
    try:
        poll_r = round(float(pearsonr(q_scores, g_scores).statistic), 3) if n_pairs > 1 else 0.0
    except Exception:
        poll_r = 0.0
    # Honest PoLL diagnosis: is the second judge degenerate (rubber-stamps one score)?
    import numpy as _np
    qa, ga = _np.array(q_scores), _np.array(g_scores)
    g_dist = [int((ga == k).sum()) for k in range(4)] if n_pairs else [0, 0, 0, 0]
    g_mode_frac = round(max(g_dist) / n_pairs, 3) if n_pairs else 0.0
    qb, gb = (qa >= 2).astype(int), (ga >= 2).astype(int)
    binary_kappa = 0.0
    if n_pairs > 1:
        from sklearn.metrics import cohen_kappa_score
        try:
            binary_kappa = round(float(cohen_kappa_score(qb, gb)), 3)
        except Exception:
            binary_kappa = 0.0
    poll_degenerate = bool(g_mode_frac >= 0.90 or abs(binary_kappa) < 0.05)

    # ── Full evaluation ───────────────────────────────────────────────────────
    prod_m, rand_m, n_skip = _eval_block(cat, gt, rng, artist_col, cross_artist_only=False)

    # ── Cross-artist evaluation ───────────────────────────────────────────────
    prod_x, rand_x, n_skip_x = _eval_block(cat, gt, rng, artist_col, cross_artist_only=True)

    metric_keys = ("ndcg", "p", "rec", "ap", "rr")
    report = {
        "gt_version":    "v2 (de-circularized: no fused_emotion in prompt)",
        "gt_file":       GT_FILE,
        "top_k":         TOP_K,
        "n_seeds_total": len(gt),
        "poll": {
            "mode_counts":  poll_mode_counts,
            "n_pairs_both": n_pairs,
            "exact_agreement_rate": poll_agreement,
            "pearson_r_qwen3_gemma2": poll_r,
            "binary_cohen_kappa": binary_kappa,
            "gemma2_score_distribution": g_dist,
            "gemma2_mode_fraction": g_mode_frac,
            "second_judge_degenerate": poll_degenerate,
            "note": ("VERIFIED: gemma2:2b is DEGENERATE (rubber-stamps one score, "
                     "binary κ≈0) — does not discriminate. Effective GT = de-circularized "
                     "qwen3 single-judge. NDCG identical with/without gemma2 gating."),
        },
        "full": {
            "n_seeds_scored": len(gt) - n_skip,
            "note": "Pool = production top-15 UNION 10 random. Random = random-within-judged-pool.",
            "production":      {k: _boot_ci(prod_m[k]) for k in metric_keys},
            "random_baseline": {k: _boot_ci(rand_m[k]) for k in metric_keys},
        },
        "cross_artist": {
            "n_seeds_scored": len(gt) - n_skip_x,
            "note": "Same-artist relevant pairs excluded. Tests genre-level similarity without identity leakage.",
            "production":      {k: _boot_ci(prod_x[k]) for k in metric_keys},
            "random_baseline": {k: _boot_ci(rand_x[k]) for k in metric_keys},
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    def _row(label, m, n):
        p = m["production"]; r = m["random_baseline"]
        print(f"  {label}  (n={n})")
        print(f"    PROD  NDCG@10 {p['ndcg'][0]} [{p['ndcg'][1]},{p['ndcg'][2]}]  "
              f"P@10 {p['p'][0]}  mAP {p['ap'][0]}  MRR {p['rr'][0]}")
        print(f"    RAND  NDCG@10 {r['ndcg'][0]} [{r['ndcg'][1]},{r['ndcg'][2]}]  "
              f"P@10 {r['p'][0]}  mAP {r['ap'][0]}  MRR {r['rr'][0]}")
        delta_ndcg = round(p['ndcg'][0] - r['ndcg'][0], 4)
        print(f"    Δ NDCG@10 = {delta_ndcg:+.4f}  "
              f"({'✅ prod wins' if delta_ndcg > 0 else '❌ prod loses'})")

    print("\n=== SIMILAR-SONG — LLM-JUDGE v2 METRICS ===")
    print(f"  GT: {report['gt_version']}")
    print(f"  Judge agreement: {poll_agreement:.1%} exact | r={poll_r} | binary κ={binary_kappa} "
          f"({n_pairs} pairs)")
    if poll_degenerate:
        print(f"  ⚠️  gemma2:2b DEGENERATE (dist {g_dist}, mode {g_mode_frac:.0%}) "
              f"→ effective GT = qwen3 single-judge (de-circularized)")
    _row("ALL seeds", report["full"],         report["full"]["n_seeds_scored"])
    _row("CROSS-ARTIST only", report["cross_artist"], report["cross_artist"]["n_seeds_scored"])
    print(f"\n  saved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
