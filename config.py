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
# Active signals in RECO_SONG_WEIGHTS_MERT: mert(0.82) + va(0.12) + lyrics(0.06)
# timbral/rhythmic/tonal slots all weight=0 (Essentia degenerate at 44.1kHz).
# Features kept: used in VA computation, UI display, or journey scoring.
# Features removed from AUDIO_FEATURES vs legacy:
#   acousticness, speechiness, instrumentalness, liveness — weight=0, not used in ranking
#   timbre_bright — weight=0 (Essentia degenerate)
#   audio_embedding(400-dim), voice_gender, mood_tags, instrument_tags — kept in catalog
#     but not in AUDIO_FEATURES (used separately via cover filter / instrument_tag_matrix)
AUDIO_FEATURES = [
    'valence',       # Musical positivity — used in song_va (V-A signal)
    'energy',        # Intensity — used in song_va arousal estimation
    'danceability',  # For UI display + journey scoring
    'tempo',         # BPM — for tempo_coherence metric + UI
    'loudness',      # For UI display
    'key',           # Musical key (0-11) — for Camelot/harmonic mix
    'mode',          # Major (1) / Minor (0) — color mapping, valence proxy
    'arousal',       # DEAM arousal (MERT-probe, R²=0.58) — song_va primary
]

# Normalized features (0-1 scale) — subset of AUDIO_FEATURES
NORMALIZED_FEATURES = [
    'valence', 'energy', 'danceability', 'arousal',
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

# Tag signal: MTG-Jamendo instrument tags (40-dim cosine) as post-ranking bonus.
# Fixed sample rate bug (44.1→16kHz) on 2026-06-09: instrument_tags now discriminative.
# Applied as: score = base_score * (1 + TAG_BONUS_WEIGHT * instrument_cosine)
# Additive-multiplier keeps existing weights unchanged; tag signal boosts/not kills.
# Intrinsic eval (80 seeds, 2026-06-09): λ=0.03 → Symmetry +0.013 ✓, 0 regressions.
# Adopted at λ=0.03 (conservative: max 3% boost, no regression at any metric).
ENABLE_TAG_SIGNAL  = os.environ.get("ENABLE_TAG_SIGNAL", "True") == "True"
TAG_BONUS_WEIGHT   = 0.03   # instrument cosine can boost score by up to 3%
# Cover/duplicate filter (2026-06-09): exclude versions of the same song from recommendations.
# Built by tools/detect_cover_songs.py — lyrics-first approach (VN-SBERT cosine > 0.92).
# Catches: same song different title/case, feat. versions, cross-lingual (April Lie / Tháng Tư).
ENABLE_COVER_FILTER = os.environ.get("ENABLE_COVER_FILTER", "True") == "True"
COVER_INDEX_FILE    = str(DATA_DIR / "cover_index.json")

# 8-signal weights (ENABLE_MERT=True — production path).
# Σ = 1.00. Breakdown: MERT 75% (audio), lyrics 15% (genre cue), V-A 10% (mood).
RECO_SONG_WEIGHTS_MERT = {
    # Sensitivity analysis + 5-fold CV + held-out validation (2026-06-09):
    # Decreasing lyrics (0.15→0.06) reduces noise from VN-SBERT at 15% weight.
    # Increasing mert (0.75→0.82) better reflects audio-dominant literature basis.
    # Increasing va (0.10→0.12) marginally improves mood alignment.
    # Held-out eval (60 seeds): ↑3 ↓0 vs baseline. Full eval (100 seeds):
    #   Symmetry +0.038 ✓, SameArtist −0.016 ✓, MoodCoherence +0.002 ✓.
    # Signal layout: [timbral,rhythmic,tonal, lyrics, va, inst_tag(=0), mood, mert]
    # Sensitivity (80 seeds): lyr=0.04 marginally better but within noise on 200 seeds.
    # Instrument tag in additive slot: consistently reduces score → removed (slot 5 = 0).
    # Weights unchanged from prior validation (82/12/6 validated Mức 1).
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
DIVERSITY_LAMBDA = 0.7   # MMR λ: relevance weight (0=pure diversity, 1=pure relevance).
# Sensitivity: λ=0.8 shows Symmetry +0.015 but within noise range (std≈0.035 on 200 seeds).
# Kept at 0.7 — no statistically significant evidence to change..

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
#   Eerola & Anderson 2026 ACM 3796518, MER meta 34 studies: arousal r=.81 > valence r=.67).
#   arXiv:2302.13321 = Krols et al "Multi-Modality in Music" — confirms multimodal > audio
#   for valence; NOT the source of r=.81/.67.
# Smaller σ = sharper kernel = songs must be CLOSE in that axis to score high.
# Larger σ  = wider kernel  = more lenient match in that axis.
# → σ_A < σ_V: trust arousal (reliable) more tightly; be lenient on valence (noisy).
# Previous E-VA-SPLIT (2026-06) tested only σ_A=0.14 at V-A weight=0.032 → REJECTED
#   because 3.2% weight is too small for σ change to surface in ranking. Now weight=0.10.
RECO_SONG_VA_SIGMA_V = 0.22   # valence — wider (less reliable, ~17% audio-predictable)
RECO_SONG_VA_SIGMA_A = 0.14   # arousal — narrower (more reliable, ~80% audio-predictable)

# V23 — Mood JOURNEY: 2 colours → waypoint-sample songs along V-A path A→B
# (Iso-Principle, Starcke 2024 d=0.52). Replaces "Hành trình" tab (merged).
# V25 — Ease-in-ease-out sigmoid waypoint schedule (2026-06-09):
#   Replaces linear spacing with sigmoid (scipy.special.expit) for smoother
#   affective arc: slow start, faster middle, slow end. Saari 2016: "10-15%/step".
COLOR_JOURNEY_ENABLED = True

# R1 (V26): CIELAB-Lch valence hybrid — default off, enable after gate passes.
# Gate: color_eval_rigor TE must not regress + T1 monotonicity must improve.
# Experiment: tools/phase3_cielab_experiment.py — valence r=.852 vs HSL .759,
#   monotonicity L*→V 0.81 vs 0.44. Arousal stays Whiteford-HSL regardless.
# Requires colormath (HAS_COLORMATH). Falls back to HSL if unavailable.
COLOR_VALENCE_CIELAB = False
# A5 (V27): Oklab valence hybrid — no colormath needed, better perceptual uniformity.
# Enable after tools/phase3_cielab_experiment.py confirms r_oklab > r_cielab AND gate passes.
COLOR_VALENCE_OKLAB = True   # C1 (V28): catalog calibration applied in hsl_to_va()

# A4 (V27): redness×saturation interaction in arousal formula.
# FPSYG 2025 (doi:10.3389/fpsyg.2025.1593928): red+high-sat → max arousal.
# Enable only after color_eval_rigor gate passes.
COLOR_AROUSAL_INTERACTION = True

# A3 (V27): Calibration reranking — boost underrepresented V-A quadrant after MMR.
# gate FAILED 2026-06-10: TE 0.0466→0.0570, ordering fail; reverted + superseded by C1.
COLOR_CALIBRATION_RERANK = False
COLOR_CALIBRATION_ALPHA  = 0.3

# C1 (V28): Catalog-relative V-A calibration — fix scale mismatch between color model
# (Jonauskaite absolute scale) and catalog V-A (MERT-compressed, A max ~0.72).
# Linear rescale: V_cal = V_p5 + (V_p95-V_p5)*V_raw, same for A.
# Percentiles computed from song_va at startup. Preserves ranking; fixes OOD queries.
COLOR_VA_CATALOG_CALIBRATE = True

# P2 (V29): V-A space MMR for intra-list diversity improvement.
# Applies a second MMR pass using V-A embeddings after _fast_rank.
# Fixes low ILD for red (0.019) and black (0.011) vs blue (0.059) reference.
# lambda_=0.5: balanced relevance-diversity (vs default 0.7 relevance-heavy).
# Gate: ILD(red)>=0.030, ILD(black)>=0.025, TE not regress.
COLOR_MMR_VA_DIVERSITY = True
COLOR_MMR_VA_LAMBDA    = 0.5

# P3 (V29): Adaptive RBF sigma for sparse V-A regions (white TE=0.054).
# Widens sigma when fewer than 200 songs are within radius 0.05 of query V-A.
# Gate: white TE < 0.050, TE overall not regress.
COLOR_ADAPTIVE_SIGMA = False

# ── VALIDATION CLAIMS (R6, 2026-06-10 updated) ──────────────────────────────
# What IS validated:
#   - Color→V-A mapping: ICEAS centroids (Jonauskaite 2020, n=4598, 30 countries)
#   - V-A emotion bridge: Palmer 2013 r=.89-.99, Whiteford 2018 PARAFAC
#   - Emotion mediation: PLOS ONE 2015 pone.0144013 (60–75% variance explained,
#     beats audio-only 3/4 colour dimensions)
#   - MER meta ACM 3796518 (Eerola & Anderson 2026): arousal r=.81 > valence r=.67;
#     NN not better than linear/tree at V-A regression
#   - Structural battery T1-T4 ALL PASS: monotonicity, commensurability,
#     distribution, cross-quadrant purity
#   - Targeting-error 0.043 CI[0.028,0.061]; 5-6× better than 5 baselines (FDR pass)
#   - Journey: KS=0.135, monotonicity ρ=0.896, Iso-Principle (Starcke 2024)
# What is NOT validated:
#   - Color-emotion mapping for Vietnamese listeners (ICEAS global, not VN-specific)
#   - Song valence labels: Gemini-based, corroborated weakly by XLM-R (ρ=0.263)
#   - Color→song-match gold-set study (future work, needs 3 listeners × 2h)
#   - Offline targeting-error ≠ user satisfaction (offline-online r≈.28, Dacrema 2021)
# Reference: Jonauskaite 2025 (128-year review): universal patterns exist but
#   "nation predicted above universals" — Vietnamese red=luck vs global red=anger.



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
RELABELED_EMOTIONS_FILE = str(DATA_DIR / "emotion_labels_v6b.json")  # V6b: A=80%MERT+20%NRC-VAD; V=20%MERT+70%NRC-VAD+10%EmoBank — no LLM; r(V,A)=0.140
VALENCE_CALIBRATION_FILE = str(DATA_DIR / "valence_calibration.json")  # isotonic fit on VN gold-set (V17)

# ============================================================================
# System Settings
# ============================================================================
RANDOM_SEED = 42
VERBOSE = False  # Set True to see detailed logs

# GPU settings
USE_GPU = True  # Auto-detect CUDA if available

