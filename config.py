"""
Configuration file for Brightify Music Recommendation System
Centralized settings for data processing and recommendation
Version 7.1
"""

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

