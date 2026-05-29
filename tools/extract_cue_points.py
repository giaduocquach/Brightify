"""Extract crossfade cue points + downbeat grid from an audio file.

Used by Smart Crossfade Phase 3:
- fade_out_cue_s: where in trackA to start the outro fade (before silence/applause)
- fade_in_cue_s: where in trackB to start playing from (after intro silence)
- downbeat_times_json: list of downbeat timestamps for beat-aligned mixing

Methods:
- Structural boundaries: librosa.segment.agglomerative on chroma CQT
  (Foote 2000 novelty curve family)
- Silence: RMS < 0.02 threshold
- Downbeats: librosa.beat.beat_track, taking every 4th beat (assumes 4/4 time signature)

Returns dict with keys above, or None on failure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("extract_cue_points")

# Sample rate is intentionally moderate — cue detection doesn't need 44.1kHz
DEFAULT_SR = 22050
RMS_SILENCE_THRESHOLD = 0.02
FADE_OUT_BUFFER_S = 1.0  # back off 1s from last loud sample so we don't cut a tail
FADE_IN_CAP_S = 15.0     # never skip more than 15s of a track's intro
MIN_FADE_OUT_S = 30.0    # ignore tracks shorter than this for outro detection


def extract_cue_points(audio_path: str | Path, sr: int = DEFAULT_SR,
                       is_danceable: bool = False) -> dict | None:
    """Compute cue points + (optional) downbeats for one audio file.

    Args:
        audio_path: path to MP3/WAV
        sr: target sample rate
        is_danceable: if True, also computes downbeat_times_json (more expensive)

    Returns: dict with keys fade_out_cue_s, fade_in_cue_s, downbeat_times_json (str or None).
             None on hard failure.
    """
    try:
        import librosa
    except ImportError:
        log.warning("librosa not installed — cue point extraction skipped")
        return None

    try:
        y, sr = librosa.load(str(audio_path), sr=sr, mono=True)
        duration = len(y) / sr
        if duration < 10:
            return None  # too short to be worth analysing

        # ── RMS for silence detection ─────────────────────────────
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        rms_times = librosa.times_like(rms, sr=sr, hop_length=512)
        silent_mask = rms < RMS_SILENCE_THRESHOLD

        # ── fade_out_cue: last loud sample minus buffer ───────────
        fade_out_cue = None
        for i in range(len(rms_times) - 1, 0, -1):
            if not silent_mask[i]:
                fade_out_cue = float(rms_times[i] - FADE_OUT_BUFFER_S)
                break
        if fade_out_cue is None or fade_out_cue < MIN_FADE_OUT_S:
            # fallback: 20s before end
            fade_out_cue = max(0.0, duration - 20.0)
        fade_out_cue = max(0.0, min(float(duration), fade_out_cue))

        # ── fade_in_cue: first non-silent + first structural boundary ─
        first_loud_idx = next((i for i in range(len(rms_times)) if not silent_mask[i]), 0)
        first_loud_s = float(rms_times[first_loud_idx]) if first_loud_idx > 0 else 0.0

        boundary_first_s = 0.0
        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            boundaries = librosa.segment.agglomerative(chroma, k=6)
            boundary_times = librosa.frames_to_time(boundaries, sr=sr)
            if len(boundary_times) > 1:
                boundary_first_s = float(boundary_times[1])
        except Exception as e:
            log.debug(f"  chroma segmentation failed: {e}")

        fade_in_cue = max(first_loud_s, boundary_first_s)
        fade_in_cue = min(fade_in_cue, FADE_IN_CAP_S)
        fade_in_cue = max(0.0, fade_in_cue)

        # ── Downbeats (only for danceable tracks) ─────────────────
        downbeat_times_json = None
        if is_danceable:
            try:
                _tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
                # 4/4 assumption: downbeat every 4 beats
                downbeats = [float(t) for t in beats[::4].tolist()]
                if len(downbeats) >= 2:
                    downbeat_times_json = json.dumps([round(t, 3) for t in downbeats])
            except Exception as e:
                log.debug(f"  downbeat tracking failed: {e}")

        return {
            "fade_out_cue_s": round(fade_out_cue, 2),
            "fade_in_cue_s": round(fade_in_cue, 2),
            "downbeat_times_json": downbeat_times_json,
        }
    except Exception as e:
        log.debug(f"  cue extraction failed for {audio_path}: {e}")
        return None
