"""Encode catalog lyrics with an arbitrary sentence-embedding model → .npy (for A/B of the
similar-song lyrics signal). Handles e5 ('query:' prefix) and bge/SBERT (plain). Mean-pooled,
L2-normalised — same geometry the engine expects for cosine.

Run: python -m tools.encode_lyrics --model BAAI/bge-m3 --out data/lyrics_bgem3.npy
"""
from __future__ import annotations
import argparse, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

BATCH, MAX_LEN = 16, 256


def main() -> int:
    import torch, pandas as pd
    from transformers import AutoTokenizer, AutoModel
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prefix = "query: " if "e5" in a.model.lower() else ""
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[encode] {a.model} device={device} prefix={prefix!r}")
    tok = AutoTokenizer.from_pretrained(a.model, cache_dir=cfg.HF_CACHE_DIR)
    m = AutoModel.from_pretrained(a.model, cache_dir=cfg.HF_CACHE_DIR).to(device).eval()
    for p in m.parameters():
        p.requires_grad_(False)

    df = pd.read_csv(cfg.PROCESSED_FILE)
    lyc = next(c for c in ["lyrics_cleaned", "lyrics", "lyric", "plain_lyrics"] if c in df.columns)
    lyrics = [prefix + t for t in df[lyc].fillna("").astype(str).tolist()]

    out = []
    with torch.no_grad():
        for b in range(0, len(lyrics), BATCH):
            enc = tok(lyrics[b:b + BATCH], padding=True, truncation=True,
                      max_length=MAX_LEN, return_tensors="pt").to(device)
            h = m(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (h * mask).sum(1) / mask.sum(1).clamp(min=1e-9)   # mean-pool
            pooled = torch.nn.functional.normalize(pooled, dim=-1)
            out.append(pooled.cpu().float().numpy())
            if b % (BATCH * 40) == 0:
                print(f"  {b}/{len(lyrics)}", flush=True)
    E = np.concatenate(out, 0).astype(np.float32)
    np.save(a.out, E)
    print(f"[encode] saved {a.out} shape={E.shape}  dim={E.shape[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
