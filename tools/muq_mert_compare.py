"""Workstream B — verify MERT vs MuQ as the audio backbone for similar-song + colour-coherence.

MuQ beat MERT on DEAM nested-CV (arousal 0.66/valence 0.55 vs 0.56/0.49) and is used for the
small valence-audio signal. This checks whether MIGRATING the similar-song backbone and the
colour acoustic-coherence space from MERT→MuQ is justified by the END metrics, or whether MERT
(the validated incumbent) stays. Gated: adopt MuQ only if it beats/ties MERT.

  B1 similar-song: mood-coherence of top-K under MERT- vs MuQ-audio cosine ranking.
  B2 colour-coherence: colour-TE + intra-list coherence under MERT-centered vs MuQ-centered.

Run: python -m tools.muq_mert_compare
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.color_eval_rigor import ICEAS_COLS, euclidean_te


def _aligned_muq(rec):
    M = np.load("data/muq_embeddings.npy")
    meta = json.load(open("data/muq_metadata.json"))
    order = meta.get("done_track_ids") or meta.get("track_ids")
    tids = rec.df["track_id"].astype(str).tolist()
    if order and len(order) == len(M):
        idx = {str(t): i for i, t in enumerate(order)}
        M = np.array([M[idx[t]] if t in idx else np.full(M.shape[1], np.nan) for t in tids])
    n = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    c = M - np.nanmean(M, axis=0, keepdims=True)
    c = c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-9)
    return n.astype(np.float32), c.astype(np.float32)


def main() -> int:
    from core.recommendation_engine import get_recommender
    import core.recommendation_engine as RE
    rec = get_recommender()
    song_va = rec.song_va
    mert_n, mert_c = rec.mert_matrix, rec.mert_centered
    muq_n, muq_c = _aligned_muq(rec)
    rng = np.random.RandomState(0)

    def mood_coh(idx):
        p = song_va[np.array(idx)]; d = p[:, None, :] - p[None, :, :]
        dist = np.sqrt((d ** 2).sum(-1))[np.triu_indices(len(idx), 1)].mean()
        return 1.0 - dist / np.sqrt(2)

    # ── B1: similar-song — mood-coherence of top-12 by audio cosine ──
    seeds = rng.choice(rec.n_songs, 60, replace=False)
    print("=== B1 similar-song: top-12 by audio cosine, mood-coherence (higher=better) ===")
    for tag, A in [("MERT", mert_n), ("MuQ", muq_n)]:
        cohs = []
        for s in seeds:
            sim = A @ A[s]; top = np.argsort(sim)[::-1][1:13]
            cohs.append(mood_coh(top))
        print(f"  {tag:5} mood-coherence = {np.mean(cohs):.4f}")

    # ── B2: colour-coherence — colour-TE + intra-list coherence, MERT- vs MuQ-centered ──
    match_va = rec.song_va_match
    print("\n=== B2 colour: TE (rank space, lower=better) + intra-list coherence under each centered backbone ===")
    for tag, C in [("MERT-centered", mert_c), ("MuQ-centered", muq_c)]:
        rec.mert_centered = C          # swap the coherence space
        tes, cohs = [], []
        for hx, _ in ICEAS_COLS:
            cv, ca = rec.color_mapper.hsl_to_va(hx); tgt = rec._color_target_quantile([cv, ca])
            df = rec.recommend_by_colors(hx, top_k=12)
            idx = df["original_index"].tolist() if df is not None and not df.empty else []
            if len(idx) < 2: continue
            tes.append(euclidean_te(idx, match_va, np.array(tgt)))
            E = C[np.array(idx)]; cohs.append(float((E @ E.T)[np.triu_indices(len(idx), 1)].mean()))
        print(f"  {tag:14} TE={np.mean(tes):.4f}  intra-list coherence={np.nanmean(cohs):.3f}")
    rec.mert_centered = mert_c          # restore
    print("\n  (intra-list coherence is in each backbone's own space — not directly comparable;")
    print("   TE is the comparable end metric. Adopt MuQ only if TE ≤ MERT.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
