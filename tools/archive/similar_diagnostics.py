"""Comprehensive diagnostics for similar-song re-evaluation.

Answers questions raised by the E-EMO-CLEAN ablation:
  Q1. Is song_emotion_vec (album-art colour) a covert ARTIST/ALBUM-identity signal?
      → corr(emotion_vec_sim, same_artist) and (emotion_vec_sim, same_album).
  Q2. Does dropping emotion change artist diversity / Gini? (if it raises diversity,
      the signal was partly an identity crutch).
  Q3. LLM-judge robustness: per-seed win rate of production vs random-in-pool.
  Q4. calm↔angry discriminant failure: catalog composition + V-A overlap.
  Q5. What does each active signal contribute pairwise (redundancy check)?

Usage: python -m tools.similar_diagnostics
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/similar_diagnostics.json"


def main() -> int:
    import config as cfg
    from tools.backtest_v2.catalog import Catalog

    cat = Catalog.load()
    df = cat.df
    rec = cat.rec
    n = cat.n
    report: dict = {}

    rng = np.random.default_rng(42)
    sample = rng.choice(n, size=min(400, n), replace=False)

    # Artist / album arrays
    artist = df["primary_artist"].fillna("").values if "primary_artist" in df.columns else None
    album = df["album_name"].fillna("").values if "album_name" in df.columns else None
    emo = rec.song_emotion_vec  # (n,13) album-art colour emotion
    emo_norm = emo / (np.linalg.norm(emo, axis=1, keepdims=True) + 1e-9)
    mert = rec.mert_matrix       # (n,768) normalized
    lyr = rec.embeddings_normalized

    # ---- Q1: emotion_vec_sim vs same-artist / same-album ----
    same_art_sims, diff_art_sims = [], []
    same_alb_sims, diff_alb_sims = [], []
    mert_same_art, mert_diff_art = [], []
    for i in sample:
        js = rng.choice(n, size=60, replace=False)
        for j in js:
            if i == j:
                continue
            e_sim = float(emo_norm[i] @ emo_norm[j])
            m_sim = float(mert[i] @ mert[j]) if mert is not None else 0.0
            if artist is not None and artist[i] and artist[j]:
                if artist[i] == artist[j]:
                    same_art_sims.append(e_sim); mert_same_art.append(m_sim)
                else:
                    diff_art_sims.append(e_sim); mert_diff_art.append(m_sim)
            if album is not None and album[i] and album[j]:
                (same_alb_sims if album[i] == album[j] else diff_alb_sims).append(e_sim)

    def _summ(a, b, label):
        a, b = np.array(a), np.array(b)
        # Cohen's d
        na, nb = len(a), len(b)
        sp = np.sqrt(((na-1)*a.var(ddof=1)+(nb-1)*b.var(ddof=1))/(na+nb-2)) if na>1 and nb>1 else 0
        d = float((a.mean()-b.mean())/sp) if sp>0 else 0.0
        return {f"{label}_same_mean": round(float(a.mean()),4),
                f"{label}_diff_mean": round(float(b.mean()),4),
                f"{label}_cohens_d": round(d,3),
                f"{label}_n_same": na, f"{label}_n_diff": nb}

    report["Q1_emotion_identity"] = {
        "hypothesis": "If emotion_vec_sim is much higher for same-artist/album pairs, "
                      "it is acting as a covert identity signal (KG-artist-bias risk).",
        **_summ(same_art_sims, diff_art_sims, "emo_artist"),
        **_summ(same_alb_sims, diff_alb_sims, "emo_album"),
        # MERT reference: how much does a LEGIT audio signal separate same-artist?
        **_summ(mert_same_art, mert_diff_art, "mert_artist"),
    }

    # ---- Q3: LLM-judge per-seed win rate ----
    try:
        from tools.backtest_v2.ground_truth.similar_llm_gt import load_similar_llm_gt
        from tools.backtest_v2.metrics.accuracy import ndcg_at_k, precision_at_k
        llm_gt = load_similar_llm_gt()
        wins, ties, losses = 0, 0, 0
        prod_p, rand_p = [], []
        for seed_str, entry in llm_gt.items():
            R = set(entry.get("relevant", []))
            judged = entry.get("judged", {})
            pool = [int(k) for k, v in judged.items() if v >= 0]
            if len(R) < 1 or len(pool) < 2:
                continue
            recs = cat.recommend_by_song(int(seed_str), top_k=10)
            randr = rng.choice(pool, size=min(10, len(pool)), replace=False).tolist()
            pp = precision_at_k(recs, R, 10); rp = precision_at_k(randr, R, 10)
            prod_p.append(pp); rand_p.append(rp)
            if pp > rp: wins += 1
            elif pp == rp: ties += 1
            else: losses += 1
        report["Q3_llm_robustness"] = {
            "n_seeds": wins+ties+losses,
            "prod_beats_random_pool": wins, "ties": ties, "prod_loses": losses,
            "win_rate": round(wins/max(wins+ties+losses,1),3),
            "mean_prod_p10": round(float(np.mean(prod_p)),4),
            "mean_rand_p10": round(float(np.mean(rand_p)),4),
            "note": "random-in-pool is a STRONG baseline (pool is half production items)",
        }
    except Exception as e:
        report["Q3_llm_robustness"] = {"error": str(e)}

    # ---- Q4: calm vs angry composition ----
    if "fused_emotion" in df.columns:
        vc = df["fused_emotion"].value_counts().to_dict()
        # V-A centroids per emotion
        va = rec.song_va
        cents = {}
        for emo_label in ("calm", "angry", "happy", "sad"):
            mask = (df["fused_emotion"].values == emo_label)
            if mask.sum() > 0:
                cents[emo_label] = [round(float(va[mask,0].mean()),3),
                                    round(float(va[mask,1].mean()),3), int(mask.sum())]
        report["Q4_calm_angry"] = {
            "counts": {k: int(v) for k, v in vc.items()},
            "va_centroids_[V,A,n]": cents,
            "note": "If calm & angry V-A centroids are close, the catalog itself blurs them.",
        }

    # ---- Q5: pairwise signal redundancy (corr of per-song sim vectors) ----
    seed_idxs = rng.choice(n, size=30, replace=False)
    sig_corr = {}
    pairs_acc = {"lyr_mert": [], "lyr_va": [], "mert_va": [], "emo_va": [], "emo_mert": []}
    va = rec.song_va
    for s in seed_idxs:
        l = lyr @ lyr[s]
        m = mert @ mert[s] if mert is not None else np.zeros(n)
        vdist = np.sqrt(((va - va[s])**2).sum(1)); v = np.exp(-(vdist**2)/(2*0.2**2))
        e = emo_norm @ emo_norm[s]
        def c(x, y):
            return float(np.corrcoef(x, y)[0,1])
        pairs_acc["lyr_mert"].append(c(l, m))
        pairs_acc["lyr_va"].append(c(l, v))
        pairs_acc["mert_va"].append(c(m, v))
        pairs_acc["emo_va"].append(c(e, v))
        pairs_acc["emo_mert"].append(c(e, m))
    for k, vlist in pairs_acc.items():
        sig_corr[k] = round(float(np.mean(vlist)), 3)
    report["Q5_signal_redundancy"] = {
        "mean_pairwise_corr": sig_corr,
        "note": "High corr => redundant signal. emo_va high would mean emotion double-counts V-A.",
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, ensure_ascii=False)

    # Print
    print("\n" + "="*68)
    print("  SIMILAR-SONG DIAGNOSTICS")
    print("="*68)
    q1 = report["Q1_emotion_identity"]
    print(f"\nQ1 — Is emotion_vec a covert identity signal?")
    print(f"  emotion_sim same-artist {q1['emo_artist_same_mean']} vs diff {q1['emo_artist_diff_mean']}  (d={q1['emo_artist_cohens_d']})")
    print(f"  emotion_sim same-album  {q1['emo_album_same_mean']} vs diff {q1['emo_album_diff_mean']}  (d={q1['emo_album_cohens_d']})")
    print(f"  [ref] MERT  same-artist {q1['mert_artist_same_mean']} vs diff {q1['mert_artist_diff_mean']}  (d={q1['mert_artist_cohens_d']})")
    if "Q3_llm_robustness" in report and "win_rate" in report["Q3_llm_robustness"]:
        q3 = report["Q3_llm_robustness"]
        print(f"\nQ3 — LLM-judge per-seed: prod beats random-pool {q3['prod_beats_random_pool']}/{q3['n_seeds']} "
              f"(win_rate {q3['win_rate']}), ties {q3['ties']}, losses {q3['prod_loses']}")
    if "Q4_calm_angry" in report:
        print(f"\nQ4 — calm/angry V-A centroids [V,A,n]: {report['Q4_calm_angry']['va_centroids_[V,A,n]']}")
    print(f"\nQ5 — signal redundancy (pairwise corr): {report['Q5_signal_redundancy']['mean_pairwise_corr']}")
    print(f"\n  saved → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
