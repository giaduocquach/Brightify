"""Build emotion_labels_v6d.json — v6c blend RE-TUNED against the GPT V-A reference.

Phase 3 (V32). The served label pipeline stays 100% non-LLM (VN-lexicon + MERT +
NRC-VAD). We only use the offline GPT reference (data/va_reference_gpt.json) as the
OPTIMIZATION TARGET to pick the blend weights, then FREEZE them. Serving never calls
an LLM. This replaces v6c's heuristic weights (valence w_lyr=1.0; arousal = v6a's
fixed 0.80 MERT / 0.20 NRC) with weights chosen by 5-fold CV agreement to GPT.

Tuned blends (rank space):
  valence = w_lyr·rank(VN-lex) + (1-w_lyr)·rank(MERT-V)   [tuned to GPT-valence]
  arousal = INHERIT v6a (MERT-acoustic)                   [default; see below]
Selection: 5-fold CV, maximise mean held-out Spearman vs GPT. Reuses v6c calibration.

AROUSAL POLICY (important): GPT judges V-A from LYRICS ONLY — it cannot hear the
music. That makes GPT a strong reference for VALENCE (lyrically carried) but a weak
one for AROUSAL (the reliable arousal signal is acoustic, r≈.81 from audio; Eerola
2026). So by default we INHERIT v6a's MERT-acoustic arousal and DO NOT pull arousal
toward GPT-lyrical-arousal. --tune-arousal opts into the (recorded, non-default)
GPT-tuned arousal, which empirically also imports GPT's intrinsic V-A correlation.

Gate (run after): held-out GPT-agreement(v6d) > v6c AND color TE(v6d) ≤ v6c.

Run: python -m tools.build_v6d_labels
"""
import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from tools.build_v6c_labels import _rank_norm, _calibrate, _vn_lexicon_valence

V6A_PATH = "data/emotion_labels_v6a.json"
MERT_V_PATH = "data/mert_valence.json"
MERT_A_PATH = "data/mert_arousal.json"
GPT_REF = "data/va_reference_gpt.json"
OUT_DEFAULT = "data/emotion_labels_v6d.json"
GRID = np.round(np.arange(0.0, 1.0001, 0.1), 2)


def _cv_best_weight(sig_a, sig_b, target, n_folds=5, seed=42):
    """Grid-search w for w·rank(a)+(1-w)·rank(b) maximising mean held-out Spearman vs target.
    sig_a, sig_b, target are arrays over the SAME songs (no NaN)."""
    n = len(target)
    rng = np.random.default_rng(seed)
    folds = np.array_split(rng.permutation(n), n_folds)
    ra, rb = (rankdata(sig_a) - 1) / (n - 1), (rankdata(sig_b) - 1) / (n - 1)
    results = {}
    for w in GRID:
        blend = w * ra + (1 - w) * rb
        cv = []
        for f in folds:
            if len(f) < 3:
                continue
            cv.append(spearmanr(blend[f], target[f]).correlation)
        results[float(w)] = float(np.nanmean(cv))
    best_w = max(results, key=results.get)
    return best_w, results


def build(out_path: str = OUT_DEFAULT, tune_arousal: bool = False) -> None:
    for p in (V6A_PATH, MERT_V_PATH, MERT_A_PATH, GPT_REF):
        if not os.path.exists(p):
            print(f"[ERROR] missing {p}"); sys.exit(1)

    v6a = json.load(open(V6A_PATH))
    mert_v = json.load(open(MERT_V_PATH))
    mert_a = json.load(open(MERT_A_PATH))
    gpt = json.load(open(GPT_REF))
    tids = list(v6a.keys())

    # lyrics lookup (copy v6c pattern)
    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"] if c in df.columns)
    lyrics_lookup = {str(r[idc]): str(r[lyc]) for _, r in df[[idc, lyc]].iterrows()
                     if isinstance(r[lyc], str) and r[lyc].strip()}

    from tools.nrc_vad_score import load_nrc_vad, score_lyrics
    nrc = load_nrc_vad()

    # ---- signals ----
    vn_val, has_lyr = _vn_lexicon_valence(tids, lyrics_lookup)
    mv = np.array([float(mert_v.get(t, np.nan)) for t in tids])
    ma = np.array([float(mert_a.get(t, np.nan)) for t in tids])
    na = np.array([score_lyrics(lyrics_lookup.get(t, ""), nrc, "arousal") for t in tids])
    gv = np.array([gpt.get(t, {}).get("valence", np.nan) if isinstance(gpt.get(t), dict) else np.nan for t in tids])
    ga = np.array([gpt.get(t, {}).get("arousal", np.nan) if isinstance(gpt.get(t), dict) else np.nan for t in tids])

    # ---- tune valence: VN-lex vs MERT-V, target GPT-V ----
    mV = has_lyr & ~np.isnan(mv) & ~np.isnan(gv)
    wv, gridv = _cv_best_weight(vn_val[mV], mv[mV], gv[mV])
    print(f"[v6d tune] valence w_lyr*={wv} (1-w=MERT)  CV-ρ={gridv[wv]:.4f}")
    if tune_arousal:
        mA = ~np.isnan(ma) & ~np.isnan(na) & ~np.isnan(ga)
        wa, grida = _cv_best_weight(ma[mA], na[mA], ga[mA])
        print(f"[v6d tune] arousal w_mert*={wa} (1-w=NRC)  CV-ρ={grida[wa]:.4f}  (GPT-tuned, NON-default)")
    else:
        wa = None
        print("[v6d] arousal = INHERIT v6a MERT-acoustic (GPT is lyrics-only → weak arousal ref)")

    # ---- build valence with chosen weight (rank space, fallbacks like v6c) ----
    vn_rank = _rank_norm(vn_val, has_lyr)
    mvr = _rank_norm(mv, ~np.isnan(mv))
    blended_v = np.full(len(tids), np.nan)
    both = has_lyr & ~np.isnan(mv)
    blended_v[both] = wv * vn_rank[both] + (1 - wv) * mvr[both]
    blended_v[has_lyr & np.isnan(mv)] = vn_rank[has_lyr & np.isnan(mv)]
    om = ~has_lyr & ~np.isnan(mv)
    blended_v[om] = mvr[om]
    blended_v[np.isnan(blended_v)] = 0.5
    valence = _calibrate((rankdata(blended_v) - 1) / (len(blended_v) - 1))

    # ---- arousal ----
    if tune_arousal:
        mar = _rank_norm(ma, ~np.isnan(ma))
        nar = _rank_norm(na, ~np.isnan(na))
        blended_a = np.full(len(tids), np.nan)
        bothA = ~np.isnan(ma) & ~np.isnan(na)
        blended_a[bothA] = wa * mar[bothA] + (1 - wa) * nar[bothA]
        blended_a[~np.isnan(ma) & np.isnan(na)] = mar[~np.isnan(ma) & np.isnan(na)]
        blended_a[np.isnan(ma) & ~np.isnan(na)] = nar[np.isnan(ma) & ~np.isnan(na)]
        a_old = np.array([v6a[t].get("arousal", 0.5) or 0.5 for t in tids])
        a_mu, a_sd = float(np.nanmean(a_old)), float(np.nanstd(a_old))
        a_rank = (rankdata(np.where(np.isnan(blended_a), 0.5, blended_a)) - 1) / (len(blended_a) - 1)
        arousal = np.clip(a_mu + (a_rank - a_rank.mean()) / (a_rank.std() + 1e-9) * a_sd, 0, 1)
    else:
        # inherit v6a's acoustic MERT arousal unchanged
        arousal = np.array([float(v6a[t].get("arousal", 0.5) or 0.5) for t in tids])

    out = {}
    for i, tid in enumerate(tids):
        e = v6a[tid]
        out[tid] = {
            "valence": round(float(valence[i]), 4),
            "arousal": round(float(arousal[i]), 4),
            "label": e.get("label"),
            "valence_vnlex": None if np.isnan(vn_val[i]) else round(float(vn_val[i]), 4),
            "valence_mert": None if np.isnan(mv[i]) else round(float(mv[i]), 4),
            "src": (f"v6d_vlyr{int(wv*100)}_gpttuned_a"
                    + (f"mert{int(wa*100)}" if tune_arousal else "inherit6a")),
        }
    json.dump(out, open(out_path, "w"), ensure_ascii=False)

    # ---- agreement report: v6d vs v6c against GPT (held-out-style, full-set ρ) ----
    def agree(arr, target, mask):
        return float(spearmanr(arr[mask], target[mask]).correlation)
    v6c = json.load(open("data/emotion_labels_v6c.json")) if os.path.exists("data/emotion_labels_v6c.json") else {}
    v6c_v = np.array([v6c.get(t, {}).get("valence", np.nan) for t in tids])
    v6c_a = np.array([v6c.get(t, {}).get("arousal", np.nan) for t in tids])
    mv2 = ~np.isnan(gv) & ~np.isnan(v6c_v)
    ma2 = ~np.isnan(ga) & ~np.isnan(v6c_a)
    print(f"\n  Valence ρ vs GPT:  v6c={agree(v6c_v, gv, mv2):.4f}  →  v6d={agree(valence, gv, mv2):.4f}")
    print(f"  Arousal ρ vs GPT:  v6c={agree(v6c_a, ga, ma2):.4f}  →  v6d={agree(arousal, ga, ma2):.4f}")
    rva = float(spearmanr(valence, arousal).correlation)
    print(f"  r(V,A) v6d = {rva:+.4f}   V mean={valence.mean():.3f} std={valence.std():.3f}  "
          f"A mean={arousal.mean():.3f} std={arousal.std():.3f}")
    print(f"  → {out_path}")
    print(f"  Next gate: python -m tools.color_eval_rigor --emotions-file {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--tune-arousal", action="store_true",
                    help="GPT-tune arousal too (non-default; GPT is lyrics-only)")
    args = ap.parse_args()
    build(out_path=args.out, tune_arousal=args.tune_arousal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
