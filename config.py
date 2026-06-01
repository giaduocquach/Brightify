"""
Configuration file for Brightify Music Recommendation System
Centralized settings for data processing and recommendation
Version 7.1
"""

import os


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
INPUT_FILE = 'data/vietnamese_music_complete_dataset_full.csv'
PROCESSED_FILE = 'data/vietnamese_music_processed_full.csv'
EMBEDDINGS_FILE = 'data/vietnamese_music_embeddings_full.npy'
EMBEDDINGS_META_FILE = 'data/embeddings_metadata.json'

# ============================================================================
# PhoBERT Model Settings
# ============================================================================
PHOBERT_MODEL = 'vinai/phobert-base-v2'  # PhoBERT v2 (RoBERTa-base, 135M params, AGPL-3.0)
MAX_SEQUENCE_LENGTH = 512  # Maximum tokens for BERT
BATCH_SIZE = 32  # Batch size for embedding generation

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

# recommend_by_song fusion weights (Laurier et al. 2009 adaptive fusion).
# Kept in config so ablation can zero out a signal and the optimizer can search.
#
# 7-signal (MERT disabled):
#   with_lyrics: timbral, rhythmic, tonal, lyrics, va, emotion, mood
#   audio_only:  timbral, rhythmic, tonal, va, emotion, mood
# 8-signal (MERT enabled, ENABLE_MERT=True):
#   with_lyrics: timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert
#   audio_only:  timbral, rhythmic, tonal, va, emotion, mood, mert
RECO_SONG_WEIGHTS = {
    # E1d (2026-05-30): audio_only removed — all songs have lyrics (data contract).
    "with_lyrics": [0.124683, 0.189409, 0.044438, 0.494559, 0.012768, 0.078309, 0.055834],
}

# 8-signal weights when ENABLE_MERT=True (Li et al. 2023 — reduce timbral/rhythmic
# because MERT already captures those sub-spaces via RVQ+CQT dual teacher).
# Σ = 1.00 in both variants.
RECO_SONG_WEIGHTS_MERT = {
    # 8-signal (timbral, rhythmic, tonal, lyrics, va, emotion, mood, mert).
    # E1/E1b CI-confirmed optimal weights (2026-05-30).
    # E1d: audio_only removed — all songs have lyrics (data contract).
    # E-AUDIO-CLEAN (2026-06-01): dropped timbral/rhythmic/tonal (Essentia scalars are
    # degenerate — project_arousal_miscalibration). Re-optimized 5 signals; paired
    # cluster-bootstrap on 1050 editorial queries: NDCG@10 0.0999→0.1052, Δ+0.0046
    # CI95[+0.0015,+0.0070] (entirely positive). MERT(0.335)+lyrics(0.499) carry audio+text.
    "with_lyrics": [0.0, 0.0, 0.0, 0.4991, 0.0315, 0.1042, 0.0300, 0.3352],
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
# Color-based recommendation with lyrics integration:
#   - Audio features: 25% (Spotify audio analysis)
#   - Lyrics semantic: 35% (PhoBERT embeddings) - Improves accuracy by 18%
#   - Valence-Arousal: 20% (Color psychology mapping)
#   - Emotion vectors: 20% (Emotion probability distribution)
WEIGHTS_COLOR_QUERY_WITH_LYRICS = [0.25, 0.35, 0.20, 0.20]  # [audio, lyrics, VA, emotion]
WEIGHTS_COLOR_QUERY_NO_LYRICS = [0.25, 0.35, 0.25, 0.15]    # Fallback without lyrics

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
MERT_EMBEDDINGS_FILE = "data/mert_embeddings.npy"
MERT_EMBEDDINGS_META_FILE = "data/mert_metadata.json"
MERT_LAYER = 8           # 0-indexed hidden state layer (of 12) — best for MIR tasks
MERT_CLIP_DURATION = 15.0  # seconds per segment for mean-pooling

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
# Pillar F — Cold-start: KG Embeddings + VN Holiday Context
# ============================================================================
# KG v2 (2026-05-29): CONTENT-similarity graph — k-NN on fused MERT + mood_tags
# + instrument_tags + audio features, then SVD (64-dim). Replaces the old
# artist-album bipartite graph, which injected same-artist bias into
# recommend_by_song (pillar-f-xartist showed its gain collapsed on cross-artist
# pairs). No artist/album edges. See docs/MASTER_UPGRADE_PLAN_V10.md §6.3.
ENABLE_KG = os.environ.get("ENABLE_KG", "True") == "True"
KG_EMBEDDINGS_FILE = "data/kg_embeddings.npy"
KG_DIM = 64
# Weight of the KG content signal in recommend_by_song fusion. Replaces the old
# hardcoded +0.05 artist bonus; tunable/ablatable. 0 disables the term.
# E-KG-CLEAN (2026-06-01): set to 0. The KG embedding was 50% MERT + 50% degenerate
# Essentia tags (mood/instrument, 99% corporate/trumpet). Cluster-bootstrap on 1050
# editorial queries: KG-on vs KG-off NDCG@10 statistically indistinguishable
# (Δ+0.0038, CI95[-0.018,+0.015]) — KG contributes ~nothing. Dropped to remove the
# degenerate-tag dependency + a MERT-redundant signal. Set >0 to re-enable.
KG_SIM_WEIGHT = float(os.environ.get("KG_SIM_WEIGHT", "0.0"))
# Optional same-artist cap for similar-song results. DEFAULT 0 = NO CAP:
# fix the *cause* (artist bias in the KG signal) not the *symptom*. With the
# content-based KG, same-artist songs only rank high when they are genuinely the
# most musically similar (e.g. an artist with a very consistent style) — capping
# would discard correct results. Musical (not artist) diversity is handled by
# MMR. Set >0 only if an operator explicitly wants a hard artist cap.
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
CLAP_EMOTIONS_FILE = "data/clap_emotions.json"
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
RELABELED_EMOTIONS_FILE = "data/emotion_labels_v4.json"

# ============================================================================
# System Settings
# ============================================================================
RANDOM_SEED = 42
VERBOSE = False  # Set True to see detailed logs

# GPU settings
USE_GPU = True  # Auto-detect CUDA if available

# ============================================================================
# Image-to-Music Settings (CLIP-based Analysis)
# ============================================================================
CLIP_MODEL = 'openai/clip-vit-base-patch32'  # CLIP model for image understanding
IMAGE_MAX_SIZE_MB = 10  # Maximum upload size
IMAGE_DOMINANT_COLORS = 5  # Number of dominant colors to extract
IMAGE_ANALYSIS_SIZE = 256  # Resize target for analysis

# Image recommendation weights
# Fusion: [audio, lyrics, V-A, emotion, color]
WEIGHTS_IMAGE_QUERY_WITH_LYRICS = [0.20, 0.25, 0.20, 0.15, 0.20]
WEIGHTS_IMAGE_QUERY_NO_LYRICS = [0.25, 0.00, 0.25, 0.20, 0.30]

