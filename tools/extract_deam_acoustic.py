"""Extract librosa tempo + RMS-loudness for DEAM mp3s, to GROUND an arousal model
on DEAM human labels. DEAM annotations have only V-A (no acoustic features), so we
measure tempo+loudness ourselves — the universal acoustic arousal determinants
(Eerola; Schubert) that transfer cross-corpus far better than 768-dim embeddings.

Output: data/external/deam/deam_acoustic.json  {song_id: {tempo, rms_db}}
Run: python -m tools.extract_deam_acoustic
"""
from __future__ import annotations
import glob, json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEAM_DIR = "data/external/deam"
IDS = f"{DEAM_DIR}/deam_ids.json"
OUT = f"{DEAM_DIR}/deam_acoustic.json"
SR = 22050
DUR = 20.0
MAX_N = 900   # enough to fit a 3-feature arousal model + CV; caps extraction time


def _find_mp3(song_id) -> str | None:
    for cand in glob.glob(f"{DEAM_DIR}/**/{song_id}.mp3", recursive=True):
        return cand
    return None


def main() -> int:
    import librosa
    ids = json.load(open(IDS)) if os.path.exists(IDS) else None
    if ids is None:
        ids = [int(os.path.basename(p)[:-4]) for p in glob.glob(f"{DEAM_DIR}/**/*.mp3", recursive=True)]
    rng = np.random.default_rng(42)
    if len(ids) > MAX_N:
        ids = sorted(rng.choice(ids, MAX_N, replace=False).tolist())
    out = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [s for s in ids if str(s) not in out]
    print(f"[deam-acoustic] {len(todo)} to extract (of {len(ids)})", flush=True)
    for i, sid in enumerate(todo):
        mp3 = _find_mp3(sid)
        if not mp3:
            continue
        try:
            y, _ = librosa.load(mp3, sr=SR, mono=True, offset=15.0, duration=DUR)
            if y.size < SR:
                y, _ = librosa.load(mp3, sr=SR, mono=True, duration=DUR)
            tempo = float(np.ravel(librosa.beat.beat_track(y=y, sr=SR)[0])[0])
            rms = float(np.sqrt(np.mean(y ** 2)) + 1e-9)
            out[str(sid)] = {"tempo": round(tempo, 2), "rms_db": round(20 * np.log10(rms), 2)}
        except Exception:
            continue
        if (i + 1) % 100 == 0:
            json.dump(out, open(OUT, "w"))
            print(f"  {i+1}/{len(todo)}", flush=True)
    json.dump(out, open(OUT, "w"))
    t = np.array([v["tempo"] for v in out.values()])
    print(f"[deam-acoustic] {len(out)} songs → {OUT}  tempo mean={t.mean():.0f} std={t.std():.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
