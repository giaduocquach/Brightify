"""Phase 4 — INDEPENDENT arousal reference via CLAP "ears" (D2: validate arousal by ears).

CLAP is a different model family than MERT/MuQ and reads audio directly (not lyrics), so
agreement between the served arousal and a CLAP-derived arousal is genuine convergent
validity — it breaks the MERT/lyrics monoculture. BACKTEST-ONLY (never served). Two steps:
  1. CALIBRATE on DEAM-human: CLAP zero-shot arousal (high-vs-low-arousal prompt projection
     in the *aligned* audio_embeds/text_embeds space) vs DEAM-human arousal → proves
     CLAP-ears actually measures arousal before we trust it.
  2. CONVERGE on VN catalog: CLAP-ears arousal on a fresh sample of catalog mp3s vs the
     served v6g arousal → independent-model agreement on our own songs.

IMPORTANT: get_*_features here returns the UNPROJECTED tower pooler (not joint-space), so we
use the projected text_embeds/audio_embeds from the full ClapModel forward — the only
cross-modal-aligned representation. Frozen CLAP, zero-shot, no fine-tune.
Run: python -m tools.clap_va_reference
"""
from __future__ import annotations
import glob, json, os, signal, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

DEAM = "data/external/deam"
MUSIC = "music_files"
MODEL_ID = "laion/larger_clap_music_and_speech"
CACHE = "models_cache"
SR = 48000
CLIP = 10.0
N_DEAM = 350
N_CAT = 500            # VN catalog sample for the convergence check
PER_FILE_TIMEOUT = 25  # guard against a single mp3 hanging librosa forever
DEAM_CACHE = "data/clap_deam_arousal.json"
CAT_CACHE = "data/clap_catalog_arousal.json"

HIGH_A = ["bài hát tràn đầy năng lượng sôi động mạnh mẽ dồn dập nhịp nhanh",
          "a high-energy intense fast loud driving exciting song"]
LOW_A = ["nhạc nhẹ nhàng yên tĩnh êm ái chậm rãi thư giãn",
         "a calm quiet gentle slow relaxing low-energy song"]


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _deam_arousal():
    fs = glob.glob(f"{DEAM}/**/song_level/static_annotations_averaged_songs_*.csv", recursive=True)
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df.columns = [c.strip() for c in df.columns]
    return {int(r.song_id): (r.arousal_mean - 1) / 8 for r in df.itertuples()}


def _load_clap():
    import torch
    from transformers import ClapModel, ClapProcessor
    proc = ClapProcessor.from_pretrained(MODEL_ID, cache_dir=CACHE)
    model = ClapModel.from_pretrained(MODEL_ID, cache_dir=CACHE).eval()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(dev)
    return model, proc, dev, torch


class _Clap:
    """Holds the model + a fixed dummy in each modality so a single full-forward yields the
    *projected* (aligned) text_embeds / audio_embeds for whichever side we care about."""

    def __init__(self):
        self.model, self.proc, self.dev, self.torch = _load_clap()
        # fixed dummy audio (for text-only embedding) and dummy text (for audio-only)
        self._dummy_audio = self.proc(audio=np.zeros(int(SR * 2), np.float32),
                                      sampling_rate=SR, return_tensors="pt")
        self._dummy_text = self.proc(text=["music"], return_tensors="pt", padding=True)

    def text_embeds(self, prompts):
        t = self.proc(text=prompts, return_tensors="pt", padding=True)
        ins = {**{k: v for k, v in t.items()},
               **{k: v for k, v in self._dummy_audio.items()}}
        ins = {k: v.to(self.dev) for k, v in ins.items()}
        with self.torch.no_grad():
            out = self.model(**ins)
        e = out.text_embeds
        e = e / e.norm(dim=-1, keepdim=True)
        return e.cpu().float().numpy()

    def audio_embed(self, y):
        a = self.proc(audio=y, sampling_rate=SR, return_tensors="pt")
        ins = {**{k: v for k, v in a.items()},
               **{k: v for k, v in self._dummy_text.items()}}
        ins = {k: v.to(self.dev) for k, v in ins.items()}
        with self.torch.no_grad():
            out = self.model(**ins)
        e = out.audio_embeds
        e = e / e.norm(dim=-1, keepdim=True)
        return e.cpu().float().numpy()[0]


def _load_audio(path):
    import librosa
    dur = librosa.get_duration(path=path)
    off = min(30.0, max(0.0, dur * 0.15))
    y, _ = librosa.load(path, sr=SR, mono=True, offset=off, duration=CLIP)
    return y if len(y) >= 1024 else None


def _score(emb, hi, lo):
    return float(emb @ hi - emb @ lo)


def _extract(paths_by_id, clap, hi, lo, cache_path, label):
    """{id: clap-ears-arousal}; SIGALRM-guarded, resumable, swallow-free errors."""
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    signal.signal(signal.SIGALRM, _alarm)
    skipped = 0
    items = list(paths_by_id.items())
    for i, (sid, path) in enumerate(items):
        if str(sid) in cache:
            continue
        signal.alarm(PER_FILE_TIMEOUT)
        try:
            y = _load_audio(path)
            cache[str(sid)] = _score(clap.audio_embed(y), hi, lo) if y is not None else None
        except _Timeout:
            cache[str(sid)] = None; skipped += 1
            print(f"  [skip] {label} {sid} >{PER_FILE_TIMEOUT}s", flush=True)
        except Exception as ex:
            cache[str(sid)] = None; skipped += 1
            print(f"  [err] {label} {sid}: {ex}", flush=True)
        finally:
            signal.alarm(0)
        if (i + 1) % 50 == 0:
            json.dump(cache, open(cache_path, "w"))
            print(f"  {label} {i+1}/{len(items)} (skipped {skipped})", flush=True)
    json.dump(cache, open(cache_path, "w"))
    return cache


def main() -> int:
    clap = _Clap()
    te = clap.text_embeds(HIGH_A + LOW_A)
    hi = te[:len(HIGH_A)].mean(0); lo = te[len(HIGH_A):].mean(0)
    hi /= np.linalg.norm(hi); lo /= np.linalg.norm(lo)
    print(f"[clap] loaded on {clap.dev}; projected arousal text-axis ‖hi-lo‖={np.linalg.norm(hi-lo):.3f}", flush=True)

    # ---- 1. CALIBRATE on DEAM-human ----
    ids = json.load(open(f"{DEAM}/deam_ids.json")); arou = _deam_arousal()
    mp3s = {}
    for p in glob.glob(f"{DEAM}/**/*.mp3", recursive=True):
        try: mp3s[int(os.path.splitext(os.path.basename(p))[0])] = p
        except ValueError: pass
    cand = {s: mp3s[s] for s in ids if s in arou and s in mp3s}
    cand = dict(list(cand.items())[:N_DEAM])
    dcache = _extract(cand, clap, hi, lo, DEAM_CACHE, "DEAM")
    cs = np.array([dcache[str(s)] for s in cand if dcache.get(str(s)) is not None])
    ys = np.array([arou[s] for s in cand if dcache.get(str(s)) is not None])
    rho_deam = spearmanr(cs, ys).correlation
    print(f"\n[CALIBRATE] CLAP-ears arousal vs DEAM-human (n={len(cs)}): ρ={rho_deam:+.3f}")
    print("  (positive ⇒ CLAP zero-shot genuinely reads arousal — reference is valid)")

    # ---- 2. CONVERGE on VN catalog vs served v6g arousal ----
    served = json.load(open(cfg.RELABELED_EMOTIONS_FILE))
    df = pd.read_csv(cfg.PROCESSED_FILE)
    cat_paths = {}
    for t in df["track_id"].astype(str):
        p = f"{MUSIC}/{t}.mp3"
        if os.path.exists(p) and isinstance(served.get(t), dict) and served[t].get("arousal") is not None:
            cat_paths[t] = p
        if len(cat_paths) >= N_CAT:
            break
    ccache = _extract(cat_paths, clap, hi, lo, CAT_CACHE, "CAT")
    tids = [t for t in cat_paths if ccache.get(t) is not None]
    ca = np.array([ccache[t] for t in tids])
    sa = np.array([float(served[t]["arousal"]) for t in tids])
    rho_cat = spearmanr(ca, sa).correlation
    rng = np.random.RandomState(0)
    boot = [spearmanr(ca[idx], sa[idx]).correlation
            for idx in (rng.randint(0, len(ca), len(ca)) for _ in range(1000))]
    ci = np.percentile(boot, [2.5, 97.5])
    print(f"\n[CONVERGE] catalog CLAP-ears arousal vs served v6g arousal (n={len(tids)}):")
    print(f"  ρ={rho_cat:+.3f}  95%CI[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print("  (independent model family + reads audio not lyrics ⇒ genuine convergent validity)")

    out = {"clap_deam_arousal_rho": round(float(rho_deam), 4),
           "clap_catalog_vs_served_rho": round(float(rho_cat), 4),
           "ci": [round(float(ci[0]), 4), round(float(ci[1]), 4)],
           "n_deam": len(cs), "n_catalog": len(tids)}
    json.dump(out, open("data/clap_va_reference.json", "w"))
    print(f"\n→ data/clap_va_reference.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
