"""
Configuration file for Brightify Music Recommendation System
Centralized settings for data processing and recommendation
Version 7.1
"""

import os
from pathlib import Path


def _read_secret_or_env(name: str, default: str = "") -> str:
    """Read a value from a Docker secret file or fall back to an env var."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        with open(file_path) as f:
            return f.read().strip()
    return os.environ.get(name, default)


# ============================================================================
# Secrets
# ============================================================================
BRIGHTIFY_ADMIN_KEY = _read_secret_or_env("BRIGHTIFY_ADMIN_KEY")

# ============================================================================
# File Paths
# ============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_path_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if not raw:
        return default
    value = Path(raw)
    if value.is_absolute():
        return value
    return (PROJECT_ROOT / value).resolve()


SERVING_ROOT = _resolve_path_env("BRIGHTIFY_SERVING_ROOT", PROJECT_ROOT)
MEDIA_ROOT = _resolve_path_env("BRIGHTIFY_MEDIA_ROOT", SERVING_ROOT)
DATA_DIR = _resolve_path_env("BRIGHTIFY_DATA_DIR", SERVING_ROOT / "data")
CHECKPOINTS_DIR = _resolve_path_env("BRIGHTIFY_CHECKPOINTS_DIR", SERVING_ROOT / "checkpoints")
MUSIC_DIR = _resolve_path_env("BRIGHTIFY_MUSIC_DIR", MEDIA_ROOT / "music_files")
ALBUM_ART_DIR = _resolve_path_env("BRIGHTIFY_ALBUM_ART_DIR", MEDIA_ROOT / "album_art")
ARTIST_IMAGES_DIR = _resolve_path_env("BRIGHTIFY_ARTIST_IMAGES_DIR", MEDIA_ROOT / "artist_images")
ARCHIVE_ROOT = _resolve_path_env("BRIGHTIFY_ARCHIVE_ROOT", PROJECT_ROOT / "var" / "archive")
RUNTIME_ROOT = _resolve_path_env("BRIGHTIFY_RUNTIME_ROOT", PROJECT_ROOT / "var" / "runtime")

INPUT_FILE = str(DATA_DIR / "vietnamese_music_complete_dataset_full.csv")
PROCESSED_FILE = str(DATA_DIR / "vietnamese_music_processed_full.csv")
# VN Sentence-BERT (dangvantuan/vietnamese-embedding) replaces PhoBERT mean-pool.
# PhoBERT mean-pool avg pairwise cosine = 0.856 (anisotropic — cosine nearly meaningless).
# VN-SBERT SimCSE contrastive-trained: avg cosine = 0.544 — proper cosine geometry.
# At 15% weight the aggregate metric improvement is small (MERT 75% dominates) but
# the lyrics component now contributes real semantic signal rather than anisotropic noise.
EMBEDDINGS_FILE = str(DATA_DIR / "vnsbert_embeddings.npy")
EMBEDDINGS_FILE_PHOBERT = str(DATA_DIR / "vietnamese_music_embeddings_full.npy")  # kept for ablation
EMBEDDINGS_META_FILE = str(DATA_DIR / "embeddings_metadata.json")
ARTIST_IMAGES_DATA_FILE = str(DATA_DIR / "artist_images.json")
PHASE1_ARTISTS_FILE = str(CHECKPOINTS_DIR / "phase1_artists.csv")
CROSSFADE_FEATURES_FILE = str(DATA_DIR / "crossfade_features.json")

# ============================================================================
# PhoBERT Model Settings
# ============================================================================
PHOBERT_MODEL = 'vinai/phobert-base-v2'  # PhoBERT v2 (RoBERTa-base, 135M params, AGPL-3.0)
MAX_SEQUENCE_LENGTH = 512  # Maximum tokens for BERT
BATCH_SIZE = 32  # Batch size for embedding generation
# VN Sentence-BERT (dangvantuan/vietnamese-embedding): SimCSE contrastive-trained on VN.
# avg pairwise cosine 0.587 vs PhoBERT mean-pool 0.856 → much less anisotropic → better retrieval.
# Switch: set EMBEDDINGS_FILE = VNSBERT_EMBEDDINGS_FILE after eval confirms improvement.
VNSBERT_MODEL          = "dangvantuan/vietnamese-embedding"
VNSBERT_EMBEDDINGS_FILE = str(DATA_DIR / "vnsbert_embeddings.npy")

# ============================================================================
# Audio Features
# ============================================================================
AUDIO_FEATURES = [
    'valence',           # Musical positivity (0-1)
    'energy',            # Intensity and activity (0-1)
    'danceability',      # How suitable for dancing (0-1)
    'acousticness',      # Acoustic vs electronic (0-1)
    'instrumentalness',  # Vocal presence (0-1)
    'speechiness',       # Spoken words detection (0-1)
    'liveness',          # Audience presence (0-1)
    'tempo',             # BPM (beats per minute)
    'loudness',          # Overall loudness in dB
    'key',               # Musical key (0-11)
    'mode',              # Major (1) or Minor (0)
    'arousal',           # DEAM arousal (0-1), complements energy
    'timbre_bright',     # Timbre brightness (0=dark, 1=bright)
]

# Normalized features (0-1 scale)
NORMALIZED_FEATURES = [
    'valence', 'energy', 'danceability', 'acousticness',
    'instrumentalness', 'speechiness', 'liveness',
    'arousal', 'timbre_bright'
]

# ============================================================================
# Color Mapping Settings (Based on Palmer et al. 2013 & Russell Model)
# ============================================================================

# HSL Color Space Ranges
HUE_MAPPING = {
    'sad_blue': (210, 240),      # Low valence → Blue
    'neutral_green': (120, 210),  # Medium valence → Green-Cyan
    'happy_yellow': (30, 120),    # High valence → Yellow-Orange
}

SATURATION_RANGE = (30, 100)  # Energy → Saturation
LIGHTNESS_RANGE = (20, 80)     # Mode & Acousticness → Lightness

# ============================================================================
# Recommendation Weights (Research-based)
# ============================================================================

# Default weights for multimodal recommendation [audio, lyrics, color]
DEFAULT_WEIGHTS = [0.40, 0.40, 0.20]

# Task-specific weights
WEIGHTS_COLOR_QUERY = [0.30, 0.35, 0.35]  # User selects color
WEIGHTS_MOOD_QUERY = [0.50, 0.30, 0.20]   # User selects mood
WEIGHTS_SONG_QUERY = [0.40, 0.40, 0.20]   # Similar song search
WEIGHTS_LYRICS_QUERY = [0.25, 0.55, 0.20] # Lyrics-based search

# recommend_by_song fusion weights.
# Signal layout (8-dim, MERT path): [timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert]
#
# DESIGN (2026-06-08, evidence-based rewrite):
# Literature: acoustic similarity > textual similarity for perceived music similarity
#   (Berenzweig & Ellis 2003; arXiv:2604.23077; arXiv:2601.19109).
# Active signals: mert (audio backbone), lyrics (genre/topic cue), va (mood alignment).
# Zeroed signals:
#   timbral/rhythmic/tonal (0,1,2) — Essentia scalars degenerate (project_arousal_miscalibration)
#   emotion (5) — redundant: color_hex is synthesised from song's own V-A/tempo/mode,
#                  so color→emotion is a noisy re-encoding of V-A already captured by signal 4.
#   mood (6)    — one-hot same-label bonus (~3%), no discriminating power after ablation.
# Intrinsic eval (tools/eval_similar_intrinsic.py, n=60 seeds, 2026-06-08):
#   mert_lyrics_va wins on 4/9 directional metrics vs baseline:
#   MoodCoherence +0.019, SelfConsistency +0.008, Symmetry +0.038, SameArtist@K -0.007.
#   mert_only collapses MoodCoherence (-0.193): V-A signal is essential for mood alignment.
RECO_SONG_WEIGHTS = {
    # 7-signal fallback (MERT disabled) — same active-signal logic, no mert term.
    "with_lyrics": [0.0, 0.0, 0.0, 0.20, 0.10, 0.0, 0.0],
}

# 8-signal weights (ENABLE_MERT=True — production path).
# Σ = 1.00. Breakdown: MERT 75% (audio), lyrics 15% (genre cue), V-A 10% (mood).
RECO_SONG_WEIGHTS_MERT = {
    # Sensitivity analysis + 5-fold CV + held-out validation (2026-06-09):
    # Decreasing lyrics (0.15→0.06) reduces noise from VN-SBERT at 15% weight.
    # Increasing mert (0.75→0.82) better reflects audio-dominant literature basis.
    # Increasing va (0.10→0.12) marginally improves mood alignment.
    # Held-out eval (60 seeds): ↑3 ↓0 vs baseline. Full eval (100 seeds):
    #   Symmetry +0.038 ✓, SameArtist −0.016 ✓, MoodCoherence +0.002 ✓.
    "with_lyrics": [0.0, 0.0, 0.0, 0.06, 0.12, 0.0, 0.0, 0.82],
}

# ============================================================================
# Russell's Circumplex Model - Mood Quadrants
# ============================================================================
MOOD_QUADRANTS = {
    'Q1': {'name': 'Happy/Excited', 'valence': (0.5, 1.0), 'energy': (0.5, 1.0)},
    'Q2': {'name': 'Angry/Tense', 'valence': (0.0, 0.5), 'energy': (0.5, 1.0)},
    'Q3': {'name': 'Sad/Depressed', 'valence': (0.0, 0.5), 'energy': (0.0, 0.5)},
    'Q4': {'name': 'Calm/Peaceful', 'valence': (0.5, 1.0), 'energy': (0.0, 0.5)},
}

# Mood keywords mapping
MOOD_KEYWORDS = {
    'happy': ('Q1', 0.75, 0.75),
    'excited': ('Q1', 0.80, 0.85),
    'joyful': ('Q1', 0.85, 0.70),
    'angry': ('Q2', 0.30, 0.80),
    'tense': ('Q2', 0.25, 0.75),
    'energetic': ('Q2', 0.45, 0.90),
    'sad': ('Q3', 0.25, 0.30),
    'depressed': ('Q3', 0.15, 0.25),
    'melancholic': ('Q3', 0.30, 0.35),
    'calm': ('Q4', 0.65, 0.35),
    'peaceful': ('Q4', 0.70, 0.30),
    'relaxed': ('Q4', 0.75, 0.25),
}

# ============================================================================
# Sentiment Analysis Settings
# ============================================================================
# Sentiment is handled by the Vietnamese Emotion Lexicon (core/emotion_analysis.py)
# with 13 emotion categories and 732+ Vietnamese words.

# ============================================================================
# Recommendation Settings
# ============================================================================
DEFAULT_TOP_K = 10              # Number of recommendations
DIVERSITY_PENALTY = 0.15        # Penalty for same artist (0-1)
MIN_SIMILARITY_THRESHOLD = 0.3  # Minimum similarity to include

# ============================================================================
# Pillar D — Diversity & Serendipity (MMR / DPP)
# ============================================================================
# DIVERSITY_METHOD: "greedy" keeps original artist-penalty behaviour.
# "mmr"  uses Maximal Marginal Relevance (Carbonell & Goldstein 1998).
# "dpp"  uses Determinantal Point Process greedy MAP (Chen et al. 2018).
DIVERSITY_METHOD = os.environ.get("DIVERSITY_METHOD", "mmr")
DIVERSITY_LAMBDA = 0.7   # MMR λ: relevance weight (0=pure diversity, 1=pure relevance)

# Multimodal Fusion Weights (Research-based - Zhang et al. 2024, Kim et al. 2024)
# ----------------------------------------------------------------------------
# recommend_by_colors() — V-A heteroscedastic RBF scorer (V19/F3)
# ----------------------------------------------------------------------------
# Scorer = exp(-½[(Δv/σ_V)² + (Δa/σ_A)²]). Only signal: V-A distance.
# Whiteford 2018: colour↔music mediation is FULLY through V-A; direct
# perceptual correspondences vanish after partialling emotion.
# σ_V > σ_A: valence less reliable (~17% audio-predictable, Delbouys 2018);
# arousal more reliable (~80%, Eerola 2026). Trust arousal more.
COLOR_SCORE_VA_SIGMA_V = 0.20   # Gaussian RBF bandwidth — valence axis (wide)
COLOR_SCORE_VA_SIGMA_A = 0.14   # Gaussian RBF bandwidth — arousal axis (narrow)

# recommend_by_song — V-A RBF (isotropic, E-VA-SPLIT gate-rejected 2026-06).
# Heteroscedastic V-A Gaussian for recommend_by_song (2026-06-09).
# Scientific basis: arousal ~80% audio-predictable, valence ~17% (Delbouys 2018;
#   Eerola & Anderson arXiv:2302.13321 r≈0.81 vs r≈0.17).
# Smaller σ = sharper kernel = songs must be CLOSE in that axis to score high.
# Larger σ  = wider kernel  = more lenient match in that axis.
# → σ_A < σ_V: trust arousal (reliable) more tightly; be lenient on valence (noisy).
# Previous E-VA-SPLIT (2026-06) tested only σ_A=0.14 at V-A weight=0.032 → REJECTED
#   because 3.2% weight is too small for σ change to surface in ranking. Now weight=0.10.
RECO_SONG_VA_SIGMA_V = 0.22   # valence — wider (less reliable, ~17% audio-predictable)
RECO_SONG_VA_SIGMA_A = 0.14   # arousal — narrower (more reliable, ~80% audio-predictable)

# V23 — Mood JOURNEY: 2 colours → waypoint-sample songs along V-A path A→B
# (Iso-Principle, Starcke 2024 d=0.52). Replaces "Hành trình" tab (merged).
COLOR_JOURNEY_ENABLED = True



# ============================================================================
# Color Distance Calculation
# ============================================================================
COLOR_DISTANCE_METHOD = 'CIEDE2000'  # Options: 'CIEDE2000', 'EUCLIDEAN', 'HSL'

# ============================================================================
# Feature Engineering
# ============================================================================
MOOD_SCORE_WEIGHTS = {'valence': 0.6, 'energy': 0.4}
DANCE_SCORE_WEIGHTS = {'danceability': 0.5, 'energy': 0.3, 'tempo': 0.2}
ACOUSTIC_SCORE_WEIGHTS = {'acousticness': 0.7, 'instrumentalness': 0.3}
COMBINED_POSITIVITY_WEIGHTS = {'valence': 0.6, 'sentiment': 0.4}

# ============================================================================
# Data Quality Settings
# ============================================================================
REQUIRE_LYRICS = True           # Remove songs without lyrics
REQUIRE_AUDIO_FEATURES = True   # Remove songs without audio features
REMOVE_DUPLICATES = True        # Remove duplicate tracks

# Tempo normalization range
TEMPO_MIN = 60
TEMPO_MAX = 200

# Loudness normalization range
LOUDNESS_MIN = -20
LOUDNESS_MAX = 0

# ============================================================================
# Visualization Settings
# ============================================================================
PLOT_STYLE = 'seaborn-v0_8-darkgrid'
FIGURE_SIZE = (12, 8)
DPI = 100

# Color palette for plots
COLOR_PALETTE = 'husl'

# ============================================================================
# Pillar A — MERT Audio Embedding (Li et al. 2023, arXiv 2306.00107)
# ============================================================================
ENABLE_MERT = os.environ.get("ENABLE_MERT", "True") == "True"
MERT_MODEL = "m-a-p/MERT-v1-95M"
# Phase 1 confirmed 2026-06-08: multilayer (mean 12 layers) wins on 3 intrinsic metrics
# vs single-layer (MoodCoherence +0.022, Symmetry +0.040, SelfConsistency +0.010).
# Old single-layer file kept as mert_embeddings_single_layer.npy for ablation.
MERT_EMBEDDINGS_FILE = str(DATA_DIR / "mert_embeddings_multilayer.npy")
MERT_EMBEDDINGS_META_FILE = str(DATA_DIR / "mert_metadata_multilayer.json")
MERT_LAYER = 8           # 0-indexed — kept for backward-compat / single-layer ablation
# Phase 1 (2026-06-08): multi-layer extraction.
# MERT hidden_states is a tuple of length 13 (input embed + 12 transformer layers).
# Layer probing (Li et al. 2023): pitch peaks at 0-4, tempo at 3-7, genre/emotion at 6-11.
# Mean across all 12 transformer layers (indices 1-12) captures the full spectrum while
# staying 768-dim (mean commutes with time-pool → no shape change, drop-in compatible).
# arXiv:2604.20847: adjacent layers encode similar structure; distant layers complementary.
MERT_LAYERS = list(range(1, 13))   # all 12 transformer layers; None → use MERT_LAYER only
MERT_EMBEDDINGS_MULTILAYER_FILE = str(DATA_DIR / "mert_embeddings_multilayer.npy")
MERT_EMBEDDINGS_MULTILAYER_META_FILE = str(DATA_DIR / "mert_metadata_multilayer.json")
MERT_CLIP_DURATION = 15.0  # seconds per segment for mean-pooling
# Phase 3 (2026-06-08): MuQ-large backbone (SOTA 2025, arXiv:2501.01108).
# MuQ-large: 12-layer transformer, 1024-dim (vs MERT-95M 768-dim).
# MARBLE benchmark avg 77.0 — outperforms MERT on all MIR tasks.
# Extraction: mean all 13 hidden states + time-pool → (N, 1024) L2-norm.
# Switch production: set MERT_EMBEDDINGS_FILE = MUQ_EMBEDDINGS_FILE after eval.
MUQ_MODEL_ID          = "OpenMuQ/MuQ-large-msd-iter"
MUQ_EMBEDDINGS_FILE   = str(DATA_DIR / "muq_embeddings.npy")
MUQ_METADATA_FILE     = str(DATA_DIR / "muq_metadata.json")
# Phase 2 (2026-06-08): SimCSE-style self-supervised metric head.
# MLP 768→384→128 trained with NT-Xent dropout contrastive (Gao et al. EMNLP 2021).
# Projected 128-dim embeddings have better cosine geometry (less anisotropic).
# Trained without any human labels — positive pairs = same embedding, different dropout.
MERT_PROJ_EMBEDDINGS_FILE            = str(DATA_DIR / "mert_proj_embeddings.npy")
MERT_PROJ_EMBEDDINGS_MULTILAYER_FILE = str(DATA_DIR / "mert_proj_embeddings_multilayer.npy")
ENABLE_MERT_PROJ = os.environ.get("ENABLE_MERT_PROJ", "False") == "True"  # off until eval confirms

# ============================================================================
# Pillar B (alt Vietnamese encoders: SimCSE/ViDeBERTa) — REMOVED 2026-06-01.
# Experiment FAILED in backtest (PhoBERT + lyrics signal already optimal; dropping
# lyrics hurt NDCG most, alt encoders gave no gain). The pipeline routing and
# core/lyrics_router.py were deleted. These two constants are kept ONLY inert
# (ENABLE_PILLAR_B permanently False) for backward-compat with the backtest A/B
# toggle in tools/backtest_v2 — they never select a real Pillar B file.
ENABLE_PILLAR_B = False
EMBEDDINGS_FILE_PILLAR_B = EMBEDDINGS_FILE  # inert: never used while ENABLE_PILLAR_B=False
EMBEDDINGS_META_FILE_PILLAR_B = EMBEDDINGS_META_FILE
HF_CACHE_DIR = os.environ.get("HF_CACHE_DIR", "var/volumes/hf_cache")

# ============================================================================
# Pillar C — RRF Hybrid Retrieval + Cross-Encoder Reranking
# ============================================================================
# ENABLE_RRF: Two-stage retrieval — RRF candidate reduction then full scoring.
# RRF fuses multiple cheap rank lists (lyrics, V-A, MERT) to form a top-N
# candidate pool before expensive diversity reranking.  k=60 per Cormack 2009.
ENABLE_RRF = os.environ.get("ENABLE_RRF", "True") == "True"
RRF_K = 60               # Cormack 2009: RRF dampening constant
RRF_CANDIDATE_SIZE = 200 # Candidate pool before full-signal scoring

# ENABLE_RERANKER: Cross-encoder second-pass for lyrics keyword queries.
# Model: multilingual MiniLM-v2 fine-tuned on MS-MARCO (covers Vietnamese).
# Disabled by default — requires sentence-transformers and extra inference time.
ENABLE_RERANKER = os.environ.get("ENABLE_RERANKER", "False") == "True"
RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
RERANKER_TOP_K = 20      # Number of candidates to re-rank

# ============================================================================
# Pillar F — VN Holiday / Time-of-Day Context  (KG removed 2026-06-08)
# ============================================================================
# KG removed: E-KG-CLEAN (2026-06-01) showed KG-on vs KG-off NDCG@10
# statistically indistinguishable (Δ+0.0038, CI95[-0.018,+0.015]).
# Embedding was 50% MERT + 50% degenerate Essentia tags → MERT-redundant.
MAX_PER_ARTIST_SIMILAR = int(os.environ.get("MAX_PER_ARTIST_SIMILAR", "0"))

# Context: applies valence/arousal shifts based on VN holidays + time-of-day.
ENABLE_VN_CONTEXT = os.environ.get("ENABLE_VN_CONTEXT", "False") == "True"  # context feature removed; off → deterministic color demo

# Weather context — requires OpenWeatherMap free-tier key (1000 calls/day).
# Set OWM_API_KEY env var or leave blank to silently skip weather shifts.
OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
# Default location: Hà Nội (override per-deploy via OWM_LAT/OWM_LON env vars).
# This is a fixed fallback — the user's real location is NOT auto-detected
# (would need browser geolocation or IP lookup; not implemented yet).
OWM_LAT = float(os.environ.get("OWM_LAT", "21.0278"))
OWM_LON = float(os.environ.get("OWM_LON", "105.8342"))
OWM_TIMEOUT_S = 2  # seconds — never block recommendation path

# ============================================================================
# Pillar E — CLAP Zero-shot Emotion Detection (Wu et al. 2023, arXiv 2211.06687)
# ============================================================================
# ENABLE_CLAP_EMOTION=True loads pre-computed labels from CLAP_EMOTIONS_FILE.
# Falls back to lexicon analysis when the file is absent or a song is missing.
ENABLE_CLAP_EMOTION = os.environ.get("ENABLE_CLAP_EMOTION", "True") == "True"
CLAP_MODEL = "laion/larger_clap_music_and_speech"
CLAP_EMOTIONS_FILE = str(DATA_DIR / "clap_emotions.json")  # raw CLAP (deprecated; file removed — see RELABELED_EMOTIONS_FILE)
CLAP_CLIP_DURATION = 15.0  # seconds — matches MERT_CLIP_DURATION

# E-RELABEL (2026-05-31) — CLAP audio zero-shot labels are biased (74% happy/excited,
# ~0 arousal correlation; see tools/relabel_emotions.py + memory project_clap_label_bias).
# Prefer the re-derived labels (lyrics-valence + audio-arousal) which score far better
# on independent metrics: valence-vs-lyric-sentiment ρ 0.077→0.422, sad-title 28%→75%.
# Set USE_RELABELED_EMOTIONS=False to revert to raw CLAP.
USE_RELABELED_EMOTIONS = os.environ.get("USE_RELABELED_EMOTIONS", "True") == "True"
# v4 = the system's intended audio+lyrics fusion:
#   valence ← LLM-from-lyrics (emotional content of the words)
#   arousal ← MERT audio probe (0.6, real acoustic energy; CV R²=0.58 on DEAM)
#             + LLM-lyrics arousal (0.4) as support
#   label   ← Russell quadrant of (valence, arousal)
# Built by tools/mert_arousal_probe.py (fuse). Restores the audio half that was lost
# when degenerate Essentia features (project_arousal_miscalibration) were bypassed.
# v3 (LLM-only) and v2 (lexicon+rank-audio) kept as fallback files.
RELABELED_EMOTIONS_FILE = str(DATA_DIR / "emotion_labels_v5c.json")  # B3: Gemini valence + quantile-mapped arousal (2026-06-04)
VALENCE_CALIBRATION_FILE = str(DATA_DIR / "valence_calibration.json")  # isotonic fit on VN gold-set (V17)

# ============================================================================
# System Settings
# ============================================================================
RANDOM_SEED = 42
VERBOSE = False  # Set True to see detailed logs

# GPU settings
USE_GPU = True  # Auto-detect CUDA if available

