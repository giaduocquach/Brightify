"""Per-colour audit — does each of the 12 colours retrieve a DISTINCT, characteristic
mood region? (V36 matching-space fix validation.)

For each colour: raw V-A → catalog-CDF target quantile → top-K recommendations → mean
REAL song (V,A) actually delivered + a mood label. Then check:
  - TARGETING: Spearman(target-A, retrieved mean-A) and (target-V, mean-V) ≥ 0.8 —
    energetic colours really retrieve higher-arousal songs, calm colours lower.
  - SEPARATION: std of per-colour retrieved mean V/A is high + mean pairwise mood-distance
    ≫ 0 — colours feel different (not just different track-IDs in the same mood).
This is the symptom test: "every colour feels mid/sad" ⇒ low separation + flat ordering.

Run: python -m tools.color_per_color_audit
"""
from __future__ import annotations
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.color_eval_rigor import ICEAS_COLS

TOP_K = 30


def _mood_label(v: float, a: float) -> str:
    """Russell quadrant + intensity, for human eyeballing."""
    quad = (("vui-sôi động (Q1)" if a >= 0.5 else "thư thái (Q4)") if v >= 0.5
            else ("căng-mạnh (Q2)" if a >= 0.5 else "buồn-trầm (Q3)"))
    return quad


def main() -> int:
    import config
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    song_va = rec.song_va                       # REAL per-song mood (what the user hears)
    has_cdf = (getattr(config, "COLOR_VA_RANK_MATCH", False)
               and getattr(config, "COLOR_VA_CDF_TARGET", False)
               and getattr(rec, "_va_sorted_v", None) is not None)

    # centred MERT — raw cosines saturate ~0.9 (anisotropy); centring discriminates
    # (random≈0.0 vs near-neighbour≈0.45). This is the meaningful "feel alike" signal.
    mert = getattr(rec, "mert_centered", None)
    if mert is None:
        mert = getattr(rec, "mert_matrix", None)

    def _coherence(idx):
        """Mean pairwise centred-MERT cosine within a result set = 'feel alike' (V37)."""
        if mert is None or len(idx) < 2:
            return float("nan")
        E = mert[np.array(idx, int)]
        S = E @ E.T
        iu = np.triu_indices(len(idx), 1)
        return float(S[iu].mean())

    # V39: per-song dominant mood tag (existing MTG-Jamendo-style `mood_tags`) for a SEMANTIC
    # coherence angle (do a colour's songs share a mood label?) + interpretability. Caveat: tags
    # are auto-tagged (Essentia/Jamendo taxonomy), used as a secondary signal only.
    import json as _json
    from collections import Counter
    top_tag = [None] * rec.n_songs
    if 'mood_tags' in rec.df.columns:
        for i, raw in enumerate(rec.df['mood_tags'].values):
            try:
                d = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                if d:
                    top_tag[i] = max(d, key=d.get)
            except Exception:
                pass

    def _tag_coherence(idx):
        """(dominant mood tag, fraction of the set sharing it) — semantic 'feel alike' (V39)."""
        tags = [top_tag[i] for i in idx if top_tag[i]]
        if not tags:
            return ("—", float("nan"))
        c = Counter(tags); dom, n = c.most_common(1)[0]
        return (dom, n / len(tags))

    rows = []
    cohs = []
    tagcohs = []
    print(f"\nPER-COLOUR AUDIT  top_k={TOP_K}  (retrieved mean = REAL song V-A delivered)\n")
    hdr = (f"{'colour':10} {'rawV':>5} {'rawA':>5} | {'tgtV':>5} {'tgtA':>5} | "
           f"{'gotV':>5} {'gotA':>5} | {'coh':>5} | {'tag(frac)':>16} | mood")
    print(hdr); print("-" * len(hdr))
    for hx, name in ICEAS_COLS:
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        tgt = rec._color_target_quantile([cv, ca]) if has_cdf else np.array([cv, ca])
        df = rec.recommend_by_colors(hx, top_k=TOP_K)
        idx = (df["original_index"].tolist()
               if df is not None and not df.empty and "original_index" in df.columns else [])
        if not idx:
            print(f"{name:10}  (no results)"); continue
        got = song_va[np.array(idx, int)].mean(axis=0)
        coh = _coherence(idx)
        cohs.append(coh)
        dom_tag, tag_frac = _tag_coherence(idx)
        if not np.isnan(tag_frac):
            tagcohs.append(tag_frac)
        rows.append((name, cv, ca, tgt[0], tgt[1], got[0], got[1]))
        print(f"{name:10} {cv:5.2f} {ca:5.2f} | {tgt[0]:5.2f} {tgt[1]:5.2f} | "
              f"{got[0]:5.2f} {got[1]:5.2f} | {coh:5.2f} | {dom_tag[:11]:>11}({tag_frac:.2f}) | "
              f"{_mood_label(got[0], got[1])}")

    R = np.array([r[1:] for r in rows], float)  # cols: rawV rawA tgtV tgtA gotV gotA
    tgtV, tgtA, gotV, gotA = R[:, 2], R[:, 3], R[:, 4], R[:, 5]

    rho_v = spearmanr(tgtV, gotV).correlation
    rho_a = spearmanr(tgtA, gotA).correlation
    sep_v, sep_a = float(gotV.std()), float(gotA.std())
    pts = np.column_stack([gotV, gotA])
    d = pts[:, None, :] - pts[None, :, :]
    pair = np.sqrt((d ** 2).sum(-1))
    mean_pair = float(pair[np.triu_indices(len(pts), 1)].mean())

    mean_coh = float(np.nanmean(cohs)) if cohs else float("nan")
    mean_tagcoh = float(np.nanmean(tagcohs)) if tagcohs else float("nan")
    print("\n=== GATES ===")
    print(f"  TARGETING  rho(tgtV,gotV)={rho_v:+.3f}  rho(tgtA,gotA)={rho_a:+.3f}   (want >= +0.80)")
    print(f"  SEPARATION std(gotV)={sep_v:.3f}  std(gotA)={sep_a:.3f}   mean-pairwise-dist={mean_pair:.3f}")
    print(f"  TAG-COHERENCE mean dominant-mood-tag share = {mean_tagcoh:.2f}  "
          f"(semantic 'feel alike'; existing mood_tags, secondary signal)")
    print(f"  COHERENCE  mean MERT intra-list cosine = {mean_coh:.3f}   (higher = songs feel alike; V37 target)")
    print(f"  acoustic-coherence active: {getattr(config, 'COLOR_ACOUSTIC_COHERENCE', False)}"
          f"  (alpha={getattr(config, 'COLOR_COHERENCE_ALPHA', None)})  |  CDF target: {bool(has_cdf)}")
    ok = rho_v >= 0.8 and rho_a >= 0.8 and mean_pair >= 0.05
    print(f"\n  RESULT: {'PASS' if ok else 'REVIEW'} — colours "
          f"{'span distinct mood regions' if ok else 'still clustered / mis-ordered'}")
    # Catalog-supply note (not a matcher bug)
    lowA = float((song_va[:, 1] < 0.4).mean()); hiA = float((song_va[:, 1] >= 0.6).mean())
    print(f"\n  [supply note] catalog arousal: {lowA*100:.0f}% low(<0.4)  {hiA*100:.0f}% high(>=0.6) "
          f"— energetic colours pull from the thinner high-arousal pool.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
