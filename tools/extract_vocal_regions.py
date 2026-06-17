"""Extract per-track vocal regions (Smart Crossfade Tier 3).

For each track we want two scalars:
- vocal_start_s: first sustained vocal onset  (≈ end of the instrumental intro)
- vocal_end_s:   last sustained vocal offset  (≈ start of the instrumental outro)

Method: separate the **vocal stem** with Demucs (htdemucs), then threshold its
RMS envelope. To avoid clashing two vocal lines, a downstream crossfade blends
over the outgoing instrumental outro into the incoming instrumental intro.

Compute-saving: vocal_start lives in the intro and vocal_end in the outro, so we
only separate the first/last `window_s` seconds of each track (not the middle).
Demucs is heavy and this machine has no CUDA — the batch is **resumable** and
writes a portable CSV (`data/vocal_regions.csv`) so the GPU-heavy part can run
on any box (Colab/cloud) and the CSV merged back via tools.backfill_vocal_regions.

Usage:
    source .venv/bin/activate
    python -m tools.extract_vocal_regions                  # all tracks → CSV
    python -m tools.extract_vocal_regions --limit 10       # sample
    python -m tools.extract_vocal_regions --device mps     # mps|cuda|cpu (auto by default)
    python -m tools.extract_vocal_regions --force          # recompute existing CSV rows
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("extract_vocal_regions")

MUSIC_DIR = cfg.MUSIC_DIR
OUT_CSV = ROOT / "data" / "vocal_regions.csv"

WINDOW_S = 60.0          # how much of the intro / outro to separate
RMS_HOP_S = 0.1          # vocal-envelope frame hop
RMS_WIN_S = 0.2          # vocal-envelope frame length
VOCAL_RATIO = 0.08       # vocal present when stem-RMS > ratio * global vocal peak …
VOCAL_FLOOR = 0.005      # … and above this absolute floor (guards near-silent stems)
MIN_RUN_S = 1.0          # a vocal run must persist this long (ignore separation bleed)
MIN_DURATION_S = 8.0     # too short to analyse
DEMUCS_SR = 44100        # htdemucs native sample rate (load straight to it)

_model = None            # lazily-built htdemucs, reused across tracks in this process


def _get_model(device: str | None):
    global _model
    if _model is None:
        from demucs.pretrained import get_model
        _model = get_model("htdemucs")
        _model.eval()
        if device:
            _model.to(device)
    return _model


def _rms_envelope(mono: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Frame-wise RMS of a mono signal → (rms, frame_start_times_s)."""
    win = max(1, int(RMS_WIN_S * sr))
    hop = max(1, int(RMS_HOP_S * sr))
    n = len(mono)
    if n < win:
        return np.array([float(np.sqrt(np.mean(mono ** 2)))]), np.array([0.0])
    starts = np.arange(0, n - win + 1, hop)
    rms = np.array([np.sqrt(np.mean(mono[s:s + win] ** 2)) for s in starts], dtype=np.float64)
    times = starts / sr
    return rms, times


def _sustained_edges(rms: np.ndarray, times: np.ndarray, thr: float) -> tuple[float | None, float | None]:
    """First and last time where rms stays above thr for >= MIN_RUN_S."""
    min_frames = max(1, int(MIN_RUN_S / RMS_HOP_S))
    above = rms > thr
    first = last = None
    j, n = 0, len(rms)
    while j < n:
        if above[j]:
            k = j
            while k < n and above[k]:
                k += 1
            if (k - j) >= min_frames:
                if first is None:
                    first = float(times[j])
                last = float(times[k - 1])
            j = k
        else:
            j += 1
    return first, last


def _vocal_stem_rms(wav, sr: int, device: str | None) -> tuple[np.ndarray, np.ndarray]:
    """Separate a (channels, samples) torch waveform → vocal-stem RMS envelope."""
    import torch
    from demucs.apply import apply_model
    model = _get_model(device)
    msr = model.samplerate
    if wav.dim() == 1:
        wav = wav.unsqueeze(0)
    if wav.shape[0] == 1:                        # demucs expects stereo
        wav = wav.repeat(2, 1)
    if sr != msr:
        import torchaudio
        wav = torchaudio.functional.resample(wav, sr, msr)
    if device:
        wav = wav.to(device)
    with torch.no_grad():
        out = apply_model(model, wav.unsqueeze(0), device=device or "cpu",
                          split=True, overlap=0.25, progress=False)[0]  # (sources, ch, samples)
    voc = out[model.sources.index("vocals")]     # (channels, samples) at msr
    mono = voc.mean(dim=0).detach().cpu().numpy().astype(np.float64)
    return _rms_envelope(mono, msr)


def extract_vocal_regions(audio_path: str | Path, device: str | None = None,
                          window_s: float = WINDOW_S) -> dict | None:
    """Compute {vocal_start_s, vocal_end_s} for one file (both may be None = instrumental)."""
    try:
        import torch
        import librosa
    except ImportError:
        log.warning("torch/librosa not installed — vocal extraction skipped")
        return None
    try:
        # librosa load avoids torchaudio's torchcodec backend dependency; load straight
        # to demucs' native rate so no resample is needed downstream.
        y, sr = librosa.load(str(audio_path), sr=DEMUCS_SR, mono=False)
        arr = np.atleast_2d(y).astype(np.float32)    # (channels, samples)
        wav = torch.from_numpy(arr)
        dur = wav.shape[1] / sr
        if dur < MIN_DURATION_S:
            return None

        if dur <= 2 * window_s:
            # short enough: separate the whole track once
            rms, times = _vocal_stem_rms(wav, sr, device)
            peak = float(rms.max()) if rms.size else 0.0
            thr = max(VOCAL_FLOOR, VOCAL_RATIO * peak)
            start, end = _sustained_edges(rms, times, thr)
            return {"vocal_start_s": _round(start), "vocal_end_s": _round(end)}

        win = int(window_s * sr)
        intro = wav[:, :win]
        outro = wav[:, -win:]
        outro_offset = dur - window_s
        r_in, t_in = _vocal_stem_rms(intro, sr, device)
        r_out, t_out = _vocal_stem_rms(outro, sr, device)
        # one global threshold across both windows so a loud-chorus-near-end track
        # doesn't drown out a quieter intro vocal
        peak = max(float(r_in.max()) if r_in.size else 0.0,
                   float(r_out.max()) if r_out.size else 0.0)
        thr = max(VOCAL_FLOOR, VOCAL_RATIO * peak)
        start, _ = _sustained_edges(r_in, t_in, thr)             # first vocal in the intro
        _, end_local = _sustained_edges(r_out, t_out, thr)       # last vocal in the outro
        end = (outro_offset + end_local) if end_local is not None else None
        return {"vocal_start_s": _round(start), "vocal_end_s": _round(end)}
    except Exception as e:
        log.debug(f"  vocal extraction failed for {audio_path}: {e}")
        return None


def _round(v: float | None) -> float | None:
    return round(float(v), 2) if v is not None else None


def _resolve_mp3(track_id: str) -> str | None:
    p = MUSIC_DIR / f"{track_id}.mp3"
    return str(p) if p.exists() else None


def _load_done(out_csv: Path) -> set[str]:
    if not out_csv.exists():
        return set()
    done = set()
    with out_csv.open() as f:
        for row in csv.DictReader(f):
            done.add(row["track_id"])
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default=None, help="mps | cuda | cpu (default: demucs auto)")
    ap.add_argument("--window", type=float, default=WINDOW_S)
    ap.add_argument("--force", action="store_true", help="recompute rows already in the CSV")
    ap.add_argument("--out", default=str(OUT_CSV))
    args = ap.parse_args()

    from db.engine import SessionLocal
    from db.models import Song

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    done = set() if args.force else _load_done(out_csv)

    session = SessionLocal()
    rows = session.query(Song.track_id).filter(Song.has_mp3.is_(True)).all()
    session.close()
    track_ids = [tid for (tid,) in rows if tid not in done]
    if args.limit:
        track_ids = track_ids[:args.limit]

    total = len(track_ids)
    if total == 0:
        log.info("Nothing to do — all tracks already in CSV (use --force to recompute).")
        return
    log.info(f"Extracting vocal regions for {total} tracks (device={args.device or 'auto'})…")

    write_header = not out_csv.exists() or args.force
    mode = "w" if args.force else "a"
    t0 = time.monotonic()
    with out_csv.open(mode, newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["track_id", "vocal_start_s", "vocal_end_s"])
        for i, tid in enumerate(track_ids):
            mp3 = _resolve_mp3(tid)
            if not mp3:
                continue
            res = extract_vocal_regions(mp3, device=args.device, window_s=args.window)
            vs = res.get("vocal_start_s") if res else None
            ve = res.get("vocal_end_s") if res else None
            writer.writerow([tid, "" if vs is None else vs, "" if ve is None else ve])
            f.flush()
            if (i + 1) % 10 == 0 or (i + 1) == total:
                rate = (time.monotonic() - t0) / (i + 1)
                eta_min = rate * (total - i - 1) / 60.0
                log.info(f"  {i+1}/{total}  ({rate:.1f}s/track, ETA {eta_min:.0f} min)")

    log.info(f"Done → {out_csv}")


if __name__ == "__main__":
    main()
