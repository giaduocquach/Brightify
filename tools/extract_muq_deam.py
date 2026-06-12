"""Extract MuQ embeddings for the DEAM corpus → data/external/deam/deam_muq.npy
(aligned to deam_ids.json order), so we can train/validate a MuQ→V-A probe and
ensemble it with MERT (Phase 2, V-A hardening). Frozen MuQ-large, same clip strategy
as the catalog extractor (15% offset, 15s, mean over hidden states + time).

Run: python -m tools.extract_muq_deam
"""
from __future__ import annotations
import glob, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEAM_DIR = "data/external/deam"
IDS = f"{DEAM_DIR}/deam_ids.json"
OUT = f"{DEAM_DIR}/deam_muq.npy"
MODEL_ID = "OpenMuQ/MuQ-large-msd-iter"
SR = 24_000
CLIP = 15.0


def main() -> int:
    import librosa, torch
    from muq import MuQ
    from dotenv import load_dotenv
    load_dotenv()
    ids = json.load(open(IDS))
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[muq-deam] loading {MODEL_ID} on {dev} for {len(ids)} songs", flush=True)
    model = MuQ.from_pretrained(MODEL_ID, token=os.environ.get("HF_TOKEN") or None)
    model = model.to(dev).eval()

    def enc(mp3):
        try:
            dur = librosa.get_duration(path=mp3)
        except Exception:
            return None
        offs = [min(30.0, max(0.0, dur * 0.15))]
        if dur > 90:
            offs.append(min(75.0, dur * 0.45))
        embs = []
        for off in offs:
            try:
                wav, _ = librosa.load(mp3, sr=SR, mono=True, offset=off, duration=CLIP)
                if wav.size < SR:
                    continue
                with torch.no_grad():
                    out = model(torch.tensor(wav, dtype=torch.float32, device=dev)[None], output_hidden_states=True)
                stacked = torch.stack(list(out.hidden_states), dim=0)   # (L,1,T,D)
                embs.append(stacked.mean(0).mean(1).squeeze(0).cpu().numpy())
            except Exception:
                continue
        return np.mean(embs, axis=0) if embs else None

    D = 1024
    X = np.full((len(ids), D), np.nan, dtype=np.float32)
    ok = 0
    for i, sid in enumerate(ids):
        m = glob.glob(f"{DEAM_DIR}/**/{sid}.mp3", recursive=True)
        if not m:
            continue
        e = enc(m[0])
        if e is not None and e.shape[0] == D:
            X[i] = e; ok += 1
        if (i + 1) % 100 == 0:
            np.save(OUT, X)
            print(f"  {i+1}/{len(ids)}  ok={ok}", flush=True)
    np.save(OUT, X)
    print(f"[muq-deam] saved {OUT}  ok={ok}/{len(ids)}  shape={X.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
