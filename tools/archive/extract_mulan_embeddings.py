"""Extract MuQ-MuLan audio embeddings for the catalog (A/B vs the MuQ backbone).

MuQ-MuLan (OpenMuQ/MuQ-MuLan-large) = MuQ audio tower + text tower, contrastively aligned
(MuLan-style). Its audio embedding lives in a text-shared semantic space — may help mood
similarity OR hurt fine acoustic similarity. Only an end-metric A/B decides.

Single 15 s mid-clip per song (sr 24 kHz), L2-normalised, catalog index order.
Run: python -m tools.extract_mulan_embeddings  → data/mulan_embeddings.npy
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = str(cfg.DATA_DIR / "mulan_embeddings.npy")
SR, CLIP_DUR = 24_000, 15.0


def main() -> int:
    import torch, librosa, pandas as pd
    from muq import MuQMuLan
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[mulan] loading OpenMuQ/MuQ-MuLan-large on {device}…", flush=True)
    model = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large", cache_dir=cfg.HF_CACHE_DIR).eval().to(device)

    df = pd.read_csv(cfg.PROCESSED_FILE)
    tids = df["track_id"].astype(str).tolist()
    music = PROJECT_ROOT / "music_files"
    dim = None; embs = None; done = []
    if os.path.exists(OUT) and os.path.exists(OUT + ".meta.json"):
        embs = np.load(OUT); done = set(json.load(open(OUT + ".meta.json"))["done"])
        print(f"[mulan] resume: {len(done)} done")

    for i, tid in enumerate(tids):
        if embs is not None and tid in done:
            continue
        mp3 = music / f"{tid}.mp3"
        vec = None
        if mp3.exists():
            try:
                wav, _ = librosa.load(str(mp3), sr=SR, mono=True, duration=CLIP_DUR,
                                      offset=max(0.0, (librosa.get_duration(path=str(mp3)) - CLIP_DUR) / 2))
                wav_t = torch.tensor(wav, dtype=torch.float32, device=device).unsqueeze(0)
                with torch.no_grad():
                    e = model(wavs=wav_t).squeeze(0).cpu().float().numpy()
                n = float(np.linalg.norm(e))
                vec = e / n if n > 1e-9 else None
            except Exception as ex:
                print(f"  [skip] {tid}: {type(ex).__name__}", flush=True)
        if dim is None and vec is not None:
            dim = len(vec); embs = np.zeros((len(tids), dim), np.float32) if embs is None else embs
        if vec is not None:
            embs[i] = vec; done = (set(done) | {tid}) if isinstance(done, (set, list)) else {tid}
        if i % 400 == 0:
            print(f"  {i}/{len(tids)}  dim={dim}", flush=True)
            if embs is not None:
                np.save(OUT, embs); json.dump({"done": list(done)}, open(OUT + ".meta.json", "w"))
    np.save(OUT, embs); json.dump({"done": list(done)}, open(OUT + ".meta.json", "w"))
    cov = sum(1 for r in embs if np.linalg.norm(r) > 1e-9)
    print(f"[mulan] saved {OUT} shape={embs.shape} covered={cov}/{len(tids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
