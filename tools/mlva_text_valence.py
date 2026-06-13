"""Phase 4c — INDEPENDENT multilingual-text valence reference (backtest-only convergent check).

Why: the served lyrical valence (v6g EWE) is validated mainly via GPT/Gemini agreement, which
is partly circular, plus convergent agreement among its own lyrical signals. This adds a
GENUINELY INDEPENDENT, non-LLM, non-circular reference: a frozen MULTILINGUAL sentiment
transformer from a DIFFERENT family than the ensemble members (not PhoBERT/wonrax, not the
EmoBank-XLM-R probe) — `cardiffnlp/twitter-xlm-roberta-base-sentiment` (Barbieri et al. 2022,
XLM-T; multilingual, handles Vietnamese tokens). We score lyric valence the same way the VN
signal does and report convergent validity (Spearman + bootstrap CI) vs the SERVED valence and
vs each ensemble member. It NEVER changes served labels — pure offline validation.

valence = (P(positive) - P(negative) + 1) / 2 ∈ [0,1]; long lyrics scored in ≤3 chunks (avg).
Run: python -m tools.mlva_text_valence [--batch 32]
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg
from tools.extract_vn_sentiment import _resolve_label_idxs, _chunks

MODEL_ID = "cardiffnlp/twitter-xlm-roberta-base-sentiment"  # independent multilingual sentiment
OUT = "data/mlva_valence.json"
MAX_LEN = 256


def _read_valence(path, field=None):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    out = {}
    for t, x in d.items():
        v = (x.get(field) if (field and isinstance(x, dict)) else
             (x.get("valence") if isinstance(x, dict) else x))
        if v is not None:
            out[t] = float(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    import pandas as pd, torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    from scipy.stats import spearmanr

    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "plain_lyrics"] if c in df.columns)
    tids = df[idc].astype(str).tolist()
    lyrics = df[lyc].fillna("").astype(str).tolist()

    cache = os.environ.get("HF_CACHE_DIR", getattr(cfg, "HF_CACHE_DIR", "models_cache"))
    print(f"[mlva] loading {MODEL_ID}", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=cache)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, cache_dir=cache).eval()
    for p in model.parameters():
        p.requires_grad = False
    pos_i, neg_i = _resolve_label_idxs(model.config.id2label)
    print(f"[mlva] id2label={model.config.id2label} pos={pos_i} neg={neg_i}", flush=True)
    if pos_i is None or neg_i is None:
        print("[ERROR] cannot resolve POS/NEG"); return 1

    flat, owner = [], []
    for si, lyr in enumerate(lyrics):
        t = lyr.strip()
        if len(t) < 5:
            continue
        for ch in _chunks(t):
            flat.append(ch); owner.append(si)
    pp = np.full(len(lyrics), np.nan); pn = np.full(len(lyrics), np.nan)
    acc: dict = {}
    sm = torch.nn.Softmax(dim=-1)
    with torch.no_grad():
        for b in range(0, len(flat), args.batch):
            enc = tok(flat[b:b+args.batch], padding=True, truncation=True,
                      max_length=MAX_LEN, return_tensors="pt")
            p = sm(model(**enc).logits).cpu().numpy()
            for k, si in enumerate(owner[b:b+args.batch]):
                acc.setdefault(si, []).append(p[k])
            if b % (args.batch*50) == 0:
                print(f"  {b}/{len(flat)} chunks", flush=True)
    for si, pl in acc.items():
        mp = np.mean(pl, axis=0); pp[si] = mp[pos_i]; pn[si] = mp[neg_i]
    val = (pp - pn + 1.0) / 2.0
    out = {tids[i]: round(float(val[i]), 4) for i in range(len(tids)) if not np.isnan(val[i])}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)
    print(f"[mlva] scored {len(out)}/{len(tids)} → {OUT}")

    # ---- convergent validity vs served valence + each ensemble member ----
    served = _read_valence(cfg.RELABELED_EMOTIONS_FILE, "valence")
    refs = {
        "SERVED v6g valence": served,
        "vn_lexicon":  _read_valence("data/emotion_labels_v6c.json", "valence_vnlex"),
        "vn_sentiment(PhoBERT)": _read_valence(cfg.VN_SENTIMENT_VALENCE_FILE),
        "emobank(XLM-R)": _read_valence("data/emobank_valence.json"),
        "GPT (offline ref)": _read_valence("data/va_reference_gpt.json", "valence"),
    }
    rng = np.random.RandomState(0)
    print("\n=== Phase 4c convergent validity: independent XLM-T sentiment vs ... ===")
    for name, ref in refs.items():
        common = [t for t in out if t in ref]
        if len(common) < 20:
            print(f"  {name:24} (n={len(common)} too few)"); continue
        a = np.array([out[t] for t in common]); b = np.array([ref[t] for t in common])
        rho = spearmanr(a, b).correlation
        boot = [spearmanr(a[idx], b[idx]).correlation
                for idx in (rng.randint(0, len(a), len(a)) for _ in range(1000))]
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"  {name:24} ρ={rho:+.3f}  95%CI[{lo:+.3f},{hi:+.3f}]  n={len(common)}")
    print("\n  (Independent of GPT/Gemini and of the PhoBERT/EmoBank ensemble members ⇒")
    print("   agreement with SERVED valence = genuine NON-circular convergent validity.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
