"""Validate the system's V-A labels against the Vietnamese gold-set (audit V17, P0 #2).

Reads var/goldset/ratings/*.csv (one filled template per annotator) and reports:
  • inter-rater reliability  — ICC(2,1) and ICC(2,k) (two-way random, agreement) per axis,
    so we know the human labels are trustworthy before trusting any comparison.
  • the real cross-validation — Pearson r + RMSE of the system's v4 labels
    (LLM-valence, MERT-arousal) vs the mean human rating, per axis.

This is the honest, in-domain number that replaces the Western/DEAM and in-sample figures.
Run after ≥3 annotators fill var/goldset/ratings/. Dependency-light (numpy/pandas only).

Usage: python -m tools.eval_color_goldset
"""
from __future__ import annotations
import os, sys, glob, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

RATINGS_DIR = 'var/goldset/ratings'


def _icc2(X):
    """ICC(2,1) and ICC(2,k) — two-way random effects, absolute agreement.
    X: (n_subjects, k_raters), no missing. McGraw & Wong (1996)."""
    n, k = X.shape
    grand = X.mean()
    row_m = X.mean(axis=1)
    col_m = X.mean(axis=0)
    SSR = k * np.sum((row_m - grand) ** 2)
    SSC = n * np.sum((col_m - grand) ** 2)
    SST = np.sum((X - grand) ** 2)
    SSE = SST - SSR - SSC
    MSR = SSR / (n - 1)
    MSC = SSC / (k - 1)
    MSE = SSE / ((n - 1) * (k - 1))
    icc1 = (MSR - MSE) / (MSR + (k - 1) * MSE + (k / n) * (MSC - MSE) + 1e-12)
    icck = (MSR - MSE) / (MSR + (MSC - MSE) / n + 1e-12)
    return float(icc1), float(icck)


def main() -> int:
    files = sorted(glob.glob(os.path.join(RATINGS_DIR, '*.csv')))
    if len(files) < 2:
        print(f"Need ≥2 annotator files in {RATINGS_DIR}/ (found {len(files)}).")
        print("Build the template first: python -m tools.build_color_goldset")
        return 0

    val_cols, aro_cols, names = {}, {}, []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        d = pd.read_csv(f).dropna(subset=['rater_valence', 'rater_arousal'])
        d = d.set_index('track_id')
        val_cols[name] = d['rater_valence'].astype(float)
        aro_cols[name] = d['rater_arousal'].astype(float)
        names.append(name)

    V = pd.DataFrame(val_cols).dropna()   # songs rated by ALL annotators
    A = pd.DataFrame(aro_cols).dropna()
    print(f"annotators: {names}  | songs rated by all: V={len(V)} A={len(A)}")
    if len(V) < 5:
        print("Too few fully-rated songs for stable ICC (need ≥~15).");
    for axis, M in (('valence', V), ('arousal', A)):
        if len(M) >= 3:
            i1, ik = _icc2(M.values)
            print(f"  [{axis}] inter-rater ICC(2,1)={i1:.3f}  ICC(2,k)={ik:.3f}  "
                  f"({'good' if ik>=0.75 else 'moderate' if ik>=0.5 else 'poor'})")

    # --- cross-validate v4 labels vs mean human rating ---
    try:
        v4 = json.load(open('data/emotion_labels_v4.json'))
    except OSError:
        print("v4 labels not found — skip cross-validation."); return 0
    mean_val = V.mean(axis=1); mean_aro = A.mean(axis=1)
    for axis, mean_h in (('valence', mean_val), ('arousal', mean_aro)):
        tids = [str(t) for t in mean_h.index]
        sysv = np.array([float(v4.get(t, {}).get(axis, np.nan)) for t in tids])
        h = mean_h.values
        m = ~np.isnan(sysv)
        if m.sum() >= 5:
            r = float(np.corrcoef(sysv[m], h[m])[0, 1])
            rmse = float(np.sqrt(np.mean((sysv[m] - h[m]) ** 2)))
            print(f"  [{axis}] system(v4) vs human:  Pearson r={r:+.3f}  RMSE={rmse:.3f}  (n={m.sum()})")
    print("\n→ This is the honest in-domain validation; compare arousal r here to the DEAM CV R²=0.58.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
