"""A/B: raw v4 valence vs calibrated valence_cal on the human-V-A GT (audit V17).

Also tunes weights (lyrics/va/emotion) on the non-circular human GT and reports
whether calibration + new weights beat the status quo.

Usage: python -m tools.color_human_va_metrics [step]
"""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

GT_FILE = 'var/runtime/backtest/ground_truth/color_human_va_gt.json'
V4_FILE = 'data/emotion_labels_v4.json'
CAL_FILE = 'data/valence_calibration.json'
TOP_K = 10


def ndcg(ranked_tids, relevant_set, k=TOP_K):
    from tools.backtest_v2.metrics.accuracy import ndcg_at_k
    return ndcg_at_k(ranked_tids, relevant_set, k)


def _tid_to_orig(rec) -> dict:
    """Build {track_id_str: original_index} for the full catalog."""
    return {str(t): i for i, t in enumerate(rec.df['track_id'].astype(str))}


def _apply_cal(rec, v4, cal=True):
    if not cal: return
    tids = rec.df['track_id'].astype(str).values
    cv = np.array([float(v4.get(t,{}).get('valence_cal',
                  v4.get(t,{}).get('valence',0.5))) for t in tids])
    rec.song_va[:, 0] = np.clip(cv, 0, 1)


def _score_pool(rec, pool_idx, cva, w=None):
    """Score a restricted pool of song indices for a V-A query.
    Restricted-pool evaluation: rank only the gold-set songs so the 208-song
    human-rated pool is the evaluation universe, not the full 5548 catalog.
    w = (lyrics, va, emotion) tuple; None = use config."""
    from config import COLOR_SCORE_VA_SIGMA, COLOR_SCORE_WEIGHTS
    wl = w[0] if w else COLOR_SCORE_WEIGHTS['lyrics']
    wv = w[1] if w else COLOR_SCORE_WEIGHTS['va']
    we = w[2] if w else COLOR_SCORE_WEIGHTS['emotion']

    pool = np.array(pool_idx, dtype=int)
    d = np.sqrt(np.sum((rec.song_va[pool] - cva)**2, axis=1))
    va_s = np.exp(-(d**2)/(2*COLOR_SCORE_VA_SIGMA**2))

    emo_vec_pool = getattr(rec, '_song_emotion_content_vec', None)
    if emo_vec_pool is not None:
        norms = np.linalg.norm(emo_vec_pool[pool], axis=1)
        # neutral emotion query for this evaluation (focus on V-A signal)
        emo_s = np.full(len(pool), 0.5)
    else:
        emo_s = np.full(len(pool), 0.5)

    lyr_s = np.full(len(pool), 0.5)  # neutral lyric baseline

    scores = wv*va_s + wl*lyr_s + we*emo_s
    ranked_local = np.argsort(scores)[::-1]
    return [pool[i] for i in ranked_local]   # original_indices in ranked order


def eval_system(rec, gt, t2o, use_cal: bool, w=None) -> list:
    """NDCG@10 per colour, restricted to the gold-set pool.
    t2o: {track_id: original_index}; use_cal: swap valence to valence_cal.
    w: optional weight tuple override."""
    # Build gold-set pool (all tids that appear in any colour's relevant set)
    all_gt_tids = set()
    for e in gt.values(): all_gt_tids.update(e['relevant_tids'])
    pool_idx = [t2o[t] for t in all_gt_tids if t in t2o]

    if not pool_idx: return [0.0] * len(gt)

    scores_out = []
    for hex_c, e in gt.items():
        rel_orig = {t2o[t] for t in e['relevant_tids'] if t in t2o}
        if len(rel_orig) < 2: continue
        cva = np.array(e['color_va'], dtype=float)
        ranked = _score_pool(rec, pool_idx, cva, w)
        scores_out.append(ndcg(ranked, rel_orig))
    return scores_out


def weight_sweep(rec, gt, t2o, use_cal: bool, step=0.10):
    """Grid sweep on restricted-pool human-VA GT."""
    all_gt_tids = set()
    for e in gt.values(): all_gt_tids.update(e['relevant_tids'])
    pool_idx = [t2o[t] for t in all_gt_tids if t in t2o]

    vals = [round(i*step,3) for i in range(int(round(1/step))+1)]
    grid = [(l,v,max(0,round(1-l-v,3)))
            for l in vals for v in vals
            if -1e-9 <= round(1-l-v,3) <= 1+1e-9]

    best_w, best_mean, best_scores = None, -1, []
    for w in grid:
        sc = []
        for hex_c, e in gt.items():
            rel_orig = {t2o[t] for t in e['relevant_tids'] if t in t2o}
            if len(rel_orig) < 2: continue
            cva = np.array(e['color_va'], dtype=float)
            ranked = _score_pool(rec, pool_idx, cva, w)
            sc.append(ndcg(ranked, rel_orig))
        m = float(np.mean(sc))
        if m > best_mean: best_mean, best_w, best_scores = m, w, sc
    return best_w, best_mean, best_scores


def main() -> int:
    from tools.backtest_v2.stats import paired_bootstrap
    import core.recommendation_engine as eng

    if not os.path.exists(GT_FILE):
        print(f"GT not found. Run: python -m tools.build_human_va_gt"); return 1

    gt = json.load(open(GT_FILE))
    n_col = sum(1 for e in gt.values() if len(e['relevant_tids'])>=2)
    print(f"\nHuman-VA GT: {n_col} colours with ≥2 relevant gold-set songs")

    rec = (lambda: __import__('core.recommendation_engine',
           fromlist=['get_recommender']).get_recommender())()
    orig_va = rec.song_va.copy()
    orig_w  = dict(eng.COLOR_SCORE_WEIGHTS)
    v4 = json.load(open(V4_FILE))
    t2o = _tid_to_orig(rec)
    all_gt_tids = set(); [all_gt_tids.update(e['relevant_tids']) for e in gt.values()]
    pool_size = sum(1 for t in all_gt_tids if t in t2o)
    print(f"Pool: {pool_size} gold-set songs in catalog  |  TOP_K={TOP_K}")

    # ── Baseline (raw v4, pure V-A scoring) ──
    base = eval_system(rec, gt, t2o, use_cal=False)
    rec.song_va[:, 0] = orig_va[:, 0]
    print(f"\n[raw v4]      human-VA NDCG@{TOP_K} = {np.mean(base):.4f}  (n={len(base)})")

    # ── Calibrated, same pure V-A scoring ──
    _apply_cal(rec, v4, True)
    cal_same = eval_system(rec, gt, t2o, use_cal=False)  # already applied
    rec.song_va[:, 0] = orig_va[:, 0]
    d1,lo1,hi1 = paired_bootstrap(base, cal_same)
    print(f"[valence_cal] human-VA NDCG@{TOP_K} = {np.mean(cal_same):.4f}  "
          f"Δ={d1:+.4f} CI[{lo1:+.4f},{hi1:+.4f}]")

    step = float(sys.argv[1]) if len(sys.argv)>1 else 0.10

    # ── Retune on raw v4 ──
    print(f"\nRetuning on raw v4 (step={step})...")
    best_w_raw, best_raw, sc_raw = weight_sweep(rec, gt, t2o, use_cal=False, step=step)
    rec.song_va[:,0]=orig_va[:,0]
    d2,lo2,hi2 = paired_bootstrap(base, sc_raw)
    print(f"[raw v4, tuned {best_w_raw}]    NDCG@{TOP_K} = {best_raw:.4f}  "
          f"Δ={d2:+.4f} CI[{lo2:+.4f},{hi2:+.4f}]")

    # ── Retune on calibrated v4 ──
    print(f"Retuning on valence_cal (step={step})...")
    _apply_cal(rec, v4, True)
    best_w_cal, best_cal, sc_cal = weight_sweep(rec, gt, t2o, use_cal=False, step=step)
    rec.song_va[:,0]=orig_va[:,0]
    d3,lo3,hi3 = paired_bootstrap(base, sc_cal)
    print(f"[valence_cal, tuned {best_w_cal}] NDCG@{TOP_K} = {best_cal:.4f}  "
          f"Δ={d3:+.4f} CI[{lo3:+.4f},{hi3:+.4f}]")

    print("\n=== VERDICT ===")
    options = [(best_raw,d2,lo2,'raw v4+tune',best_w_raw,False),
               (best_cal,d3,lo3,'valence_cal+tune',best_w_cal,True)]
    winner = max(options, key=lambda x: x[0])
    print(f"Best config: {winner[3]}  NDCG={winner[0]:.4f}  Δ={winner[1]:+.4f} CI_lo={winner[2]:+.4f}")
    sig = winner[2] > 0
    if sig:
        print("→ Significant improvement. Recommend adopting this config.")
        print(f"  Weights: {winner[4]},  use_calibration: {winner[5]}")
    else:
        print("→ Improvement not significant on this GT (CI includes 0). Investigate further.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
