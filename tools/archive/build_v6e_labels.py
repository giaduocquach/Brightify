"""Build emotion_labels_v6e.json — VALENCE purely from lyrics (B+C+D).

Motivation (product owner, scientifically correct): valence belongs to LYRICS, not
audio (Hu & Downie 2010; Delbouys 2018: valence ~17% audio-predictable). v6d kept 0.3
MERT because the bag-of-words lexicon was weak. v6e replaces that with a stronger
LYRICAL ensemble and keeps audio only as a fallback for songs with no lyrics.

Lyrical signals (all non-LLM, frozen, public-data only):
  - vn_lex   : Vietnamese emotion lexicon (negation/adversative FIXED, V6e)
  - vn_sent  : pretrained VN sentiment transformer (data/vn_sentiment_valence.json)
  - emobank  : EmoBank→XLM-R cross-lingual probe (data/emobank_valence.json)
  - nrc      : NRC-VAD lexical valence (optional member)
Audio CANDIDATE (decisive test, NOT a lyrical signal):
  - mert     : DEAM→MERT valence probe (data/mert_valence.json)

Method (C): rank-transform every signal; fit NON-NEGATIVE least squares of the signal
ranks onto the GPT valence rank (offline reference) with 5-fold CV; normalize the NNLS
coefficients → blend weights; FREEZE. Serving stays LLM-free (GPT only picks weights).
DECISIVE TEST (D): mert is in the candidate set — if lyrics suffice, its weight → ~0.
Fallback (D): songs with NO lyrical signal use mert (audio) only. Arousal = v6a (acoustic).

Gate: valence ρ vs GPT ≥ v6d (0.513) AND vs INDEPENDENT Gemini ≥ v6d (0.579);
color TE not regress (run color_eval_rigor --emotions-file after).

Run: python -m tools.build_v6e_labels [--with-nrc] [--out PATH]
"""
import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from scipy.optimize import nnls

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from tools.build_v6c_labels import _rank_norm, _calibrate, _vn_lexicon_valence

V6A_PATH = "data/emotion_labels_v6a.json"
GPT_REF = "data/va_reference_gpt.json"
GEMINI_REF = "data/emotion_labels_v5d.json"
OUT_DEFAULT = "data/emotion_labels_v6e.json"


def _load_json_valence(path, tids):
    """Load {tid: float} or {tid:{valence:..}} → array aligned to tids (NaN if missing)."""
    if not os.path.exists(path):
        return np.full(len(tids), np.nan)
    d = json.load(open(path))
    def get(t):
        x = d.get(t)
        if isinstance(x, dict):
            return x.get("valence", np.nan)
        return x if x is not None else np.nan
    return np.array([float(get(t)) if get(t) is not None else np.nan for t in tids])


def _catalog_rank(arr):
    """Rank-normalise non-NaN entries to [0,1]; NaN stays NaN."""
    out = np.full(len(arr), np.nan)
    m = ~np.isnan(arr)
    if m.sum() > 1:
        out[m] = (rankdata(arr[m]) - 1) / (m.sum() - 1)
    return out


def _cv_nnls(X, y, n_folds=5, seed=42):
    """NNLS fit of rank-features X → rank-target y, with k-fold held-out Spearman."""
    n = len(y)
    rng = np.random.default_rng(seed)
    folds = np.array_split(rng.permutation(n), n_folds)
    cv_rho = []
    for f in folds:
        tr = np.setdiff1d(np.arange(n), f)
        w, _ = nnls(X[tr], y[tr])
        if w.sum() == 0:
            continue
        pred = X[f] @ w
        cv_rho.append(spearmanr(pred, y[f]).correlation)
    w_full, _ = nnls(X, y)
    w_norm = w_full / (w_full.sum() + 1e-12)
    return w_norm, float(np.nanmean(cv_rho))


def build(out_path=OUT_DEFAULT, with_nrc=False):
    v6a = json.load(open(V6A_PATH))
    tids = list(v6a.keys())

    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"] if c in df.columns)
    lyrics_lookup = {str(r[idc]): str(r[lyc]) for _, r in df[[idc, lyc]].iterrows()
                     if isinstance(r[lyc], str) and r[lyc].strip()}

    # ---- signals ----
    vn_lex, has_lyr = _vn_lexicon_valence(tids, lyrics_lookup)          # fixed-negation lexicon
    vn_sent = _load_json_valence(cfg.VN_SENTIMENT_VALENCE_FILE, tids)
    emobank = _load_json_valence("data/emobank_valence.json", tids)
    mert = _load_json_valence("data/mert_valence.json", tids)
    gpt = _load_json_valence(GPT_REF, tids)
    gem = _load_json_valence(GEMINI_REF, tids)
    nrc = np.full(len(tids), np.nan)
    if with_nrc:
        from tools.nrc_vad_score import load_nrc_vad, score_lyrics
        lex = load_nrc_vad()
        nrc = np.array([score_lyrics(lyrics_lookup.get(t, ""), lex, "valence") for t in tids])

    signals = {"vn_lex": vn_lex, "vn_sent": vn_sent, "emobank": emobank, "mert": mert}
    if with_nrc:
        signals["nrc"] = nrc
    ranks = {k: _catalog_rank(v) for k, v in signals.items()}

    # ---- convergent validity (Phase 2): lyrical signals vs GPT & independent Gemini ----
    print("=== CONVERGENT VALIDITY (lyrical signals) ===")
    lyrical = [k for k in signals if k != "mert"]
    def rho(a, b):
        m = ~np.isnan(a) & ~np.isnan(b)
        return float(spearmanr(a[m], b[m]).correlation) if m.sum() > 50 else float("nan")
    for k in signals:
        print(f"  {k:8} n={int((~np.isnan(signals[k])).sum()):5}  ρ vs GPT={rho(signals[k],gpt):+.3f}  ρ vs Gemini={rho(signals[k],gem):+.3f}")
    print("  pairwise (lyrical):", {f"{a}~{b}": round(rho(signals[a],signals[b]),3)
                                     for i,a in enumerate(lyrical) for b in lyrical[i+1:]})

    # ---- NNLS tune to GPT (fit on rows where ALL candidate signals + GPT present) ----
    cand = list(signals.keys())   # includes mert as candidate (decisive test)
    M = np.column_stack([ranks[k] for k in cand])
    fit = ~np.isnan(M).any(axis=1) & ~np.isnan(gpt)
    y = _catalog_rank(np.where(fit, gpt, np.nan))[fit]
    X = M[fit]
    w, cv_rho = _cv_nnls(X, y)
    weights = dict(zip(cand, np.round(w, 3)))
    print(f"\n=== NNLS BLEND (fit n={fit.sum()}, 5-fold CV ρ={cv_rho:.4f}) ===")
    print("  weights:", weights)
    print(f"  >>> DECISIVE TEST — audio(MERT) weight = {weights['mert']:.3f}  "
          f"(expect ≈0 if lyrics suffice)")

    # Pure-lyrical ablation (DROP mert) — the honest test is whether removing audio hurts
    # agreement with the INDEPENDENT Gemini reference (GPT is lyrics-only → biased toward
    # keeping a small audio weight). If Gemini-agreement is ~unchanged, audio adds nothing real.
    lyr_cols = [k for k in cand if k != "mert"]
    Ml = np.column_stack([ranks[k] for k in lyr_cols])
    fitl = ~np.isnan(Ml).any(axis=1) & ~np.isnan(gpt)
    wl, cvl = _cv_nnls(Ml[fitl], _catalog_rank(np.where(fitl, gpt, np.nan))[fitl])
    gem_rank = _catalog_rank(gem)
    def _blend_pred(cols, weights_, mask_ref):
        Mp = np.column_stack([ranks[k] for k in cols])
        ok = ~np.isnan(Mp).any(axis=1) & ~np.isnan(mask_ref)
        pred = Mp[ok] @ weights_
        return spearmanr(pred, mask_ref[ok]).correlation
    print("  --- pure-lyrical (no audio) ablation ---")
    print(f"    weights: {dict(zip(lyr_cols, np.round(wl,3)))}  5-fold CV ρ(GPT)={cvl:.4f}")
    print(f"    ρ vs Gemini: with-audio={_blend_pred(cand, w, gem):.4f}  "
          f"pure-lyrical={_blend_pred(lyr_cols, wl, gem):.4f}  "
          f"(if ~equal → audio adds nothing real)")

    # ---- build per-song valence: weighted avg over AVAILABLE signals, renormalised ----
    W = np.array([w[i] for i in range(len(cand))])
    Rm = M.copy()                         # (n, n_cand) ranks, NaN where missing
    blended = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = Rm[i]
        avail = ~np.isnan(row)
        if not avail.any():
            continue
        ww = W[avail]
        if ww.sum() <= 0:
            blended[i] = float(np.nanmean(row[avail]))
        else:
            blended[i] = float((row[avail] @ ww) / ww.sum())
    # Fallback (D): no lyrical signal at all → mert (audio) only
    no_lyr = np.array([not has_lyr[i] and np.isnan(vn_sent[i]) and np.isnan(emobank[i]) for i in range(len(tids))])
    blended[no_lyr & ~np.isnan(ranks["mert"])] = ranks["mert"][no_lyr & ~np.isnan(ranks["mert"])]
    blended[np.isnan(blended)] = 0.5

    valence = _calibrate((rankdata(blended) - 1) / (len(blended) - 1))
    arousal = np.array([float(v6a[t].get("arousal", 0.5) or 0.5) for t in tids])

    out = {}
    for i, tid in enumerate(tids):
        e = v6a[tid]
        out[tid] = {
            "valence": round(float(valence[i]), 4),
            "arousal": round(float(arousal[i]), 4),
            "label": e.get("label"),
            "valence_vnlex": None if np.isnan(vn_lex[i]) else round(float(vn_lex[i]), 4),
            "valence_vnsent": None if np.isnan(vn_sent[i]) else round(float(vn_sent[i]), 4),
            "src": "v6e_lyrical_nnls",
        }
    json.dump(out, open(out_path, "w"), ensure_ascii=False)

    # ---- gate numbers ----
    def agree(arr, ref):
        m = ~np.isnan(ref)
        return float(spearmanr(arr[m], ref[m]).correlation)
    print(f"\n=== v6e GATE NUMBERS ===")
    print(f"  valence ρ vs GPT    : v6e={agree(valence,gpt):.4f}   (v6d=0.513, must ≥)")
    print(f"  valence ρ vs Gemini : v6e={agree(valence,gem):.4f}   (v6d=0.579, must ≥, INDEPENDENT)")
    print(f"  r(V,A) v6e = {spearmanr(valence,arousal).correlation:+.4f}")
    print(f"  lyric coverage: {100*has_lyr.mean():.1f}% lexicon; vn_sent {100*(~np.isnan(vn_sent)).mean():.1f}%; "
          f"audio-fallback songs: {int((no_lyr).sum())}")
    print(f"  → {out_path}\n  Next: python -m tools.color_eval_rigor --emotions-file {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--with-nrc", action="store_true", help="include NRC-VAD valence as a member")
    args = ap.parse_args()
    build(out_path=args.out, with_nrc=args.with_nrc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
