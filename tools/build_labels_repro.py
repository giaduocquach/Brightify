"""Reproduce the served emotion labels (emotion_labels_v6i.json) from scratch — a single,
documented, deterministic script that proves the V-A labelling pipeline is reproducible.

It rebuilds the FINAL labels directly from the grounded signals (skipping the historical
v6a→v6c→v6g→v6h replay), using the EXACT method the on-disk builders use:

  VALENCE = EWE (reliability-weighted, NO LLM target) over four grounded signals, then
            rank → affine-calibrate. Mirrors tools/build_v6h_labels.py.
              vn_lex  : data/vnlex_grounded_valence.json   (NRC-VAD-Vietnamese, Mohammad 2018)
              vn_sent : data/vnsent_grounded_valence.json  (frozen ViSoBERT + UIT-VSMEC probe)
              emobank : data/emobank_valence.json          (frozen XLM-R + EmoBank probe)
              muq     : data/muq_valence.json              (frozen MuQ + DEAM probe)
  AROUSAL = rank-blend [MuQ-arousal 0.574, clean-BPM 0.35, loudness 0.076] → standardise.
            Mirrors tools/build_v6i_labels.py (hand-set weights; tempo raised to 0.35 for MuQ).

Signals are produced offline by: muq_probe.py, build_grounded_vnlex.py, build_grounded_vnsent.py,
emobank_valence_probe.py  (all frozen models + linear probes; no fine-tuning; no LLM at build time).

Writes data/emotion_labels_repro.json (NEVER overwrites the frozen v6i) and prints a gate:
reproduction Spearman ρ vs the frozen v6i, plus convergent validity vs the independent GPT ref.

Run: python -m tools.build_labels_repro
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.build_v6g_labels import _jv, _rank          # identical signal-loading + ranking
from tools.build_v6c_labels import _calibrate           # identical affine calibration
from tools.va_ewe_weights import ewe                     # identical reliability weighting

V6I = "data/emotion_labels_v6i.json"
OUT = "data/emotion_labels_repro.json"

# 8 Russell-circumplex emotion centroids (V, A) — used only to attach a label string; the
# reproduction gate is on the continuous V/A, not on labels.
_CENTROIDS = {
    "happy": (0.80, 0.66), "excited": (0.62, 0.86), "peaceful": (0.74, 0.30),
    "calm": (0.62, 0.18), "melancholic": (0.36, 0.30), "sad": (0.22, 0.30),
    "tense": (0.30, 0.72), "angry": (0.22, 0.80),
}


def _label(v: float, a: float) -> str:
    return min(_CENTROIDS, key=lambda k: (v - _CENTROIDS[k][0]) ** 2 + (a - _CENTROIDS[k][1]) ** 2)


def main() -> int:
    df = pd.read_csv(cfg.PROCESSED_FILE)
    tids = df["track_id"].astype(str).tolist()

    # ---------- VALENCE: EWE over the four grounded signals (mirror build_v6h) ----------
    vsig = {
        "vn_lex":  _jv("data/vnlex_grounded_valence.json", None, tids),
        "vn_sent": _jv("data/vnsent_grounded_valence.json", None, tids),
        "emobank": _jv("data/emobank_valence.json", None, tids),
        "muq":     _jv("data/muq_valence.json", None, tids),
    }
    present = [k for k, v in vsig.items() if np.isfinite(v).sum() > 100]
    missing = [k for k in vsig if k not in present]
    if missing:
        print(f"[repro][WARN] missing/empty signals {missing} — rebuild them first "
              f"(muq_probe / build_grounded_vnlex / build_grounded_vnsent / emobank_valence_probe).")
    names = present
    R = {k: _rank(vsig[k]) for k in names}
    M = np.column_stack([R[k] for k in names])
    complete = ~np.isnan(M).any(1)
    w, rel = ewe(M[complete])
    print(f"[repro valence] EWE weights {dict(zip(names, np.round(w, 3)))}  "
          f"reliab {dict(zip(names, np.round(rel, 2)))}  (n_complete={int(complete.sum())})")
    blended = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = M[i]; av = ~np.isnan(row)
        if av.any():
            ww = w[av]; blended[i] = float(row[av] @ ww / (ww.sum() + 1e-12))
    blended[np.isnan(blended)] = 0.5
    valence = _calibrate((rankdata(blended) - 1) / (len(blended) - 1))

    # ---------- AROUSAL: rank-blend [MuQ-arousal, clean-BPM, loudness] (mirror build_v6i) ----------
    wt = float(os.environ.get("BRIGHTIFY_MUQ_TEMPO_W", "0.35"))
    rest = 1 - wt; r = 0.76 / 0.86
    wa = np.array([rest * r, wt, rest * (1 - r)])      # ≈ [0.574, 0.350, 0.076]
    print(f"[repro arousal] MuQ/tempo/loud weights = {np.round(wa, 3).tolist()}")
    cf = json.load(open("data/crossfade_features.json"))
    muq_a = _jv("data/muq_arousal.json", None, tids)
    bpm = _jv("data/clean_bpm.json", None, tids)
    loud = np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids], float)
    Fv = np.column_stack([_rank(muq_a), _rank(bpm), _rank(loud)])
    araw = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = Fv[i]; av = ~np.isnan(row)
        if av.any():
            araw[i] = float(row[av] @ wa[av] / (wa[av].sum() + 1e-12))
    araw[np.isnan(araw)] = 0.5
    ar = _rank(araw)
    arousal = np.clip(0.471 + (ar - ar.mean()) / (ar.std() + 1e-9) * 0.133, 0, 1)

    # ---------- write (NEVER touch the frozen v6i) ----------
    out = {}
    for i, t in enumerate(tids):
        v, a = round(float(valence[i]), 4), round(float(arousal[i]), 4)
        out[t] = {"valence": v, "arousal": a, "label": _label(v, a), "src": "repro_grounded-ewe-valence_muq-arousal"}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)
    print(f"[repro] wrote {len(out)} labels → {OUT}")

    # ---------- GATE: reproduction vs frozen v6i + convergent validity vs GPT ----------
    def rho(a, b):
        m = ~np.isnan(a) & ~np.isnan(b)
        return spearmanr(a[m], b[m]).correlation if m.sum() > 2 else float("nan")

    v6i = json.load(open(V6I))
    iv = np.array([float(v6i.get(t, {}).get("valence", np.nan)) for t in tids])
    ia = np.array([float(v6i.get(t, {}).get("arousal", np.nan)) for t in tids])
    a_absdiff = np.nanmax(np.abs(arousal - ia))
    rv, ra = rho(valence, iv), rho(arousal, ia)
    print("\n=== REPRODUCTION GATE (repro vs frozen v6i) ===")
    print(f"  VALENCE ρ = {rv:+.4f}   (target ≥ 0.95)  {'PASS' if rv >= 0.95 else 'CHECK'}")
    print(f"  AROUSAL ρ = {ra:+.4f}   (target ≥ 0.97)  {'PASS' if ra >= 0.97 else 'CHECK'}  "
          f"max|Δ|={a_absdiff:.4f}")

    gpt = _jv("data/va_reference_gpt.json", "valence", tids)
    gpta = _jv("data/va_reference_gpt.json", "arousal", tids)
    if np.isfinite(gpt).sum() > 100:
        print("\n=== CONVERGENT VALIDITY (vs independent GPT reference) ===")
        print(f"  repro valence ρ vs GPT = {rho(valence, gpt):+.3f}   "
              f"v6i valence ρ vs GPT = {rho(iv, gpt):+.3f}")
        print(f"  repro arousal ρ vs GPT = {rho(arousal, gpta):+.3f}   "
              f"v6i arousal ρ vs GPT = {rho(ia, gpta):+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
