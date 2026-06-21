import os
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

from config import *

# Import color mapping
from core.advanced_color_mapping import get_advanced_color_mapper as get_color_mapper

from core.emotion_analysis import get_emotion_analyzer
from core import color_va
# Cross-platform reproducible descending argsort — moved to core/ranking/_stable.py
# so the extracted ranking helpers (coherence/journey) share the exact same tie-break.
from core.ranking._stable import argsort_desc_stable as _argsort_desc_stable
from core.ranking.artist import cap_per_artist as _cap_per_artist_fn
from core.ranking import coherence as _coherence
from core.ranking import journey as _journey
from core import explain as _explain


def detect_artist_column(df):
    """Detect artist column name from dataset"""
    for name in ['artist', 'artist_name', 'artists', 'performer']:
        if name in df.columns:
            return name
    return None


# Columns the result-builders must carry through so the API (and the frontend Smart
# Crossfade) sees per-track loudness, cue points, downbeats, vocal regions and the
# (DB-reconciled) duration. Hydrated from the DB at startup; without these in the
# allowlist, recommend_by_song / _build_result_df silently drop them → planCrossfade
# loses vocal_end_s/duration and mis-decides the transition. duration_ms (DB) takes
# precedence over the stale CSV track_duration_ms in api _song_to_dict.
CROSSFADE_PASSTHROUGH_COLS = [
    'loudness_lufs', 'fade_out_cue_s', 'fade_in_cue_s', 'downbeat_times_json',
    'vocal_start_s', 'vocal_end_s', 'duration_ms', 'track_duration_ms', 'mp3_duration_s',
]


class MusicRecommender:

    def __init__(self,
                 data_path=PROCESSED_FILE,
                 embeddings_path=EMBEDDINGS_FILE,
                 verbose=VERBOSE):

        self.verbose = verbose

        logger.info("Initializing Music Recommender v6.0 (Multimodal + Lyrics)...")

        self.color_mapper = get_color_mapper()
        self.emotion_lexicon, self.emotion_classifier, self.emotion_fusion = get_emotion_analyzer()

        if self.verbose:
            logger.debug("Loaded emotion analysis system")

        # Load data
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Data file not found: {data_path}")

        self.df = pd.read_csv(data_path)
        self.n_songs = len(self.df)

        if self.verbose:
            logger.debug(f"Loaded {self.n_songs:,} songs")

        # Remove Spotify URLs — we use local audio files now
        for col in ['track_url', 'preview_url']:
            if col in self.df.columns:
                self.df.drop(columns=[col], inplace=True)
        if self.verbose:
            logger.debug("Using local audio (Spotify URLs removed)")

        # Load embeddings
        if os.path.exists(embeddings_path):
            self.embeddings = np.load(embeddings_path)

            # Validate embeddings size matches dataset
            if self.embeddings.shape[0] != self.n_songs:
                logger.warning(
                    f"Embeddings size mismatch ({self.embeddings.shape[0]} vs {self.n_songs})"
                    " — disabling lyrics embeddings, using audio + color only"
                )
                self.embeddings = None
                self.embeddings_normalized = None
            else:
                # Pre-normalize for fast cosine similarity
                norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1
                self.embeddings_normalized = self.embeddings / norms
                if self.verbose:
                    logger.debug(f"Loaded embeddings: {self.embeddings.shape}")
        else:
            self.embeddings = None
            self.embeddings_normalized = None

        # Audio features
        self.audio_features = [f for f in AUDIO_FEATURES if f in self.df.columns]
        self._normalize_audio_features()

        # Pre-compute all color-related features (CRITICAL for speed)
        if 'color_hex' in self.df.columns:
            self.colors = self.df['color_hex'].values
            self._precompute_all_features()
            if self.verbose:
                logger.debug("Pre-computed color & emotion features")
        else:
            self.colors = None

        # Pillar E — load pre-computed emotion labels (E-RELABEL v2 preferred over CLAP)
        _emo_file = (RELABELED_EMOTIONS_FILE
                     if globals().get('USE_RELABELED_EMOTIONS', False)
                     and os.path.exists(globals().get('RELABELED_EMOTIONS_FILE', ''))
                     else CLAP_EMOTIONS_FILE)
        if ENABLE_CLAP_EMOTION and os.path.exists(_emo_file) \
                and 'fused_emotion' not in self.df.columns:
            self._load_clap_emotions()

        # Fallback: derive fused_emotion from lyrics lexicon when no CLAP file
        if 'lyrics_cleaned' in self.df.columns and 'fused_emotion' not in self.df.columns:
            self._analyze_lyrics_emotions()

        # Recompute song_va now that fused_emotion labels are available.
        # _precompute_all_features runs before CLAP load, so song_va was built
        # with the default 'happy' for all songs. Now that real labels are loaded,
        # re-derive the audio+lyrics V-A with correct CLAP Russell centroids.
        if self.colors is not None and 'fused_emotion' in self.df.columns:
            self._recompute_song_va()
            self._compute_va_calibration()
            # Sync v6c song_va back to df so _fast_rank / _build_result_df return values
            # that match the recommendation scoring signal. audio_matrix / tonal_matrix
            # are already built above — this does not affect those pre-computed arrays.
            self.df['valence'] = self.song_va[:, 0]
            self.df['arousal'] = self.song_va[:, 1]

        # Re-derive mood_quadrant from the trusted emotion labels (the CSV's
        # mood_quadrant was built from the broken raw-arousal column + a fixed 0.5
        # cut → 98% collapsed to Q3/Q4). Browse-by-mood / /api/moods read this column.
        if 'fused_emotion' in self.df.columns:
            self._derive_mood_quadrant()

        # Artist column for diversity
        self.artist_col = detect_artist_column(self.df)
        if self.artist_col:
            self.artists = self.df[self.artist_col].values
            if self.verbose:
                logger.debug("Artist diversity enabled")
        else:
            self.artists = None

        # Pillar A — MERT audio embeddings (Li et al. 2023)
        self.mert_matrix = None
        if ENABLE_MERT and os.path.exists(MERT_EMBEDDINGS_FILE):
            try:
                mert_raw = np.load(MERT_EMBEDDINGS_FILE)
                if mert_raw.shape[0] == self.n_songs and mert_raw.ndim == 2 and mert_raw.shape[1] > 0:
                    mert_raw = mert_raw.astype(np.float64)  # float64 reductions → cross-platform reproducible
                    norms = np.linalg.norm(mert_raw, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    mert_norm = mert_raw / norms                       # float64
                    self.mert_matrix = mert_norm.astype(np.float32)
                    # V37: anisotropy-corrected (mean-centred + renormalised) MERT for
                    # acoustic-coherence scoring. Raw MERT cosines saturate ~0.9 (narrow
                    # cone) so they can't discriminate "feel alike"; centring restores
                    # dynamic range (random≈0.0 vs near-neighbour≈0.45). See _coherent_cluster_select.
                    mc = mert_norm - mert_norm.mean(axis=0, keepdims=True)   # float64
                    mcn = np.linalg.norm(mc, axis=1, keepdims=True)
                    mcn[mcn == 0] = 1
                    self.mert_centered = (mc / mcn).astype(np.float32)
                    logger.info(f"[MERT] Loaded {self.mert_matrix.shape} embeddings (+centred for coherence)")
                else:
                    logger.warning(
                        f"[MERT] Shape mismatch {mert_raw.shape} — expected ({self.n_songs}, D) — disabled"
                    )
            except Exception as e:
                logger.warning(f"[MERT] Load failed: {e} — disabled")

        # V40 (2026-06-13): optional MuQ audio backbone (SOTA-2025, arXiv 2501.01108).
        # After RE-OPTIMIZATION, MuQ beats MERT on BOTH end metrics: editorial NDCG@10
        # 0.0739 vs 0.0708 (similar-song) and colour-TE 0.0267 vs 0.0302. Replaces MERT in
        # `self.mert_matrix` (the audio-backbone slot — name kept to avoid churn) + rebuilds
        # the centred matrix for colour coherence. MuQ embeddings aligned to catalog order via
        # muq_metadata done_track_ids. Cover index (precomputed on MERT) is unaffected.
        # Resolve from config (DATA_DIR / serving release), NOT a CWD-relative "data/..."
        # path: in Docker CWD=/app and the .npy lives in the mounted serving release, so the
        # old hardcoded path silently failed → MuQ never loaded → the app fell back to the
        # MERT backbone, giving DIFFERENT recommendations than local. (Same bug class as clean_bpm.)
        _muq_file = globals().get("MUQ_EMBEDDINGS_FILE", "data/muq_embeddings.npy")
        _muq_meta = globals().get("MUQ_METADATA_FILE", "data/muq_metadata.json")
        if str(globals().get("AUDIO_BACKBONE", "mert")).lower() == "muq" \
                and os.path.exists(_muq_file):
            try:
                import json as _json
                muq = np.load(_muq_file)
                meta = _json.load(open(_muq_meta))
                order = meta.get("done_track_ids") or meta.get("track_ids")
                tids = self.df["track_id"].astype(str).tolist()
                if order and len(order) == len(muq):
                    pos = {str(t): i for i, t in enumerate(order)}
                    muq = np.array([muq[pos[t]] if t in pos else np.full(muq.shape[1], np.nan)
                                    for t in tids])
                # float64 for the mean-centring + norms: float32 reductions差 ~1e-5 between
                # arm64 (Accelerate) and amd64 (OpenBLAS), which shifts mert_centered enough to
                # flip the greedy coherence cascade → different colour order per host. Computing
                # in float64 then storing float32 yields byte-identical embeddings everywhere.
                muq64 = muq.astype(np.float64)
                nn = np.linalg.norm(muq64, axis=1, keepdims=True); nn[nn == 0] = 1
                self.mert_matrix = (muq64 / nn).astype(np.float32)
                mc = muq64 - np.nanmean(muq64, axis=0, keepdims=True)
                mcn = np.linalg.norm(mc, axis=1, keepdims=True); mcn[mcn == 0] = 1
                self.mert_centered = (mc / mcn).astype(np.float32)
                # Tracks absent from muq_metadata become NaN rows above; the nn==0 guard does NOT
                # catch NaN (NaN != 0), so zero them out — a NaN row would otherwise sort to the
                # front of argsort/argmax and poison coherence/journey selection (cosine 0 = neutral).
                n_nan = int(np.isnan(self.mert_matrix).any(axis=1).sum())
                if n_nan:
                    logger.warning(f"[AUDIO] {n_nan} tracks missing MuQ embeddings → zeroed (neutral)")
                self.mert_matrix = np.nan_to_num(self.mert_matrix, nan=0.0)
                self.mert_centered = np.nan_to_num(self.mert_centered, nan=0.0)
                logger.info(f"[AUDIO] backbone=MuQ {self.mert_matrix.shape} (replaces MERT; +centred)")
            except Exception as e:
                logger.warning(f"[MuQ] backbone load failed: {e} — staying on MERT")



        # Instrument tag signal (MTG-Jamendo, 40-dim, fixed 16kHz 2026-06-09)
        # Pre-compute L2-normalised instrument vector for each song.
        # Applied as multiplicative bonus in recommend_by_song when ENABLE_TAG_SIGNAL=True.
        self.instrument_tag_matrix = None
        if ENABLE_TAG_SIGNAL and 'instrument_tags' in self.df.columns:
            self.instrument_tag_matrix = self._build_instrument_matrix()
            if self.instrument_tag_matrix is not None:
                logger.info(f"[TAG] Instrument tag matrix: {self.instrument_tag_matrix.shape}")

        # Cover/duplicate filter — exclude same-song versions from recommendations
        self._cover_index: dict = {}  # track_id → set of cover track_ids
        if ENABLE_COVER_FILTER and os.path.exists(COVER_INDEX_FILE):
            try:
                import json as _json
                raw = _json.load(open(COVER_INDEX_FILE))
                # Build reverse lookup: original_index → set of indices to exclude
                tid_to_idx = {str(row["track_id"]): i
                              for i, row in self.df[["track_id"]].iterrows()}
                self._cover_exclude: dict = {}  # int idx → set of int idxs
                for tid, covers in raw.items():
                    i = tid_to_idx.get(str(tid))
                    if i is None:
                        continue
                    excl = {tid_to_idx[str(c)] for c in covers if str(c) in tid_to_idx}
                    if excl:
                        self._cover_exclude[i] = excl
                logger.info(f"[COVER] Loaded cover index: {len(self._cover_exclude)} songs have covers")
            except Exception as e:
                logger.warning(f"[COVER] Load failed: {e}")
        else:
            self._cover_exclude: dict = {}

        logger.info(f"Recommender ready — {self.n_songs:,} songs loaded")

    def _build_instrument_matrix(self) -> 'np.ndarray | None':
        """Build (N, 40) L2-normalised instrument probability matrix from instrument_tags JSON."""
        import json as _json
        from tools.extract_audio_features import MTG_INST_LABELS  # 40 instrument names
        n_inst = len(MTG_INST_LABELS)
        inst_idx = {name: i for i, name in enumerate(MTG_INST_LABELS)}
        matrix = np.zeros((self.n_songs, n_inst), dtype=np.float32)
        n_loaded = 0
        for i, v in enumerate(self.df['instrument_tags'].values):
            if not isinstance(v, str) or not v.strip():
                continue
            try:
                d = _json.loads(v)
                for name, score in d.items():
                    if name in inst_idx:
                        matrix[i, inst_idx[name]] = float(score)
                n_loaded += 1
            except Exception:
                continue
        if n_loaded < self.n_songs * 0.5:
            logger.warning(f"[TAG] Only {n_loaded}/{self.n_songs} songs have instrument tags — disabling")
            return None
        # L2-normalise rows
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def _normalize_audio_features(self):
        """Normalize audio features to [0, 1]"""
        audio_data = self.df[self.audio_features].copy()

        if 'tempo' in audio_data.columns:
            audio_data['tempo'] = ((audio_data['tempo'] - TEMPO_MIN) / (TEMPO_MAX - TEMPO_MIN)).clip(0, 1)
        if 'loudness' in audio_data.columns:
            audio_data['loudness'] = ((audio_data['loudness'] - LOUDNESS_MIN) / (LOUDNESS_MAX - LOUDNESS_MIN)).clip(0, 1)
        if 'key' in audio_data.columns:
            audio_data['key'] = audio_data['key'] / 11.0

        self.audio_matrix = audio_data.fillna(audio_data.median()).values

    def _precompute_all_features(self):
        """
        Pre-compute all features for instant query response

        Pre-computed arrays:
        - song_va: (n_songs, 2) - valence, arousal for each song
        - song_emotion_vec: (n_songs, 13) - emotion probability vector
        - color_lab: (n_songs, 3) - LAB color space for CIEDE2000
        """
        # Emotion labels — derived from color mapper profiles to stay in sync
        self.emotion_labels = sorted(self.color_mapper.emotion_color_profiles.keys())
        n_emotions = len(self.emotion_labels)

        # Pre-allocate arrays
        self.song_va = np.zeros((self.n_songs, 2))  # valence, arousal
        self.song_emotion_vec = np.zeros((self.n_songs, n_emotions))
        self.color_hsl = np.zeros((self.n_songs, 3))

        # Emotion vector from color_hex — NOTE: color_hex is SYNTHESIZED from the song's
        # own audio V-A/tempo/mode (tools/process_data.apply_color_mapping), NOT extracted
        # from album art. So this vec is a redundant non-linear re-encoding of V-A.
        # Kept only as the emotion signal for recommend_by_colors display.
        for idx in range(self.n_songs):
            color = self.colors[idx]
            if pd.isna(color):
                self.color_hsl[idx] = [0, 0, 50]
                continue
            try:
                hsl = self.color_mapper.hex_to_hsl(color)
                self.color_hsl[idx] = hsl
                emotion_probs = self.color_mapper.color_to_emotion_probs(color)
                for i, emo in enumerate(self.emotion_labels):
                    self.song_emotion_vec[idx, i] = emotion_probs.get(emo, 0)
            except Exception:
                self.color_hsl[idx] = [0, 0, 50]

        row_sums = self.song_emotion_vec.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        self.song_emotion_vec = self.song_emotion_vec / row_sums

        # song_va initial fill — will be recomputed after CLAP loads via _recompute_song_va
        self._recompute_song_va()
        self._compute_va_calibration()

        # --- Pre-computed feature groups for multi-faceted similarity ---
        # Berenzweig et al. (2004): Separate timbral, rhythmic, and tonal
        # features yield better similarity than a single flat vector.
        self._timbral_cols = [f for f in ['energy', 'loudness', 'acousticness',
                                          'instrumentalness', 'speechiness',
                                          'timbre_bright'] if f in self.df.columns]
        self._rhythmic_cols = [f for f in ['tempo', 'danceability', 'liveness',
                                           'arousal'] if f in self.df.columns]
        self._tonal_cols = [f for f in ['valence', 'key', 'mode'] if f in self.df.columns]

        def _col_indices(names):
            return [self.audio_features.index(c) for c in names if c in self.audio_features]

        self._timbral_idx = _col_indices(self._timbral_cols)
        self._rhythmic_idx = _col_indices(self._rhythmic_cols)
        self._tonal_idx = _col_indices(self._tonal_cols)

        # Pre-extract sub-matrices for fast lookup
        if self._timbral_idx:
            self._timbral_matrix = self.audio_matrix[:, self._timbral_idx]
        else:
            self._timbral_matrix = self.audio_matrix
        if self._rhythmic_idx:
            self._rhythmic_matrix = self.audio_matrix[:, self._rhythmic_idx]
        else:
            self._rhythmic_matrix = self.audio_matrix
        if self._tonal_idx:
            self._tonal_matrix = self.audio_matrix[:, self._tonal_idx]
        else:
            self._tonal_matrix = self.audio_matrix

        # Sentiment vector per song (for polarity alignment)
        self._sentiment_vec = np.zeros(self.n_songs)
        if 'sentiment_compound' in self.df.columns:
            self._sentiment_vec = self.df['sentiment_compound'].fillna(0).values

        # Mood-quadrant one-hot for category matching
        # McFee & Lanckriet (2011): Genre/mood coherence boosts perceived similarity
        self._mood_labels = self.df.get('fused_emotion', pd.Series([''] * self.n_songs)).fillna('').values

    def _recompute_song_va(self) -> None:
        """Compute song_va from AUDIO+LYRICS signals (not album-art color).

        Root cause fix (2026-05-30): the old approach stored V-A derived from
        each song's album-art color_hex, which reflected album art palette NOT
        musical content (measured valence correlation with multi-signal proxy:
        r=0.22 — effectively random).

        New approach (evidence-grounded):
          Arousal = 0.60×Essentia_energy + 0.40×Essentia_arousal
            → audio energy/tempo reliably predicts arousal across cultures
              (r≈0.81, Eerola & Anderson ACM CSUR 2026; arXiv:2302.13321)
          Valence = 0.50×CLAP_Russell_centroid + 0.50×Essentia_valence
            → CLAP fused_emotion labels mapped to Russell 1980 circumplex
              centroids provide valence signal grounded in music content;
              blended with Essentia audio valence estimate

        Called twice: once during _precompute_all_features (fused_emotion may
        not yet exist → defaults to 'happy') and once after CLAP/lexicon load
        to use real emotion labels.

        E-RELABEL (2026-05-31): when the v2 emotion file provides per-song valence/
        arousal (lyrics-valence + rank-normalised audio-arousal), use those DIRECTLY
        — they are the trusted per-song mood estimate, avoid the label→centroid
        quantisation loss, and put song_va on the same scale as GT-COLOR.
        """
        if globals().get('USE_RELABELED_EMOTIONS', False):
            import json as _json
            _f = globals().get('RELABELED_EMOTIONS_FILE', '')
            if _f and os.path.exists(_f):
                try:
                    with open(_f) as _fh:
                        _v2 = _json.load(_fh)
                    tids = self.df.get('track_id',
                                       pd.Series(range(self.n_songs))).astype(str).values
                    val = np.array([float(_v2.get(t, {}).get('valence', 0.5)) for t in tids])
                    aro = np.array([float(_v2.get(t, {}).get('arousal', 0.5)) for t in tids])
                    self.song_va[:, 0] = np.clip(val, 0.0, 1.0)
                    self.song_va[:, 1] = np.clip(aro, 0.0, 1.0)
                    return
                except (ValueError, KeyError, OSError):
                    pass  # fall through to the label-derived computation

        _RUSSELL_V = {"happy": 0.90, "excited": 0.70, "peaceful": 0.78, "calm": 0.72,
                      "melancholic": 0.30, "sad": 0.15, "tense": 0.35, "angry": 0.15}
        _RUSSELL_A = {"happy": 0.75, "excited": 0.90, "peaceful": 0.20, "calm": 0.15,
                      "melancholic": 0.35, "sad": 0.30, "tense": 0.85, "angry": 0.90}

        def _norm(col):
            if col not in self.df.columns:
                return np.full(self.n_songs, 0.5)
            v = self.df[col].fillna(0.5).astype(float).values
            mn, mx = v.min(), v.max()
            return np.clip((v - mn) / (mx - mn + 1e-9), 0.0, 1.0)

        emo_labels = (
            self.df['fused_emotion'].fillna('happy').str.lower().values
            if 'fused_emotion' in self.df.columns
            else np.full(self.n_songs, 'happy')
        )
        clap_v = np.array([_RUSSELL_V.get(e, 0.50) for e in emo_labels])
        clap_a = np.array([_RUSSELL_A.get(e, 0.50) for e in emo_labels])

        # 'valence' = Essentia valence (reliable), 'valence_estimated' is a broken col
        song_arousal = 0.60 * _norm('energy') + 0.40 * _norm('arousal')
        song_valence = 0.50 * clap_v + 0.50 * _norm('valence')

        self.song_va[:, 0] = np.clip(song_valence, 0.0, 1.0)
        self.song_va[:, 1] = np.clip(song_arousal, 0.0, 1.0)

        # Override with fused_valence/fused_energy if available (full pipeline)
        if 'fused_valence' in self.df.columns:
            fused_va = self.df[['fused_valence', 'fused_energy']].fillna(0.5).values
            self.song_va = np.clip(fused_va, 0.0, 1.0)

    def _compute_va_calibration(self) -> None:
        """Prepare the colour→song V-A matching space.

        V31 (COLOR_VA_RANK_MATCH): build the catalog's empirical-CDF ranks so the
        colour scorer matches in quantile space (see config note). When rank-match
        is on we do NOT inject linear calibration — hsl_to_va keeps returning the
        raw Oklab V-A, which is used directly as the target quantile. self.song_va
        (the real per-song mood values) is left untouched for display/atmosphere.

        C1 (V28, legacy fallback): when rank-match is off, compute catalog V-A
        percentiles and inject a linear rescale into the colour mapper so its
        Jonauskaite-absolute predictions land in the MERT-compressed catalog support.
        """
        # song_va_match is what the colour scorer / journey compare against.
        if COLOR_VA_RANK_MATCH:
            self.song_va_match, self._va_sorted_v, self._va_sorted_a = \
                color_va.build_rank_match_space(self.song_va, self.n_songs)
            # Ensure no stale linear calibration leaks into hsl_to_va.
            if hasattr(self.color_mapper, 'set_va_calibration'):
                self.color_mapper._va_cal = None
            return

        self.song_va_match = self.song_va
        if not COLOR_VA_CATALOG_CALIBRATE:
            return
        cal = color_va.catalog_va_percentiles(self.song_va)
        self._va_cal = cal
        if hasattr(self.color_mapper, 'set_va_calibration'):
            self.color_mapper.set_va_calibration(**cal)

    def _color_target_quantile(self, cva) -> np.ndarray:
        """Map a colour's raw V-A to its percentile within the catalog's own mood
        distribution (V36) — delegates to color_va.target_quantile. Only meaningful in
        rank-match mode (match space = catalog CDF ranks)."""
        return color_va.target_quantile(cva, self._va_sorted_v, self._va_sorted_a)

    # Russell mood quadrant + Vietnamese label maps (moved to core/color_va.py).
    _EMO_QUADRANT = color_va.EMO_QUADRANT

    def _derive_mood_quadrant(self) -> None:
        """Overwrite mood_quadrant from fused_emotion (trusted labels) instead of the
        broken raw-arousal column. Fixes browse-by-mood returning ~nothing for Q1/Q2."""
        emo = self.df['fused_emotion'].fillna('').str.lower()
        self.df['mood_quadrant'] = emo.map(self._EMO_QUADRANT).fillna(
            self.df.get('mood_quadrant', 'Q3: Sad/Melancholic'))

    def _analyze_lyrics_emotions(self):
        """One-time lyrics emotion analysis"""
        fused_valence = []
        fused_energy = []
        fused_emotion = []

        for idx, row in self.df.iterrows():
            lyrics = row.get('lyrics_cleaned', '')
            audio_val = row.get('valence', 0.5)
            # Prefer DEAM arousal over energy proxy when available
            audio_eng = row.get('arousal', row.get('energy', 0.5))
            if pd.isna(audio_eng):
                audio_eng = row.get('energy', 0.5)

            if lyrics and not pd.isna(lyrics):
                emotion_scores = self.emotion_lexicon.analyze_lyrics(lyrics)
                lyrics_val, lyrics_aro = self.emotion_classifier.emotions_to_valence_arousal(emotion_scores)

                # Fuse audio and lyrics (research-based weighting)
                # Audio features are more reliable for valence/arousal
                val = 0.6 * audio_val + 0.4 * lyrics_val
                eng = 0.6 * audio_eng + 0.4 * lyrics_aro
            else:
                val, eng = audio_val, audio_eng

            emotion = self.emotion_fusion.get_emotion_label(val, eng)
            fused_valence.append(val)
            fused_energy.append(eng)
            fused_emotion.append(emotion)

        self.df['fused_valence'] = fused_valence
        self.df['fused_energy'] = fused_energy
        self.df['fused_emotion'] = fused_emotion

        if self.verbose:
            emotion_dist = self.df['fused_emotion'].value_counts()
            top5 = ", ".join(f"{e}:{c}" for e, c in emotion_dist.head(5).items())
            logger.debug(f"Emotion distribution (top 5): {top5}")

    def _load_clap_emotions(self) -> None:
        """Load pre-computed emotion labels and merge into self.df.

        E-RELABEL: prefer the re-derived labels (lyrics-valence + audio-arousal) over
        the biased CLAP audio zero-shot labels when available (config flag). The v2
        file maps track_id → {label, valence, arousal}; CLAP file maps track_id → label.
        """
        import json
        use_v2 = (globals().get('USE_RELABELED_EMOTIONS', False)
                  and os.path.exists(globals().get('RELABELED_EMOTIONS_FILE', '')))
        src = RELABELED_EMOTIONS_FILE if use_v2 else CLAP_EMOTIONS_FILE
        tag = "RELABEL-v2" if use_v2 else "CLAP"
        with open(src) as fh:
            emo_map: dict = json.load(fh)

        def _label(entry):
            return entry.get('label') if isinstance(entry, dict) else entry

        track_ids = self.df.get("track_id", pd.Series(range(self.n_songs))).astype(str).values
        labels = np.array([_label(emo_map.get(tid)) for tid in track_ids], dtype=object)
        self.df["fused_emotion"] = labels

        n_labeled = pd.notna(pd.Series(labels)).sum()
        coverage = n_labeled / self.n_songs * 100
        logger.info(f"[{tag}] Loaded {n_labeled}/{self.n_songs} emotion labels ({coverage:.1f}%)")

        # For un-labelled songs fall back to heuristic V-A mapping
        missing_mask = pd.isna(self.df["fused_emotion"])
        n_missing = int(missing_mask.sum())
        if n_missing > 0:
            valence_arr = self.df.loc[missing_mask, "valence"].fillna(0.5).values
            arousal_arr = self.df.loc[missing_mask, "arousal"].fillna(
                self.df.loc[missing_mask, "energy"].fillna(0.5)
            ).values
            fallback = [
                self.emotion_fusion.get_emotion_label(float(v), float(a))
                for v, a in zip(valence_arr, arousal_arr)
            ]
            self.df.loc[missing_mask, "fused_emotion"] = fallback
            logger.info(f"[CLAP] Filled {n_missing} missing labels via V-A heuristic")

    def _resolve_indices(self, track_ids):
        """Map track_id strings → positional indices into the score arrays.

        df has a positional RangeIndex (see api/music.py similar-song resolution),
        so df.index values are valid indices into the (n_songs,) score vectors.
        Returns [] when nothing matches — callers treat that as "exclude nothing".
        """
        if not track_ids or 'track_id' not in self.df.columns:
            return []
        return self.df.index[self.df['track_id'].isin(set(track_ids))].tolist()

    def recommend_by_colors(self,
                           color_hexes,
                           top_k=DEFAULT_TOP_K,
                           weights=None,
                           diversity_penalty=DIVERSITY_PENALTY,
                           exclude_ids=None):

        if isinstance(color_hexes, str):
            color_hexes = [color_hexes]

        # V23: cap at 2 colours. 1 colour = static mood; 2 colours = a mood JOURNEY
        # (from colour A's mood → colour B's mood), sequenced smoothly by the
        # Iso-Principle (Starcke 2024, d=0.52). 3+ colours dropped — interleaved
        # multi-mood playlists cause "mood whiplash" (user-reported, V23 research).
        color_hexes = list(color_hexes)[:2]

        if self.verbose:
            logger.debug(f"Recommending by colors: {color_hexes}")

        # F3-cleanup (V19): scorer is pure V-A heteroscedastic — lyric encoding and
        # emotion vectors are no longer used in _color_score. Build only what is needed:
        # per-colour V-A point + emotion vec (for _build_color_why label and display).
        # PhoBERT keyword encoding removed (was ~150ms/query, confirmed dead by F2 ablation).
        per_color_va = []          # [[v, a], ...]
        per_color_emotion = []     # [emotion_vec, ...] — display only (why-chip label)
        query_emotion = np.zeros(len(self.emotion_labels))
        target_quadrant = None

        for color in color_hexes:
            try:
                q_valence, q_arousal = self.color_mapper.hsl_to_va(color)
                per_color_va.append([q_valence, q_arousal])
                emotion_probs = self.color_mapper.color_to_emotion_probs(color)
                evec = np.array([emotion_probs.get(emo, 0.0) for emo in self.emotion_labels])
                per_color_emotion.append(evec)
                query_emotion += evec
            except (ValueError, KeyError, TypeError):
                per_color_va.append([0.5, 0.5])
                per_color_emotion.append(np.ones(len(self.emotion_labels)) / len(self.emotion_labels))
        # per_color_lyrics no longer needed; pass None sentinels for API compat downstream
        per_color_lyrics = [None] * len(per_color_va)

        per_color_va = np.array(per_color_va, dtype=float)  # (C, 2)

        # Endless-radio: drop already-played tracks so re-querying the same colour
        # yields fresh songs (no loop → avoids the inverted-U satiation curve).
        exclude_idx = self._resolve_indices(exclude_ids)

        return self._rank_by_color_features(
            per_color_va, per_color_emotion, per_color_lyrics,
            color_hexes, top_k, diversity_penalty, exclude_idx=exclude_idx)

    def _rank_by_color_features(self, per_color_va, per_color_emotion,
                                per_color_lyrics, color_hexes, top_k,
                                diversity_penalty, exclude_idx=None):
        """Pure V-A heteroscedastic RBF scorer (F3 V19).

        Matches colour V-A against song V-A using per-axis bandwidth (σ_V>σ_A —
        valence less reliable than arousal per Eerola/Yang). F2 ablation confirmed
        lyr-cosine and emo-cosine add no information; both removed.
        Multi-colour: RRF union so each colour has equal representation.
        per_color_lyrics accepted for API compat but ignored.
        """
        per_color_va = np.asarray(per_color_va, dtype=float)

        # V36: map each colour's raw V-A through the catalog CDF to its target quantile,
        # so the 12 colours span the full catalog instead of the middle band (fixes "every
        # colour feels mid/sad"). Centralised here so all downstream paths — single-colour
        # RBF, multi-colour RRF, journey waypoints, adaptive-σ, quadrant bonus — use the
        # same spread targets against song_va_match (catalog ranks).
        if (COLOR_VA_RANK_MATCH and COLOR_VA_CDF_TARGET
                and getattr(self, '_va_sorted_v', None) is not None):
            per_color_va = np.array(
                [self._color_target_quantile(c) for c in per_color_va], dtype=float)

        # Centroid for quadrant display only (no penalty applied in F3).
        query_va_centroid = per_color_va.mean(axis=0)

        # Centroid quadrant — for verbose logging and why-chip display.
        valence, arousal = query_va_centroid
        if valence >= 0.5 and arousal >= 0.5:
            target_quadrant = 'Q1'  # Happy/Excited
        elif valence < 0.5 and arousal >= 0.5:
            target_quadrant = 'Q2'  # Angry/Tense
        elif valence < 0.5 and arousal < 0.5:
            target_quadrant = 'Q3'  # Sad/Melancholic
        else:
            target_quadrant = 'Q4'  # Calm/Peaceful

        if self.verbose:
            print(f"   Query V-A: valence={valence:.2f}, arousal={arousal:.2f} ({target_quadrant})")

        # ===== PER-COLOUR SCORING (F3 V19) =====
        # Pure V-A heteroscedastic RBF. fused_emo retained for the why-chip only.
        fused_emo = (self.df['fused_emotion'].fillna('').str.lower().values
                     if 'fused_emotion' in self.df.columns else None)

        # V-A heteroscedastic RBF (F3/V19). σ_V > σ_A: trust arousal more than
        # valence (arousal ~80% audio-predictable, valence ~17%; Delbouys 2018).
        _sigma_v = COLOR_SCORE_VA_SIGMA_V
        _sigma_a = COLOR_SCORE_VA_SIGMA_A

        # P3 (V29): Adaptive sigma for sparse V-A regions (white TE=0.054).
        if COLOR_ADAPTIVE_SIGMA and len(per_color_va) == 1:
            qva = np.asarray(per_color_va[0], float)
            nearby = int(np.sum(np.sum((getattr(self, 'song_va_match', self.song_va) - qva) ** 2, axis=1) < 0.05 ** 2))
            if nearby < 50:
                _sigma_v = COLOR_SCORE_VA_SIGMA_V * 1.8
                _sigma_a = COLOR_SCORE_VA_SIGMA_A * 1.8
            elif nearby < 200:
                _sigma_v = COLOR_SCORE_VA_SIGMA_V * 1.3
                _sigma_a = COLOR_SCORE_VA_SIGMA_A * 1.3

        # V31: match in quantile space (song_va_match = catalog CDF ranks when
        # COLOR_VA_RANK_MATCH; cva is the colour's raw V-A used as target quantile).
        # Falls back to song_va when rank-match is off.
        match_va = getattr(self, 'song_va_match', self.song_va)

        def _color_score(cva, evec, lyr):
            dv = match_va[:, 0] - cva[0]
            da = match_va[:, 1] - cva[1]
            va_s = np.exp(-0.5 * ((dv / _sigma_v) ** 2 + (da / _sigma_a) ** 2))
            emo_s = np.full(self.n_songs, 0.5)
            lyr_s = np.full(self.n_songs, 0.5)
            return va_s, va_s, emo_s, lyr_s

        # ---- Single colour: unambiguous mood → cross-mood penalty + RRF ----
        if len(per_color_va) == 1:
            final_scores, va_s, emo_s, lyr_s = _color_score(
                per_color_va[0], per_color_emotion[0], per_color_lyrics[0])
            # F3: cross-mood penalty removed — the heteroscedastic V-A RBF already
            # makes large mood-distance songs score near-zero without explicit rules.

            # A3 (V27): calibration bonus — boost underrepresented target quadrant.
            # Addresses catalog Q3-skew (35.5% sad) by giving songs in the same
            # V-A quadrant as the query color a small additive boost before ranking.
            if COLOR_CALIBRATION_RERANK:
                qv, qa = float(per_color_va[0][0]), float(per_color_va[0][1])
                in_target = (
                    (match_va[:, 0] >= 0.5) == (qv >= 0.5)
                ) & (
                    (match_va[:, 1] >= 0.5) == (qa >= 0.5)
                )
                alpha = COLOR_CALIBRATION_ALPHA
                final_scores = (1.0 - alpha) * final_scores + alpha * in_target.astype(float)

            # Endless-radio exclusion: sink already-played songs below every legit
            # score (scores ≥ 0) so all three selectors below skip them — mirrors the
            # reference-song exclusion in recommend_by_song (final_scores[idx] = -1).
            if exclude_idx:
                final_scores[exclude_idx] = -1.0

            # V37: acoustic-coherence selection — V-A picks the mood region, MERT makes
            # the set an on-vibe cluster (feel alike + feel like the colour). Supersedes the
            # V-A-diversity MMR below (which scattered results). Falls back if MERT missing.
            if COLOR_ACOUSTIC_COHERENCE and getattr(self, 'mert_matrix', None) is not None:
                chosen = self._coherent_cluster_select(
                    final_scores, top_k, diversity_penalty)
                res = self._build_result_df(chosen)
            # P2 (V29): V-A space Euclidean MMR — over-fetch then re-rank for ILD.
            # Fixes red/black ILD_raw≈0.013-0.024 (vs blue 0.063 reference).
            # Uses Euclidean distance in V-A space (not cosine) for meaningful
            # diversity within a small V-A neighborhood.
            elif COLOR_MMR_VA_DIVERSITY:
                lam = COLOR_MMR_VA_LAMBDA
                n_cand = min(top_k * 5, self.n_songs)
                top_cands = _argsort_desc_stable(final_scores, n_cand)
                va_cands = match_va[top_cands]           # (n_cand, 2) — match space
                rel = final_scores[top_cands]             # (n_cand,)
                selected_local, remaining = [], list(range(n_cand))
                for _ in range(top_k):
                    if not remaining:
                        break
                    if not selected_local:
                        best = int(np.argmax(rel[remaining]))
                    else:
                        sel_va = va_cands[selected_local]   # (s, 2)
                        # min Euclidean distance to any already-selected song
                        dists = np.min(
                            np.linalg.norm(va_cands[remaining][:, None] - sel_va[None], axis=2),
                            axis=1)
                        mmr_s = lam * rel[remaining] + (1.0 - lam) * dists
                        best = remaining[int(np.argmax(mmr_s))]
                    selected_local.append(best)
                    remaining.remove(best)
                chosen = top_cands[selected_local].tolist()
                res = self._build_result_df(chosen)
            else:
                candidates = (self._rrf_candidates([va_s, emo_s, lyr_s])
                              if ENABLE_RRF else None)
                res = self._fast_rank(final_scores, top_k, diversity_penalty,
                                      restrict_to=candidates)
            if not res.empty and 'original_index' in res.columns:
                res = res.copy()
                res['why'] = self._build_color_why(
                    res['original_index'].tolist(), per_color_va[0],
                    va_s, emo_s, lyr_s, color_hexes[0])
            return res

        # ---- 2 colours: true mood JOURNEY via WAYPOINT SAMPLING (V23 fix) ----
        # Previous approach (RRF union → sort) produced 2 solid blocks: all songs
        # for colour A first, all for colour B after — no intermediate steps.
        # Root cause: RRF rewards songs closest to EITHER endpoint; intermediate songs
        # score low for both → never selected. Sorting selected songs by projection
        # then naturally gives 2 blocks.
        #
        # Fix: WAYPOINT SAMPLING — divide path P1→P2 into top_k evenly-spaced
        # waypoints and greedily pick the best song for each waypoint (excluding
        # already-chosen songs). This FORCES intermediate songs into the playlist.
        # Basis: Iso-Principle (Starcke 2024 d=0.52): ~10-15% V-A shift per step
        # (Saari 2016). top_k=10 waypoints across the path achieves this spacing.
        if COLOR_JOURNEY_ENABLED:
            idxs = self._journey_waypoint_sample(
                per_color_va[0], per_color_va[1], top_k, diversity_penalty,
                exclude_idx=exclude_idx)
            res = self._build_result_df(idxs)
            if not res.empty and 'original_index' in res.columns:
                res = res.copy()
                # why: attribute each song to nearest colour (A or B)
                p1 = np.asarray(per_color_va[0], float)
                p2 = np.asarray(per_color_va[1], float)
                whys = []
                match_va = getattr(self, 'song_va_match', self.song_va)
                for oi in res['original_index'].tolist():
                    oi = int(oi)
                    sv = match_va[oi]
                    # nearest endpoint (in match space)
                    if np.linalg.norm(sv - p1) <= np.linalg.norm(sv - p2):
                        cva, hexc = p1, color_hexes[0]
                    else:
                        cva, hexc = p2, color_hexes[1] if len(color_hexes) > 1 else color_hexes[0]
                    va_s_why = np.exp(-0.5 * (
                        ((match_va[:, 0] - cva[0]) / _sigma_v) ** 2 +
                        ((match_va[:, 1] - cva[1]) / _sigma_a) ** 2))
                    whys.append(self._build_color_why(
                        [oi], cva, va_s_why, np.full(self.n_songs, 0.5),
                        np.full(self.n_songs, 0.5), hexc)[0])
                res['why'] = whys
            return res

        # Fallback (COLOR_JOURNEY_ENABLED=False): RRF union, no journey ordering.
        per_color = []
        for ci, (cva, evec, lyr) in enumerate(
                zip(per_color_va, per_color_emotion, per_color_lyrics)):
            sc, va_s, emo_s, lyr_s = _color_score(cva, evec, lyr)
            
            per_color.append((sc, va_s, emo_s, lyr_s, cva,
                              color_hexes[ci] if ci < len(color_hexes) else None))
        score_stack = np.vstack([p[0] for p in per_color])
        rrf = np.zeros(self.n_songs)
        for sc in score_stack:
            ranks = np.empty(self.n_songs, dtype=float)
            ranks[_argsort_desc_stable(sc)] = np.arange(self.n_songs)
            rrf += 1.0 / (RRF_K + ranks + 1.0)
        rrf_norm = rrf / (rrf.max() + 1e-12)
        res = self._fast_rank(rrf_norm, top_k, diversity_penalty)
        if not res.empty and 'original_index' in res.columns:
            res = res.copy()
            best_color = score_stack.argmax(axis=0)
            whys = []
            for oi in res['original_index'].tolist():
                _sc, va_s, emo_s, lyr_s, cva, hexc = per_color[int(best_color[int(oi)])]
                whys.append(self._build_color_why(
                    [int(oi)], cva, va_s, emo_s, lyr_s, hexc)[0])
            res['why'] = whys
        return res

    def _coherent_cluster_select(self, scores: np.ndarray, top_k: int,
                                 diversity_penalty: float) -> list[int]:
        """V37 acoustically-coherent on-mood selection — delegates to
        core.ranking.coherence.coherent_cluster_select (the recommender owns the matrices)."""
        M = (self.mert_centered if getattr(self, 'mert_centered', None) is not None
             else self.mert_matrix)
        artists = (self.df[self.artist_col].fillna('__unknown__').values
                   if self.artist_col else None)
        cover_excl = getattr(self, '_cover_exclude', {}) if ENABLE_COVER_FILTER else {}
        return _coherence.coherent_cluster_select(
            scores, top_k, diversity_penalty,
            mert=M, artists=artists, cover_excl=cover_excl,
            alpha=COLOR_COHERENCE_ALPHA, overfetch=COLOR_COHERENCE_OVERFETCH)

    def _journey_waypoint_sample(self, p1, p2, top_k: int,
                                  diversity_penalty: float,
                                  exclude_idx=None) -> list[int]:
        """Iso-Principle 2-colour waypoint sampling — delegates to
        core.ranking.journey.waypoint_sample (the recommender owns the matrices)."""
        smooth = COLOR_JOURNEY_AUDIO_SMOOTH
        artists = (self.df[self.artist_col].fillna('__unknown__').values
                   if self.artist_col else None)
        return _journey.waypoint_sample(
            p1, p2, top_k, diversity_penalty,
            match_va=getattr(self, 'song_va_match', self.song_va),
            mert_centered=(getattr(self, 'mert_centered', None) if smooth else None),
            bpm=(self._journey_bpm_array() if smooth else None),
            artists=artists, n_songs=self.n_songs, exclude_idx=exclude_idx,
            sigma_v=COLOR_SCORE_VA_SIGMA_V, sigma_a=COLOR_SCORE_VA_SIGMA_A,
            smooth=smooth, bpm_tau=COLOR_JOURNEY_BPM_TAU, smooth_gamma=COLOR_JOURNEY_SMOOTH_GAMMA)

    def _journey_bpm_array(self) -> "np.ndarray | None":
        """Per-song clean BPM aligned to catalog order (NaN where missing); cached. V39."""
        if hasattr(self, '_bpm_arr'):
            return self._bpm_arr
        # Resolve from DATA_DIR (serving release), not CWD-relative — otherwise in
        # Docker (CWD=/app) this missed the mounted serving data and BPM went NaN.
        path = globals().get("CLEAN_BPM_FILE", "data/clean_bpm.json")
        self._bpm_arr = _journey.load_bpm_array(self.df, self.n_songs, path)
        return self._bpm_arr

    def _build_result_df(self, idxs: list[int]):
        """Build a result DataFrame from a list of song indices (for journey)."""
        if not idxs:
            return pd.DataFrame()
        rows = self.df.iloc[idxs].copy()
        rows['original_index'] = idxs
        optional = ['track_name', 'similarity_score', 'valence', 'energy', 'arousal',
                    'fused_valence', 'fused_energy', 'fused_emotion', 'color_hex',
                    'track_url', 'preview_url', 'track_id', 'original_index',
                    'thumbnail_url', 'danceability', 'tempo', 'timbre_bright',
                    'mood_quadrant', 'album_name', 'artist_ids',
                    *CROSSFADE_PASSTHROUGH_COLS]
        if self.artist_col and self.artist_col not in optional:
            optional.append(self.artist_col)
        cols = [c for c in optional if c in rows.columns]
        return rows[cols].reset_index(drop=True)

    # Vietnamese display names for the 8 CLAP emotion labels
    _EMO_VI = color_va.EMO_VI

    def _build_color_why(self, original_indices, cva, va_s, emo_s, lyr_s, src_hex=None):
        """Per-rec "why this song" for recommend-by-color — delegates to core.explain.
        (emo_s/lyr_s kept for call-site compatibility; the V-A-only scorer doesn't use them.)"""
        fe = self.df['fused_emotion'] if 'fused_emotion' in self.df.columns else None
        return _explain.build_color_why(original_indices, cva, va_s, src_hex,
                                        song_va=self.song_va, fused_emotion=fe, emo_vi=self._EMO_VI)

    def _build_similar_why(self, seed_idx: int, rec_indices: list) -> list:
        """Per-rec "why this song" for recommend_by_song — delegates to core.explain."""
        fe = self.df['fused_emotion'] if 'fused_emotion' in self.df.columns else None
        return _explain.build_similar_why(
            seed_idx, rec_indices,
            song_va=self.song_va, mert_matrix=self.mert_matrix,
            lyrics_emb=self.embeddings_normalized, fused_emotion=fe, emo_vi=self._EMO_VI,
            sigma_v=RECO_SONG_VA_SIGMA_V, sigma_a=RECO_SONG_VA_SIGMA_A)

    def color_emotion_bridge(self, color_hexes):
        """Colour→emotion bridge for UI display (no song matching) — delegates to
        core.explain.build_bridge (Palmer/PLOS: emotion mediates the colour↔music link)."""
        return _explain.build_bridge(color_hexes, self.color_mapper, self._EMO_VI)

    def recommend_by_song(self,
                         song_id_or_name,
                         top_k=DEFAULT_TOP_K,
                         weights=None,
                         diversity_penalty=DIVERSITY_PENALTY,
                         exclude_ids=None):
        """
        Multi-faceted song similarity with 7 complementary signals.

        Research basis:
        - Berenzweig et al. (2004) "A Large-Scale Evaluation of Acoustic and
          Subjective Music-Similarity Measures": Decomposing audio into
          timbral, rhythmic, and tonal sub-spaces improves perceived
          similarity over a flat feature vector.
        - Hu & Downie (2010) "When Lyrics Outperform Audio for Music Mood
          Classification": Lyrics embeddings carry the strongest mood signal,
          especially for valence.
        - Logan & Salomon (2001) "A Music Similarity Function Based on Signal
          Analysis": Cosine similarity on spectral features is robust.
        - Russell (1980) Circumplex Model: Valence-Arousal angular proximity
          maps mood similarity better than Euclidean distance.
        - McFee & Lanckriet (2011) "The Natural Language of Playlists":
          Mood/genre category coherence strongly predicts co-occurrence in
          human-curated playlists.
        - Laurier et al. (2009) "Multimodal Music Mood Classification Using
          Audio and Lyrics": Multimodal fusion outperforms any single
          modality by 15-20%.
        - Flexer et al. (2006) "A Closer Look on Artist Filters for Musical
          Genre Classification": Artist diversity is essential for evaluation
          validity.

        Signals:
        1. Timbral similarity   — energy, loudness, acousticness, etc.
        2. Rhythmic similarity  — tempo, danceability, liveness
        3. Tonal similarity     — valence, key, mode
        4. Lyrics semantic sim  — PhoBERT embedding cosine
        5. V-A proximity        — Gaussian RBF on Circumplex distance
        6. Emotion profile sim  — Emotion vector cosine
        7. Mood category match  — Bonus for same fused_emotion label
        """
        if isinstance(song_id_or_name, int):
            song_idx = song_id_or_name
        else:
            mask = self.df['track_name'].str.contains(song_id_or_name, case=False, na=False)
            if mask.sum() == 0:
                return pd.DataFrame()
            song_idx = mask.idxmax()

        song = self.df.iloc[song_idx]

        if self.verbose:
            artist = song.get(self.artist_col, 'Unknown') if self.artist_col else 'Unknown'
            print(f"🎵 Finding songs similar to: {song['track_name']} - {artist}")

        # Resolve fusion weights up-front so zero-weighted signals can be SKIPPED
        # (perf): timbral/rhythmic/tonal are 0 in production (E-AUDIO-CLEAN) — computing
        # their cosine/Manhattan sims every query was wasted work. Guarding on w[i]
        # keeps ablation correct (it zeros the signal under test → skipped → contributes
        # 0, identical to before; non-zero → computed as usual).
        use_mert = self.mert_matrix is not None
        w_dict = RECO_SONG_WEIGHTS_MERT if use_mert else RECO_SONG_WEIGHTS
        w = weights if weights is not None else w_dict["with_lyrics"]

        # === Signal 1: Timbral similarity (Berenzweig et al. 2004) ===
        if w[0]:
            q_tim = self._timbral_matrix[song_idx]
            timbral_sim = cosine_similarity(q_tim.reshape(1, -1), self._timbral_matrix)[0]
        else:
            timbral_sim = 0.0

        # === Signal 2: Rhythmic similarity ===
        if w[1]:
            q_rhy = self._rhythmic_matrix[song_idx]
            rhythmic_sim = 1.0 - np.abs(self._rhythmic_matrix - q_rhy).mean(axis=1)
        else:
            rhythmic_sim = 0.0

        # === Signal 3: Tonal similarity ===
        if w[2]:
            q_ton = self._tonal_matrix[song_idx]
            tonal_sim = cosine_similarity(q_ton.reshape(1, -1), self._tonal_matrix)[0]
        else:
            tonal_sim = 0.0

        # === Signal 4: Lyrics semantic similarity (Hu & Downie 2010) ===
        # All songs guaranteed to have lyrics (data contract); embeddings always loaded.
        query_lyrics = self.embeddings_normalized[song_idx]
        lyrics_sim = self.embeddings_normalized @ query_lyrics
        lyrics_sim = (lyrics_sim + 1) / 2

        # === Signal 5: V-A proximity (Russell 1980 Circumplex) ===
        # Heteroscedastic Gaussian RBF: per-axis σ reflecting reliability of each dim.
        # Delbouys 2018: arousal ~80% audio-predictable (σ_A narrow = trust it);
        #               valence ~17% audio-predictable (σ_V wide = lenient).
        # Note: E-VA-SPLIT 2026-06 tested σ_A=0.14 at VA weight=0.032 → REJECTED
        # (too small weight for σ change to surface). Now weight=0.10 — retested 2026-06-09.
        query_va = self.song_va[song_idx]
        _sv = RECO_SONG_VA_SIGMA_V
        _sa = RECO_SONG_VA_SIGMA_A
        dv = self.song_va[:, 0] - query_va[0]
        da = self.song_va[:, 1] - query_va[1]
        va_sim = np.exp(-0.5 * ((dv / _sv) ** 2 + (da / _sa) ** 2))

        # === Signal 6: Instrument tag similarity (MTG-Jamendo 40-dim, 16kHz fixed 2026-06-09) ===
        # Slot 5 (previously "emotion profile" from color_hex, weight=0) repurposed.
        # Instrument cosine similarity: songs sharing same instruments score higher.
        # Literature: MusiCNN (arXiv:2409.08987) outperforms MERT because trained on
        # instrument/genre tags → explicit instrument similarity is a meaningful signal.
        # Weight tuned via sensitivity analysis (see config.RECO_SONG_WEIGHTS_MERT).
        # Root cause: lexicon bag-of-words is redundant with PhoBERT (signal 4, w=0.499)
        # and much noisier (word count ≠ evoked emotion; metaphor/negation not handled).
        # Color-based vec acts as weak genre/aesthetic tie-breaker — less harmful.
        # Instrument tag cosine: (N,) in [0,1]
        inst_sim = np.zeros(self.n_songs)
        if self.instrument_tag_matrix is not None and w[5] != 0:
            q_inst = self.instrument_tag_matrix[song_idx]
            raw_inst = self.instrument_tag_matrix @ q_inst   # [-1,1]
            inst_sim = (raw_inst + 1.0) / 2.0               # → [0,1]

        # === Signal 7: Mood category coherence (McFee & Lanckriet 2011) ===
        query_mood = self._mood_labels[song_idx]
        mood_match = np.zeros(self.n_songs)
        if query_mood:
            mood_match = (self._mood_labels == query_mood).astype(float)

        # === Signal 8: MERT audio embedding (Li et al. 2023) — Pillar A ===
        if use_mert:
            mert_sim = self.mert_matrix @ self.mert_matrix[song_idx]  # (n_songs,)
            mert_sim = (mert_sim + 1.0) / 2.0                         # [-1,1] → [0,1]

        # === Adaptive fusion — weights resolved above ===
        # Signal layout: [timbral, rhythmic, tonal, lyrics, va, instrument_tag, mood, mert]
        # Slot 5 repurposed from "emotion" (always 0, redundant) to "instrument_tag" 2026-06-09.
        base = (
            w[0] * timbral_sim +
            w[1] * rhythmic_sim +
            w[2] * tonal_sim +
            w[3] * lyrics_sim +
            w[4] * va_sim +
            w[5] * inst_sim +       # instrument tag cosine (slot 5, additive in Σw=1)
            w[6] * mood_match
        )
        final_scores = base + (w[7] * mert_sim if use_mert and len(w) > 7 else 0)

        # Exclude reference song and its covers/duplicates
        final_scores[song_idx] = -1
        if ENABLE_COVER_FILTER and self._cover_exclude:
            for cover_idx in self._cover_exclude.get(song_idx, set()):
                final_scores[cover_idx] = -1

        # Endless-radio: drop already-played tracks so re-querying the same seed
        # song keeps surfacing fresh similars instead of looping the same list.
        exclude_idx = self._resolve_indices(exclude_ids)
        if exclude_idx:
            final_scores[exclude_idx] = -1

        # No RRF for recommend_by_song: the multi-signal weighted fusion is already
        # the right ranking function here.  RRF pre-filtering hurts recall because
        # relevant songs can score highly on timbral/rhythmic but not on va/lyrics.
        # max_per_artist is an optional operator hard-cap (default 0 = no cap).
        return self._fast_rank(final_scores, top_k, diversity_penalty,
                               max_per_artist=MAX_PER_ARTIST_SIMILAR or None)
    def _rrf_candidates(
        self,
        score_arrays: list,
        weights=None,
        n: int = None,
    ) -> np.ndarray:
        """
        RRF candidate reduction (Cormack et al. 2009) — Pillar C.

        Fuses multiple cheap per-song score arrays into a single ranked
        candidate pool of size n using Reciprocal Rank Fusion.

        Args:
            score_arrays: list of (n_songs,) similarity arrays.
            weights: per-array RRF weights (default: uniform).
            n: candidate pool size (default: RRF_CANDIDATE_SIZE).

        Returns:
            (≤n,) int64 array of candidate song indices, RRF order.
        """
        from core.ranking.retrieval import reciprocal_rank_fusion, scores_to_rank_list
        if n is None:
            n = RRF_CANDIDATE_SIZE
        rank_lists = [scores_to_rank_list(s, top_n=n * 2) for s in score_arrays]
        fused = reciprocal_rank_fusion(rank_lists, k=RRF_K, weights=weights, top_n=n)
        return np.array(fused, dtype=np.int64)

    def _cap_per_artist(self, indices, max_per_artist, top_k):
        """Cap songs per artist (delegates to core.ranking.artist.cap_per_artist)."""
        return _cap_per_artist_fn(indices, self.artists, max_per_artist, top_k)

    def _fast_rank(self, scores, top_k, diversity_penalty, restrict_to=None, max_per_artist=None):
        """
        Diversity-aware ranking. Dispatches to MMR, DPP, or greedy based on
        config.DIVERSITY_METHOD (default "mmr").

        MMR  — Carbonell & Goldstein 1998: λ·relevance − (1−λ)·max_sim_to_selected
        DPP  — Chen et al. 2018 fast greedy MAP
        greedy — original artist-penalty heuristic (kept for backward-compat)

        restrict_to: optional array of candidate indices from RRF (Pillar C).
            When supplied, only those indices are considered; argsort runs on
            the restricted subset — O(|restrict_to|) instead of O(n_songs).
        max_per_artist: optional hard cap on songs per artist in the result.
            Applied in BOTH the MMR/DPP and greedy paths (MMR/DPP diversify by
            embedding distance, not artist, so the cap is what actually limits
            same-artist domination in recommend_by_song).
        """
        if restrict_to is not None and len(restrict_to) > 0:
            cand_arr = np.asarray(restrict_to, dtype=np.int64)
            cand_scores = scores[cand_arr]
            n = min(top_k * 4, len(cand_arr))
            top_local = _argsort_desc_stable(cand_scores, n)
            top_indices = cand_arr[top_local]
        else:
            n_candidates = min(top_k * 4, self.n_songs)
            top_indices = _argsort_desc_stable(scores, n_candidates)

        # Filter by minimum threshold
        valid = scores[top_indices] >= MIN_SIMILARITY_THRESHOLD
        top_indices = top_indices[valid]

        if len(top_indices) == 0:
            return pd.DataFrame()

        # --- MMR / DPP path ---
        if DIVERSITY_METHOD in ("mmr", "dpp") and self.embeddings_normalized is not None:
            from core.ranking.diversity import mmr_rerank, dpp_greedy_map
            candidates = top_indices.tolist()
            # Over-fetch when an artist cap is set, so trimming still yields top_k.
            fetch_k = top_k if not max_per_artist else min(top_k * 3, len(candidates))
            if DIVERSITY_METHOD == "mmr":
                chosen = mmr_rerank(
                    candidates, scores, self.embeddings_normalized,
                    top_k=fetch_k, lambda_=DIVERSITY_LAMBDA,
                )
            else:
                chosen = dpp_greedy_map(
                    candidates, scores, self.embeddings_normalized, top_k=fetch_k,
                )
            if max_per_artist:
                chosen = self._cap_per_artist(chosen, max_per_artist, top_k)
            indices = chosen
            final_scores_list = [float(scores[i]) for i in indices]

        # --- Greedy path (original behaviour) ---
        else:
            selected = []
            selected_artists = {}
            selected_moods = set()

            for idx in top_indices:
                if len(selected) >= top_k:
                    break
                score = float(scores[idx])

                if self.artists is not None:
                    artist = self.artists[idx]
                    if artist:
                        count = selected_artists.get(artist, 0)
                        if max_per_artist and count >= max_per_artist:
                            continue
                        if count > 0:
                            score *= (1 - diversity_penalty) ** count
                            if score < MIN_SIMILARITY_THRESHOLD:
                                continue

                mood = self._mood_labels[idx] if hasattr(self, '_mood_labels') else ''
                if mood and mood not in selected_moods:
                    score *= 1.03

                selected.append((int(idx), score))

                if self.artists is not None:
                    art = self.artists[idx]
                    if art:
                        selected_artists[art] = selected_artists.get(art, 0) + 1
                if mood:
                    selected_moods.add(mood)

            if not selected:
                return pd.DataFrame()
            indices, final_scores_list = zip(*selected)
            indices = list(indices)

        results = self.df.iloc[indices].copy()
        results['similarity_score'] = list(final_scores_list)
        results['original_index'] = indices

        cols = ['track_name']
        if self.artist_col and self.artist_col in results.columns:
            cols.append(self.artist_col)

        optional = ['similarity_score', 'valence', 'energy', 'arousal', 'fused_valence',
                   'fused_energy', 'fused_emotion', 'color_hex', 'track_url', 'preview_url', 'track_id',
                   'original_index', 'thumbnail_url', 'danceability', 'tempo', 'timbre_bright',
                   'mood_quadrant', 'album_name', 'artist_ids', 'key', 'mode',
                   *CROSSFADE_PASSTHROUGH_COLS]
        cols.extend([c for c in optional if c in results.columns])

        return results[cols].reset_index(drop=True)

    def get_song_info(self, song_id):
        """Get song details"""
        if 0 <= song_id < self.n_songs:
            return self.df.iloc[song_id].to_dict()
        return None

    def semantic_search(self, query_vec: np.ndarray, top_k: int = 50) -> list:
        """Cosine similarity of query_vec vs lyrics embeddings.

        Returns list of (df_integer_index, score) pairs sorted by descending score.
        Returns [] when lyrics embeddings are unavailable.
        """
        if self.embeddings_normalized is None:
            return []
        sims = self.embeddings_normalized.dot(query_vec)  # (n_songs,)
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [(int(i), float(sims[i])) for i in top_idx]

    def get_statistics(self):
        """Get system stats"""
        return {
            'total_songs': self.n_songs,
            'audio_features': len(self.audio_features),
            'has_embeddings': self.embeddings is not None,
            'has_colors': self.colors is not None,
            'embedding_dimension': self.embeddings.shape[1] if self.embeddings is not None else 0
        }


# Singleton
_recommender = None

def get_recommender(reload=False):
    """Get singleton recommender instance"""
    global _recommender
    if _recommender is None or reload:
        _recommender = MusicRecommender()
    return _recommender


if __name__ == "__main__":
    import time

    print("=" * 80)
    print("🎵 PERFORMANCE TEST")
    print("=" * 80)

    r = MusicRecommender()

    # Warm up
    r.recommend_by_colors("#FF0000", top_k=5)

    # Test speed
    colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF"]

    start = time.time()
    for _ in range(10):
        r.recommend_by_colors(colors, top_k=10)
    elapsed = time.time() - start

    print(f"\n⏱️  Average query time: {elapsed/10*1000:.1f}ms")
    print(f"   (10 queries with 5 colors each)")
