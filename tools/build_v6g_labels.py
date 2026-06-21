"""Build emotion_labels_v6g.json — V-A hardening culmination.

VALENCE: EWE (reliability-weighted, de-circularized — NO LLM target) blend of the
  audited signals {VN-lexicon, VN-sentiment, EmoBank-XLMR, MuQ-valence}. MuQ replaces
  MERT (better DEAM nested-CV). mode rejected by Phase-1 audit (hurt valence).
AROUSAL: DEAM-human-grounded NNLS blend of {MuQ-arousal, clean-BPM, loudness} (MuQ
  replaces MERT: DEAM arousal R² 0.56→0.66). MuQ still doesn't capture tempo → explicit
  clean-BPM keeps the tempo facet (Eerola). All frozen embeddings + linear probe.

Run: python -m tools.build_v6g_labels
"""
from __future__ import annotations
import glob, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from scipy.optimize import nnls
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.build_v6c_labels import _calibrate
from tools.va_ewe_weights import ewe

DEAM = "data/external/deam"
V6A = "data/emotion_labels_v6a.json"
OUT = "data/emotion_labels_v6g.json"


def _rank(a):
    a = np.asarray(a, float); o = np.full(len(a), np.nan); m = ~np.isnan(a)
    if m.sum() > 1: o[m] = (rankdata(a[m]) - 1) / (m.sum() - 1)
    return o


def _jv(path, field, tids):
    if not os.path.exists(path): return np.full(len(tids), np.nan)
    d = json.load(open(path))
    def g(t):
        x = d.get(t); return (x.get(field) if isinstance(x, dict) else x) if x is not None else np.nan
    return np.array([g(t) if g(t) is not None else np.nan for t in tids], float)


def _deam_arousal():
    fs = glob.glob(f"{DEAM}/**/song_level/static_annotations_averaged_songs_*.csv", recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True); df.columns = [c.strip() for c in df.columns]
    return {int(r.song_id): (r.arousal_mean - 1) / 8 for r in df.itertuples()}


def main() -> int:
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    df = pd.read_csv(cfg.PROCESSED_FILE); tids = df["track_id"].astype(str).tolist()
    v6a = json.load(open(V6A))

    # ---------- VALENCE: EWE over audited signals (MuQ replaces MERT) ----------
    vsig = {"vn_lex": _jv("data/emotion_labels_v6c.json", "valence_vnlex", tids),
            "vn_sent": _jv(cfg.VN_SENTIMENT_VALENCE_FILE, None, tids),
            "emobank": _jv("data/emobank_valence.json", None, tids),
            "muq": _jv("data/muq_valence.json", None, tids)}
    names = list(vsig); R = {k: _rank(v) for k, v in vsig.items()}
    M = np.column_stack([R[k] for k in names]); complete = ~np.isnan(M).any(1)
    w, rel = ewe(M[complete])
    wv = dict(zip(names, w))
    print(f"[v6g valence] EWE weights {dict(zip(names, np.round(w,3)))}  reliab {dict(zip(names, np.round(rel,2)))}")
    # per-song weighted avg over available signals
    blended_v = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = M[i]; av = ~np.isnan(row)
        if av.any():
            ww = w[av]; blended_v[i] = float(row[av] @ ww / (ww.sum() + 1e-12))
    blended_v[np.isnan(blended_v)] = 0.5
    valence = _calibrate((rankdata(blended_v) - 1) / (len(blended_v) - 1))

    # ---------- AROUSAL: INHERIT v6f (DEAM-grounded MERT+tempo+loudness) ----------
    # MuQ-arousal was evaluated (DEAM human-CV 0.647→0.775, better) BUT shipping it
    # regressed the VN colour-TE (0.0227→0.0238) and tempo-tracking — its DEAM-human gain
    # doesn't transfer to better VN recommendation (cross-corpus + self-referential TE).
    # Per the no-regression gate, keep v6f arousal (tracks tempo 0.18, TE 0.0227). The MuQ
    # arousal probe is kept as a documented, validated artifact (data/muq_arousal.json).
    INHERIT_V6F_AROUSAL = True
    ids = json.load(open(f"{DEAM}/deam_ids.json")); arou = _deam_arousal()
    aco = json.load(open(f"{DEAM}/deam_acoustic.json"))
    muq_d = np.load(f"{DEAM}/deam_muq.npy")
    keep = [i for i, s in enumerate(ids) if s in arou and str(s) in aco and not np.isnan(muq_d[i]).any()]
    yA = np.array([arou[ids[i]] for i in keep])
    # OOF MuQ-arousal on DEAM (no leakage)
    Xm = muq_d[keep]; oof = np.zeros(len(yA))
    for tr, te in KFold(5, shuffle=True, random_state=42).split(Xm):
        oof[te] = Ridge(alpha=100).fit(Xm[tr], yA[tr]).predict(Xm[te])
    tempo_d = np.array([aco[str(ids[i])]["tempo"] for i in keep])
    loud_d = np.array([aco[str(ids[i])]["rms_db"] for i in keep])
    F = np.column_stack([_rank(oof), _rank(tempo_d), _rank(loud_d)]); yr = _rank(yA)
    wa, _ = nnls(F, yr); wa = wa / (wa.sum() + 1e-12)
    # Tempo floor: DEAM (Western) cross-corpus fit underweights tempo because DEAM's MuQ
    # already encodes DEAM tempo↔arousal coupling; but on VN, MuQ is orthogonal to tempo
    # (ρ=−0.02) and tempo is an established arousal determinant (Eerola; v6f-validated).
    # Floor tempo at 0.15 (v6f level) to preserve construct validity, renormalize.
    TEMPO_FLOOR = 0.15
    if wa[1] < TEMPO_FLOOR:
        wa[1] = TEMPO_FLOOR; wa = wa / wa.sum()
    print(f"[v6g arousal] weights MuQ/tempo/loud = {np.round(wa,3).tolist()} (tempo floored to {TEMPO_FLOOR})")
    cvr = []
    for tr, te in KFold(5, shuffle=True, random_state=1).split(F):
        wt, _ = nnls(F[tr], yr[tr]); wt = wt / (wt.sum()+1e-12)
        cvr.append(spearmanr(F[te] @ wt, yA[te]).correlation)
    print(f"[v6g arousal] DEAM human-CV ρ = {np.nanmean(cvr):.3f}  (v6f MERT-based was 0.647)")
    # apply to catalog
    cf = json.load(open("data/crossfade_features.json"))
    muq_a = _jv("data/muq_arousal.json", None, tids)
    bpm = _jv("data/clean_bpm.json", None, tids)
    loud = np.array([cf.get(t, {}).get("loudness_lufs", np.nan) for t in tids], float)
    Fv = np.column_stack([_rank(muq_a), _rank(bpm), _rank(loud)])
    araw = np.full(len(tids), np.nan)
    for i in range(len(tids)):
        row = Fv[i]; av = ~np.isnan(row)
        if av.any():
            ww = wa[av]; araw[i] = float(row[av] @ ww / (ww.sum()+1e-12))
    araw[np.isnan(araw)] = 0.5
    ar = _rank(araw); arousal_muq = np.clip(0.471 + (ar - ar.mean()) / (ar.std()+1e-9) * 0.133, 0, 1)
    if INHERIT_V6F_AROUSAL and os.path.exists("data/emotion_labels_v6f.json"):
        v6f_a = json.load(open("data/emotion_labels_v6f.json"))
        arousal = np.array([float(v6f_a.get(t, {}).get("arousal", arousal_muq[i])) for i, t in enumerate(tids)])
    else:
        arousal = arousal_muq

    # ---------- write + report ----------
    v6e = json.load(open("data/emotion_labels_v6e.json")) if os.path.exists("data/emotion_labels_v6e.json") else {}
    out = {}
    for i, t in enumerate(tids):
        e = v6a.get(t, {})
        out[t] = {"valence": round(float(valence[i]), 4), "arousal": round(float(arousal[i]), 4),
                  "label": e.get("label"), "src": "v6g_ewe-valence_muq-arousal"}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)

    gpt = _jv("data/va_reference_gpt.json", "valence", tids); gem = _jv("data/emotion_labels_v5d.json", "valence", tids)
    def rho(a, b): m = ~np.isnan(a) & ~np.isnan(b); return spearmanr(a[m], b[m]).correlation
    print(f"\n=== v6g GATE NUMBERS ===")
    print(f"  valence ρ vs GPT={rho(valence,gpt):.3f}  vs Gemini(indep)={rho(valence,gem):.3f}  (v6f: 0.718/0.651)")
    print(f"  arousal vs clean_bpm={rho(arousal,bpm):+.3f}  vs loudness={rho(arousal,loud):+.3f}  (v6f: 0.18/0.52)")
    print(f"  r(V,A)={spearmanr(valence,arousal).correlation:+.3f}  → {OUT}")
    print(f"  Next gate: python -m tools.color_eval_rigor --emotions-file {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
