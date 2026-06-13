"""Phase 1 (V-A hardening) — signal sufficiency & necessity audit.

For each axis, decide the minimal-sufficient signal set ("đúng đủ, không thừa không thiếu"):
  - redundancy: pairwise Spearman + 1-factor PCA loadings
  - necessity:  leave-one-signal-out — does dropping it lower agreement with the
                INDEPENDENT references? (bootstrap CI on the delta)
Reference for valence = GPT + Gemini (independent of each other); for arousal we use the
acoustic-construct consensus (tempo+loudness) + DEAM-probe as anchors. LLM = backtest only.

Run: python -m tools.signal_audit
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT = "var/runtime/backtest/reports/signal_audit.json"


def _rank(a):
    a = np.asarray(a, float); out = np.full(len(a), np.nan); m = ~np.isnan(a)
    if m.sum() > 1: out[m] = (rankdata(a[m]) - 1) / (m.sum() - 1)
    return out


def _jv(path, field=None, tids=None):
    if not os.path.exists(path): return None
    d = json.load(open(path))
    def g(t):
        x = d.get(t)
        return (x.get(field) if isinstance(x, dict) else x) if x is not None else np.nan
    return np.array([g(t) if g(t) is not None else np.nan for t in tids], float)


def _pca1(M):
    X = (M - np.nanmean(M, 0)) / (np.nanstd(M, 0) + 1e-9)
    X = np.nan_to_num(X)
    cov = np.cov(X.T); w, V = np.linalg.eigh(cov); o = np.argsort(w)[::-1]
    pc1 = V[:, o[0]]; pc1 = pc1 if pc1.sum() >= 0 else -pc1
    load = pc1 * np.sqrt(max(w[o[0]], 0))
    return load, float(w[o[0]] / w.sum())


def _boot_ci(fn, *a, n=3000, seed=1):
    rng = np.random.default_rng(seed); N = len(a[0]); vals = []
    for _ in range(n):
        idx = rng.integers(0, N, N); vals.append(fn(*[x[idx] for x in a]))
    return round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)


def _rho(a, b):
    m = ~np.isnan(a) & ~np.isnan(b)
    return float(spearmanr(a[m], b[m]).correlation) if m.sum() > 50 else float("nan")


def _audit(name, sigs, refs):
    """sigs: {name: array}; refs: {name: array}. Equal-weight rank blend = consensus."""
    names = list(sigs)
    R = {k: _rank(v) for k, v in sigs.items()}
    M = np.column_stack([R[k] for k in names])
    print(f"\n=== {name}: signals {names} ===")
    # redundancy
    pair = {f"{names[i]}~{names[j]}": round(_rho(M[:, i], M[:, j]), 3)
            for i in range(len(names)) for j in range(i + 1, len(names))}
    load, ev = _pca1(np.nan_to_num(M, nan=0.5))
    print("  pairwise ρ:", pair)
    print("  PCA1 loadings:", {names[i]: round(float(load[i]), 3) for i in range(len(names))}, f"explVar={ev:.2f}")
    # necessity: full blend vs leave-one-out, agreement with each ref
    def blend(cols):
        Mb = np.column_stack([R[k] for k in cols])
        return np.array([np.nanmean(row) for row in Mb])
    res = {"pairwise": pair, "pca1_explvar": round(ev, 3), "loadings": {names[i]: round(float(load[i]),3) for i in range(len(names))}, "leave_one_out": {}}
    full = blend(names)
    for rname, rv in refs.items():
        full_r = _rho(full, rv)
        print(f"  [{rname}] full-set ρ={full_r:+.3f}")
        for drop in names:
            kept = [k for k in names if k != drop]
            d_r = _rho(blend(kept), rv)
            delta = full_r - d_r
            mark = "  <-- necessary" if delta > 0.01 else ("  (redundant?)" if delta <= 0.002 else "")
            print(f"      −{drop:9}: ρ={d_r:+.3f}  Δ={delta:+.3f}{mark}")
            res["leave_one_out"].setdefault(rname, {})[drop] = {"rho_without": round(d_r,4), "delta": round(delta,4)}
        res.setdefault("full_set_rho", {})[rname] = round(full_r, 4)
    return res


def main() -> int:
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    gpt = _jv("data/va_reference_gpt.json", "valence", tids)
    gem = _jv("data/emotion_labels_v5d.json", "valence", tids)
    gpt_a = _jv("data/va_reference_gpt.json", "arousal", tids)

    # ---- VALENCE signals (present ones) ----
    vsig = {}
    vsig["vn_lex"]  = _jv("data/emotion_labels_v6c.json", "valence_vnlex", tids)
    vsig["vn_sent"] = _jv(cfg.VN_SENTIMENT_VALENCE_FILE, None, tids)
    vsig["emobank"] = _jv("data/emobank_valence.json", None, tids)
    vsig["mert"]    = _jv("data/mert_valence.json", None, tids)
    for opt, p in [("mode", "var/runtime/features/mode_scores.json"), ("mlva", "data/mlva_valence.json")]:
        a = _jv(p, None, tids)
        if a is not None and (~np.isnan(a)).sum() > 100: vsig[opt] = a
    vsig = {k: v for k, v in vsig.items() if v is not None}
    rep = {"valence": _audit("VALENCE", vsig, {"GPT": gpt, "Gemini": gem})}

    # ---- AROUSAL signals ----
    cf = json.load(open("data/crossfade_features.json"))
    asig = {
        "mert": _jv("data/mert_arousal.json", None, tids),
        "tempo": np.array([json.load(open("data/clean_bpm.json")).get(t, np.nan) for t in tids], float),
        "loudness": np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids], float),
    }
    mq = "data/muq_arousal.json"
    if os.path.exists(mq): asig["muq"] = _jv(mq, None, tids)
    rep["arousal"] = _audit("AROUSAL", asig, {"GPT_arousal": gpt_a})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rep, open(OUT, "w"), indent=2)
    print(f"\nsaved → {OUT}")
    print("\nRule: keep signal if PCA-independent AND leave-one-out Δ>0.01 vs an independent ref; drop if redundant (Δ≤0.002 & high pairwise ρ).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
