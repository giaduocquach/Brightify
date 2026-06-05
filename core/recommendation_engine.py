import os
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

from config import *

# Import color mapping
try:
    from core.advanced_color_mapping import get_advanced_color_mapper as get_color_mapper
    USE_ADVANCED_COLOR = True
except ImportError:
    try:
        from core.color_mapping import get_color_mapper
    except ImportError:
        from core.advanced_color_mapping import get_advanced_color_mapper as get_color_mapper
    USE_ADVANCED_COLOR = False

from core.emotion_analysis import get_emotion_analyzer


def detect_artist_column(df):
    """Detect artist column name from dataset"""
    for name in ['artist', 'artist_name', 'artists', 'performer']:
        if name in df.columns:
            return name
    return None


class MusicRecommender:

    def __init__(self,
                 data_path=PROCESSED_FILE,
                 embeddings_path=EMBEDDINGS_FILE,
                 verbose=VERBOSE):

        self.verbose = verbose

        logger.info("Initializing Music Recommender v6.0 (Multimodal + Lyrics)...")

        # Load modules — V17 fix B4: vietnamese=False (pure-global colour↔emotion per
        # project decision; cultural_adjustments only affected the reverse song→colour
        # path anyway, but keep it off for clarity).
        self.color_mapper = get_color_mapper(vietnamese=False)
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
                if mert_raw.shape[0] == self.n_songs and mert_raw.shape[1] == 768:
                    norms = np.linalg.norm(mert_raw, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    self.mert_matrix = (mert_raw / norms).astype(np.float32)
                    logger.info(f"[MERT] Loaded {self.mert_matrix.shape} embeddings")
                else:
                    logger.warning(
                        f"[MERT] Shape mismatch {mert_raw.shape} vs ({self.n_songs}, 768) — disabled"
                    )
            except Exception as e:
                logger.warning(f"[MERT] Load failed: {e} — disabled")

        # Pillar F — KG embeddings (artist-album bipartite SVD)
        self.kg_matrix = None
        if ENABLE_KG and os.path.exists(KG_EMBEDDINGS_FILE):
            try:
                kg_raw = np.load(KG_EMBEDDINGS_FILE)
                if kg_raw.shape[0] == self.n_songs:
                    norms = np.linalg.norm(kg_raw, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    self.kg_matrix = (kg_raw / norms).astype(np.float32)
                    logger.info(f"[KG] Loaded {self.kg_matrix.shape} embeddings")
                else:
                    logger.warning(f"[KG] Shape mismatch {kg_raw.shape[0]} vs {self.n_songs} — disabled")
            except Exception as e:
                logger.warning(f"[KG] Load failed: {e} — disabled")

        logger.info(f"Recommender ready — {self.n_songs:,} songs loaded")

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

        # Emotion vector from album-art color (kept for recommend_by_colors emotion signal)
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

        # Anti-skew density weights (precomputed once; used in _color_score).
        self._density_weights = self._precompute_density_weights()

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

    # 8 CLAP emotion labels → Russell mood quadrant string (format the API expects:
    # "QN: Name", consumed via startswith('QN') in /api/moods and contains() in filter)
    _EMO_QUADRANT = {
        'happy': 'Q1: Happy/Excited', 'excited': 'Q1: Happy/Excited',
        'angry': 'Q2: Angry/Tense', 'tense': 'Q2: Angry/Tense',
        'sad': 'Q3: Sad/Melancholic', 'melancholic': 'Q3: Sad/Melancholic',
        'calm': 'Q4: Calm/Peaceful', 'peaceful': 'Q4: Calm/Peaceful',
    }

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

    def recommend_by_colors(self,
                           color_hexes,
                           top_k=DEFAULT_TOP_K,
                           weights=None,
                           diversity_penalty=DIVERSITY_PENALTY,
                           novelty=COLOR_NOVELTY_DEFAULT):

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

        # Pillar F — apply VN holiday + time-of-day V-A shift to every colour's V-A
        if ENABLE_VN_CONTEXT:
            try:
                from core.vn_context import get_context_shift
                ctx = get_context_shift()
                per_color_va = np.clip(
                    per_color_va + np.array([ctx["valence_shift"], ctx["arousal_shift"]]),
                    0.0, 1.0,
                )
            except Exception:
                pass

        return self._rank_by_color_features(
            per_color_va, per_color_emotion, per_color_lyrics,
            color_hexes, top_k, diversity_penalty, novelty)

    def _novelty_prior(self):
        """Per-song popularity prior in [0,1] (high = mainstream). E8.

        No play-count data exists → proxy = artist frequency in the catalog
        (prolific artist ≈ more mainstream here), log-scaled + min-max normalised.
        Cached on first use.
        """
        if getattr(self, '_artist_pop_prior', None) is None:
            col = ('primary_artist' if 'primary_artist' in self.df.columns
                   else (self.artist_col if self.artist_col in self.df.columns else None))
            if col:
                s = self.df[col].fillna('')
                counts = s.map(s.value_counts()).values.astype(float)
                c = np.log1p(counts)
                rng = float(c.max() - c.min())
                self._artist_pop_prior = ((c - c.min()) / rng if rng > 0
                                          else np.full(self.n_songs, 0.5))
            else:
                self._artist_pop_prior = np.full(self.n_songs, 0.5)
        return self._artist_pop_prior

    def _apply_novelty(self, scores, novelty):
        """E8 — re-weight scores by the novelty dial (0.5 = neutral, no change)."""
        if novelty is None or abs(float(novelty) - 0.5) < 1e-6:
            return scores
        pop = self._novelty_prior()
        s = COLOR_NOVELTY_STRENGTH
        if novelty > 0.5:                              # deep cuts: suppress mainstream
            factor = 1.0 - s * (novelty - 0.5) * 2.0 * pop
        else:                                          # familiar: suppress long-tail
            factor = 1.0 - s * (0.5 - novelty) * 2.0 * (1.0 - pop)
        return np.clip(scores * factor, 0.0, 1.0)

    def _precompute_density_weights(self) -> np.ndarray:
        """Inverse catalog density weights for anti-skew (Saerens 2002 / Steck 2018).

        Approximates the V-A catalog density on a grid (COLOR_ANTISKEW_BINS × bins).
        Returns per-song weight = 1/density, normalised to mean=1.  Songs in
        over-represented regions (Q3 sad, 54% of catalog) get weight < 1; sparse
        regions (Q1 happy, Q4 calm) get weight > 1, making them more accessible even
        for queries near Q3.
        """
        n_bins = COLOR_ANTISKEW_BINS
        v = self.song_va[:, 0]
        a = self.song_va[:, 1]
        H, v_edges, a_edges = np.histogram2d(
            v, a, bins=n_bins, range=[[0.0, 1.0], [0.0, 1.0]])
        # Laplace smoothing (avoids zero-density cells crashing inv)
        H = H + 0.5
        H_norm = H / H.sum()
        # Map each song to its bin density
        v_idx = np.clip((v * n_bins).astype(int), 0, n_bins - 1)
        a_idx = np.clip((a * n_bins).astype(int), 0, n_bins - 1)
        density = H_norm[v_idx, a_idx].astype(np.float32)
        inv_d = 1.0 / density
        # Normalise to mean=1 so overall score scale is preserved
        inv_d = inv_d / (inv_d.mean() + 1e-12)
        return inv_d.astype(np.float32)

    def _precompute_valence_quantile(self):
        """Empirical quantile rank of each song's valence in [0, 1].

        rank/quantile matching is scale-invariant: any monotone rescale/calibration
        of song_va[:,0] preserves order → cannot break colour↔song commensurability
        (Cormack 2009 RRF; Bolstad 2003 quantile normalisation).
        """
        v = self.song_va[:, 0]
        order = np.argsort(v)
        ranks = np.empty(len(v), dtype=np.float32)
        ranks[order] = np.arange(len(v), dtype=np.float32)
        return ranks / max(len(v) - 1, 1)

    def _antiskew_balance(self, res, color_va, all_scores, top_k):
        """Post-rank quadrant balancing (Steck 2018 calibrated recommendations).

        If the result list is ≥80% Q3-sad AND the query colour is NOT strongly Q3
        (i.e. color_V > 0.30), swap out some Q3 songs for the best available songs
        from the query's intended quadrant and adjacent ones.  This addresses the
        case where all nearby catalog songs happen to be sad — the density correction
        alone cannot help when the local neighborhood itself is mono-mood.

        Only activated when COLOR_ANTISKEW_ENABLED=True.
        """
        idxs = res['original_index'].tolist()
        if not idxs:
            return res

        # Query quadrant
        cv, ca = float(color_va[0]), float(color_va[1])
        if cv >= 0.5 and ca >= 0.5:   q_col = 'Q1'
        elif cv < 0.5 and ca >= 0.5:  q_col = 'Q2'
        elif cv < 0.5 and ca < 0.5:   q_col = 'Q3'
        else:                          q_col = 'Q4'

        def _q(i):
            v, a = self.song_va[i, 0], self.song_va[i, 1]
            if v >= 0.5 and a >= 0.5: return 'Q1'
            if v <  0.5 and a >= 0.5: return 'Q2'
            if v <  0.5 and a <  0.5: return 'Q3'
            return 'Q4'

        result_qs = [_q(i) for i in idxs]
        q3_frac = result_qs.count('Q3') / len(result_qs)

        # Only balance when result is heavily Q3 AND query is NOT strongly sad (V<0.30).
        # Black (V=0.25) → genuinely sad, no correction.
        # Grey (V=0.41) → borderline, correct the skew.
        if q3_frac < 0.80 or cv < 0.30:
            return res

        # Find best non-Q3 candidates not already in results
        in_set = set(idxs)
        # Rank all non-Q3 songs by their anti-skew-corrected score
        alt_scores = all_scores.copy()
        q3_mask = (self.song_va[:, 0] < 0.5) & (self.song_va[:, 1] < 0.5)
        alt_scores[list(in_set)] = -1.0
        alt_scores[q3_mask] = -1.0      # exclude Q3 from alternatives
        n_swap = min(top_k // 3, int(q3_frac * len(idxs) - 0.79 * len(idxs)) + 1)
        n_swap = max(1, n_swap)
        best_alts = np.argsort(alt_scores)[::-1][:n_swap].tolist()

        # Replace the worst Q3 songs with the best alternatives
        q3_positions = [i for i, q in enumerate(result_qs) if q == 'Q3']
        # sort by score ascending (worst first)
        q3_positions.sort(key=lambda p: float(all_scores[idxs[p]]))
        to_replace = q3_positions[:n_swap]

        new_idxs = idxs.copy()
        for pos, alt in zip(to_replace, best_alts):
            new_idxs[pos] = alt

        # Rebuild result DataFrame with new indices
        new_res = self.df.iloc[new_idxs].copy()
        new_res['similarity_score'] = [float(all_scores[i]) for i in new_idxs]
        new_res['original_index'] = new_idxs
        id_col = 'track_id' if 'track_id' in self.df.columns else 'track_name'
        optional = ['similarity_score', 'valence', 'energy', 'arousal', 'fused_valence',
                    'fused_energy', 'fused_emotion', 'color_hex', 'track_url', 'preview_url',
                    'track_id', 'original_index', 'thumbnail_url', 'danceability', 'tempo',
                    'timbre_bright', 'mood_quadrant', 'album_name', 'artist_ids']
        cols = ['track_name']
        if self.artist_col and self.artist_col in new_res.columns:
            cols.append(self.artist_col)
        cols.extend([c for c in optional if c in new_res.columns and c not in cols])
        return new_res[cols].reset_index(drop=True)

    def _rank_by_color_features(self, per_color_va, per_color_emotion,
                                per_color_lyrics, color_hexes, top_k,
                                diversity_penalty, novelty=COLOR_NOVELTY_DEFAULT):
        """Pure V-A heteroscedastic RBF scorer (F3 V19).

        Matches colour V-A against song V-A using per-axis bandwidth (σ_V>σ_A —
        valence less reliable than arousal per Eerola/Yang). F2 ablation confirmed
        lyr-cosine and emo-cosine add no information; both removed.
        Multi-colour: RRF union so each colour has equal representation.
        per_color_lyrics accepted for API compat but ignored.
        """
        per_color_va = np.asarray(per_color_va, dtype=float)

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

        # F3 (V19) — V-A heteroscedastic RBF only.
        # Heteroscedastic σ per axis (median heuristic, Garreau 2017):
        _sigma_v = COLOR_SCORE_VA_SIGMA_V   # 0.20 — valence axis (wide, less reliable)
        _sigma_a = COLOR_SCORE_VA_SIGMA_A   # 0.14 — arousal axis (narrow, more reliable)

        # Anti-skew (Saerens 2002 / Steck 2018): inverse-density pre-weighting.
        _dw = self._density_weights if COLOR_ANTISKEW_ENABLED else None

        def _color_score(cva, evec, lyr):
            if COLOR_SCORE_VALENCE_QUANTILE:
                # Quantile-transform valence: scale-invariant matching.
                # colour valence → its empirical quantile in the song distribution
                # (= fraction of songs with valence ≤ color_v).
                color_v_q = float(np.mean(self.song_va[:, 0] <= cva[0]))
                dv = self._song_v_quantile - color_v_q
            else:
                dv = self.song_va[:, 0] - cva[0]
            da = self.song_va[:, 1] - cva[1]
            va_s = np.exp(-0.5 * ((dv / _sigma_v) ** 2 + (da / _sigma_a) ** 2))
            # Density correction only for borderline queries (0.30 ≤ V ≤ 0.70).
            # Strongly-valenced queries (red/yellow/black) stay pure V-A; only
            # neutral-ish colours (grey, ngoc, white) get the skew correction.
            cv_query = float(cva[0])
            if _dw is not None and 0.30 <= cv_query <= 0.70:
                va_s = va_s * (_dw ** COLOR_ANTISKEW_STRENGTH)
            emo_s = np.full(self.n_songs, 0.5)
            lyr_s = np.full(self.n_songs, 0.5)
            return va_s, va_s, emo_s, lyr_s

        # ---- Single colour: unambiguous mood → cross-mood penalty + RRF ----
        if len(per_color_va) == 1:
            final_scores, va_s, emo_s, lyr_s = _color_score(
                per_color_va[0], per_color_emotion[0], per_color_lyrics[0])
            # F3: cross-mood penalty removed — the heteroscedastic V-A RBF already
            # makes large mood-distance songs score near-zero without explicit rules.
            final_scores = self._apply_novelty(final_scores, novelty)   # E8
            candidates = (self._rrf_candidates([va_s, emo_s, lyr_s])
                          if ENABLE_RRF else None)
            res = self._fast_rank(final_scores, top_k, diversity_penalty,
                                  restrict_to=candidates)
            if not res.empty and 'original_index' in res.columns:
                res = res.copy()
                if COLOR_ANTISKEW_ENABLED:
                    res = self._antiskew_balance(res, per_color_va[0], final_scores, top_k)
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
                per_color_va[0], per_color_va[1], top_k, diversity_penalty)
            res = self._build_result_df(idxs)
            if not res.empty and 'original_index' in res.columns:
                res = res.copy()
                # why: attribute each song to nearest colour (A or B)
                p1 = np.asarray(per_color_va[0], float)
                p2 = np.asarray(per_color_va[1], float)
                whys = []
                for oi in res['original_index'].tolist():
                    oi = int(oi)
                    sv = self.song_va[oi]
                    # nearest endpoint
                    if np.linalg.norm(sv - p1) <= np.linalg.norm(sv - p2):
                        cva, hexc = p1, color_hexes[0]
                    else:
                        cva, hexc = p2, color_hexes[1] if len(color_hexes) > 1 else color_hexes[0]
                    va_s_why = np.exp(-0.5 * (
                        ((self.song_va[:, 0] - cva[0]) / _sigma_v) ** 2 +
                        ((self.song_va[:, 1] - cva[1]) / _sigma_a) ** 2))
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
            sc = self._apply_novelty(sc, novelty)
            per_color.append((sc, va_s, emo_s, lyr_s, cva,
                              color_hexes[ci] if ci < len(color_hexes) else None))
        score_stack = np.vstack([p[0] for p in per_color])
        rrf = np.zeros(self.n_songs)
        for sc in score_stack:
            ranks = np.empty(self.n_songs, dtype=float)
            ranks[np.argsort(sc)[::-1]] = np.arange(self.n_songs)
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

    def _journey_waypoint_sample(self, p1, p2, top_k: int,
                                  diversity_penalty: float) -> list[int]:
        """Greedy waypoint sampling for a true Iso-Principle gradient (V23 fix).

        Divides the V-A path P1→P2 into `top_k` evenly-spaced waypoints and
        greedily picks the best unselected song for each waypoint. This forces
        intermediate songs into the list, avoiding the "2-block" artefact of
        RRF + projection-sort (which only selected songs near the endpoints).

        Basis: Iso-Principle — start matching A, shift ~10-15% per step (Saari
        2016). Artist diversity applied with mild penalty (Δ ≤ 0.3 per repeat).
        """
        p1 = np.asarray(p1, float); p2 = np.asarray(p2, float)
        n = self.n_songs
        _sv = COLOR_SCORE_VA_SIGMA_V
        _sa = COLOR_SCORE_VA_SIGMA_A

        excluded = np.zeros(n, dtype=bool)
        artist_counts: dict[str, int] = {}
        artists = (self.df[self.artist_col].fillna('__unknown__').values
                   if self.artist_col else None)
        selected: list[int] = []

        # Evenly-spaced waypoints from P1 (t=0) to P2 (t=1)
        ts = np.linspace(0.0, 1.0, top_k)
        waypoints = p1[None, :] + ts[:, None] * (p2 - p1)[None, :]  # (K, 2)

        for wp in waypoints:
            dv = self.song_va[:, 0] - wp[0]
            da = self.song_va[:, 1] - wp[1]
            scores = np.exp(-0.5 * ((dv / _sv) ** 2 + (da / _sa) ** 2))
            scores[excluded] = -1.0

            # Mild diversity penalty (cap repeat-artist contribution at 3)
            if diversity_penalty > 0 and artists is not None:
                for i in np.where(scores > 0)[0]:
                    cnt = artist_counts.get(artists[i], 0)
                    if cnt:
                        scores[i] *= max(0.0, 1.0 - diversity_penalty * min(cnt, 3))

            best = int(np.argmax(scores))
            if scores[best] <= 0:
                continue
            selected.append(best)
            excluded[best] = True
            if artists is not None:
                art = artists[best]
                artist_counts[art] = artist_counts.get(art, 0) + 1

        return selected

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
                    'mood_quadrant', 'album_name', 'artist_ids']
        if self.artist_col and self.artist_col not in optional:
            optional.append(self.artist_col)
        cols = [c for c in optional if c in rows.columns]
        return rows[cols].reset_index(drop=True)

    def _sequence_journey(self, res, p1, p2):
        """Order selected songs along the V-A path P1 → P2 (Iso-Principle, V23).

        Projects each song's V-A onto the journey vector (p1→p2), giving a position
        t∈[0,1]; sorting by t makes the playlist start at colour A's mood and shift
        smoothly to colour B's. Replaces interleaved order (mood-whiplash).
        Basis: Iso-Principle (Starcke & von Georgi 2024, d=0.52); affective arc
        (Neto 2025). Retrieval (which songs) is unchanged — only the ORDER.
        """
        p1 = np.asarray(p1, float); p2 = np.asarray(p2, float)
        axis = p2 - p1
        denom = float(axis @ axis)
        idxs = [int(i) for i in res['original_index'].tolist()]
        if denom < 1e-9:               # two colours nearly identical → no journey
            return res
        # t = normalised projection of (songVA - p1) onto (p2 - p1), clamped [0,1]
        t = {i: float(np.clip(((self.song_va[i] - p1) @ axis) / denom, 0.0, 1.0))
             for i in idxs}
        order = sorted(idxs, key=lambda i: t[i])
        res = res.set_index('original_index').loc[order].reset_index()
        return res

    def _build_color_why(self, original_indices, cva, va_s, emo_s, lyr_s,
                         src_hex=None):
        """E6 (V16) — per-recommendation "why this song".

        Verbalises the REAL signal deltas behind each pick (no fabrication): the
        song's V-A vs the colour's V-A (mood closeness), the dominant contributing
        signal (mood / lyric-theme / categorical emotion), and the song's own mood
        label. Norman's reflective level / explainability — earns trust vs a
        black-box mood button. Values are JSON-safe primitives.
        """
        # F3: V-A-only scorer — "why" is purely the V-A closeness.
        cval, caro = float(cva[0]), float(cva[1])
        _has_fe = 'fused_emotion' in self.df.columns
        out = []
        for i in original_indices:
            i = int(i)
            sv, sa = float(self.song_va[i, 0]), float(self.song_va[i, 1])
            song_emo = ''
            if _has_fe:
                _fe = self.df['fused_emotion'].iloc[i]
                song_emo = '' if pd.isna(_fe) else str(_fe).lower()
            va_match = round(float(va_s[i]), 3)
            song_emo_vi = self._EMO_VI.get(song_emo, song_emo)
            reason = 'Cùng vùng cảm xúc (Valence–Arousal) với màu bạn chọn'
            if song_emo_vi:
                reason = f"Tâm trạng bài ({song_emo_vi}) khớp vùng V-A của màu"
            out.append({
                'reason': reason,
                'top_signal': 'mood',
                'mood_match': va_match,
                'song_va': [round(sv, 3), round(sa, 3)],
                'color_va': [round(cval, 3), round(caro, 3)],
                'song_emotion': song_emo,
                'song_emotion_vi': song_emo_vi,
                **({'color_hex': src_hex} if src_hex else {}),
            })
        return out

    # Vietnamese display names for the 8 CLAP emotion labels (for the bridge chip)
    _EMO_VI = {
        'happy': 'Vui vẻ', 'excited': 'Phấn khích', 'peaceful': 'Bình yên',
        'calm': 'Thư thái', 'melancholic': 'U sầu', 'sad': 'Buồn',
        'tense': 'Căng thẳng', 'angry': 'Giận dữ',
    }

    def color_emotion_bridge(self, color_hexes):
        """Return the colour→emotion bridge for UI display (no song matching).

        For each chosen colour: its inferred top emotion (CLAP label + Vietnamese
        name) and V-A point. This is the feature's core value made visible
        (Palmer/PLOS: emotion mediates the colour↔music link).
        """
        if isinstance(color_hexes, str):
            color_hexes = [color_hexes]
        bridge = []
        for color in list(color_hexes)[:3]:
            try:
                v, a = self.color_mapper.hsl_to_va(color)
                probs = self.color_mapper.color_to_emotion_probs(color)
                top = max(probs.items(), key=lambda x: x[1])[0]
                bridge.append({
                    'hex': color,
                    'emotion': top,
                    'emotion_vi': self._EMO_VI.get(top, top),
                    'valence': round(float(v), 2),
                    'arousal': round(float(a), 2),
                })
            except (ValueError, KeyError, TypeError):
                continue
        return bridge

    def recommend_by_song(self,
                         song_id_or_name,
                         top_k=DEFAULT_TOP_K,
                         weights=None,
                         diversity_penalty=DIVERSITY_PENALTY):
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
        # Gaussian RBF with adaptive σ based on local V-A density
        query_va = self.song_va[song_idx]
        va_diff = self.song_va - query_va
        va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
        # σ set so ~68% of songs within ±0.3 V-A units fall inside 1σ
        va_sim = np.exp(-(va_dist ** 2) / (2 * 0.20 ** 2))

        # === Signal 6: Emotion profile similarity ===
        query_emotion = self.song_emotion_vec[song_idx]
        emotion_sim = self.song_emotion_vec @ query_emotion

        # === Signal 7: Mood category coherence (McFee & Lanckriet 2011) ===
        query_mood = self._mood_labels[song_idx]
        mood_match = np.zeros(self.n_songs)
        if query_mood:
            mood_match = (self._mood_labels == query_mood).astype(float)

        # === Signal 8: MERT audio embedding (Li et al. 2023) — Pillar A ===
        if use_mert:
            mert_sim = self.mert_matrix @ self.mert_matrix[song_idx]  # (n_songs,)
            mert_sim = (mert_sim + 1.0) / 2.0                         # [-1,1] → [0,1]

        # === Adaptive fusion (Laurier et al. 2009) — weights resolved above ===
        base = (
            w[0] * timbral_sim +
            w[1] * rhythmic_sim +
            w[2] * tonal_sim +
            w[3] * lyrics_sim +
            w[4] * va_sim +
            w[5] * emotion_sim +
            w[6] * mood_match
        )
        final_scores = base + (w[7] * mert_sim if use_mert and len(w) > 7 else 0)

        # Pillar F — KG content-similarity proximity (musical-neighbourhood signal).
        # KG v2 is content-based (MERT+mood+instrument+audio), NOT artist identity,
        # so it no longer biases toward same-artist songs. Weight is configurable
        # (replaces the old hardcoded +0.05 artist bonus); 0 disables the term.
        if self.kg_matrix is not None and KG_SIM_WEIGHT:
            kg_sim = self.kg_matrix @ self.kg_matrix[song_idx]
            final_scores += KG_SIM_WEIGHT * kg_sim

        # Exclude reference song
        final_scores[song_idx] = -1

        # No RRF for recommend_by_song: the 7/8-signal weighted fusion is already
        # the right ranking function here.  RRF pre-filtering hurts recall because
        # relevant songs can score highly on timbral/rhythmic but not on va/lyrics.
        # No imposed artist cap by default (MAX_PER_ARTIST_SIMILAR=0): the
        # content-based KG + artist-agnostic fusion mean same-artist songs only
        # surface when genuinely the most musically similar (e.g. a stylistically
        # consistent artist) — which is correct, not a bug. Musical diversity is
        # handled by MMR (de-dups near-identical results by sound, not by artist).
        # max_per_artist stays an optional operator override only.
        return self._fast_rank(final_scores, top_k, diversity_penalty,
                               max_per_artist=MAX_PER_ARTIST_SIMILAR or None)

    def recommend_by_image(self,
                          image_analysis: dict,
                          top_k=DEFAULT_TOP_K,
                          diversity_penalty=DIVERSITY_PENALTY):
        """
        Recommend songs based on image analysis results.
        
        Uses multi-signal fusion:
        1. Color similarity (dominant colors from image → CIEDE2000 distance)
        2. V-A proximity (image valence/arousal → song valence/arousal)
        3. Emotion alignment (CLIP emotions → song emotions)
        4. Lyrics semantic matching (emotion-matched embeddings)
        5. Audio feature matching (visual features → audio profile)
        
        Args:
            image_analysis: dict from ImageAnalyzer.analyze_image()
            top_k: number of recommendations
            diversity_penalty: artist diversity penalty
            
        Returns:
            DataFrame with recommended songs
        """
        if self.verbose:
            print(f"🖼️  Recommending by image analysis...")
            print(f"   Mood: {image_analysis.get('mood_label', 'unknown')}")
            print(f"   Colors: {image_analysis.get('dominant_colors', [])}")
        
        # === Extract signals from image analysis ===
        query_valence = image_analysis.get('valence', 0.5)
        query_arousal = image_analysis.get('arousal', 0.5)
        query_va = np.array([query_valence, query_arousal])
        
        dominant_colors = image_analysis.get('dominant_colors', [])[:3]  # Top 3 colors
        color_weights = image_analysis.get('color_weights', [])[:3]
        emotion_scores = image_analysis.get('emotion_scores', {})
        brightness = image_analysis.get('brightness', 0.5)
        saturation = image_analysis.get('saturation', 0.5)
        warmth = image_analysis.get('warmth', 0.5)
        
        # === 1. V-A Similarity (Gaussian kernel) ===
        va_diff = self.song_va - query_va
        va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
        va_sim = np.exp(-va_dist * 3.0)  # Tighter kernel for image
        
        # === 2. Color Similarity (reuse existing color infrastructure) ===
        color_sim = np.zeros(self.n_songs)
        if dominant_colors and self.colors is not None:
            for color_hex, weight in zip(dominant_colors, color_weights):
                try:
                    # V-A from this color — V17 fix B2: use the recalibrated hsl_to_va
                    # (ICEAS-fit, Pearson 0.85) for consistency with recommend_by_colors,
                    # instead of the older Palmer color_to_valence_arousal.
                    color_va = self.color_mapper.hsl_to_va(color_hex)
                    color_emotion = self.color_mapper.color_to_emotion_probs(color_hex)
                    
                    # V-A distance from this color
                    c_va = np.array([color_va[0], color_va[1]])
                    c_diff = self.song_va - c_va
                    c_dist = np.sqrt(np.sum(c_diff ** 2, axis=1))
                    c_sim = np.exp(-c_dist * 2.5)
                    
                    # Emotion alignment from this color  
                    c_emo_vec = np.array([color_emotion.get(e, 0) for e in self.emotion_labels])
                    c_emo_norm = np.linalg.norm(c_emo_vec)
                    if c_emo_norm > 0:
                        c_emo_vec = c_emo_vec / c_emo_norm
                        emo_dots = self.song_emotion_vec @ c_emo_vec
                        song_norms = np.linalg.norm(self.song_emotion_vec, axis=1)
                        c_emo_sim = emo_dots / (song_norms + 1e-10)
                        c_emo_sim = (c_emo_sim + 1) / 2
                    else:
                        c_emo_sim = np.ones(self.n_songs) * 0.5
                    
                    color_sim += weight * (0.6 * c_sim + 0.4 * c_emo_sim)
                except Exception:
                    pass
            
            # Normalize
            total_weight = sum(color_weights[:len(dominant_colors)])
            if total_weight > 0:
                color_sim /= total_weight
        else:
            color_sim = np.ones(self.n_songs) * 0.5
        
        # === 3. Emotion Vector Similarity (CLIP emotions → song emotions) ===
        # Map CLIP emotion categories to our emotion labels
        clip_to_labels = {
            'happy': 'happy', 'sad': 'sad', 'peaceful': 'peaceful',
            'excited': 'excited', 'romantic': 'romantic',
            'melancholic': 'melancholic', 'angry': 'angry',
            'calm': 'calm', 'longing': 'nostalgic', 'hope': 'hopeful'
        }
        
        query_emotion_vec = np.zeros(len(self.emotion_labels))
        for clip_emo, score in emotion_scores.items():
            mapped = clip_to_labels.get(clip_emo)
            if mapped and mapped in self.emotion_labels:
                idx = self.emotion_labels.index(mapped)
                query_emotion_vec[idx] = score
        
        # Normalize
        emo_norm = np.linalg.norm(query_emotion_vec)
        if emo_norm > 0:
            query_emotion_vec_n = query_emotion_vec / emo_norm
            song_norms = np.linalg.norm(self.song_emotion_vec, axis=1)
            dots = self.song_emotion_vec @ query_emotion_vec_n
            emotion_sim = dots / (song_norms + 1e-10)
            emotion_sim = (emotion_sim + 1) / 2
        else:
            emotion_sim = np.ones(self.n_songs) * 0.5
        
        # === 4. Audio Feature Matching ===
        # Map visual features to target audio profile
        target_audio = np.full(len(self.audio_features), 0.5)
        for i, feat in enumerate(self.audio_features):
            if feat == 'valence':
                target_audio[i] = query_valence
            elif feat == 'energy':
                target_audio[i] = query_arousal
            elif feat == 'danceability':
                target_audio[i] = 0.3 * query_arousal + 0.4 * saturation + 0.3 * 0.5
            elif feat == 'acousticness':
                # Calm/peaceful images → more acoustic
                target_audio[i] = max(0, 1.0 - query_arousal * 0.7 - saturation * 0.3)
            elif feat == 'instrumentalness':
                target_audio[i] = 0.3  # Slight preference for vocal
            elif feat == 'tempo':
                target_audio[i] = 0.3 + 0.5 * query_arousal  # Higher arousal → faster tempo
            elif feat == 'loudness':
                target_audio[i] = 0.3 + 0.4 * query_arousal
        
        audio_sim = cosine_similarity(target_audio.reshape(1, -1), self.audio_matrix)[0]
        audio_sim = np.clip(audio_sim, 0, 1)
        
        # === 5. Lyrics Semantic Matching ===
        # Build a query embedding from top-2 target emotions; all songs have lyrics.
        lyrics_sim = np.ones(self.n_songs) * 0.5  # neutral fallback if no target emotion found
        top_emotions = sorted(emotion_scores.items(), key=lambda x: -x[1])[:2]
        query_lyrics_vecs = []
        if 'fused_emotion' in self.df.columns:
            for emo_name, emo_score in top_emotions:
                mapped_emo = clip_to_labels.get(emo_name)
                if mapped_emo:
                    mask = self.df['fused_emotion'].str.lower().str.contains(mapped_emo, na=False)
                    if mask.sum() > 0:
                        sample = np.where(mask)[0][:min(8, mask.sum())]
                        avg_emb = self.embeddings_normalized[sample].mean(axis=0)
                        query_lyrics_vecs.append(avg_emb * emo_score)
        if query_lyrics_vecs:
            q = np.mean(query_lyrics_vecs, axis=0)
            norm = np.linalg.norm(q)
            if norm > 0:
                lyrics_sim = self.embeddings_normalized @ (q / norm)
                lyrics_sim = np.clip((lyrics_sim + 1) / 2, 0, 1)
        
        # === 6. Emotion-based Boost/Penalty ===
        emotion_boost = np.zeros(self.n_songs)
        primary_mood = image_analysis.get('mood_label', '')
        
        # Map primary mood to preferred emotions
        mood_preference_map = {
            'happy':      {'happy', 'excited', 'passionate'},
            'excited':    {'excited', 'happy', 'passionate'},
            'peaceful':   {'calm', 'peaceful', 'romantic', 'tender'},
            'calm':       {'calm', 'peaceful', 'tender'},
            'romantic':   {'romantic', 'tender', 'melancholic'},
            'sad':        {'sad', 'melancholic', 'nostalgic'},
            'melancholic':{'melancholic', 'sad', 'nostalgic'},
            'angry':      {'angry', 'tense', 'excited'},
            'longing':    {'nostalgic', 'melancholic', 'sad'},
            'hope':       {'hopeful', 'happy', 'calm'},
        }
        
        preferred = mood_preference_map.get(primary_mood, set())
        
        if 'fused_emotion' in self.df.columns and preferred:
            for idx in range(self.n_songs):
                song_emotion = str(self.df.iloc[idx].get('fused_emotion', '')).lower()
                if song_emotion in preferred:
                    emotion_boost[idx] = 0.10
                # Penalize strong mismatches
                elif (primary_mood in {'happy', 'excited'} and song_emotion in {'sad', 'melancholic'}):
                    emotion_boost[idx] = -0.06
                elif (primary_mood in {'sad', 'melancholic'} and song_emotion in {'happy', 'excited'}):
                    emotion_boost[idx] = -0.06
        
        # === WEIGHTED FUSION ===
        final_scores = (
            0.20 * audio_sim +
            0.25 * lyrics_sim +
            0.20 * va_sim +
            0.15 * emotion_sim +
            0.20 * color_sim +
            emotion_boost
        )
        final_scores = np.clip(final_scores, 0, 1)

        if self.verbose:
            top_idx = np.argmax(final_scores)
            print(f"   V-A target: ({query_valence:.2f}, {query_arousal:.2f})")
            print(f"   Top score: {final_scores[top_idx]:.3f}")
        
        return self._fast_rank(final_scores, top_k, diversity_penalty)

    # ========================================================================
    # Emotion Journey — Iso-Principle-based adaptive playlist
    # ========================================================================

    # ========================================================================
    # Smart Context Engine — Contextual/Temporal AI Recommendation
    # ========================================================================
    #
    # Scientific foundation:
    #
    # • Cunningham, Bainbridge & Falconer (2006) "'More of an Art than a
    #   Science': Supporting the Creation of Playlists and Mixes":
    #   Listening context (time, activity, social setting) is the dominant
    #   factor in music selection — outweighing genre or artist preference.
    #
    # • Kaminskas & Ricci (2012) "Contextual Music Information Retrieval
    #   and Recommendation: State of the Art and Challenges":
    #   Temporal context (time-of-day, day-of-week) is the single most
    #   accessible and impactful contextual signal for MIR systems.
    #
    # • North & Hargreaves (1996) "Situational influences on reported
    #   musical preference": Environmental context modulates arousal
    #   preference — quieter environments → lower arousal preference.
    #
    # • Skowronek, McKinney & Van de Par (2006) "A demonstrator for
    #   automatic music mood estimation": Demonstrated circadian mood
    #   patterns in listening — morning calm, afternoon energy, evening
    #   relaxation — matching biological arousal curves.
    #
    # • Randall & Rickard (2017) "Preferences for and Responses to
    #   Self-Selected and Researcher-Selected Music": User's past
    #   behaviour is the strongest personalization signal.
    #
    # Algorithm:
    # 1. Circadian Profile (Skowronek 2006): Map hour → target V-A region
    #    using a piecewise Gaussian model of biological arousal.
    # 2. User History Pattern (Randall & Rickard 2017): Analyze user's
    #    liked/played songs to detect taste center in V-A space.
    # 3. Activity Context (North & Hargreaves 1996): Activity label shifts
    #    the target arousal — workout ↑, study ↓, commute → mid.
    # 4. Season/Weather Mood (Cunningham 2006): Season modulates valence
    #    and acousticness preference subtly.
    # 5. Multi-signal scoring per song:
    #    - Circadian V-A proximity (35%)
    #    - User taste alignment (25%)
    #    - Audio feature matching to activity (20%)
    #    - Emotion profile consistency (10%)
    #    - Diversity & freshness (10%)

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
        from core.retrieval import reciprocal_rank_fusion, scores_to_rank_list
        if n is None:
            n = RRF_CANDIDATE_SIZE
        rank_lists = [scores_to_rank_list(s, top_n=n * 2) for s in score_arrays]
        fused = reciprocal_rank_fusion(rank_lists, k=RRF_K, weights=weights, top_n=n)
        return np.array(fused, dtype=np.int64)

    def _cap_per_artist(self, indices, max_per_artist, top_k):
        """Keep at most `max_per_artist` songs per artist, preserving the input
        order, until `top_k` are collected. Works regardless of DIVERSITY_METHOD.
        Backfills from the surplus if the cap leaves the list short."""
        if self.artists is None or not max_per_artist:
            return list(indices)[:top_k]
        out, counts, seen = [], {}, set()
        for idx in indices:
            artist = self.artists[idx]
            if artist and counts.get(artist, 0) >= max_per_artist:
                continue
            out.append(idx); seen.add(idx)
            if artist:
                counts[artist] = counts.get(artist, 0) + 1
            if len(out) >= top_k:
                return out
        for idx in indices:  # backfill if cap left us short
            if idx not in seen:
                out.append(idx)
                if len(out) >= top_k:
                    break
        return out

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
            top_local = np.argsort(cand_scores)[::-1][:n]
            top_indices = cand_arr[top_local]
        else:
            n_candidates = min(top_k * 4, self.n_songs)
            top_indices = np.argsort(scores)[::-1][:n_candidates]

        # Filter by minimum threshold
        valid = scores[top_indices] >= MIN_SIMILARITY_THRESHOLD
        top_indices = top_indices[valid]

        if len(top_indices) == 0:
            return pd.DataFrame()

        # --- MMR / DPP path ---
        if DIVERSITY_METHOD in ("mmr", "dpp") and self.embeddings_normalized is not None:
            from core.diversity import mmr_rerank, dpp_greedy_map
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
                   'mood_quadrant', 'album_name', 'artist_ids']
        cols.extend([c for c in optional if c in results.columns])

        return results[cols].reset_index(drop=True)

    def recommend_by_lyrics_keywords(self, keywords, top_k=10, weights=None, diversity_penalty=0.15):
        """
        Hybrid lyrics search: keyword matching + PhoBERT semantic similarity.

        Pipeline:
        1. PhoBERT encode query → cosine similarity vs all song embeddings
           (Nguyen & Nguyen 2020: PhoBERT captures Vietnamese semantic meaning)
        2. Keyword term matching in lyrics/track_name/artist
        3. Hybrid score = α·semantic + β·keyword + γ·centroid
           When keyword matches exist: α=0.40, β=0.35, γ=0.25
           Pure semantic fallback: α=1.0

        This replaces the previous random fallback when no keyword matches,
        enabling genuine semantic discovery (e.g. "tình yêu mùa đông" finds
        winter-love songs even without exact word matches).
        """
        df = self.df.copy()
        keywords_lower = keywords.lower().strip()
        terms = [t.strip() for t in keywords_lower.split() if t.strip()]

        if not terms:
            return df.head(0)

        # --- PhoBERT semantic similarity (always computed when available) ---
        semantic_scores = None
        if self.embeddings_normalized is not None and self.emotion_classifier.available:
            query_emb = self.emotion_classifier.encode_lyrics(keywords)
            if query_emb is not None:
                norm = np.linalg.norm(query_emb)
                if norm > 0:
                    query_emb = query_emb / norm
                    semantic_scores = self.embeddings_normalized @ query_emb
                    semantic_scores = (semantic_scores + 1) / 2  # → [0, 1]

        # --- Keyword matching ---
        if 'lyrics_cleaned' not in df.columns:
            # No lyrics column: rely on semantic only
            if semantic_scores is not None:
                df['_final_score'] = semantic_scores
                result = df.nlargest(top_k, '_final_score').copy()
                result['similarity_score'] = result['_final_score'].values
                result['original_index'] = result.index
                return result.drop(columns=['_final_score'])
            return df.head(0)

        lyrics_col = df['lyrics_cleaned'].fillna('').str.lower()
        match_scores = pd.Series(0.0, index=df.index)
        for term in terms:
            match_scores += lyrics_col.str.count(term).clip(upper=5)

        # Also check track name and artist
        name_col = df['track_name'].fillna('').str.lower()
        match_scores += name_col.str.count(keywords_lower).clip(upper=3) * 2

        artist_col_name = detect_artist_column(df)
        if artist_col_name:
            artist_col = df[artist_col_name].fillna('').str.lower()
            match_scores += artist_col.str.count(keywords_lower).clip(upper=2) * 1.5

        has_matches = (match_scores > 0).any()

        if has_matches:
            matched = df[match_scores > 0].copy()
            matched['_match_score'] = match_scores[match_scores > 0]
            max_match = matched['_match_score'].max()
            if max_match > 0:
                matched['_kw_norm'] = matched['_match_score'] / max_match
            else:
                matched['_kw_norm'] = 0.0

            # Semantic score for matched subset
            matched['_sem'] = 0.0
            if semantic_scores is not None:
                matched['_sem'] = semantic_scores[matched.index]

            # E8 — emotion/V-A term for mood/vibe queries.
            # The centroid-γ term (0.25) was removed (E8 2026-05-30): it added noise
            # without clear benefit (V11 plan), and V-A/emotion alignment is the right
            # signal for "vibe" intent.  We gate this term on whether the query looks
            # like a mood description (≥2 tokens and a non-trivial emotion score).
            # E8 — emotion/V-A alignment for mood/vibe queries (≥2 tokens).
            # Encodes the query's emotional intent as a V-A coordinate and scores
            # songs by Gaussian RBF proximity (σ=0.25). Only applied when the
            # emotion classifier returns a meaningful emotion dict. Silent on failure.
            matched['_emo_va'] = 0.0
            if len(terms) >= 2 and self.emotion_classifier.available:
                try:
                    q_emo = self.emotion_classifier.analyze_emotion(keywords)
                    if q_emo and max(q_emo.values(), default=0) > 0.05:
                        q_v, q_a = self.emotion_classifier.emotions_to_valence_arousal(q_emo)
                        va_dist = np.sqrt(
                            (self.song_va[:, 0] - q_v) ** 2 +
                            (self.song_va[:, 1] - q_a) ** 2
                        )
                        va_sim = np.exp(-(va_dist ** 2) / (2 * 0.25 ** 2))
                        mid = matched.index.tolist()
                        matched['_emo_va'] = va_sim[mid]
                except Exception:
                    pass

            # Hybrid: keyword 40% + semantic 45% + emotion/V-A 15%
            # (centroid-γ removed; emotion/V-A adds the mood-alignment signal)
            matched['_final_score'] = (
                0.40 * matched['_kw_norm'] +
                0.45 * matched['_sem'] +
                0.15 * matched['_emo_va']
            )

            matched = matched.sort_values('_final_score', ascending=False)
            result = matched.head(top_k).copy()
        elif semantic_scores is not None:
            # No keyword matches — pure semantic search
            df['_final_score'] = semantic_scores
            result = df.nlargest(top_k, '_final_score').copy()
        else:
            return df.head(0)

        result['original_index'] = result.index
        result['similarity_score'] = result['_final_score'].values

        for col in ['_match_score', '_kw_norm', '_sem', '_emo_va', '_final_score']:
            if col in result.columns:
                result = result.drop(columns=[col])

        # Cross-encoder reranking (Pillar C) — applied when ENABLE_RERANKER=True
        if ENABLE_RERANKER and len(result) >= 2:
            try:
                from core.reranker import get_reranker
                reranker = get_reranker(RERANKER_MODEL)
                if reranker is not None and 'original_index' in result.columns:
                    orig_indices = result['original_index'].tolist()
                    passages = []
                    for i in orig_indices:
                        row = self.df.iloc[i]
                        parts = [str(row.get('track_name', '') or '')]
                        if self.artist_col:
                            parts.append(str(row.get(self.artist_col, '') or ''))
                        if 'lyrics_cleaned' in self.df.columns:
                            parts.append(str(row.get('lyrics_cleaned', '') or '')[:200])
                        passages.append(' '.join(p for p in parts if p))
                    reranked = reranker.rerank(
                        keywords, passages, orig_indices,
                        top_k=min(len(orig_indices), RERANKER_TOP_K),
                    )
                    idx_order = {v: i for i, v in enumerate(reranked)}
                    result = result[result['original_index'].isin(idx_order)].copy()
                    result['_rr'] = result['original_index'].map(idx_order)
                    result = result.sort_values('_rr').drop(columns=['_rr']).reset_index(drop=True)
            except Exception as _e:
                logger.debug(f"[Reranker] rerank failed: {_e}")

        return result

    def get_song_info(self, song_id):
        """Get song details"""
        if 0 <= song_id < self.n_songs:
            return self.df.iloc[song_id].to_dict()
        return None

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
