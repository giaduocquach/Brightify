"""Grounded vn_sent — VN lyrical valence from a FROZEN ViSoBERT + linear probe on a
PEER-REVIEWED VN dataset (replaces the community `wonrax` sentiment head, unknown corpus).

Why: vn_sent (~30% of the EWE valence) was the only lyrics signal whose training data was
not citable — a community fine-tune over an unpublished corpus. This re-grounds it with the
SAME recipe as the EmoBank probe (frozen encoder + Ridge probe + published dataset, NO
fine-tuning, offline-only): every component now traces to a citable source.

  - Backbone: ViSoBERT (Nguyen et al. 2023, EMNLP Findings) — encoder pretrained for VN
    social-media text (slang/emoji/teencode), matching the register of VN song lyrics.
  - Target:   UIT-VSFC (Nguyen et al. 2018, peer-reviewed) sentiment → ordinal valence
    {negative:0.0, neutral:0.5, positive:1.0}. Pure ordinal polarity — NO subjective scores.
  - Probe:    Ridge [mean-pooled 768-d] → valence; alpha by 5-fold CV; held-out test eval.

valence ∈ [0,1]; long lyrics scored as up to 3 chunks, embeddings averaged.
Run: python -m tools.build_grounded_vnsent   (writes data/vnsent_grounded_valence.json)
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

MODEL_ID = os.environ.get("VN_SENT_BACKBONE", "uitnlp/visobert")
DATASET  = os.environ.get("VN_SENT_DATASET", "tridm/UIT-VSMEC")
OUT      = "data/vnsent_grounded_valence.json"
CACHE    = os.environ.get("HF_CACHE_DIR", cfg.HF_CACHE_DIR)
SENT2VAL = {"negative": 0.0, "neutral": 0.5, "positive": 1.0}
# VSMEC emotion → the NRC-VAD valence of that emotion word (grounded, NOT self-made).
EMOTION2WORD = {"enjoyment": "enjoyment", "sadness": "sadness", "anger": "anger",
                "fear": "fear", "disgust": "disgust", "surprise": "surprise", "other": None}
NRC_VN = "data/external/lexicons/NRC-VAD-Lexicon/OneFilePerLanguage/Vietnamese-NRC-VAD-Lexicon.txt"
BATCH, MAX_LEN, N_CHUNKS = 32, 256, 3


def _nrc_emotion_valence() -> dict:
    """VSMEC emotion label → valence, read from NRC-VAD (Mohammad 2018). 'other' → 0.5."""
    want = {w for w in EMOTION2WORD.values() if w}
    vmap = {}
    for ln in open(NRC_VN, encoding="utf-8").read().splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 2 and p[0].strip().lower() in want:
            vmap[p[0].strip().lower()] = float(p[1])
    return {emo: (vmap[w] if w else 0.5) for emo, w in EMOTION2WORD.items()}


def _chunks(text: str, n: int = N_CHUNKS) -> list[str]:
    words = text.split()
    if len(words) <= 180:
        return [text]
    seg = max(1, len(words) // n)
    return [" ".join(words[i * seg:(i + 1) * seg]) for i in range(n)]


def _encode(texts, model, tok, device):
    """Masked mean-pool of frozen last_hidden_state → (N, 768)."""
    import torch
    out = []
    with torch.no_grad():
        for b in range(0, len(texts), BATCH):
            enc = tok(texts[b:b + BATCH], padding=True, truncation=True,
                      max_length=MAX_LEN, return_tensors="pt").to(device)
            h = model(**enc).last_hidden_state            # (B, T, 768)
            m = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)
            out.append(pooled.cpu().float().numpy())
    return np.concatenate(out, 0)


def main() -> int:
    import torch
    import pandas as pd
    from datasets import load_dataset
    from transformers import AutoTokenizer, AutoModel
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    from scipy.stats import spearmanr

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    os.makedirs(CACHE, exist_ok=True)
    print(f"[vnsent] backbone={MODEL_ID} dataset={DATASET} device={device}")
    tok = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=CACHE)
    model = AutoModel.from_pretrained(MODEL_ID, cache_dir=CACHE).to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)

    # ── training data → continuous valence target (grounded, no self-made scores) ──
    ds = load_dataset(DATASET)
    is_vsmec = "Emotion" in ds[list(ds.keys())[0]].column_names
    emo2val = _nrc_emotion_valence() if is_vsmec else None
    if is_vsmec:
        print(f"[vnsent] VSMEC emotion→valence (NRC-VAD): "
              f"{ {k: round(v,3) for k,v in emo2val.items()} }")
    def split_xy(sp):
        s = ds[sp]
        txt = [str(t) for t in s["Sentence"]]
        if is_vsmec:
            y = np.array([emo2val[str(l).lower()] for l in s["Emotion"]], float)
        else:
            y = np.array([SENT2VAL[str(l).lower()] for l in s["Sentiment"]], float)
        return txt, y
    tr_txt, tr_y = split_xy("train")
    if "validation" in ds:
        v_txt, v_y = split_xy("validation"); tr_txt += v_txt; tr_y = np.concatenate([tr_y, v_y])
    te_txt, te_y = split_xy("test")
    print(f"[vnsent] {DATASET} train+val={len(tr_y)} test={len(te_y)}  "
          f"target mean={tr_y.mean():.3f} std={tr_y.std():.3f}")

    Xtr = _encode(tr_txt, model, tok, device)
    Xte = _encode(te_txt, model, tok, device)

    # ── probe validity: 5-fold CV alpha selection + held-out test ──
    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    best_a, best = 1.0, -9.0
    for a in [1.0, 10.0, 100.0, 1000.0]:
        r2 = cross_val_score(Ridge(alpha=a), Xtr, tr_y, cv=cv, scoring="r2").mean()
        print(f"  Ridge α={a:7}: CV R²={r2:+.3f}")
        if r2 > best: best, best_a = r2, a
    probe = Ridge(alpha=best_a).fit(Xtr, tr_y)
    pred_te = probe.predict(Xte)
    rho_te = spearmanr(pred_te, te_y).correlation
    # high-vs-low valence separation (the polarity the signal must encode)
    pos, neg = pred_te[te_y >= 0.7], pred_te[te_y <= 0.3]
    sep = (pos.mean() - neg.mean())
    print(f"[vnsent] held-out test: ρ(pred,sentiment)={rho_te:+.3f}  "
          f"pos−neg mean gap={sep:+.3f} (pos={pos.mean():.3f} neg={neg.mean():.3f})")

    probe_full = Ridge(alpha=best_a).fit(np.vstack([Xtr, Xte]),
                                         np.concatenate([tr_y, te_y]))

    # ── apply to catalog lyrics (chunked, embeddings averaged) ──
    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"] if c in df.columns)
    tids = df[idc].astype(str).tolist()
    lyrics = df[lyc].fillna("").astype(str).tolist()

    flat, owner = [], []
    for si, lyr in enumerate(lyrics):
        t = lyr.strip()
        if len(t) < 5:
            continue
        for ch in _chunks(t):
            flat.append(ch); owner.append(si)
    Xcat_flat = _encode(flat, model, tok, device)
    pred_flat = np.clip(probe_full.predict(Xcat_flat), 0, 1)
    acc: dict[int, list] = {}
    for k, si in enumerate(owner):
        acc.setdefault(si, []).append(pred_flat[k])
    out = {tids[si]: round(float(np.mean(v)), 4) for si, v in acc.items()}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)
    vals = np.array(list(out.values()))
    print(f"[vnsent] scored {len(out)}/{len(tids)} ({100*len(out)/len(tids):.1f}%) → {OUT}")
    print(f"  valence mean={vals.mean():.3f} std={vals.std():.3f} "
          f"p5={np.percentile(vals,5):.3f} p95={np.percentile(vals,95):.3f}")

    # ── agreement vs the OLD wonrax vn_sent + served valence (sanity, not a target) ──
    def jv(p):
        if not os.path.exists(p): return {}
        d = json.load(open(p))
        return {t: float(x.get("valence") if isinstance(x, dict) else x)
                for t, x in d.items() if (x.get("valence") if isinstance(x, dict) else x) is not None}
    for nm, p in [("old wonrax vn_sent", cfg.VN_SENTIMENT_VALENCE_FILE),
                  ("served v6i valence", cfg.RELABELED_EMOTIONS_FILE)]:
        ref = jv(p); common = [t for t in out if t in ref]
        if len(common) >= 50:
            a = np.array([out[t] for t in common]); b = np.array([ref[t] for t in common])
            print(f"  ρ vs {nm:20} = {spearmanr(a, b).correlation:+.3f}  (n={len(common)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
