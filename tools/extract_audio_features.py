"""
Brightify – Phase 5: Audio Feature Extraction v2.1
(Essentia DSP + Essentia-TF pre-trained models + DEAM V-A + Librosa fallback)

Extracts audio features from MP3 files in music_files/ and writes them
to checkpoints/phase5_features.csv for the next pipeline phase.

Pipeline position: Phase 5 (after Phase 4 Lyrics gate)
Input:  checkpoints/phase4_lyrics_gated.csv (tracks with lyrics, strict)
        Falls back to: phase4_lyrics.csv → phase3_downloaded.csv → raw CSV
Output: checkpoints/phase5_features.csv (tracks with audio features)

Features extracted (DSP — Essentia/Librosa):
  - energy, key, loudness, mode, liveness, tempo, time_signature

Features extracted (Pre-trained TF models — Essentia EffNet-Discogs):
  - danceability            (danceability classification head)
  - acousticness            (mood_acoustic classification head)
  - speechiness             (voice_instrumental head, inverted)
  - instrumentalness        (voice_instrumental head)
  - mood_tags   JSON        (MTG-Jamendo mood/theme head, 56 classes)
  - instrument_tags JSON    (MTG-Jamendo instrument head, 40 classes)
  - voice_gender             (gender classification head)
  - audio_embedding  400-d   (EffNet-Discogs default output)

Features extracted (DEAM — MSD-MusiCNN backbone):
  - valence                 (DEAM V-A regression, replaces heuristic)
  - arousal                 (DEAM V-A regression, new feature)

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

SAMPLE_RATE = 44100  # Standard sample rate for Essentia
EMBEDDING_DIM = 400  # EffNet-Discogs default embedding output


# ── Essentia TF Model Registry ──────────────────────────────────────────────

MODEL_BASE_URL = "https://essentia.upf.edu/models"

MODEL_REGISTRY = {
    # ── Feature extractors (standalone, take raw audio) ──
    # EffNet-Discogs feature extractor → 400-dim embeddings
    "discogs_effnet": {
        "url": f"{MODEL_BASE_URL}/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb",
        "type": "extractor",
        "predict_cls": "TensorflowPredictEffnetDiscogs",
    },
    # TempoCNN (standalone, takes raw audio)
    "tempocnn": {
        "url": f"{MODEL_BASE_URL}/tempo/tempocnn/deepsquare-k16-3.pb",
        "type": "extractor",
        "predict_cls": "TensorflowPredictTempoCNN",
    },

    # ── Classification heads (take 1280-dim EffNet-Discogs embeddings as input) ──
    # Danceability (binary, EffNet-Discogs head)
    "danceability": {
        "url": f"{MODEL_BASE_URL}/classification-heads/danceability/danceability-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    # Mood acoustic (binary, EffNet-Discogs head)
    "mood_acoustic": {
        "url": f"{MODEL_BASE_URL}/classification-heads/mood_acoustic/mood_acoustic-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    # Voice/instrumental (binary, EffNet-Discogs head)
    "voice_instrumental": {
        "url": f"{MODEL_BASE_URL}/classification-heads/voice_instrumental/voice_instrumental-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    # Gender (male / female, EffNet-Discogs head)
    "gender": {
        "url": f"{MODEL_BASE_URL}/classification-heads/gender/gender-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },
    # MTG-Jamendo mood/theme (56 classes, EffNet-Discogs head)
    "mtg_jamendo_moodtheme": {
        "url": f"{MODEL_BASE_URL}/classification-heads/mtg_jamendo_moodtheme/mtg_jamendo_moodtheme-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Sigmoid",
    },
    # MTG-Jamendo instrument (40 classes, EffNet-Discogs head)
    "mtg_jamendo_instrument": {
        "url": f"{MODEL_BASE_URL}/classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Sigmoid",
    },

    # Timbre bright/dark (binary, EffNet-Discogs head)
    # Alluri & Toiviainen (2010): perceptual timbre correlates with color warmth
    "timbre": {
        "url": f"{MODEL_BASE_URL}/classification-heads/timbre/timbre-discogs-effnet-1.pb",
        "type": "effnet_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Softmax",
    },

    # ── MSD-MusiCNN feature extractor (for DEAM V-A model) ──
    "msd_musicnn": {
        "url": f"{MODEL_BASE_URL}/feature-extractors/musicnn/msd-musicnn-1.pb",
        "type": "extractor",
        "predict_cls": "TensorflowPredictMusiCNN",
        "output_node": "model/batch_normalization_10/batchnorm/add_1",  # 200-dim embeddings for DEAM
    },

    # ── DEAM Valence-Arousal (MusiCNN head, regression) ──
    # Alonso-Jiménez et al. (2023), trained on DEAM dataset (1802 songs)
    # Input: 200-dim MusiCNN embeddings, Output: [valence, arousal]
    # Values in range [1, 9] — normalized to [0, 1] in extraction code
    "deam_valence_arousal": {
        "url": f"{MODEL_BASE_URL}/classification-heads/deam/deam-msd-musicnn-2.pb",
        "type": "musicnn_head",
        "input_node": "model/Placeholder",
        "output_node": "model/Identity",
    },
}

# Label lists for multi-class models
MOOD_THEME_LABELS = [
    "action", "adventure", "advertising", "ambient", "background", "ballad", "calm",
    "children", "christmas", "commercial", "cool", "corporate", "dark",
    "deep", "documentary", "drama", "dream", "emotional", "energetic",
    "epic", "fast", "film", "fun", "funny", "game", "groovy", "happy",
    "heavy", "holiday", "hopeful", "inspiring", "love", "meditative",
    "melancholic", "melodic", "motivational", "movie", "nature",
    "party", "positive", "powerful", "relaxing", "retro", "romantic",
    "sad", "sexy", "slow", "soft", "soundscape", "space", "sport",
    "summer", "trailer", "travel", "upbeat", "uplifting",
]

INSTRUMENT_LABELS = [
    "accordion", "acousticguitar", "bass", "beat", "bell", "bongo",
    "brass", "cello", "clarinet", "classicalguitar", "computer",
    "cymbal", "drums", "electricguitar", "electricpiano", "flute",
    "guitar", "harmonica", "harp", "horn", "keyboard", "oboe",
    "orchestra", "organ", "pad", "percussion", "piano", "pipeorgan",
    "Rhodes", "sampler", "saxophone", "strings", "synthesizer",
    "trombone", "trumpet", "ukulele", "violin", "voice",
]

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

        # Dynamic complexity (proxy for liveness)
        try:
            dyn_complexity, _ = es.DynamicComplexity()(audio)
        except Exception:
            dyn_complexity = 0.0

        # RMS energy normalized
        rms = np.sqrt(np.mean(audio ** 2))
        energy_norm = min(rms / 0.3, 1.0)

        # Liveness from dynamic complexity
        liveness = np.clip(min(dyn_complexity / 10, 1.0), 0, 1)

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
            "liveness": round(float(liveness), 4),
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
    1. EffNet-Discogs extractor → 1280-dim embeddings (per-patch) for classification heads
    2. EffNet-Discogs extractor → 400-dim embeddings (default output) for storage/similarity
    3. Classification heads consume 1280-dim EffNet embeddings via TensorflowPredict2D
    4. MSD-MusiCNN extractor → 200-dim embeddings → DEAM head → [valence, arousal]
    """
    results = {}
    import essentia.standard as es

    # ── Step 1: Extract EffNet-Discogs embeddings ──
    effnet_embeddings_1280 = None
    try:
        effnet_path = str(_ensure_model("discogs_effnet"))
        # 1280-dim for classification heads
        effnet_1280 = es.TensorflowPredictEffnetDiscogs(
            graphFilename=effnet_path, output="PartitionedCall:1"
        )
        effnet_embeddings_1280 = effnet_1280(audio)

        # 400-dim (default) for storage as audio embedding
        effnet_400 = _get_model("discogs_effnet")
        if effnet_400 is not None:
            emb_400 = effnet_400(audio)
            avg_embedding = np.mean(emb_400, axis=0) if emb_400.ndim == 2 else emb_400
            results["audio_embedding"] = avg_embedding.tolist()
    except Exception as e:
        log.debug(f"  EffNet-Discogs embedding extraction failed: {e}")

    # ── Step 2: Run EffNet classification heads (need 1280-dim embeddings) ──
    # ⚠️ KNOWN BUG (verified 2026-06-01, see memory project_arousal_miscalibration):
    #   These heads read `avg[1]` as the "positive" class WITHOUT loading each model's
    #   documented class order from its Essentia metadata .json. Class order is often
    #   NOT [negative, positive] (e.g. danceability = [danceable, not_danceable];
    #   mood_acoustic = [acoustic, non_acoustic]) → several outputs are INVERTED.
    #   Worse: across the catalog these features are near-constant / mutually
    #   uncorrelated (danceability flat ~0.27 across all tempo bands; acousticness
    #   ~0.80 for a pop/rap catalog) → the embeddings feeding the heads look
    #   non-discriminative (likely an audio-preprocessing / clip-selection issue).
    #   BEFORE re-extracting: (1) load `classes` from each model's .json metadata and
    #   index the correct class; (2) verify the EffNet/MusiCNN input preprocessing
    #   (16kHz mono, representative segment) so embeddings actually vary per song;
    #   (3) calibrate DEAM V-A per-dimension (the shared /2.0 below compresses arousal).
    #   Emotion labels are currently sourced from LLM-on-lyrics (E-RELABEL v3), which
    #   bypasses these broken audio features entirely.
    if effnet_embeddings_1280 is not None:
        # Danceability
        try:
            model = _get_model("danceability")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                # Softmax output: [not_danceable, danceable]
                danceable_prob = float(avg[1]) if len(avg) >= 2 else float(avg[0])
                results["danceability"] = round(np.clip(danceable_prob, 0, 1), 4)
        except Exception as e:
            log.debug(f"  Danceability model failed: {e}")

        # Mood Acoustic
        try:
            model = _get_model("mood_acoustic")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                acoustic_prob = float(avg[1]) if len(avg) >= 2 else float(avg[0])
                results["acousticness"] = round(np.clip(acoustic_prob, 0, 1), 4)
        except Exception as e:
            log.debug(f"  Mood acoustic model failed: {e}")

        # Voice / Instrumental
        try:
            model = _get_model("voice_instrumental")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                # [voice, instrumental]
                instrumental_prob = float(avg[1]) if len(avg) >= 2 else float(avg[0])
                results["instrumentalness"] = round(np.clip(instrumental_prob, 0, 1), 4)
                results["speechiness"] = round(np.clip(1.0 - instrumental_prob, 0, 1) * 0.5, 4)
        except Exception as e:
            log.debug(f"  Voice/instrumental model failed: {e}")

        # Gender
        try:
            model = _get_model("gender")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                # [female, male]
                if len(avg) >= 2:
                    female_prob = float(avg[0])
                    results["voice_gender"] = "female" if female_prob > 0.5 else "male"
                    results["voice_gender_confidence"] = round(max(female_prob, 1 - female_prob), 3)
        except Exception as e:
            log.debug(f"  Gender model failed: {e}")

        # MTG-Jamendo Mood/Theme
        try:
            model = _get_model("mtg_jamendo_moodtheme")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg_preds = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                top_indices = np.where(avg_preds > 0.1)[0]
                mood_tags = {}
                for idx in top_indices:
                    if idx < len(MOOD_THEME_LABELS):
                        mood_tags[MOOD_THEME_LABELS[idx]] = round(float(avg_preds[idx]), 3)
                mood_tags = dict(sorted(mood_tags.items(), key=lambda x: x[1], reverse=True)[:10])
                results["mood_tags"] = json.dumps(mood_tags, ensure_ascii=False)
        except Exception as e:
            log.debug(f"  Mood/theme model failed: {e}")

        # MTG-Jamendo Instrument
        try:
            model = _get_model("mtg_jamendo_instrument")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg_preds = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                top_indices = np.where(avg_preds > 0.1)[0]
                instrument_tags = {}
                for idx in top_indices:
                    if idx < len(INSTRUMENT_LABELS):
                        instrument_tags[INSTRUMENT_LABELS[idx]] = round(float(avg_preds[idx]), 3)
                instrument_tags = dict(sorted(instrument_tags.items(), key=lambda x: x[1], reverse=True)[:10])
                results["instrument_tags"] = json.dumps(instrument_tags, ensure_ascii=False)
        except Exception as e:
            log.debug(f"  Instrument model failed: {e}")

        # Timbre (bright / dark)
        try:
            model = _get_model("timbre")
            if model is not None:
                predictions = model(effnet_embeddings_1280)
                avg = np.mean(predictions, axis=0) if predictions.ndim == 2 else predictions
                # Softmax output: [bright, dark]
                bright_prob = float(avg[0]) if len(avg) >= 2 else 0.5
                results["timbre_bright"] = round(np.clip(bright_prob, 0, 1), 4)
        except Exception as e:
            log.debug(f"  Timbre model failed: {e}")

    # ── Step 3: DEAM Valence-Arousal via MSD-MusiCNN embeddings ──
    # Architecture: audio → MusiCNN → 200-dim embeddings → DEAM head → [valence, arousal]
    # DEAM v2 raw output is unbounded regression in approx [0, 2] range.
    # Normalize: divide by 2, then clip to [0, 1].
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

        # Liveness (spectral flux variability)
        spec_flux = librosa.onset.onset_strength(y=y, sr=sr)
        liveness = float(np.clip(np.std(spec_flux) / 3.0, 0, 1))

        # LUFS (ITU-R BS.1770) for Smart Crossfade
        loudness_lufs = measure_lufs(audio, SAMPLE_RATE)

        return {
            "energy": round(float(energy_norm), 4),
            "key": int(key_int),
            "loudness": round(float(loudness_db), 2),
            "loudness_lufs": loudness_lufs,
            "mode": int(mode_int),
            "liveness": round(float(liveness), 4),
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
    for key in ["valence", "danceability", "acousticness", "instrumentalness", "speechiness"]:
        if key in tf_features:
            features[key] = tf_features[key]

    # Valence fallback
    if "valence" not in features:
        features["valence"] = _estimate_valence(features)
        features["valence_estimated"] = True
    else:
        features["valence_estimated"] = tf_features.get("valence_estimated", False)

    # Additional ML features
    for key in ["arousal", "timbre_bright", "voice_gender", "voice_gender_confidence",
                 "mood_tags", "genre_tags", "instrument_tags", "audio_embedding"]:
        if key in tf_features:
            features[key] = tf_features[key]

    # Mark source as essentia_tf if any TF model succeeded
    if tf_features:
        features["audio_feature_source"] = f"{dsp_source}+tf"

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
        features = extract_features_for_track(Path(mp3_path_str))
        return (tid, features)
    except Exception as e:
        return (tid, None)


def _extract_new_features_only(mp3_path: Path) -> dict | None:
    """Extract ONLY the new features (timbre + DEAM V-A).
    Skips DSP and existing EffNet classification heads for speed.
    ~3x faster than full extract_features_for_track().
    """
    audio = _load_audio_safe(mp3_path)
    if audio is None:
        return None

    results = {}

    try:
        import essentia.standard as es

        # EffNet 1280-dim → timbre head
        try:
            effnet_path = str(_ensure_model("discogs_effnet"))
            effnet_1280 = es.TensorflowPredictEffnetDiscogs(
                graphFilename=effnet_path, output="PartitionedCall:1"
            )
            effnet_embeddings_1280 = effnet_1280(audio)

            timbre_model = _get_model("timbre")
            if timbre_model is not None and effnet_embeddings_1280 is not None:
                preds = timbre_model(effnet_embeddings_1280)
                avg = np.mean(preds, axis=0) if preds.ndim == 2 else preds
                bright_prob = float(avg[0]) if len(avg) >= 2 else float(avg[0])
                results["timbre_bright"] = round(np.clip(bright_prob, 0, 1), 4)
        except Exception as e:
            log.debug(f"  Timbre extraction failed: {e}")

        # MusiCNN → DEAM V-A
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
        except Exception as e:
            log.debug(f"  DEAM V-A extraction failed: {e}")

    except ImportError:
        log.warning("  Essentia not available for new feature extraction")

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
    """Fast patch: extract ONLY timbre + DEAM V-A for tracks missing these features.
    Skips DSP, danceability, acousticness, gender, mood_tags, instrument_tags.
    ~3x faster than full re-extraction per track, plus multi-worker parallelism.
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

    # Find tracks needing patch (missing timbre_bright OR arousal)
    needs_patch = []
    for _, row in df.iterrows():
        tid = str(row.get("track_id", "")).strip()
        if not tid or tid not in mp3_files:
            continue
        has_timbre = "timbre_bright" in df.columns and pd.notna(row.get("timbre_bright"))
        has_arousal = "arousal" in df.columns and pd.notna(row.get("arousal"))
        if not has_timbre or not has_arousal:
            needs_patch.append((tid, mp3_files[tid]))

    if limit:
        needs_patch = needs_patch[:limit]

    if not needs_patch:
        log.info("  All tracks already have timbre + DEAM V-A features!")
        return df

    log.info(f"  Tracks needing patch: {len(needs_patch)}")

    # Ensure columns exist
    for col in ["timbre_bright", "arousal"]:
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
                df[col] = None
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
    existing_embeddings = {}
    if not reprocess:
        # Check existing output first (from previous partial run)
        if OUTPUT_CSV.exists():
            try:
                df_existing = pd.read_csv(str(OUTPUT_CSV))
                if "audio_feature_source" in df_existing.columns:
                    done_mask = df_existing["audio_feature_source"].notna()
                    already_done = set(df_existing.loc[done_mask, "track_id"].astype(str))
                    # Merge existing results into df
                    if already_done:
                        df = df_existing
                        log.info(f"  Resuming from {OUTPUT_CSV.name}: {len(already_done)} already done")
            except Exception:
                pass

        # Also check input CSV columns
        if not already_done and "audio_feature_source" in df.columns:
            already_done = set(df.loc[df["audio_feature_source"].notna(), "track_id"].astype(str))

        # Load existing embeddings for resume
        emb_path = DATA_DIR / "audio_embeddings.json"
        if emb_path.exists():
            try:
                with open(emb_path, "r") as f:
                    existing_embeddings = json.load(f)
            except Exception:
                pass

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

    stats = {"essentia+tf": 0, "essentia": 0, "librosa+tf": 0, "librosa": 0, "failed": 0}

    # Audio embeddings (merge with existing)
    audio_embeddings = dict(existing_embeddings)
    completed_count = 0

    def _apply_features(tid, features):
        """Apply extracted features to the DataFrame row."""
        nonlocal completed_count
        if features is None:
            stats["failed"] += 1
            return

        source = features.pop("audio_feature_source", "unknown")
        valence_est = features.pop("valence_estimated", True)

        audio_emb = features.pop("audio_embedding", None)
        if audio_emb is not None:
            audio_embeddings[tid] = audio_emb

        stats[source] = stats.get(source, 0) + 1

        mask = df["track_id"] == tid
        if not mask.any():
            return

        for col, val in features.items():
            if col not in df.columns:
                df[col] = None
            df.loc[mask, col] = val

        df.loc[mask, "has_audio_features"] = True
        df.loc[mask, "audio_feature_source"] = source
        df.loc[mask, "valence_estimated"] = valence_est
        completed_count += 1

    def _save_checkpoint():
        """Save current progress to output CSV and embeddings."""
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(str(OUTPUT_CSV), index=False, encoding="utf-8-sig")
        if audio_embeddings:
            emb_path = DATA_DIR / "audio_embeddings.json"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(emb_path, "w") as f:
                json.dump(audio_embeddings, f)

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

    # Save audio embeddings
    if audio_embeddings:
        emb_path = DATA_DIR / "audio_embeddings.json"
        log.info(f"  Audio embeddings saved: {len(audio_embeddings)} tracks → {emb_path}")

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
            "speechiness", "acousticness", "instrumentalness", "liveness",
            "valence", "tempo", "time_signature",
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
