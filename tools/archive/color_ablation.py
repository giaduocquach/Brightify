"""Ablation study for recommend-by-color (thesis empirical core).

Measures each cumulative component on config-INDEPENDENT quality metrics, so every design
step is justified empirically (not just by citation):

  V31  rank-match only            (CDF off, coherence off, ICEAS-fit arousal)
  +V36 catalog-CDF target         (un-compress: colours span the catalog)
  +V37 MERT acoustic coherence    (centred MERT: a colour's songs feel alike)
  +V38 Whiteford colour↔music A   (dark/cool → slow; corrects the arousal sign)

Metrics (bootstrap 95% CI over the 12 colours, n_boot=2000):
  separation      mean pairwise dist of per-colour delivered mean (V,A)  [V36 should ↑]
  coherence       mean centred-MERT intra-list cosine                    [V37 should ↑]
  rho_light_BPM   Spearman(colour lightness, retrieved mean tempo)       [V38 should turn +]
  rho_sat_BPM     Spearman(colour saturation, retrieved mean tempo)      [V38 should turn +]
  dark_arousal    mean delivered REAL arousal for dark colours           [V38 should ↓ = slow]
  TE              targeting error in the recommender's own target space  [stays low]

Single process; toggles module flags (no re-init needed — song_va/ranks are flag-independent).
Run: python -m tools.color_ablation
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import core.recommendation_engine as RE
from core.recommendation_engine import get_recommender
from tools.color_eval_rigor import ICEAS_COLS, euclidean_te

TOP_K = 10
DARK = {'purple', 'brown', 'grey', 'black'}   # somber colours that should map slow/sad

CONFIGS = [  # (label, CDF_TARGET, ACOUSTIC_COHERENCE, WHITEFORD_AROUSAL)
    ("V31 rank-match",  False, False, False),
    ("+V36 CDF target", True,  False, False),
    ("+V37 coherence",  True,  True,  False),
    ("+V38 Whiteford A", True,  True,  True),
]


def _set_config(cdf, coh, whiteford):
    RE.COLOR_VA_CDF_TARGET = cdf
    RE.COLOR_ACOUSTIC_COHERENCE = coh
    config.COLOR_AROUSAL_WHITEFORD = whiteford
    config.COLOR_AROUSAL_ICEAS_FIT = not whiteford   # fall back to ICEAS-fit when Whiteford off


def _boot_ci(vals, fn, n_boot=2000, seed=0):
    rng = np.random.RandomState(seed)
    a = np.asarray(vals, float)
    pt = fn(a)
    boots = [fn(a[rng.randint(0, len(a), len(a))]) for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return pt, lo, hi


def main() -> int:
    rec = get_recommender()
    song_va = rec.song_va
    match_va = rec.song_va_match
    mert = getattr(rec, "mert_centered", None)
    bpm_map = json.load(open("data/clean_bpm.json")) if os.path.exists("data/clean_bpm.json") else {}
    tids = rec.df["track_id"].astype(str).values

    def coherence(idx):
        if mert is None or len(idx) < 2: return np.nan
        E = mert[np.array(idx, int)]; S = E @ E.T
        return float(S[np.triu_indices(len(idx), 1)].mean())

    rows = []
    for label, cdf, coh, wf in CONFIGS:
        _set_config(cdf, coh, wf)
        per = []   # (lightness, saturation, gotV, gotA, coherence, BPM, TE)
        for hx, name in ICEAS_COLS:
            h, l, s = rec.color_mapper.hex_to_hsl(hx)
            cv, ca = rec.color_mapper.hsl_to_va(hx)
            tgt = rec._color_target_quantile([cv, ca]) if cdf else np.array([cv, ca])
            df = rec.recommend_by_colors(hx, top_k=TOP_K)
            idx = df["original_index"].tolist() if df is not None and not df.empty else []
            if len(idx) < 2: continue
            g = song_va[np.array(idx, int)].mean(0)
            bpms = [bpm_map.get(tids[i]) for i in idx if bpm_map.get(tids[i])]
            per.append(dict(name=name, l=l/100, s=s/100, gv=g[0], ga=g[1],
                            coh=coherence(idx), bpm=(np.mean(bpms) if bpms else np.nan),
                            te=euclidean_te(idx, match_va, np.array(tgt))))
        # aggregate metrics
        pts = np.array([[p['gv'], p['ga']] for p in per])
        d = pts[:, None, :] - pts[None, :, :]
        sep = float(np.sqrt((d**2).sum(-1))[np.triu_indices(len(pts), 1)].mean())
        cohs = np.array([p['coh'] for p in per]); coh_m = float(np.nanmean(cohs))
        ls = np.array([p['l'] for p in per]); ss_ = np.array([p['s'] for p in per])
        bp = np.array([p['bpm'] for p in per]); m = ~np.isnan(bp)
        rho_l = spearmanr(ls[m], bp[m]).correlation
        rho_s = spearmanr(ss_[m], bp[m]).correlation
        dark_a = float(np.mean([p['ga'] for p in per if p['name'] in DARK]))
        dark_bpm = float(np.nanmean([p['bpm'] for p in per if p['name'] in DARK]))
        te_pt, te_lo, te_hi = _boot_ci([p['te'] for p in per], np.mean)
        rows.append((label, sep, coh_m, rho_l, rho_s, dark_a, dark_bpm, te_pt, te_lo, te_hi))

    print("\n================= ABLATION: recommend-by-color (top_k=%d, n=12 colours) =================" % TOP_K)
    print(f"{'config':18}{'separ':>7}{'coher':>7}{'ρ(L,BPM)':>10}{'ρ(S,BPM)':>10}{'darkA':>7}{'darkBPM':>8}{'TE':>8}")
    print("-"*76)
    for (label, sep, coh_m, rho_l, rho_s, dark_a, dark_bpm, te, lo, hi) in rows:
        print(f"{label:18}{sep:7.3f}{coh_m:7.3f}{rho_l:+10.3f}{rho_s:+10.3f}{dark_a:7.2f}{dark_bpm:8.0f}{te:8.4f}")
    print("-"*76)
    print("Expected story: +V36 ↑separation; +V37 ↑coherence; +V38 ρ(L/S,BPM) turn POSITIVE & darkA/darkBPM ↓ (slow).")
    print("(TE shown with its own target space per config; full bootstrap CI in color_eval_rigor.)")
    # save
    out = {r[0]: dict(separation=round(r[1],4), coherence=round(r[2],4),
                      rho_light_bpm=round(float(r[3]),4), rho_sat_bpm=round(float(r[4]),4),
                      dark_arousal=round(r[5],4), dark_bpm=round(r[6],1),
                      te=round(r[7],4), te_ci=[round(r[8],4), round(r[9],4)]) for r in rows}
    json.dump(out, open("data/color_ablation.json", "w"), ensure_ascii=False, indent=2)
    print("→ data/color_ablation.json")
    # restore shipped config
    _set_config(True, True, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
