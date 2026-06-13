"""Phase 2 (V32) — Convergent validity + cross-corpus transfer for V-A labels.

Turns the "circular validation" weakness into convergent validity: if multiple
INDEPENDENT signals agree, the construct is real (no single ground truth needed).

Valence signals : VN-lexicon (v6c.valence_vnlex) · MERT-audio (mert_valence.json) · GPT (va_reference_gpt.json)
Arousal signals : MERT-audio (mert_arousal.json) · NRC-VAD (lyrics) · GPT

Reports per dimension:
  - pairwise Spearman ρ matrix
  - Cronbach's α (internal consistency across the independent signals)
  - 1-factor PCA loadings + explained variance (do signals load on one latent factor?)
  - Bland-Altman (bias + 95% limits of agreement) of each served signal vs GPT

Cross-corpus transfer (the headline NEW number): the MERT probe was trained+CV'd on
DEAM (Western). mert_valence.json / mert_arousal.json ARE that probe applied to the VN
catalog. ρ/R² of those vs the GPT reference = the real DEAM→Vietnamese transfer, with
bootstrap CI. (LLM used only as an offline reference — never served.)

Run: python -m tools.va_convergent_validity
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as ss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = "var/runtime/backtest/reports/va_convergent_validity.json"


def _boot_ci(fn, *arrs, n_boot=5000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(arrs[0])
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        vals.append(fn(*[a[idx] for a in arrs]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(np.mean(vals)), 4), round(float(lo), 4), round(float(hi), 4)


def _cronbach_alpha(M):
    """M: (n_items, n_subjects). Standardised-item alpha."""
    M = np.asarray(M, float)
    k = M.shape[0]
    if k < 2:
        return float("nan")
    # correlation-based (standardised) alpha
    C = np.corrcoef(M)
    r_bar = (C.sum() - k) / (k * (k - 1))
    return float(k * r_bar / (1 + (k - 1) * r_bar))


def _pca_1factor(M):
    """M: (n_subjects, n_items) standardised. Return (loadings, explained_var_frac)."""
    X = (M - M.mean(0)) / (M.std(0) + 1e-12)
    cov = np.cov(X.T)
    w, V = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    w, V = w[order], V[:, order]
    pc1 = V[:, 0]
    if pc1.sum() < 0:
        pc1 = -pc1
    loadings = pc1 * np.sqrt(max(w[0], 0))
    return loadings, float(w[0] / w.sum())


def _bland_altman(served, ref):
    diff = served - ref
    bias = float(diff.mean())
    sd = float(diff.std(ddof=1))
    return {"bias": round(bias, 4), "loa_lo": round(bias - 1.96 * sd, 4),
            "loa_hi": round(bias + 1.96 * sd, 4)}


def _signals_valence(tids):
    v6c = json.load(open("data/emotion_labels_v6c.json"))
    mert = json.load(open("data/mert_valence.json"))
    gpt = json.load(open("data/va_reference_gpt.json"))
    out = {}
    for t in tids:
        vn = v6c.get(t, {}).get("valence_vnlex")
        me = mert.get(t)
        gp = gpt.get(t, {}).get("valence") if isinstance(gpt.get(t), dict) else None
        if vn is not None and me is not None and gp is not None:
            out[t] = (float(vn), float(me), float(gp))
    return out, ("VN_lexicon", "MERT_audio", "GPT")


def _signals_arousal(tids, lyr_map):
    from tools.nrc_vad_score import load_nrc_vad, score_lyrics
    lex = load_nrc_vad()
    mert = json.load(open("data/mert_arousal.json"))
    gpt = json.load(open("data/va_reference_gpt.json"))
    out = {}
    for t in tids:
        me = mert.get(t)
        gp = gpt.get(t, {}).get("arousal") if isinstance(gpt.get(t), dict) else None
        nrc = score_lyrics(lyr_map.get(t, ""), lex, "arousal")
        if me is not None and gp is not None and not np.isnan(nrc):
            out[t] = (float(me), float(nrc), float(gp))
    return out, ("MERT_audio", "NRC_VAD", "GPT")


def _analyze(sig, names, gpt_idx):
    tids = list(sig.keys())
    M = np.array([sig[t] for t in tids])           # (n, 3)
    n = len(tids)
    # pairwise Spearman
    rho = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = float(ss.spearmanr(M[:, i], M[:, j]).correlation)
            rho[f"{names[i]}~{names[j]}"] = round(r, 4)
    alpha = round(_cronbach_alpha(M.T), 4)
    loadings, ev = _pca_1factor(M)
    ba = _bland_altman(M[:, gpt_idx], M[:, gpt_idx])  # placeholder, replaced below
    bland = {names[i]: _bland_altman(M[:, i], M[:, gpt_idx])
             for i in range(len(names)) if i != gpt_idx}
    return {
        "n": n,
        "pairwise_spearman": rho,
        "cronbach_alpha": alpha,
        "pca_1factor": {"loadings": {names[i]: round(float(loadings[i]), 4) for i in range(len(names))},
                         "explained_var": round(ev, 4)},
        "bland_altman_vs_GPT": bland,
        "n_signals_loading_gt_0.5": int((np.abs(loadings) > 0.5).sum()),
    }


def _cross_corpus(sig, names, gpt_idx, probe_name):
    """DEAM-probe (MERT) vs GPT reference: the real transfer number."""
    tids = list(sig.keys())
    M = np.array([sig[t] for t in tids])
    pi = names.index(probe_name)
    probe, gpt = M[:, pi], M[:, gpt_idx]
    r = float(ss.pearsonr(probe, gpt)[0])
    rho = float(ss.spearmanr(probe, gpt).correlation)
    r_ci = _boot_ci(lambda a, b: float(ss.pearsonr(a, b)[0]), probe, gpt)
    return {"probe": probe_name, "n": len(tids),
            "pearson_r": round(r, 4), "pearson_ci95": [r_ci[1], r_ci[2]],
            "spearman_rho": round(rho, 4), "r2": round(r * r, 4)}


def main() -> int:
    import config as cfg
    df = pd.read_csv(cfg.PROCESSED_FILE)
    tids = df["track_id"].astype(str).tolist()
    lyr_map = dict(zip(df["track_id"].astype(str), df["lyrics_cleaned"].fillna("").astype(str)))

    if not os.path.exists("data/va_reference_gpt.json"):
        print("[ERROR] data/va_reference_gpt.json missing — run build_va_reference_gpt first")
        return 1

    vsig, vnames = _signals_valence(tids)
    asig, anames = _signals_arousal(tids, lyr_map)
    print(f"valence signals overlap n={len(vsig)} · arousal signals overlap n={len(asig)}")

    rep = {
        "valence": _analyze(vsig, vnames, gpt_idx=vnames.index("GPT")),
        "arousal": _analyze(asig, anames, gpt_idx=anames.index("GPT")),
        "cross_corpus_transfer": {
            "valence": _cross_corpus(vsig, vnames, vnames.index("GPT"), "MERT_audio"),
            "arousal": _cross_corpus(asig, anames, anames.index("GPT"), "MERT_audio"),
        },
        "note": ("Convergent validity: independent signals agreeing corroborates the "
                 "construct without a single ground truth. Cross-corpus = DEAM-trained "
                 "MERT probe vs GPT reference on Vietnamese songs."),
    }

    print("\n=== CONVERGENT VALIDITY ===")
    for dim in ("valence", "arousal"):
        d = rep[dim]
        print(f"\n[{dim}] n={d['n']}  Cronbach α={d['cronbach_alpha']}  "
              f"PCA1 explained={d['pca_1factor']['explained_var']}  "
              f"signals|loading|>0.5: {d['n_signals_loading_gt_0.5']}/3")
        print("  pairwise ρ:", d["pairwise_spearman"])
        print("  PCA loadings:", d["pca_1factor"]["loadings"])
    print("\n=== CROSS-CORPUS TRANSFER (DEAM→VN, MERT probe vs GPT) ===")
    for dim in ("valence", "arousal"):
        c = rep["cross_corpus_transfer"][dim]
        print(f"  {dim}: r={c['pearson_r']} CI{c['pearson_ci95']}  ρ={c['spearman_rho']}  R²={c['r2']}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rep, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
