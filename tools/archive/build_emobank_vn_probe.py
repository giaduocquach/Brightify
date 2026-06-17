"""Experiment — does an IN-LANGUAGE (VN-translated) EmoBank probe beat the cross-lingual one?

Current emobank signal: train Ridge on ENGLISH EmoBank XLM-R[CLS] → apply to VN lyrics
(cross-lingual train/test mismatch). Hypothesis: machine-translate EmoBank EN→VI, train the
probe on the VN-translated embeddings (same XLM-R encoder) → train & serving both Vietnamese →
better transfer. EmoBank's human V-A labels still apply (MT preserves sentence meaning).

Steps: translate EmoBank (opus-mt-en-vi) → encode VN sentences XLM-R[CLS] → Ridge CV →
apply to the SAME catalog_xlmr_cls.npy → emobank_vn_valence.json + compare to EN baseline.
Run: python -m tools.build_emobank_vn_probe
"""
from __future__ import annotations
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

EMOBANK_CSV = "data/external/emobank.csv"
EMOBANK_VN  = "data/external/emobank_vi.csv"          # cached translations
EMOBANK_VN_EMB = "data/external/emobank_vi_xlmr_cls.npy"
CATALOG_EMB = "data/catalog_xlmr_cls.npy"
EMOBANK_EN_EMB = "data/external/emobank_xlmr_cls.npy"  # existing EN embeddings (baseline)
OUT = "data/emobank_vn_valence.json"
MODEL_ID = "xlm-roberta-base"
MT_MODEL = "Helsinki-NLP/opus-mt-en-vi"
BATCH, MAX_LEN = 32, 128


def _ccc(yt, yp):
    mt, mp = yt.mean(), yp.mean(); st, sp = yt.std(), yp.std()
    rho = float(np.corrcoef(yt, yp)[0, 1])
    return float(2 * st * sp * rho / (st**2 + sp**2 + (mt - mp)**2 + 1e-9))


def _translate(texts, device):
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    import torch
    tok = AutoTokenizer.from_pretrained(MT_MODEL, cache_dir=cfg.HF_CACHE_DIR)
    mt = AutoModelForSeq2SeqLM.from_pretrained(MT_MODEL, cache_dir=cfg.HF_CACHE_DIR).to(device).eval()
    out = []
    with torch.no_grad():
        for b in range(0, len(texts), BATCH):
            enc = tok([t[:512] for t in texts[b:b + BATCH]], return_tensors="pt",
                      padding=True, truncation=True, max_length=MAX_LEN).to(device)
            gen = mt.generate(**enc, max_length=MAX_LEN, num_beams=1)
            out += tok.batch_decode(gen, skip_special_tokens=True)
            if b % (BATCH * 50) == 0:
                print(f"  translated {b}/{len(texts)}", flush=True)
    return out


def _encode(texts, device):
    from transformers import AutoTokenizer, AutoModel
    import torch
    tok = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=cfg.HF_CACHE_DIR)
    m = AutoModel.from_pretrained(MODEL_ID, cache_dir=cfg.HF_CACHE_DIR).to(device).eval()
    for p in m.parameters():
        p.requires_grad_(False)
    out = []
    with torch.no_grad():
        for b in range(0, len(texts), BATCH):
            enc = tok(texts[b:b + BATCH], padding=True, truncation=True,
                      max_length=MAX_LEN, return_tensors="pt").to(device)
            out.append(m(**enc).last_hidden_state[:, 0, :].cpu().float().numpy())
    return np.concatenate(out, 0)


def main() -> int:
    import torch
    import pandas as pd
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    from scipy.stats import spearmanr
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    eb = pd.read_csv(EMOBANK_CSV)
    y = ((eb["V"].values - 1.0) / 4.0).astype(float)

    # 1) translate (cached)
    if os.path.exists(EMOBANK_VN):
        vi = pd.read_csv(EMOBANK_VN)["vi"].fillna("").astype(str).tolist()
        print(f"[emobank-vn] loaded {len(vi)} cached translations")
    else:
        print(f"[emobank-vn] translating {len(eb)} sentences EN→VI ({MT_MODEL})…")
        vi = _translate(eb["text"].fillna("").astype(str).tolist(), device)
        pd.DataFrame({"vi": vi}).to_csv(EMOBANK_VN, index=False)
    print(f"  sample: {vi[0][:70]!r}")

    # 2) encode VN translations
    if os.path.exists(EMOBANK_VN_EMB):
        Xvn = np.load(EMOBANK_VN_EMB)
    else:
        Xvn = _encode(vi, device); np.save(EMOBANK_VN_EMB, Xvn.astype(np.float32))
    print(f"[emobank-vn] VN emb {Xvn.shape}")

    # 3) probe CV — VN-translated vs EN baseline (same labels, same encoder)
    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    def best_cv(X):
        b_a, b = 1.0, -9.0
        for a in [1.0, 10.0, 100.0]:
            r2 = cross_val_score(Ridge(alpha=a), X, y, cv=cv, scoring="r2").mean()
            if r2 > b: b, b_a = r2, a
        return b_a, b
    aV, cvV = best_cv(Xvn)
    Xen = np.load(EMOBANK_EN_EMB); aE, cvE = best_cv(Xen)
    print(f"[emobank-vn] in-domain CV R²:  VN-translated={cvV:+.3f} (α={aV})  |  EN-baseline={cvE:+.3f} (α={aE})")
    # held-out CCC
    split = eb["split"].values; tr, te = split == "train", split != "train"
    pvn = Ridge(alpha=aV).fit(Xvn[tr], y[tr]).predict(Xvn[te])
    pen = Ridge(alpha=aE).fit(Xen[tr], y[tr]).predict(Xen[te])
    print(f"  held-out CCC:  VN={_ccc(y[te], pvn):.3f}  EN={_ccc(y[te], pen):.3f}")

    # 4) apply VN-trained probe to catalog (same XLM-R[CLS] catalog embeddings)
    probe = Ridge(alpha=aV).fit(Xvn, y)
    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    tids = df[idc].astype(str).tolist()
    Xcat = np.load(CATALOG_EMB)
    ycat = np.clip(probe.predict(Xcat), 0, 1)
    json.dump({t: round(float(v), 4) for t, v in zip(tids, ycat)}, open(OUT, "w"), ensure_ascii=False)
    print(f"[emobank-vn] catalog: mean={ycat.mean():.3f} std={ycat.std():.3f} → {OUT}")

    # 5) agreement vs served valence + vs EN-emobank catalog output
    def jv(p):
        if not os.path.exists(p): return {}
        d = json.load(open(p))
        return {t: float(x.get("valence") if isinstance(x, dict) else x)
                for t, x in d.items() if (x.get("valence") if isinstance(x, dict) else x) is not None}
    for nm, p in [("EN-emobank (current)", "data/emobank_valence.json"),
                  ("served v6i valence", cfg.RELABELED_EMOTIONS_FILE)]:
        ref = jv(p); common = [t for t in tids if t in ref and t in dict(zip(tids, ycat))]
        if len(common) >= 50:
            a = np.array([ycat[tids.index(t)] for t in common]); b = np.array([ref[t] for t in common])
            print(f"  ρ vs {nm:22} = {spearmanr(a, b).correlation:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
