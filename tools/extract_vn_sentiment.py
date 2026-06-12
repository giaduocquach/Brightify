"""V6e — context-aware lyrical valence from a frozen Vietnamese sentiment transformer.

Why: v6d valence leaned partly on audio because the bag-of-words VN lexicon is weak
(no real context/negation). A pretrained VN sentiment model (PhoBERT-class) reads the
lyrics WITH context → polarity → valence, sidestepping the lexicon's limits. The model
is a frozen encoder+classifier trained on a PUBLIC VN sentiment corpus (NOT our GPT/
Gemini labels, NOT a generative LLM) and is run OFFLINE only — serving stays LLM-free.

valence = (P(positive) - P(negative) + 1) / 2   ∈ [0,1]   (neutral mass → ~0.5)
Long lyrics: scored in up to 3 chunks (start/mid/end), probabilities averaged.

Run: python -m tools.extract_vn_sentiment [--batch 32]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

OUT = cfg.VN_SENTIMENT_VALENCE_FILE
MAX_LEN = 256
N_CHUNKS = 3


def _resolve_label_idxs(id2label: dict) -> tuple[int | None, int | None]:
    """Find the POS and NEG class indices from the model's id2label (robust to ordering)."""
    pos = neg = None
    for i, name in id2label.items():
        n = str(name).lower()
        if any(k in n for k in ("pos", "positive", "tích cực", "1")) and "neg" not in n:
            pos = int(i)
        if any(k in n for k in ("neg", "negative", "tiêu cực")):
            neg = int(i)
    return pos, neg


def _chunks(text: str, n: int = N_CHUNKS) -> list[str]:
    words = text.split()
    if len(words) <= 180:
        return [text]
    seg = max(1, len(words) // n)
    return [" ".join(words[i * seg:(i + 1) * seg]) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    import pandas as pd
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    df = pd.read_csv(cfg.PROCESSED_FILE)
    idc = next(c for c in ["track_id", "id", "song_id", "ID"] if c in df.columns)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"] if c in df.columns)
    tids = df[idc].astype(str).tolist()
    lyrics = df[lyc].fillna("").astype(str).tolist()

    model_id = cfg.VN_SENTIMENT_MODEL
    cache = os.environ.get("HF_CACHE_DIR", cfg.HF_CACHE_DIR)
    os.makedirs(cache, exist_ok=True)
    print(f"[vn-sentiment] loading {model_id} (cache={cache})", flush=True)
    tok = AutoTokenizer.from_pretrained(model_id, cache_dir=cache, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(model_id, cache_dir=cache)
    model.eval()
    for p in model.parameters():
        p.requires_grad = False

    id2label = model.config.id2label
    pos_i, neg_i = _resolve_label_idxs(id2label)
    print(f"[vn-sentiment] id2label={id2label}  pos_idx={pos_i} neg_idx={neg_i}", flush=True)
    if pos_i is None or neg_i is None:
        print("[ERROR] could not resolve POS/NEG label indices — set them manually."); return 1

    # Flatten all chunks, batch-encode, then re-aggregate per song.
    flat_text, owner = [], []
    for si, lyr in enumerate(lyrics):
        t = lyr.strip()
        if len(t) < 5:
            continue
        for ch in _chunks(t):
            flat_text.append(ch); owner.append(si)

    probs_pos = np.full(len(lyrics), np.nan)
    probs_neg = np.full(len(lyrics), np.nan)
    acc: dict[int, list] = {}
    sm = torch.nn.Softmax(dim=-1)
    with torch.no_grad():
        for b in range(0, len(flat_text), args.batch):
            chunk = flat_text[b:b + args.batch]
            enc = tok(chunk, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt")
            logits = model(**enc).logits
            p = sm(logits).cpu().numpy()
            for k, si in enumerate(owner[b:b + args.batch]):
                acc.setdefault(si, []).append(p[k])
            if b % (args.batch * 50) == 0:
                print(f"  {b}/{len(flat_text)} chunks", flush=True)

    for si, plist in acc.items():
        mean_p = np.mean(plist, axis=0)
        probs_pos[si] = float(mean_p[pos_i])
        probs_neg[si] = float(mean_p[neg_i])

    valence = (probs_pos - probs_neg + 1.0) / 2.0   # [0,1]
    out = {tids[i]: round(float(valence[i]), 4) for i in range(len(tids)) if not np.isnan(valence[i])}
    json.dump(out, open(OUT, "w"), ensure_ascii=False)
    cov = len(out)
    print(f"[vn-sentiment] {cov}/{len(tids)} songs scored ({100*cov/len(tids):.1f}%) → {OUT}")
    vals = np.array(list(out.values()))
    print(f"  valence: mean={vals.mean():.3f} std={vals.std():.3f} "
          f"p5={np.percentile(vals,5):.3f} p95={np.percentile(vals,95):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
