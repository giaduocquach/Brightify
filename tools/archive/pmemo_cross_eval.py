"""Phase 5 — CROSS-DATASET validation (D5) on PMEmo (Zhang 2018, ~794 songs, human V-A).

DEAM alone is one corpus; honest probe quality needs cross-corpus transfer. This:
  1. Unzips PMEmo, reads its static V-A annotations + chorus mp3s.
  2. Extracts frozen MuQ on PMEmo chorus clips (same recipe as extract_muq_deam).
  3. TRANSFER: train MuQ→V-A Ridge on DEAM-human, test on PMEmo-human (Spearman) — the
     real cross-corpus generalization number (not in-sample DEAM-CV).
  4. WITHIN-PMEmo nested-CV R² + bootstrap CI — second independent corpus' own ceiling.
Frozen MuQ + linear probe, public datasets only, no fine-tune. Idempotent (caches MuQ).

Run: python -m tools.pmemo_cross_eval
"""
from __future__ import annotations
import glob, json, os, sys, warnings, zipfile
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PM = "data/external/pmemo"
ZIP = f"{PM}/PMEmo.zip"
MUQ_OUT = f"{PM}/pmemo_muq.npy"
IDS_OUT = f"{PM}/pmemo_ids.json"
DEAM = "data/external/deam"
MODEL_ID = "OpenMuQ/MuQ-large-msd-iter"
SR = 24_000
CLIP = 15.0


def _unzip():
    if not os.path.exists(ZIP):
        print(f"[pmemo] {ZIP} missing — download first"); return False
    # extract once (look for any csv as the done-marker)
    if not glob.glob(f"{PM}/**/*.csv", recursive=True):
        print(f"[pmemo] extracting {ZIP} …")
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(PM)
    return True


def _annotations():
    """Aggregate per-subject static annotations → {musicId: (valence, arousal)}.
    This PMEmo edition stores Annotations/{Arousal,Valence}/{id}-{A,V}.csv (col 'static',
    ~10 subjects). Per-song label = mean of 'static' across subjects (Spearman is scale-free
    so the native continuous scale is used as-is — no normalization needed)."""
    def load_dir(axis, suffix):
        out = {}
        for f in glob.glob(f"{PM}/**/Annotations/{axis}/*-{suffix}.csv", recursive=True):
            try:
                mid = int(os.path.basename(f).split("-")[0])
                out[mid] = float(pd.read_csv(f)["static"].mean())
            except Exception:
                continue
        return out
    val = load_dir("Valence", "V"); aro = load_dir("Arousal", "A")
    mids = set(val) & set(aro)
    print(f"[pmemo] aggregated annotations: {len(val)} V, {len(aro)} A → {len(mids)} songs with both")
    return {m: (val[m], aro[m]) for m in mids}


def _mp3_for(mid):
    for pat in (f"{PM}/**/Chorus/{mid}.mp3", f"{PM}/**/{mid}.mp3"):
        m = glob.glob(pat, recursive=True)
        if m: return m[0]
    return None


def _extract_muq(mids):
    if os.path.exists(MUQ_OUT) and os.path.exists(IDS_OUT):
        saved = json.load(open(IDS_OUT))
        if saved == mids:
            print(f"[pmemo] MuQ cached {MUQ_OUT}"); return np.load(MUQ_OUT)
    import librosa, torch
    from muq import MuQ
    from dotenv import load_dotenv
    load_dotenv()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[pmemo] loading MuQ on {dev} for {len(mids)} clips", flush=True)
    model = MuQ.from_pretrained(MODEL_ID, token=os.environ.get("HF_TOKEN") or None).to(dev).eval()
    X = np.full((len(mids), 1024), np.nan, np.float32); ok = 0
    for i, mid in enumerate(mids):
        mp3 = _mp3_for(mid)
        if not mp3: continue
        try:
            dur = librosa.get_duration(path=mp3)
            off = min(10.0, max(0.0, dur * 0.15))
            wav, _ = librosa.load(mp3, sr=SR, mono=True, offset=off, duration=CLIP)
            if wav.size < SR: continue
            with torch.no_grad():
                out = model(torch.tensor(wav, dtype=torch.float32, device=dev)[None], output_hidden_states=True)
            st = torch.stack(list(out.hidden_states), 0)
            X[i] = st.mean(0).mean(1).squeeze(0).cpu().numpy(); ok += 1
        except Exception:
            continue
        if (i + 1) % 100 == 0:
            np.save(MUQ_OUT, X); print(f"  {i+1}/{len(mids)} ok={ok}", flush=True)
    np.save(MUQ_OUT, X); json.dump(mids, open(IDS_OUT, "w"))
    print(f"[pmemo] MuQ ok={ok}/{len(mids)}")
    return X


def _deam_muq_labels():
    ids = json.load(open(f"{DEAM}/deam_ids.json"))
    muq = np.load(f"{DEAM}/deam_muq.npy")
    fs = glob.glob(f"{DEAM}/**/song_level/static_annotations_averaged_songs_*.csv", recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True); df.columns = [c.strip() for c in df.columns]
    lab = {int(r.song_id): ((r.valence_mean - 1) / 8, (r.arousal_mean - 1) / 8) for r in df.itertuples()}
    keep = [i for i, s in enumerate(ids) if s in lab and not np.isnan(muq[i]).any()]
    return muq[keep], np.array([lab[ids[i]] for i in keep])


def _nested_cv(X, y, seed=42):
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    r2s = []
    for tr, te in KFold(5, shuffle=True, random_state=seed).split(X):
        ba, bs = 1.0, -9
        for a in [1, 10, 100, 300, 1000]:
            s = cross_val_score(Ridge(alpha=a), X[tr], y[tr], cv=3, scoring="r2").mean()
            if s > bs: bs, ba = s, a
        p = Ridge(alpha=ba).fit(X[tr], y[tr]).predict(X[te])
        r2s.append(1 - ((y[te]-p)**2).sum() / ((y[te]-y[te].mean())**2).sum())
    return float(np.mean(r2s)), float(np.std(r2s))


def main() -> int:
    from sklearn.linear_model import Ridge
    if not _unzip(): return 1
    ann = _annotations()
    if not ann:
        print("[pmemo] no annotations found — aborting"); return 1
    mids = sorted(ann)
    X = _extract_muq(mids)
    valid = ~np.isnan(X).any(1)
    Xv = X[valid]; mv = [mids[i] for i in range(len(mids)) if valid[i]]
    yv = np.array([ann[m][0] for m in mv]); ya = np.array([ann[m][1] for m in mv])
    print(f"\n[pmemo] usable n={len(mv)}")

    Xd, yd = _deam_muq_labels()
    print(f"[deam]  train n={len(Xd)}")
    rng = np.random.RandomState(0)
    res = {}
    for axis, col, y in [("valence", 0, yv), ("arousal", 1, ya)]:
        # TRANSFER: DEAM-trained → PMEmo
        m = Ridge(alpha=100).fit(Xd, yd[:, col])
        pred = m.predict(Xv)
        rho_t = spearmanr(pred, y).correlation
        boot = [spearmanr(pred[idx], y[idx]).correlation
                for idx in (rng.randint(0, len(y), len(y)) for _ in range(800))]
        ci = np.percentile(boot, [2.5, 97.5])
        # WITHIN-PMEmo nested-CV
        r2, sd = _nested_cv(Xv, y)
        res[axis] = {"transfer_rho": round(float(rho_t), 4),
                     "transfer_ci": [round(float(ci[0]), 4), round(float(ci[1]), 4)],
                     "within_pmemo_cv_r2": round(r2, 4), "within_sd": round(sd, 4)}
        print(f"\n=== {axis.upper()} ===")
        print(f"  TRANSFER DEAM→PMEmo  ρ={rho_t:+.3f}  95%CI[{ci[0]:+.3f},{ci[1]:+.3f}]")
        print(f"  WITHIN-PMEmo nested-CV R²={r2:+.3f} ± {sd:.3f}")
    res["n_pmemo"] = len(mv); res["n_deam"] = len(Xd)
    json.dump(res, open("data/pmemo_cross_eval.json", "w"))
    print(f"\n→ data/pmemo_cross_eval.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
