"""
Brightify – Phase 5: Audio Feature Extraction v3.0
(Essentia DSP + Essentia-TF DEAM V-A + Librosa fallback)

Extracts audio features from MP3 files in music_files/ and writes them
to checkpoints/phase5_features.csv for the next pipeline phase.

Pipeline position: Phase 5 (after Phase 4 Lyrics gate)
Input:  checkpoints/phase4_lyrics_gated.csv (tracks with lyrics, strict)
        Falls back to: phase4_lyrics.csv → phase3_downloaded.csv → raw CSV
Output: checkpoints/phase5_features.csv (tracks with audio features)

Features extracted (DSP — Essentia/Librosa):
  - energy, key, loudness, loudness_lufs, mode, tempo, time_signature

Features extracted (Pre-trained TF models):
  - danceability  (EffNet-Discogs classification head, 16kHz)
  - valence       (DEAM V-A regression via MSD-MusiCNN)
  - arousal       (DEAM V-A regression via MSD-MusiCNN)

Removed in v3.0 (weight=0 in recommender, degenerate at 44kHz):
  acousticness, speechiness, instrumentalness, liveness, timbre_bright,
  audio_embedding (400-dim), voice_gender, mood_tags, instrument_tags.

FFT safety: all audio is resampled to 44100 Hz mono with even sample count.

Usage:
    python -m tools.extract_audio_features                # Extract all
    python -m tools.extract_audio_features --limit 50     # Limit
    python -m tools.extract_audio_features --test         # 3 tracks
    python -m tools.extract_audio_features --reprocess    # Re-extract all
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
from tqdm import tqdm

log = logging.getLogger("brightify.audio_features")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"
MUSIC_DIR = PROJECT_ROOT / "music_files"
LYRICS_CSV = CHECKPOINT_DIR / "phase4_lyrics_gated.csv"
LYRICS_CSV_FALLBACK = CHECKPOINT_DIR / "phase4_lyrics.csv"
DOWNLOADED_CSV = CHECKPOINT_DIR / "phase3_downloaded.csv"
OUTPUT_CSV = CHECKPOINT_DIR / "phase5_features.csv"
RAW_CSV = DATA_DIR / "vietnamese_music_complete_dataset_full.csv"
PROCESSED_CSV = DATA_DIR / "vietnamese_music_processed_full.csv"
MODEL_CACHE_DIR = PROJECT_ROOT / "models_cache"

SAMPLE_RATE = 44100  # Standard sample rate for Essentia DSP


# ── Essentia TF Model Registry ──────────────────────────────────────────────

MODEL_BASE_URL = "https://essentia.upf.edu/models"

MODEL_REGISTRY = {
    # EffNet-Discogs feature extractor — 1280-dim for danceability head
    "discogs_effnet": {
        "url": f"{MODEL_BASE_URL}/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb",
        "type": "extractor",
        "predict_cls": "TensorflowPredictEffnetDiscogs",
        "output_node": "PartitionedCall:1",
    },

    # Danceability (binary, EffNet-Discogs head)
    # Classes: ['not_danceable', 'danceable'] — index 1 is danceable prob
    "danceability": {
        "url": f"{MODEL_BASE_URL}/classification-heads/danceability/danceability-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    # Voice vs instrumental (classes: instrumental, voice).
    "voice_instrumental": {
        "url": (
            f"{MODEL_BASE_URL}/classification-heads/voice_instrumental/"
            "voice_instrumental-discogs-effnet-1.pb"
        ),
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    "audioset_yamnet": {
        "url": (
            f"{MODEL_BASE_URL}/audio-event-recognition/audioset-yamnet/"
            "audioset-yamnet-1.pb"
        ),
        "type": "vggish",
        "input_node": "melspectrogram",
        "output_node": "activations",
    },

    # MSD-MusiCNN feature extractor (200-dim embeddings → DEAM V-A head)
    "msd_musicnn": {
        "url": f"{MODEL_BASE_URL}/feature-extractors/musicnn/msd-musicnn-1.pb",
        "type": "extractor",
        "predict_cls": "TensorflowPredictMusiCNN",
        "output_node": "model/batch_normalization_10/batchnorm/add_1",
    },

    # DEAM Valence-Arousal regression (Alonso-Jiménez et al. 2023, DEAM dataset)
    # Input: 200-dim MusiCNN embeddings, Output: [valence, arousal] ≈ [0, 2]
    "deam_valence_arousal": {
        "url": f"{MODEL_BASE_URL}/classification-heads/deam/deam-msd-musicnn-2.pb",
        "type": "musicnn_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Identity",
    },

    # MTG-Jamendo Mood/Theme (56 classes, EffNet-Discogs head, REQUIRES 16kHz input).
    # At 44.1kHz (original pipeline) → 99% "corporate" (degenerate).
    # At 16kHz → discriminative mood labels (epic, meditative, emotional, etc.).
    # Re-added 2026-06-09 with 16kHz fix (patch_tags_16k).
    "mtg_jamendo_moodtheme": {
        "url": (
            f"{MODEL_BASE_URL}/classification-heads/mtg_jamendo_moodtheme/"
            "mtg_jamendo_moodtheme-discogs-effnet-1.pb"
        ),
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Sigmoid",
    },

    # MTG-Jamendo Instrument (40 classes, EffNet-Discogs head, REQUIRES 16kHz input).
    # At 44.1kHz → 98% "trumpet" (degenerate).
    # At 16kHz → meaningful instrument mix (guitar, piano, saxophone, beat, etc.).
    "mtg_jamendo_instrument": {
        "url": (
            f"{MODEL_BASE_URL}/classification-heads/mtg_jamendo_instrument/"
            "mtg_jamendo_instrument-discogs-effnet-1.pb"
        ),
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Sigmoid",
    },
}

# Loaded model instances (lazy singleton)
_loaded_models = {}


def _ensure_model(name: str) -> Path:
    """Download model file if not cached, return local path."""
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    info = MODEL_REGISTRY[name]
    url = info["url"]
    filename = url.split("/")[-1]
    local_path = MODEL_CACHE_DIR / filename
    if local_path.exists() and local_path.stat().st_size > 1000:
        return local_path

    # Try up to 3 times with increasing timeout
    import urllib.request
    for attempt in range(3):
        log.info(f"  Downloading model: {name} ({filename})... (attempt {attempt + 1}/3)")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Brightify/6.0"})
            with urllib.request.urlopen(req, timeout=60 * (attempt + 1)) as resp:
                data = resp.read()
            local_path.write_bytes(data)
            log.info(f"  ✓ {filename} ({len(data) / 1e6:.1f} MB)")
            return local_path
        except Exception as e:
            log.warning(f"  ✗ Attempt {attempt + 1} failed for {name}: {e}")
            local_path.unlink(missing_ok=True)
            if attempt < 2:
                import time as _time
                _time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"Failed to download model {name} after 3 attempts")


def _get_model(name: str):
    """Get a loaded TF model instance (lazy, cached). Returns None if unavailable."""
    if name in _loaded_models:
        return _loaded_models[name]
    try:
        import essentia.standard as es
        info = MODEL_REGISTRY[name]
        model_path = str(_ensure_model(name))

        if info["type"] == "extractor":
            # Standalone feature extractor — uses dedicated predict class
            predict_cls = getattr(es, info["predict_cls"])
            kwargs = {"graphFilename": model_path}
            if "output_node" in info:
                kwargs["output"] = info["output_node"]
            model = predict_cls(**kwargs)
        elif info["type"] in ("effnet_head", "musicnn_head"):
            # Classification head — uses generic TensorflowPredict2D with custom nodes
            model = es.TensorflowPredict2D(
                graphFilename=model_path,
                input=info["input_node"],
                output=info["output_node"],
            )
        elif info["type"] == "vggish":
            model = es.TensorflowPredictVGGish(
                graphFilename=model_path,
                input=info["input_node"],
                output=info["output_node"],
            )
        else:
            raise ValueError(f"Unknown model type: {info['type']}")

        _loaded_models[name] = model
        return model
    except Exception as e:
        log.warning(f"  ⚠ Model {name} unavailable: {e}")
        _loaded_models[name] = None
        return None


# ── FFT-safe audio loader ───────────────────────────────────────────────────

def _load_audio_safe(mp3_path: Path) -> np.ndarray | None:
    """Load MP3 to mono float32 numpy array at 44100 Hz with even sample count.
    Uses ffmpeg for decoding to avoid codec issues.
    """
    try:
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        # Decode to 44100 Hz mono PCM 16-bit WAV
        cmd = [
            ffmpeg_bin, "-i", str(mp3_path),
            "-ar", str(SAMPLE_RATE),
            "-ac", "1",
            "-sample_fmt", "s16",
            "-y", tmp_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            return None

        # Load WAV
        import wave
        with wave.open(tmp_path, "rb") as wf:
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # Ensure even number of samples (FFT requirement)
        if len(audio) % 2 != 0:
            audio = audio[:-1]

        return audio if len(audio) > SAMPLE_RATE else None  # Skip < 1s
    except Exception as e:
        log.debug(f"  Audio load failed for {mp3_path}: {e}")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── LUFS measurement (ITU-R BS.1770 / EBU R128) ──────────────────────────────

def measure_lufs(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float | None:
    """Integrated loudness in LUFS per ITU-R BS.1770-4.

    Used by Smart Crossfade Phase 2 to LUFS-normalize playback across tracks.
    Returns None if measurement fails or value is outside the plausible range
    (audio shorter than ~3s, complete silence, or non-finite output).
    Target reference for normalization is -14 LUFS (Spotify standard).
    """
    try:
        import pyloudnorm as pyln
    except ImportError:
        log.warning("pyloudnorm not installed — LUFS measurement skipped")
        return None
    try:
        # BS.1770 requires audio >= ~0.4s (a single integration block).
        # pyloudnorm needs at least 1 block, so guard against very short clips.
        if audio is None or len(audio) < int(0.5 * sample_rate):
            return None
        meter = pyln.Meter(sample_rate)
        loudness = meter.integrated_loudness(audio)
        if not np.isfinite(loudness) or loudness < -70 or loudness > 0:
            return None
        return round(float(loudness), 2)
    except Exception as e:
        log.debug(f"  LUFS measure failed: {e}")
        return None


# ── Essentia extraction (DSP + pre-trained TF models) ────────────────────────

def _extract_essentia_dsp(audio: np.ndarray) -> dict | None:
    """Extract low-level DSP features using Essentia (no TF models)."""
    try:
        import essentia.standard as es

        # Rhythm
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, beats_confidence, _, beats_intervals = rhythm_extractor(audio)

        # Key/mode
        key_extractor = es.KeyExtractor()
        key_str, scale, key_strength = key_extractor(audio)

        key_map = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
                    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
                    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
        key_int = key_map.get(key_str, 0)
        mode_int = 1 if scale == "major" else 0

        # Energy / loudness
        loudness = es.Loudness()(audio)
        loudness_db = 20 * np.log10(max(loudness, 1e-10))

        # RMS energy normalized
        rms = np.sqrt(np.mean(audio ** 2))
        energy_norm = min(rms / 0.3, 1.0)

        # Beat-based time signature estimation
        time_signature = _estimate_time_signature(beats_intervals, bpm)

        # LUFS (ITU-R BS.1770) for Smart Crossfade — optional, returns None on failure
        loudness_lufs = measure_lufs(audio, SAMPLE_RATE)

        return {
            "energy": round(float(energy_norm), 4),
            "key": int(key_int),
            "loudness": round(float(loudness_db), 2),
            "loudness_lufs": loudness_lufs,
            "mode": int(mode_int),
            "tempo": round(float(bpm), 2),
            "time_signature": time_signature,
        }
    except Exception as e:
        log.debug(f"  Essentia DSP extraction failed: {e}")
        return None


def _estimate_time_signature(beat_intervals: np.ndarray, bpm: float) -> int:
    """Estimate time signature from beat intervals (3/4, 4/4, 6/8, etc.)."""
    if len(beat_intervals) < 4:
        return 4
    try:
        median_interval = float(np.median(beat_intervals))
        if median_interval <= 0:
            return 4
        # Group beats into bars by detecting accent patterns
        # A 3/4 waltz has ~3 beats per bar, 4/4 has ~4
        bar_duration_4 = median_interval * 4
        bar_duration_3 = median_interval * 3
        # If tempo suggests waltz range (70-120 BPM) and intervals cluster in 3s
        if 70 <= bpm <= 130:
            # Check variance of intervals grouped by 3 vs 4
            def group_var(n):
                grouped = [sum(beat_intervals[i:i+n]) for i in range(0, len(beat_intervals)-n+1, n)]
                return float(np.std(grouped)) if len(grouped) > 2 else float('inf')
            var3 = group_var(3)
            var4 = group_var(4)
            if var3 < var4 * 0.7:
                return 3
        return 4
    except Exception:
        return 4


def _extract_tf_features(audio: np.ndarray) -> dict:
    """Extract features using Essentia pre-trained TF models.

    Architecture:
    1. EffNet-Discogs (16kHz, 1280-dim) → danceability head
    2. MSD-MusiCNN (44kHz, 200-dim) → DEAM head → [valence, arousal]
    """
    results = {}
    import essentia.standard as es

    # ── Step 1: Danceability via EffNet-Discogs (1280-dim head) ──
    # Note: EffNet requires 16kHz input for discriminative embeddings.
    # The main audio array here is 44kHz — danceability at correct 16kHz
    # is handled separately by _extract_danceability_16k / --patch-dance.
    # We still run it here at 44kHz as a best-effort default.
    try:
        effnet_1280 = _get_model("discogs_effnet")
        effnet_embeddings_1280 = effnet_1280(audio) if effnet_1280 is not None else None
        model = _get_model("danceability")
        if model is not None and effnet_embeddings_1280 is not None:
            predictions = model(effnet_embeddings_1280)
            avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
            # Softmax output: [not_danceable, danceable]
            danceable_prob = float(avg[1]) if len(avg) >= 2 else float(avg[0])
            results["danceability"] = round(np.clip(danceable_prob, 0, 1), 4)
    except Exception as e:
        log.debug(f"  Danceability model failed: {e}")

    # ── Step 2: DEAM Valence-Arousal via MSD-MusiCNN embeddings ──
    # audio → MusiCNN (200-dim) → DEAM regression → [valence, arousal]
    # Raw output ≈ [0, 2] range; normalize by /2 then clip to [0, 1].
    try:
        musicnn_model = _get_model("msd_musicnn")
        deam_model = _get_model("deam_valence_arousal")
        if musicnn_model is not None and deam_model is not None:
            musicnn_embeddings = musicnn_model(audio)
            deam_predictions = deam_model(musicnn_embeddings)
            avg_va = np.mean(deam_predictions, axis=0) if deam_predictions.ndim == 2 else deam_predictions
            if len(avg_va) >= 2:
                valence = float(np.clip(avg_va[0] / 2.0, 0.0, 1.0))
                arousal = float(np.clip(avg_va[1] / 2.0, 0.0, 1.0))
                results["valence"] = round(valence, 4)
                results["arousal"] = round(arousal, 4)
                results["valence_estimated"] = False
                log.debug(f"  DEAM V-A: valence={valence:.3f}, arousal={arousal:.3f}")
    except Exception as e:
        log.debug(f"  DEAM V-A model failed: {e}")

    return results


# ── Librosa extraction (fallback for DSP when Essentia fails) ────────────────

def _extract_librosa_dsp(audio: np.ndarray) -> dict | None:
    """Extract basic DSP features using Librosa as fallback."""
    try:
        import librosa

        y = audio.astype(np.float32)
        sr = SAMPLE_RATE

        # Tempo / beat
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
        else:
            tempo = float(tempo)

        # Key / mode via chroma
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = chroma.mean(axis=1)
        key_int = int(np.argmax(chroma_mean))

        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        major_corr = np.corrcoef(chroma_mean, np.roll(major_profile, key_int))[0, 1]
        minor_corr = np.corrcoef(chroma_mean, np.roll(minor_profile, key_int))[0, 1]
        mode_int = 1 if major_corr >= minor_corr else 0

        # RMS energy
        rms = librosa.feature.rms(y=y)[0]
        energy_norm = float(np.clip(np.mean(rms) / 0.3, 0, 1))

        # Loudness
        rms_mean = float(np.mean(rms))
        loudness_db = 20 * np.log10(max(rms_mean, 1e-10))

        # LUFS (ITU-R BS.1770) for Smart Crossfade
        loudness_lufs = measure_lufs(audio, SAMPLE_RATE)

        return {
            "energy": round(float(energy_norm), 4),
            "key": int(key_int),
            "loudness": round(float(loudness_db), 2),
            "loudness_lufs": loudness_lufs,
            "mode": int(mode_int),
            "tempo": round(float(tempo), 2),
            "time_signature": 4,
        }
    except Exception as e:
        log.debug(f"  Librosa DSP extraction failed: {e}")
        return None


# ── Valence estimation (heuristic, Palmer et al. 2013) ──────────────────────

def _estimate_valence(features: dict) -> float:
    """
    Estimate valence from mode, tempo, energy, and loudness.
    Based on Palmer et al. (2013). Fallback when DEAM model is unavailable.
    """
    mode = features.get("mode", 1)
    tempo = features.get("tempo", 120)
    energy = features.get("energy", 0.5)
    loudness = features.get("loudness", -8)

    mode_contrib = 0.15 if mode == 1 else -0.15
    tempo_norm = np.clip((tempo - 60) / 120, 0, 1)
    tempo_contrib = (tempo_norm - 0.5) * 0.2
    energy_contrib = (energy - 0.5) * 0.15
    loudness_norm = np.clip((loudness + 20) / 20, 0, 1)
    loudness_contrib = (loudness_norm - 0.5) * 0.1

    valence = 0.5 + mode_contrib + tempo_contrib + energy_contrib + loudness_contrib
    return round(float(np.clip(valence, 0, 1)), 4)


# ── main extraction ─────────────────────────────────────────────────────────

def extract_features_for_track(mp3_path: Path) -> dict | None:
    """Extract audio features for a single track.
    Pipeline:
      1. DSP features via Essentia (fallback: Librosa)
      2. ML features via Essentia pre-trained TF models (EffNet-Discogs + DEAM V-A)
      3. Valence: DEAM model (primary), heuristic estimation (fallback)
    """
    audio = _load_audio_safe(mp3_path)
    if audio is None:
        return None

    # 1. DSP features (Essentia primary, Librosa fallback)
    dsp_features = _extract_essentia_dsp(audio)
    dsp_source = "essentia"
    if dsp_features is None:
        dsp_features = _extract_librosa_dsp(audio)
        dsp_source = "librosa"
    if dsp_features is None:
        return None

    # 2. ML features from pre-trained TF models
    tf_features = {}
    try:
        tf_features = _extract_tf_features(audio)
    except Exception as e:
        log.debug(f"  TF model extraction failed: {e}")

    # 3. Merge: TF results override DSP results where available
    features = dict(dsp_features)
    features["audio_feature_source"] = dsp_source

    # ML-based features override DSP proxies
    for key in ["valence", "danceability"]:
        if key in tf_features:
            features[key] = tf_features[key]

    # Valence fallback
    if "valence" not in features:
        features["valence"] = _estimate_valence(features)
        features["valence_estimated"] = True
    else:
        features["valence_estimated"] = tf_features.get("valence_estimated", False)

    # Arousal from DEAM
    if "arousal" in tf_features:
        features["arousal"] = tf_features["arousal"]

    # Mark source as essentia_tf if any TF model succeeded
    if tf_features:
        features["audio_feature_source"] = f"{dsp_source}+tf"

    # Voice/instrumental probability is a quality gate, not a recommendation
    # feature. Run it at the model's native 16 kHz sample rate.
    try:
        audio_16k = _load_audio_16k(mp3_path)
        effnet_model = _get_model("discogs_effnet")
        voice_model = _get_model("voice_instrumental")
        if audio_16k is not None and effnet_model is not None and voice_model is not None:
            predictions = voice_model(effnet_model(audio_16k))
            average = np.mean(predictions, axis=0)
            if len(average) >= 2:
                features["instrumental_probability"] = round(float(average[0]), 5)
                features["voice_probability"] = round(float(average[1]), 5)
            if len(audio_16k) / 16_000 < 150:
                features.update(_extract_yamnet_quality(audio_16k))
    except Exception as e:
        log.debug(f"  voice/instrumental model failed: {e}")

    # ── Smart Crossfade: cue points + downbeats ───────────────────────
    # Reuses the already-loaded `audio` array (no extra disk read).
    # Only computes downbeats when track looks danceable to save CPU.
    try:
        is_danceable = float(features.get("danceability") or 0) >= 0.7
        cues = _extract_cue_points_from_array(audio, SAMPLE_RATE, is_danceable)
        if cues:
            features.update(cues)
    except Exception as e:
        log.debug(f"  cue point extraction failed: {e}")

    return features


def _extract_cue_points_from_array(audio: np.ndarray, sr: int, is_danceable: bool) -> dict | None:
    """Wrap tools.extract_cue_points for an in-memory array (no MP3 reread)."""
    try:
        import json as _json
        import librosa

        duration = len(audio) / sr
        if duration < 10:
            return None

        rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
        rms_times = librosa.times_like(rms, sr=sr, hop_length=512)
        silent = rms < 0.02

        # fade_out: last non-silent − 1s
        fade_out = None
        for i in range(len(rms_times) - 1, 0, -1):
            if not silent[i]:
                fade_out = float(rms_times[i] - 1.0)
                break
        if fade_out is None or fade_out < 30:
            fade_out = max(0.0, duration - 20.0)
        fade_out = max(0.0, min(float(duration), fade_out))

        # fade_in: first non-silent + first structural boundary
        first_loud = next((float(rms_times[i]) for i in range(len(rms_times)) if not silent[i]), 0.0)
        boundary = 0.0
        try:
            chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
            bounds = librosa.segment.agglomerative(chroma, k=6)
            btimes = librosa.frames_to_time(bounds, sr=sr)
            if len(btimes) > 1:
                boundary = float(btimes[1])
        except Exception:
            pass
        fade_in = max(0.0, min(15.0, max(first_loud, boundary)))

        downbeat_json = None
        if is_danceable:
            try:
                _t, beats = librosa.beat.beat_track(y=audio, sr=sr, units='time')
                downbeats = [round(float(t), 3) for t in beats[::4].tolist()]
                if len(downbeats) >= 2:
                    downbeat_json = _json.dumps(downbeats)
            except Exception:
                pass

        return {
            "fade_out_cue_s": round(fade_out, 2),
            "fade_in_cue_s": round(fade_in, 2),
            "downbeat_times_json": downbeat_json,
        }
    except Exception:
        return None


# ── Worker function for multiprocessing ──────────────────────────────────────

def _extract_worker(args: tuple) -> tuple:
    """Worker function for ProcessPoolExecutor.
    Takes (track_id, mp3_path_str) and returns (track_id, features_dict | None).
    Runs in a separate process with its own model instances.
    """
    tid, mp3_path_str = args
    try:
        import essentia

        # Essentia emits a destructor warning for every internal TF network
        # object on some macOS builds. In multiprocessing this can produce
        # millions of stderr lines and make logging slower than extraction.
        essentia.log.infoActive = False
        essentia.log.warningActive = False
        features = extract_features_for_track(Path(mp3_path_str))
        return (tid, features)
    except Exception as e:
        return (tid, None)


def _load_audio_16k(mp3_path: Path) -> np.ndarray | None:
    """Load MP3 to mono float32 at 16000 Hz — required by Essentia TF models (EffNet, MusiCNN)."""
    try:
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [ffmpeg_bin, "-i", str(mp3_path), "-ar", "16000", "-ac", "1",
               "-sample_fmt", "s16", "-y", tmp_path]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            return None
        import wave
        with wave.open(tmp_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) % 2 != 0:
            audio = audio[:-1]
        return audio if len(audio) > 16000 else None
    except Exception as e:
        log.debug(f"  16kHz load failed for {mp3_path}: {e}")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _extract_yamnet_quality(audio_16k: np.ndarray) -> dict:
    """Return speech/music/singing evidence for suspicious short audio."""
    metadata_path = MODEL_CACHE_DIR / "audioset-yamnet-1.json"
    if not metadata_path.exists():
        return {}
    model = _get_model("audioset_yamnet")
    if model is None:
        return {}
    try:
        classes = json.loads(metadata_path.read_text(encoding="utf-8"))["classes"]
        predictions = model(audio_16k)
        groups = {
            "speech": {
                "Speech", "Child speech, kid speaking", "Conversation",
                "Narration, monologue", "Babbling", "Speech synthesizer",
                "Chatter", "Hubbub, speech noise, speech babble",
            },
            "singing": {"Singing", "Rapping", "Vocal music", "Song"},
            "music": {
                "Music", "Musical instrument", "Pop music", "Hip hop music",
                "Electronic music", "Dance music", "Background music",
                "Soundtrack music", "Song",
            },
        }
        indices = {
            key: [index for index, label in enumerate(classes) if label in labels]
            for key, labels in groups.items()
        }
        speech = np.max(predictions[:, indices["speech"]], axis=1)
        singing = np.max(predictions[:, indices["singing"]], axis=1)
        music = np.max(predictions[:, indices["music"]], axis=1)
        return {
            "yamnet_speech_mean": round(float(np.mean(speech)), 5),
            "yamnet_singing_mean": round(float(np.mean(singing)), 5),
            "yamnet_music_mean": round(float(np.mean(music)), 5),
            "speech_dominant_fraction": round(
                float(np.mean((speech >= 0.10) & (speech > music))), 5
            ),
            "low_music_fraction": round(float(np.mean(music < 0.10)), 5),
        }
    except Exception as e:
        log.debug(f"  YAMNet quality model failed: {e}")
        return {}


def _extract_danceability_16k(mp3_path: Path) -> float | None:
    """Extract danceability at the correct 16kHz sample rate.

    Essentia EffNet-Discogs requires 16kHz input. The original pipeline used 44100Hz,
    producing near-constant embeddings (mean pairwise cosine 0.83 vs 0.57 at 16kHz).
    Classes: ['not_danceable', 'danceable'] → index 1 is the danceable probability.
    """
    audio = _load_audio_16k(mp3_path)
    if audio is None:
        return None
    try:
        import essentia.standard as es
        effnet_path = str(_ensure_model("discogs_effnet"))
        effnet_1280 = es.TensorflowPredictEffnetDiscogs(
            graphFilename=effnet_path, output="PartitionedCall:1"
        )
        dance_model = _get_model("danceability")
        if dance_model is None:
            return None
        embeddings = effnet_1280(audio)
        preds = dance_model(embeddings)
        avg = np.mean(preds, axis=0) if preds.ndim == 2 else preds
        return round(float(np.clip(avg[1], 0.0, 1.0)), 4)
    except Exception as e:
        log.debug(f"  danceability 16kHz failed for {mp3_path}: {e}")
        return None


# ── MTG-Jamendo label sets ───────────────────────────────────────────────────
MTG_MOOD_LABELS = [
    "action","adventure","advertising","background","ballad","children","christmas",
    "commercial","cool","corporate","dark","deep","documentary","drama","dramatic",
    "dream","emotional","energetic","epic","fast","film","fun","funny","game",
    "groovy","happy","heavy","holiday","horror","inspiring","love","meditative",
    "melancholic","melodic","motivational","nature","party","positive","powerful",
    "relaxing","retro","romantic","sad","sexy","slow","soft","soundscape","space",
    "sport","summer","trailer","travel","upbeat","uplifting",
]
MTG_INST_LABELS = [
    "accordion","acousticguitar","bass","beat","bell","bongo","brass","cello",
    "clarinet","classicalguitar","computer","doublebass","drummachine","drums",
    "electricguitar","electricpiano","flute","guitar","harp","horn","keyboard",
    "organ","pad","percussion","piano","pipeorgan","rhodes","sampler","saxophone",
    "strings","synthesizer","trombone","trumpet","ukulele","vibraphone","violin",
    "voice","wind","woodwind",
]


def _extract_tags_16k(mp3_path: Path) -> dict:
    """Extract MTG-Jamendo mood/instrument tags at the correct 16kHz sample rate.

    EffNet-Discogs requires 16kHz input. At 44.1kHz (original pipeline) the
    embeddings were nearly constant → 99% "corporate" / 98% "trumpet" (degenerate).
    At 16kHz: discriminative. Returns {"mood_tags": JSON, "instrument_tags": JSON}.

    Patch script: python -m tools.extract_audio_features --patch-tags
    """
    audio = _load_audio_16k(mp3_path)
    if audio is None:
        return {}
    try:
        import essentia.standard as es
        effnet_path = str(_ensure_model("discogs_effnet"))
        effnet = es.TensorflowPredictEffnetDiscogs(
            graphFilename=effnet_path, output="PartitionedCall:1"
        )
        embeddings = effnet(audio)

        result = {}

        # Mood/theme tags
        mood_model = _get_model("mtg_jamendo_moodtheme")
        if mood_model is not None:
            preds = mood_model(embeddings)
            avg = np.mean(preds, axis=0) if preds.ndim == 2 else preds
            threshold = 0.07  # keep tags above 7% probability
            mood_tags = {
                MTG_MOOD_LABELS[i]: round(float(avg[i]), 3)
                for i in range(min(len(avg), len(MTG_MOOD_LABELS)))
                if float(avg[i]) >= threshold
            }
            mood_tags = dict(sorted(mood_tags.items(), key=lambda x: -x[1])[:8])
            if mood_tags:
                result["mood_tags"] = json.dumps(mood_tags, ensure_ascii=False)

        # Instrument tags
        inst_model = _get_model("mtg_jamendo_instrument")
        if inst_model is not None:
            preds = inst_model(embeddings)
            avg = np.mean(preds, axis=0) if preds.ndim == 2 else preds
            threshold = 0.10
            inst_tags = {
                MTG_INST_LABELS[i]: round(float(avg[i]), 3)
                for i in range(min(len(avg), len(MTG_INST_LABELS)))
                if float(avg[i]) >= threshold
            }
            inst_tags = dict(sorted(inst_tags.items(), key=lambda x: -x[1])[:8])
            if inst_tags:
                result["instrument_tags"] = json.dumps(inst_tags, ensure_ascii=False)

        return result
    except Exception as e:
        log.debug(f"  tags 16kHz failed for {mp3_path}: {e}")
        return {}


def _tags_worker(args: tuple) -> tuple:
    """Worker for tags patch — returns (track_id, {mood_tags, instrument_tags})."""
    tid, mp3_path_str = args
    try:
        return (tid, _extract_tags_16k(Path(mp3_path_str)))
    except Exception:
        return (tid, {})


def patch_tags(
    workers: int = 1,
    checkpoint_interval: int = 50,
    limit: int | None = None,
) -> None:
    """Re-extract MTG-Jamendo mood/instrument tags at correct 16kHz sample rate.

    Fixes the degenerate tags caused by feeding 44.1kHz audio to EffNet-Discogs
    (which expects 16kHz). Updates both phase5_features.csv and PROCESSED_FILE.

    Usage: python -m tools.extract_audio_features --patch-tags [--workers N]
    """
    import multiprocessing, sys
    sys.path.insert(0, str(PROJECT_ROOT))
    import config as _cfg

    targets = [p for p in [OUTPUT_CSV, Path(_cfg.PROCESSED_FILE)] if p.exists()]
    if not targets:
        log.error("No CSV found. Run full extraction first.")
        return

    mp3_files = {f.stem: f for f in MUSIC_DIR.glob("*.mp3")}

    for csv_path in targets:
        log.info(f"\n{'='*60}\n  patch_tags → {csv_path.name}\n{'='*60}")
        df = pd.read_csv(str(csv_path))
        for col in ("mood_tags", "instrument_tags"):
            if col not in df.columns:
                df[col] = None

        pending = [
            (str(row["track_id"]), str(mp3_files[str(row["track_id"])]))
            for _, row in df.iterrows()
            if str(row["track_id"]) in mp3_files
        ]
        if limit:
            pending = pending[:limit]
        log.info(f"  Tracks to patch: {len(pending)}  workers={workers}")

        stats = {"ok": 0, "fail": 0}
        completed = 0

        def _apply(tid, tags):
            nonlocal completed
            if not tags:
                stats["fail"] += 1
            else:
                mask = df["track_id"].astype(str) == str(tid)
                for col, val in tags.items():
                    df.loc[mask, col] = val
                stats["ok"] += 1
            completed += 1
            if completed % checkpoint_interval == 0:
                df.to_csv(str(csv_path), index=False)
                ok_r = stats['ok']/max(completed,1)*100
                log.info(f"  {completed}/{len(pending)}  ok={stats['ok']} fail={stats['fail']} ({ok_r:.0f}%)")

        if workers == 1:
            for task in pending:
                tid, tags = _tags_worker(task)
                _apply(tid, tags)
        else:
            ctx = multiprocessing.get_context("spawn")
            with ctx.Pool(workers) as pool:
                for tid, tags in pool.imap_unordered(_tags_worker, pending, chunksize=4):
                    _apply(tid, tags)

        df.to_csv(str(csv_path), index=False)
        log.info(f"  Done: ok={stats['ok']} fail={stats['fail']} → {csv_path}")

    # Quick discriminativeness check
    try:
        df_check = pd.read_csv(str(targets[-1]))
        from tools.backtest_v2.ground_truth.mood_tags_weak import discriminativeness_check
        result = discriminativeness_check(df_check)
        log.info(f"  §7.3 gate: verdict={result.get('verdict')}  "
                 f"top1_frac={result.get('top1_frac', 0):.3f}  "
                 f"distinct={result.get('distinct_top_tags', 0)}")
    except Exception as e:
        log.debug(f"  §7.3 check failed: {e}")


def _dance_worker(args: tuple) -> tuple:
    """Worker for danceability patch — returns (track_id, danceability | None)."""
    tid, mp3_path_str = args
    try:
        val = _extract_danceability_16k(Path(mp3_path_str))
        return (tid, val)
    except Exception:
        return (tid, None)


def patch_danceability(
    workers: int = 4,
    checkpoint_interval: int = 100,
    limit: int | None = None,
    force: bool = False,
) -> None:
    """Re-extract danceability at correct 16kHz sample rate for all songs.

    Updates both phase5_features.csv and PROCESSED_FILE (the file the recommendation
    engine reads at startup). Run with --workers 4 for ~20-30 min on 5548 songs.
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    import config as _cfg

    targets = []
    for csv_path in [OUTPUT_CSV, Path(_cfg.PROCESSED_FILE)]:
        if csv_path.exists():
            targets.append(csv_path)

    if not targets:
        log.error("No CSV found to patch. Run full extraction first.")
        return

    mp3_files = {f.stem: f for f in MUSIC_DIR.glob("*.mp3")}

    for csv_path in targets:
        log.info(f"\n{'='*60}")
        log.info(f"  patch_danceability → {csv_path.name}")
        log.info(f"  Workers: {workers}")
        log.info(f"{'='*60}")

        df = pd.read_csv(str(csv_path))

        if force:
            pending = [(str(row["track_id"]), mp3_files[str(row["track_id"])])
                       for _, row in df.iterrows()
                       if str(row["track_id"]) in mp3_files]
        else:
            pending = [(str(row["track_id"]), mp3_files[str(row["track_id"])])
                       for _, row in df.iterrows()
                       if str(row["track_id"]) in mp3_files]

        if limit:
            pending = pending[:limit]

        if not pending:
            log.info("  No tracks to patch.")
            continue

        log.info(f"  Tracks to patch: {len(pending)}")
        if "danceability" not in df.columns:
            df["danceability"] = None

        stats = {"patched": 0, "failed": 0}
        completed = 0

        def _apply(tid, val):
            nonlocal completed
            if val is None:
                stats["failed"] += 1
                return
            mask = df["track_id"].astype(str) == str(tid)
            if not mask.any():
                return
            df.loc[mask, "danceability"] = val
            stats["patched"] += 1
            completed += 1

        def _save():
            df.to_csv(str(csv_path), index=False, encoding="utf-8-sig")

        if workers <= 1:
            pbar = tqdm(pending, desc=f"danceability 16kHz ({csv_path.name})")
            for tid, mp3_path in pbar:
                _apply(tid, _extract_danceability_16k(mp3_path))
                if completed > 0 and completed % checkpoint_interval == 0:
                    _save()
                    pbar.set_postfix(done=completed, failed=stats["failed"])
            pbar.close()
        else:
            work_items = [(tid, str(mp3_path)) for tid, mp3_path in pending]
            pbar = tqdm(total=len(work_items), desc=f"danceability 16kHz ({workers}w)")
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_dance_worker, item): item[0] for item in work_items}
                for future in as_completed(futures):
                    try:
                        tid, val = future.result()
                        _apply(tid, val)
                    except Exception:
                        stats["failed"] += 1
                    pbar.update(1)
                    if completed > 0 and completed % checkpoint_interval == 0:
                        _save()
                        pbar.set_postfix(done=completed, failed=stats["failed"])
            pbar.close()

        _save()
        log.info(f"  Done: {stats['patched']} patched, {stats['failed']} failed → {csv_path}")

        # Stats
        dance = pd.to_numeric(df["danceability"], errors="coerce")
        log.info(f"  New distribution: mean={dance.mean():.3f} std={dance.std():.3f} "
                 f">=0.5: {(dance>=0.5).mean()*100:.1f}%  >=0.7: {(dance>=0.7).mean()*100:.1f}%")


def update_db_danceability() -> None:
    """Push re-extracted danceability values from PROCESSED_FILE to the songs table."""
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from db.engine import SessionLocal
        from db.models import Song
        import config as _cfg
    except ImportError:
        log.warning("  Database not available")
        return

    csv_path = Path(_cfg.PROCESSED_FILE)
    if not csv_path.exists():
        log.warning(f"  {csv_path} not found")
        return

    df = pd.read_csv(str(csv_path))
    if "danceability" not in df.columns:
        log.warning("  No danceability column in CSV")
        return

    session = SessionLocal()
    try:
        updated = 0
        for _, row in tqdm(df.iterrows(), total=len(df), desc="DB danceability update"):
            val = row.get("danceability")
            if not pd.notna(val):
                continue
            song = session.query(Song).filter_by(track_id=str(row["track_id"])).first()
            if song:
                song.danceability = float(val)
                updated += 1
                if updated % 500 == 0:
                    session.flush()
        session.commit()
        log.info(f"  DB updated: {updated} songs")
    except Exception as e:
        session.rollback()
        log.error(f"  DB update failed: {e}")
    finally:
        session.close()


def _extract_new_features_only(mp3_path: Path) -> dict | None:
    """Extract ONLY DEAM V-A (valence + arousal) for tracks missing these features.
    Skips DSP and danceability for speed (~3x faster than full extraction).
    """
    audio = _load_audio_safe(mp3_path)
    if audio is None:
        return None

    results = {}
    try:
        musicnn_model = _get_model("msd_musicnn")
        deam_model = _get_model("deam_valence_arousal")
        if musicnn_model is not None and deam_model is not None:
            musicnn_embeddings = musicnn_model(audio)
            deam_predictions = deam_model(musicnn_embeddings)
            avg_va = np.mean(deam_predictions, axis=0) if deam_predictions.ndim == 2 else deam_predictions
            if len(avg_va) >= 2:
                results["valence"] = round(float(np.clip(avg_va[0] / 2.0, 0.0, 1.0)), 4)
                results["arousal"] = round(float(np.clip(avg_va[1] / 2.0, 0.0, 1.0)), 4)
                results["valence_estimated"] = False
    except Exception as e:
        log.debug(f"  DEAM V-A extraction failed: {e}")

    return results if results else None


def _patch_worker(args: tuple) -> tuple:
    """Worker for patch extraction — returns (track_id, new_features | None)."""
    tid, mp3_path_str = args
    try:
        features = _extract_new_features_only(Path(mp3_path_str))
        return (tid, features)
    except Exception:
        return (tid, None)


def patch_new_features(
    workers: int = 4,
    checkpoint_interval: int = 100,
    limit: int | None = None,
) -> pd.DataFrame:
    """Fast patch: extract ONLY DEAM V-A (valence + arousal) for tracks missing them.
    ~3x faster than full re-extraction per track.
    """
    if not OUTPUT_CSV.exists():
        log.error(f"  No existing {OUTPUT_CSV.name} found. Run full extraction first.")
        return pd.DataFrame()

    df = pd.read_csv(str(OUTPUT_CSV))
    log.info(f"\n{'='*60}")
    log.info(f"  Phase 5 PATCH: Adding timbre + DEAM V-A features")
    log.info(f"  Input: {OUTPUT_CSV.name} ({len(df)} tracks)")
    log.info(f"  Workers: {workers}")
    log.info(f"{'='*60}")

    mp3_files = {f.stem: f for f in MUSIC_DIR.glob("*.mp3")}

    # Find tracks needing patch (missing valence or arousal)
    needs_patch = []
    for _, row in df.iterrows():
        tid = str(row.get("track_id", "")).strip()
        if not tid or tid not in mp3_files:
            continue
        has_valence = "valence" in df.columns and pd.notna(row.get("valence"))
        has_arousal = "arousal" in df.columns and pd.notna(row.get("arousal"))
        if not has_valence or not has_arousal:
            needs_patch.append((tid, mp3_files[tid]))

    if limit:
        needs_patch = needs_patch[:limit]

    if not needs_patch:
        log.info("  All tracks already have valence + arousal!")
        return df

    log.info(f"  Tracks needing patch: {len(needs_patch)}")

    # Ensure columns exist
    for col in ["valence", "arousal"]:
        if col not in df.columns:
            df[col] = None

    stats = {"patched": 0, "failed": 0}
    completed = 0

    def _apply_patch(tid, features):
        nonlocal completed
        if features is None:
            stats["failed"] += 1
            return
        mask = df["track_id"] == tid
        if not mask.any():
            return
        for col, val in features.items():
            if col not in df.columns:
                df[col] = pd.Series([None] * len(df), dtype="object")
            elif isinstance(val, (str, list, tuple, dict)):
                if df[col].dtype != "object":
                    df[col] = df[col].astype("object")
            df.loc[mask, col] = val
        stats["patched"] += 1
        completed += 1

    def _save():
        df.to_csv(str(OUTPUT_CSV), index=False, encoding="utf-8-sig")

    if workers <= 1:
        pbar = tqdm(needs_patch, desc="Patching (timbre+DEAM)")
        for tid, mp3_path in pbar:
            features = _extract_new_features_only(mp3_path)
            _apply_patch(tid, features)
            if completed > 0 and completed % checkpoint_interval == 0:
                _save()
                pbar.set_postfix(done=completed, failed=stats["failed"])
        pbar.close()
    else:
        work_items = [(tid, str(mp3_path)) for tid, mp3_path in needs_patch]
        pbar = tqdm(total=len(work_items), desc=f"Patching ({workers} workers)")

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_patch_worker, item): item[0]
                       for item in work_items}
            for future in as_completed(futures):
                try:
                    tid, features = future.result()
                    _apply_patch(tid, features)
                except Exception:
                    stats["failed"] += 1
                pbar.update(1)
                if completed > 0 and completed % checkpoint_interval == 0:
                    _save()
                    pbar.set_postfix(done=completed, failed=stats["failed"])
        pbar.close()

    _save()
    log.info(f"\n  Patch complete: {stats['patched']} patched, {stats['failed']} failed")
    log.info(f"  Output: {OUTPUT_CSV}")
    return df


def batch_extract(
    limit: int | None = None,
    reprocess: bool = False,
    workers: int = 1,
    checkpoint_interval: int = 50,
) -> pd.DataFrame:
    """Extract audio features for all tracks with MP3 files.
    Reads from phase4_lyrics_gated.csv (preferred) → phase4_lyrics.csv → phase3_downloaded.csv → raw.
    Supports resume: skips tracks already in phase5_features.csv output.
    Supports multiprocessing with --workers N.
    """
    # Input: phase4_lyrics_gated.csv (preferred) → fallbacks
    csv_path = None
    for candidate in [LYRICS_CSV, LYRICS_CSV_FALLBACK, DOWNLOADED_CSV, PROCESSED_CSV, RAW_CSV]:
        if candidate.exists():
            csv_path = candidate
            break
    if csv_path is None:
        log.error(f"No input CSV found")
        return pd.DataFrame()

    df = pd.read_csv(str(csv_path))
    log.info(f"\n{'='*60}")
    log.info(f"  Phase 5: Audio Feature Extraction (Essentia + Librosa)")
    log.info(f"  Input: {csv_path.name} ({len(df)} tracks)")
    log.info(f"  Workers: {workers} | Checkpoint every {checkpoint_interval} tracks")
    log.info(f"{'='*60}")

    # Find tracks that need extraction
    mp3_files = {f.stem: f for f in MUSIC_DIR.glob("*.mp3")}
    log.info(f"  MP3 files available: {len(mp3_files)}")

    # Resume: load already-done tracks from existing output CSV
    already_done = set()
    if not reprocess:
        # Check existing output first (from previous partial run)
        if OUTPUT_CSV.exists():
            try:
                df_existing = pd.read_csv(str(OUTPUT_CSV))
                if "track_id" in df_existing.columns:
                    df_existing["track_id"] = df_existing["track_id"].astype(str)
                    df["track_id"] = df["track_id"].astype(str)
                if "audio_feature_source" in df_existing.columns:
                    done_mask = df_existing["audio_feature_source"].notna()
                    already_done = set(df_existing.loc[done_mask, "track_id"].astype(str))
                    if already_done:
                        log.info(f"  Resuming from {OUTPUT_CSV.name}: {len(already_done)} already done")
                        existing_by_id = df_existing.drop_duplicates(subset=["track_id"], keep="last")
                        existing_lookup = existing_by_id.set_index("track_id")
                        current_ids = df["track_id"]
                        for col in existing_lookup.columns:
                            values = existing_lookup.reindex(current_ids)[col].tolist()
                            if col not in df.columns:
                                df[col] = values
                                continue
                            mask = df[col].isna()
                            if mask.any():
                                fill_values = pd.Series(values, index=df.index)
                                df.loc[mask, col] = fill_values.loc[mask]
            except Exception:
                pass

        # Also check input CSV columns
        if not already_done and "audio_feature_source" in df.columns:
            already_done = set(df.loc[df["audio_feature_source"].notna(), "track_id"].astype(str))

        log.info(f"  Already extracted: {len(already_done)}")

    pending = []
    for _, row in df.iterrows():
        tid = str(row.get("track_id", "")).strip()
        if tid and tid in mp3_files and tid not in already_done:
            pending.append((tid, mp3_files[tid]))

    if limit:
        pending = pending[:limit]

    if not pending:
        log.info("  All tracks already have audio features!")
        return df

    log.info(f"  Pending extraction: {len(pending)}")

    # Ensure columns exist
    for col in ["audio_feature_source", "valence_estimated"]:
        if col not in df.columns:
            df[col] = None
    df["audio_feature_source"] = df["audio_feature_source"].astype("object")

    stats = {"essentia+tf": 0, "essentia": 0, "librosa+tf": 0, "librosa": 0, "failed": 0}
    completed_count = 0

    def _apply_features(tid, features):
        """Apply extracted features to the DataFrame row."""
        nonlocal completed_count
        if features is None:
            stats["failed"] += 1
            return

        source = features.pop("audio_feature_source", "unknown")
        valence_est = features.pop("valence_estimated", True)
        stats[source] = stats.get(source, 0) + 1

        mask = df["track_id"] == tid
        if not mask.any():
            return

        for col, val in features.items():
            if col not in df.columns:
                df[col] = pd.Series([None] * len(df), dtype="object")
            elif isinstance(val, (str, list, tuple, dict)):
                if df[col].dtype != "object":
                    df[col] = df[col].astype("object")
            df.loc[mask, col] = val

        df.loc[mask, "has_audio_features"] = True
        df.loc[mask, "audio_feature_source"] = source
        df.loc[mask, "valence_estimated"] = valence_est
        completed_count += 1

    def _save_checkpoint():
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(str(OUTPUT_CSV), index=False, encoding="utf-8-sig")

    if workers <= 1:
        # Sequential extraction
        pbar = tqdm(pending, desc="Extracting features")
        for tid, mp3_path in pbar:
            features = extract_features_for_track(mp3_path)
            _apply_features(tid, features)

            # Periodic checkpoint
            if completed_count > 0 and completed_count % checkpoint_interval == 0:
                _save_checkpoint()
                done_total = len(already_done) + completed_count
                pbar.set_postfix(saved=done_total, failed=stats["failed"])
        pbar.close()
    else:
        # Parallel extraction with ProcessPoolExecutor
        work_items = [(tid, str(mp3_path)) for tid, mp3_path in pending]
        pbar = tqdm(total=len(work_items), desc=f"Extracting ({workers} workers)")

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_extract_worker, item): item[0]
                       for item in work_items}

            for future in as_completed(futures):
                try:
                    tid, features = future.result()
                    _apply_features(tid, features)
                except Exception:
                    stats["failed"] += 1

                pbar.update(1)

                # Periodic checkpoint
                if completed_count > 0 and completed_count % checkpoint_interval == 0:
                    _save_checkpoint()
                    done_total = len(already_done) + completed_count
                    pbar.set_postfix(saved=done_total, failed=stats["failed"])

        pbar.close()

    # Final save
    _save_checkpoint()

    log.info(f"\n  Extraction complete:")
    for src, count in sorted(stats.items()):
        if count > 0:
            log.info(f"    {src}: {count}")
    log.info(f"  Total done: {len(already_done) + completed_count} / {len(df)}")
    log.info(f"  Output: {OUTPUT_CSV}")

    return df


# ── DB update ────────────────────────────────────────────────────────────────

def update_dw_audio_features():
    """Update songs table with audio features extracted from MP3 analysis."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from db.engine import SessionLocal
        from db.models import Song
    except ImportError:
        log.warning("  Database not available — skipping DB update")
        return

    # Prefer phase5_features.csv → processed → raw
    csv_path = None
    for candidate in [OUTPUT_CSV, PROCESSED_CSV, RAW_CSV]:
        if candidate.exists():
            csv_path = candidate
            break
    if csv_path is None:
        log.warning("  No CSV found for DB update")
        return

    df = pd.read_csv(str(csv_path))
    # Only update tracks with extracted features
    mask = df["audio_feature_source"].isin(["essentia", "librosa", "essentia+tf", "librosa+tf"]) if "audio_feature_source" in df.columns else pd.Series([False]*len(df))
    df_extracted = df[mask]

    if df_extracted.empty:
        log.info("  No extracted features to push to DB")
        return

    session = SessionLocal()
    try:
        updated = 0
        feature_cols = [
            "danceability", "energy", "key", "loudness", "mode",
            "valence", "arousal", "tempo", "time_signature",
        ]
        for _, row in tqdm(df_extracted.iterrows(), total=len(df_extracted), desc="DB update"):
            tid = str(row["track_id"])
            song = session.query(Song).filter_by(track_id=tid).first()
            if not song:
                continue

            for col in feature_cols:
                val = row.get(col)
                if pd.notna(val) and hasattr(song, col):
                    setattr(song, col, float(val) if col not in ("key", "mode", "time_signature") else int(val))

            song.has_audio_features = True
            if hasattr(song, "audio_feature_source"):
                song.audio_feature_source = str(row.get("audio_feature_source", ""))
            if hasattr(song, "valence_estimated"):
                song.valence_estimated = bool(row.get("valence_estimated", True))

            updated += 1
            if updated % 200 == 0:
                session.flush()

        session.commit()
        log.info(f"  DB updated: {updated} songs with extracted audio features")
    except Exception as e:
        session.rollback()
        log.error(f"  DB update failed: {e}")
    finally:
        session.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Brightify Audio Feature Extraction (Essentia + Librosa)")
    parser.add_argument("--limit", type=int, help="Max tracks to process")
    parser.add_argument("--test", action="store_true", help="Test: extract 3 tracks")
    parser.add_argument("--reprocess", action="store_true", help="Re-extract even if already done")
    parser.add_argument("--patch", action="store_true", help="Fast patch: only extract NEW features (timbre+DEAM) for existing CSV")
    parser.add_argument("--patch-dance", action="store_true", help="Re-extract danceability at correct 16kHz sample rate")
    parser.add_argument("--patch-dance-db", action="store_true", help="Push patched danceability to DB (run after --patch-dance)")
    parser.add_argument("--patch-tags", action="store_true", help="Re-extract MTG-Jamendo mood/instrument tags at correct 16kHz sample rate")
    parser.add_argument("--force", action="store_true", help="Re-extract all tracks, even already-done ones (for --patch-dance)")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel workers (default: 1, use 2-4 for speed)")
    parser.add_argument("--checkpoint-interval", type=int, default=50, help="Save checkpoint every N tracks (default: 50)")
    parser.add_argument("--update-db", action="store_true", help="Push extracted features to DB")
    parser.add_argument("--input", "-i", type=str, help="Input CSV path (default: checkpoints/phase4_lyrics_gated.csv)")
    parser.add_argument("--output", "-o", type=str, help="Output CSV path (default: checkpoints/phase5_features.csv)")
    parser.add_argument("--music-dir", type=str, help="MP3 files directory (default: music_files/)")
    args = parser.parse_args()

    # Override global paths if CLI args provided
    global LYRICS_CSV, PROCESSED_CSV, OUTPUT_CSV, MUSIC_DIR
    if args.input:
        LYRICS_CSV = Path(args.input).resolve()
        PROCESSED_CSV = LYRICS_CSV  # single source when explicit
    if args.output:
        OUTPUT_CSV = Path(args.output).resolve()
    if args.music_dir:
        MUSIC_DIR = Path(args.music_dir).resolve()

    if args.update_db:
        update_dw_audio_features()
    elif args.patch_dance_db:
        update_db_danceability()
    elif args.patch_dance:
        patch_danceability(
            workers=args.workers or 4,
            checkpoint_interval=args.checkpoint_interval,
            limit=args.limit,
            force=getattr(args, "force", False),
        )
    elif args.patch_tags:
        patch_tags(
            workers=args.workers or 1,
            checkpoint_interval=args.checkpoint_interval,
            limit=args.limit,
        )
    elif args.patch:
        patch_new_features(
            workers=args.workers or 4,
            checkpoint_interval=args.checkpoint_interval,
            limit=args.limit,
        )
    elif args.test:
        batch_extract(limit=3, workers=1)
    else:
        batch_extract(
            limit=args.limit,
            reprocess=args.reprocess,
            workers=args.workers,
            checkpoint_interval=args.checkpoint_interval,
        )


if __name__ == "__main__":
    main()
