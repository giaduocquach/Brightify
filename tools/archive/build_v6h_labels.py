"""Build emotion_labels_v6h.json — v6g with the hand-built VN lexicon REPLACED by the
grounded NRC-VAD-Vietnamese lexicon (Workstream A: no more self-made).

VALENCE: EWE over {vn_lex(GROUNDED NRC-VAD-VN), vn_sent, emobank, MuQ} — same method as v6g,
  but vn_lex now traces to NRC-VAD (Mohammad 2018) instead of the in-code dict. EWE re-weights
  by measured reliability, so a comparable grounded signal keeps the ensemble valence stable.
AROUSAL: identical to v6g (DEAM-grounded MERT+tempo+loudness) — unchanged, read from v6g.

Run: python -m tools.build_v6h_labels   (then gate: color_eval_rigor --emotions-file data/emotion_labels_v6h.json)
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.build_v6g_labels import _jv, _rank
from tools.build_v6c_labels import _calibrate
from tools.va_ewe_weights import ewe

V6G = "data/emotion_labels_v6g.json"
OUT = "data/emotion_labels_v6h.json"


def main() -> int:
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    v6g = json.load(open(V6G))

    # VALENCE: EWE, vn_lex = GROUNDED NRC-VAD-VN (vs v6g's hand lexicon)
    vsig = {"vn_lex": _jv("data/vnlex_grounded_valence.json", None, tids),   # ← grounded
            "vn_sent": _jv(cfg.VN_SENTIMENT_VALENCE_FILE, None, tids),
            "emobank": _jv("data/emobank_valence.json", None, tids),
            "muq": _jv("data/muq_valence.json", None, tids)}
    names = list(vsig); R = {k: _rank(v) for k, v in vsig.items()}
    M = np.column_stack([R[k] for k in names]); complete = ~np.isnan(M).any(1)
    w, rel = ewe(M[complete])
    print(f"[v6h valence] EWE weights {dict(zip(names, np.round(w,3)))}  reliab {dict(zip(names, np.round(rel,2)))}")
    blended = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = M[i]; av = ~np.isnan(row)
        if av.any():
            ww = w[av]; blended[i] = float(row[av] @ ww / (ww.sum() + 1e-12))
    blended[np.isnan(blended)] = 0.5
    valence = _calibrate((rankdata(blended) - 1) / (len(blended) - 1))

    # AROUSAL: inherit v6g exactly (unchanged)
    arousal = np.array([float(v6g.get(t, {}).get("arousal", 0.5)) for t in tids])

    out = {}
    for i, t in enumerate(tids):
        e = v6g.get(t, {})
        out[t] = {"valence": round(float(valence[i]), 4), "arousal": round(float(arousal[i]), 4),
                  "label": e.get("label"), "src": "v6h_grounded-vnlex(NRC-VAD-VN)"}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)

    # gate vs references + vs v6g
    gpt = _jv("data/va_reference_gpt.json", "valence", tids)
    gem = _jv("data/emotion_labels_v5d.json", "valence", tids)
    v6gval = np.array([float(v6g.get(t, {}).get("valence", np.nan)) for t in tids])
    def rho(a, b): m = ~np.isnan(a) & ~np.isnan(b); return spearmanr(a[m], b[m]).correlation
    print(f"\n=== v6h GATE ===")
    print(f"  valence ρ vs GPT={rho(valence,gpt):.3f}  vs Gemini={rho(valence,gem):.3f}  (v6g: 0.706/0.637)")
    print(f"  valence ρ vs v6g (should be high — ensemble stable)={rho(valence,v6gval):.3f}")
    print(f"  r(V,A)={spearmanr(valence,arousal).correlation:+.3f}  → {OUT}")
    print(f"  Next: python -m tools.color_eval_rigor --emotions-file {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
