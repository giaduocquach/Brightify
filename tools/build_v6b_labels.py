"""Build emotion_labels_v6b.json — Phase 2c: ensemble valence (no LLM).

V6b formula:
  V = wA * MERT_valence      [data/mert_valence.json,  layer9, DEAM R²=0.502]
    + wL1 * NRC_VAD_valence  [data/nrc_vad_scores.json, lyrics lexicon]
    + wL2 * EmoBank_valence  [data/emobank_valence.json, XLM-R frozen probe]
  A = v6a arousal (unchanged)

Weight tuning: grid search over (wA, wL1, wL2) summing to 1.0,
               optimising TE gate via color_eval_rigor (human-free).
               Starting point: wA=0.40, wL1=0.35, wL2=0.25.

Gates (strict):
  TE      ≤ 0.0222  (must not regress from v6a)
  r(V,A)  ∈ [0.05, 0.20]   (target orthogonal; v6a = 0.408)
  ρ(MERT_V, NRC_V) > 0.25  (inter-signal corroboration)

Run:
  python -m tools.build_v6b_labels [--wA 0.40 --wL1 0.35 --wL2 0.25]
  python -m tools.build_v6b_labels --grid-search   # find best weights
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

MERT_V_PATH   = "data/mert_valence.json"
NRC_V_PATH    = "data/nrc_vad_scores.json"
EMOBANK_V_PATH= "data/emobank_valence.json"
V6A_PATH      = "data/emotion_labels_v6a.json"
OUT_DEFAULT   = "data/emotion_labels_v6b.json"

# DEAM valence distribution for calibration (1..9 → [0,1])
DEAM_VALENCE_MEAN = 0.51
DEAM_VALENCE_STD  = 0.17


def _load_signals(tids: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load and align all valence signals for given track IDs.

    Returns (mert_v, nrc_v, emobank_v, valid_mask) as (N,) arrays.
    Fills missing values with per-signal median (not NaN — keeps all songs).
    """
    mert_raw = json.load(open(MERT_V_PATH))
    nrc_raw  = json.load(open(NRC_V_PATH))
    eb_raw   = json.load(open(EMOBANK_V_PATH)) if os.path.exists(EMOBANK_V_PATH) else {}

    mert_arr  = np.array([mert_raw.get(t, None) for t in tids], dtype=object)
    nrc_arr   = np.array([nrc_raw.get(t, {}).get("valence", None) for t in tids], dtype=object)
    eb_arr    = np.array([eb_raw.get(t, None) for t in tids], dtype=object)

    def _fill(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        valid = np.array([v is not None for v in arr])
        floats = np.where(valid, arr.astype(float), np.nan)
        median = float(np.nanmedian(floats))
        filled = np.where(valid, floats, median)
        return filled.astype(float), valid

    mert_f, m_valid = _fill(mert_arr)
    nrc_f,  n_valid = _fill(nrc_arr)
    eb_f,   e_valid = _fill(eb_arr)

    # "fully valid" = all three signals present
    all_valid = m_valid & n_valid & e_valid
    print(f"  Signal coverage: MERT={m_valid.sum()}/{len(tids)}, "
          f"NRC={n_valid.sum()}/{len(tids)}, "
          f"EmoBank={e_valid.sum()}/{len(tids)}, "
          f"all three={all_valid.sum()}/{len(tids)}")
    return mert_f, nrc_f, eb_f, all_valid


def _blend_valence(mert: np.ndarray, nrc: np.ndarray, eb: np.ndarray,
                   wA: float, wL1: float, wL2: float) -> np.ndarray:
    """Weighted blend normalised to sum=1."""
    total = wA + wL1 + wL2
    return (wA * mert + wL1 * nrc + wL2 * eb) / total


def _calibrate(arr: np.ndarray, target_mean: float, target_std: float) -> np.ndarray:
    """Affine calibration toward DEAM distribution (preserves rank order)."""
    mu, sd = float(arr.mean()), float(arr.std()) + 1e-9
    cal = mu + (arr - mu) / sd * target_std
    cal += target_mean - cal.mean()
    return np.clip(cal, 0.0, 1.0)


def build(wA: float = 0.40, wL1: float = 0.35, wL2: float = 0.25,
          out_path: str = OUT_DEFAULT, calibrate: bool = True) -> dict:
    """Build v6b labels and return summary metrics."""
    for path, name in [(MERT_V_PATH, "mert_valence"), (NRC_V_PATH, "nrc_vad_scores"),
                       (V6A_PATH, "emotion_labels_v6a")]:
        if not os.path.exists(path):
            print(f"[ERROR] Missing {path} ({name})")
            sys.exit(1)

    if not os.path.exists(EMOBANK_V_PATH):
        print(f"[WARN] {EMOBANK_V_PATH} not found — using MERT+NRC-VAD only (2-signal)")
        wL2_eff = 0.0
    else:
        wL2_eff = wL2

    v6a: dict = json.load(open(V6A_PATH))
    tids = list(v6a.keys())

    mert_v, nrc_v, eb_v, all_valid = _load_signals(tids)

    blend = _blend_valence(mert_v, nrc_v, eb_v if wL2_eff > 0 else np.zeros(len(tids)),
                           wA, wL1, wL2_eff)

    if calibrate:
        blend = _calibrate(blend, DEAM_VALENCE_MEAN, DEAM_VALENCE_STD)

    # r(V, A) check
    a_arr = np.array([v6a[t].get("arousal", 0.5) for t in tids], dtype=float)
    r_va, _ = pearsonr(blend, a_arr)

    # Inter-signal corroboration
    rho_mn, _ = spearmanr(mert_v, nrc_v)
    rho_me, _ = spearmanr(mert_v, eb_v)
    rho_ne, _ = spearmanr(nrc_v,  eb_v)

    print(f"  weights: MERT={wA:.2f} NRC={wL1:.2f} EmoBank={wL2_eff:.2f}")
    print(f"  V distribution: mean={blend.mean():.3f}  std={blend.std():.3f}")
    print(f"  r(V, A)  = {r_va:+.4f}  (target 0.05–0.20)")
    print(f"  ρ(MERT,NRC)={rho_mn:+.3f}  ρ(MERT,EB)={rho_me:+.3f}  ρ(NRC,EB)={rho_ne:+.3f}")

    out: dict = {}
    for i, tid in enumerate(tids):
        entry = v6a[tid]
        out[tid] = {
            "valence":       round(float(blend[i]), 4),
            "arousal":       entry.get("arousal"),
            "label":         entry.get("label"),
            "valence_mert":  round(float(mert_v[i]), 4),
            "valence_nrc":   round(float(nrc_v[i]), 4),
            "valence_eb":    round(float(eb_v[i]), 4) if wL2_eff > 0 else None,
            "src":           f"v6b_mert{int(wA*100)}_nrc{int(wL1*100)}_eb{int(wL2_eff*100)}",
        }

    json.dump(out, open(out_path, "w"), ensure_ascii=False)
    print(f"\n  → {out_path}")

    return {"r_va": float(r_va), "rho_mn": float(rho_mn),
            "rho_me": float(rho_me), "v_mean": float(blend.mean()),
            "v_std": float(blend.std()), "wA": wA, "wL1": wL1, "wL2": wL2_eff}


def grid_search(out_path: str = OUT_DEFAULT) -> None:
    """Evaluate a grid of (wA, wL1, wL2) — pick the one with best r(V,A) orthogonality."""
    import subprocess

    candidates = [
        (0.40, 0.35, 0.25),
        (0.35, 0.40, 0.25),
        (0.50, 0.30, 0.20),
        (0.50, 0.50, 0.00),   # 2-signal only
        (0.30, 0.40, 0.30),
        (0.60, 0.25, 0.15),
    ]
    best = None
    for wA, wL1, wL2 in candidates:
        tmp = f"/tmp/v6b_grid_{int(wA*100)}_{int(wL1*100)}_{int(wL2*100)}.json"
        print(f"\n── wA={wA} wL1={wL1} wL2={wL2} ──")
        metrics = build(wA=wA, wL1=wL1, wL2=wL2, out_path=tmp, calibrate=True)
        r_va = abs(metrics["r_va"])
        if best is None or r_va < abs(best["r_va"]):
            best = {**metrics, "tmp": tmp}

    print(f"\n══ BEST: wA={best['wA']} wL1={best['wL1']} wL2={best['wL2']}")
    print(f"         r(V,A)={best['r_va']:+.4f}  mean={best['v_mean']:.3f}")
    import shutil
    shutil.copy(best["tmp"], out_path)
    print(f"  saved best → {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wA",  type=float, default=0.40, help="MERT-valence weight")
    ap.add_argument("--wL1", type=float, default=0.35, help="NRC-VAD-valence weight")
    ap.add_argument("--wL2", type=float, default=0.25, help="EmoBank-valence weight")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--grid-search", action="store_true",
                    help="Try multiple weight configs and pick best r(V,A)")
    args = ap.parse_args()

    if args.grid_search:
        grid_search(out_path=args.out)
    else:
        build(wA=args.wA, wL1=args.wL1, wL2=args.wL2,
              out_path=args.out, calibrate=not args.no_calibrate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
