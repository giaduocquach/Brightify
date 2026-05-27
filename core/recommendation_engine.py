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

        # Load modules
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

        # Analyze lyrics emotions (one-time)
        if 'lyrics_cleaned' in self.df.columns and 'fused_emotion' not in self.df.columns:
            self._analyze_lyrics_emotions()

        # Artist column for diversity
        self.artist_col = detect_artist_column(self.df)
        if self.artist_col:
            self.artists = self.df[self.artist_col].values
            if self.verbose:
                logger.debug("Artist diversity enabled")
        else:
            self.artists = None

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

        for idx in range(self.n_songs):
            color = self.colors[idx]

            if pd.isna(color):
                self.song_va[idx] = [0.5, 0.5]
                self.color_hsl[idx] = [0, 0, 50]
                continue

            try:
                # Get V-A from color
                va = self.color_mapper.color_to_valence_arousal(color)
                self.song_va[idx] = [va[0], va[1]]

                # Get HSL
                hsl = self.color_mapper.hex_to_hsl(color)
                self.color_hsl[idx] = hsl

                # Get emotion probabilities
                emotion_probs = self.color_mapper.color_to_emotion_probs(color)
                for i, emo in enumerate(self.emotion_labels):
                    self.song_emotion_vec[idx, i] = emotion_probs.get(emo, 0)
            except Exception:
                self.song_va[idx] = [0.5, 0.5]
                self.color_hsl[idx] = [0, 0, 50]

        # Normalize emotion vectors
        row_sums = self.song_emotion_vec.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        self.song_emotion_vec = self.song_emotion_vec / row_sums

        # Add fused valence/energy from dataframe if available
        if 'fused_valence' in self.df.columns:
            fused_va = self.df[['fused_valence', 'fused_energy']].fillna(0.5).values
            # Blend with color-derived V-A (audio takes priority)
            self.song_va = 0.6 * fused_va + 0.4 * self.song_va

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

    def recommend_by_colors(self,
                           color_hexes,
                           top_k=DEFAULT_TOP_K,
                           weights=None,
                           diversity_penalty=DIVERSITY_PENALTY):

        if isinstance(color_hexes, str):
            color_hexes = [color_hexes]

        if self.verbose:
            logger.debug(f"Recommending by colors: {color_hexes}")

        # Extract query features
        query_va = []
        query_audio = []
        query_emotion = np.zeros(len(self.emotion_labels))
        query_lyrics_vecs = []  # Collect lyrics embeddings for colors
        target_quadrant = None

        for color in color_hexes:
            try:
                va = self.color_mapper.color_to_valence_arousal(color)
                query_va.append([va[0], va[1]])

                audio_dict = self.color_mapper.color_to_audio(color)
                audio_vec = np.array([audio_dict.get(f, 0.5) for f in self.audio_features])
                query_audio.append(audio_vec)

                emotion_probs = self.color_mapper.color_to_emotion_probs(color)
                for i, emo in enumerate(self.emotion_labels):
                    query_emotion[i] += emotion_probs.get(emo, 0)

                # Map color to target emotions, then find representative lyrics embeddings
                # This creates a "query lyrics vector" based on emotional profile
                if self.embeddings_normalized is not None and 'fused_emotion' in self.df.columns:
                    # Get top emotion for this color
                    top_emotion = max(emotion_probs.items(), key=lambda x: x[1])[0]
                    # Find songs with this emotion and use their average embedding
                    emotion_mask = self.df['fused_emotion'] == top_emotion
                    if emotion_mask.sum() > 0:
                        emotion_indices = np.where(emotion_mask)[0]
                        # Average of top 5 songs with this emotion
                        sample_indices = emotion_indices[:min(5, len(emotion_indices))]
                        avg_lyrics = self.embeddings_normalized[sample_indices].mean(axis=0)
                        query_lyrics_vecs.append(avg_lyrics)
            except (ValueError, KeyError, TypeError):
                query_va.append([0.5, 0.5])
                query_audio.append(np.full(len(self.audio_features), 0.5))

        # Compute centroids
        query_va_centroid = np.mean(query_va, axis=0)
        query_audio_centroid = np.mean(query_audio, axis=0)
        query_emotion /= len(color_hexes)

        # Normalize emotion vector
        emotion_sum = query_emotion.sum()
        if emotion_sum > 0:
            query_emotion /= emotion_sum

        # Compute lyrics query vector (average of representative embeddings)
        if len(query_lyrics_vecs) > 0:
            query_lyrics_centroid = np.mean(query_lyrics_vecs, axis=0)
            # Normalize
            query_lyrics_norm = np.linalg.norm(query_lyrics_centroid)
            if query_lyrics_norm > 0:
                query_lyrics_centroid = query_lyrics_centroid / query_lyrics_norm
        else:
            query_lyrics_centroid = None

        # Determine target mood quadrant based on V-A
        valence, arousal = query_va_centroid
        if valence >= 0.5 and arousal >= 0.5:
            target_quadrant = 'Q1'  # Happy/Excited
            preferred_emotions = {'happy', 'excited', 'passionate'}
        elif valence < 0.5 and arousal >= 0.5:
            target_quadrant = 'Q2'  # Angry/Tense
            preferred_emotions = {'angry', 'tense', 'excited'}
        elif valence < 0.5 and arousal < 0.5:
            target_quadrant = 'Q3'  # Sad/Melancholic
            preferred_emotions = {'sad', 'melancholic', 'nostalgic'}
        else:
            target_quadrant = 'Q4'  # Calm/Peaceful
            preferred_emotions = {'calm', 'peaceful', 'romantic', 'tender'}

        if self.verbose:
            print(f"   Query V-A: valence={valence:.2f}, arousal={arousal:.2f} ({target_quadrant})")

        # ===== VECTORIZED SIMILARITY COMPUTATION =====

        # 1. V-A similarity with tighter Gaussian kernel
        va_diff = self.song_va - query_va_centroid
        va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
        va_sim = np.exp(-va_dist * 3)  # Tighter kernel (was 2)

        # 2. Emotion vector cosine similarity
        query_norm = np.linalg.norm(query_emotion)
        if query_norm > 0:
            song_norms = np.linalg.norm(self.song_emotion_vec, axis=1)
            dots = self.song_emotion_vec @ query_emotion
            emotion_sim = dots / (song_norms * query_norm + 1e-10)
            emotion_sim = (emotion_sim + 1) / 2
        else:
            emotion_sim = np.ones(self.n_songs) * 0.5

        # 3. Audio feature cosine similarity
        audio_sim = cosine_similarity(query_audio_centroid.reshape(1, -1), self.audio_matrix)[0]
        audio_sim = np.clip(audio_sim, 0, 1)

        # 4. Lyrics semantic similarity (NEW - Kim et al. 2024)
        if query_lyrics_centroid is not None and self.embeddings_normalized is not None:
            lyrics_sim = self.embeddings_normalized @ query_lyrics_centroid
            # Normalize to [0, 1]
            lyrics_sim = (lyrics_sim + 1) / 2
            lyrics_sim = np.clip(lyrics_sim, 0, 1)
            use_lyrics = True
        else:
            lyrics_sim = np.ones(self.n_songs) * 0.5  # Neutral if no lyrics
            use_lyrics = False

        # 5. Emotion-based boost/penalty
        # Boost songs with matching fused_emotion
        emotion_boost = np.zeros(self.n_songs)
        if 'fused_emotion' in self.df.columns:
            for idx in range(self.n_songs):
                song_emotion = self.df.iloc[idx].get('fused_emotion', '')
                if song_emotion in preferred_emotions:
                    emotion_boost[idx] = 0.12  # Boost matching emotions (reduced from 0.15)
                elif song_emotion in {'sad', 'melancholic'} and target_quadrant in ['Q1', 'Q4']:
                    emotion_boost[idx] = -0.08  # Penalize mismatched emotions
                elif song_emotion in {'happy', 'excited'} and target_quadrant == 'Q3':
                    emotion_boost[idx] = -0.08

        # ===== WEIGHTED FUSION (Research-based) =====
        # Zhang et al. (2024): Optimal multimodal fusion for music recommendation
        # Kim et al. (2024): Lyrics improve recommendation by 18%
        if use_lyrics:
            # Multimodal fusion with lyrics
            final_scores = (
                0.25 * audio_sim +      # Audio features (25%)
                0.35 * lyrics_sim +     # Lyrics semantic similarity (35%) - NEW!
                0.20 * va_sim +         # Valence-Arousal (20%)
                0.20 * emotion_sim +    # Emotion vector (20%)
                emotion_boost           # Emotion matching boost
            )
        else:
            # Fallback without lyrics (original weights)
            final_scores = (
                0.25 * audio_sim +      # Audio features
                0.35 * va_sim +         # Valence-Arousal distance (most important)
                0.25 * emotion_sim +    # Emotion vector similarity
                emotion_boost           # Emotion matching boost
            )

        # Ensure scores are positive
        final_scores = np.clip(final_scores, 0, 1)

        # ===== FAST RANKING WITH DIVERSITY =====
        return self._fast_rank(final_scores, top_k, diversity_penalty)

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

        # === Signal 1: Timbral similarity (Berenzweig et al. 2004) ===
        q_tim = self._timbral_matrix[song_idx]
        timbral_sim = cosine_similarity(q_tim.reshape(1, -1), self._timbral_matrix)[0]

        # === Signal 2: Rhythmic similarity ===
        q_rhy = self._rhythmic_matrix[song_idx]
        rhy_diff = np.abs(self._rhythmic_matrix - q_rhy)
        # Manhattan distance normalised to [0,1] per dimension, then averaged
        rhythmic_sim = 1.0 - rhy_diff.mean(axis=1)

        # === Signal 3: Tonal similarity ===
        q_ton = self._tonal_matrix[song_idx]
        tonal_sim = cosine_similarity(q_ton.reshape(1, -1), self._tonal_matrix)[0]

        # === Signal 4: Lyrics semantic similarity (Hu & Downie 2010) ===
        lyrics_sim = np.zeros(self.n_songs)
        has_lyrics = False
        if self.embeddings_normalized is not None:
            query_lyrics = self.embeddings_normalized[song_idx]
            lyrics_sim = self.embeddings_normalized @ query_lyrics
            lyrics_sim = (lyrics_sim + 1) / 2
            has_lyrics = True

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

        # === Adaptive fusion (Laurier et al. 2009) ===
        # Weights live in config.RECO_SONG_WEIGHTS; `weights` overrides them
        # (used by ablation to zero a signal and by the weight optimizer).
        if has_lyrics:
            # Full multimodal: lyrics carry strongest mood signal
            w = weights if weights is not None else RECO_SONG_WEIGHTS["with_lyrics"]
            final_scores = (
                w[0] * timbral_sim +
                w[1] * rhythmic_sim +
                w[2] * tonal_sim +
                w[3] * lyrics_sim +
                w[4] * va_sim +
                w[5] * emotion_sim +
                w[6] * mood_match
            )
        else:
            # Audio-only fallback (no lyrics signal)
            w = weights if weights is not None else RECO_SONG_WEIGHTS["audio_only"]
            final_scores = (
                w[0] * timbral_sim +
                w[1] * rhythmic_sim +
                w[2] * tonal_sim +
                w[3] * va_sim +
                w[4] * emotion_sim +
                w[5] * mood_match
            )

        # Exclude reference song
        final_scores[song_idx] = -1

        return self._fast_rank(final_scores, top_k, diversity_penalty)

    def recommend_by_mood(self,
                         mood,
                         top_k=DEFAULT_TOP_K,
                         weights=None,
                         diversity_penalty=DIVERSITY_PENALTY):
        """Recommend by mood keyword"""
        mood_lower = mood.lower()

        if self.verbose:
            print(f"😊 Recommending by mood: {mood}")

        if mood_lower in MOOD_KEYWORDS:
            _, valence, energy = MOOD_KEYWORDS[mood_lower]
        else:
            valence, energy = 0.5, 0.5

        query_va = np.array([valence, energy])

        # V-A similarity
        va_diff = self.song_va - query_va
        va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
        final_scores = np.exp(-va_dist * 2)

        return self._fast_rank(final_scores, top_k, diversity_penalty)

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
                    # Get V-A from this color
                    color_va = self.color_mapper.color_to_valence_arousal(color_hex)
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
        lyrics_sim = np.ones(self.n_songs) * 0.5
        use_lyrics = False
        
        if self.embeddings_normalized is not None and 'fused_emotion' in self.df.columns:
            # Find representative lyrics based on target emotions
            # Get top 2 emotions from image analysis
            top_emotions = sorted(emotion_scores.items(), key=lambda x: -x[1])[:2]
            query_lyrics_vecs = []
            
            for emo_name, emo_score in top_emotions:
                mapped_emo = clip_to_labels.get(emo_name)
                if mapped_emo:
                    # Find songs with this fused_emotion
                    mask = self.df['fused_emotion'].str.lower().str.contains(mapped_emo, na=False)
                    if mask.sum() > 0:
                        indices = np.where(mask)[0]
                        sample = indices[:min(8, len(indices))]
                        avg_emb = self.embeddings_normalized[sample].mean(axis=0)
                        query_lyrics_vecs.append(avg_emb * emo_score)
            
            if query_lyrics_vecs:
                query_lyrics = np.mean(query_lyrics_vecs, axis=0)
                norm = np.linalg.norm(query_lyrics)
                if norm > 0:
                    query_lyrics = query_lyrics / norm
                    lyrics_sim = self.embeddings_normalized @ query_lyrics
                    lyrics_sim = (lyrics_sim + 1) / 2
                    lyrics_sim = np.clip(lyrics_sim, 0, 1)
                    use_lyrics = True
        
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
        # Image recommendation uses more signals → distribute weights accordingly
        if use_lyrics:
            final_scores = (
                0.20 * audio_sim +       # Audio features (20%)
                0.25 * lyrics_sim +      # Lyrics semantic (25%)
                0.20 * va_sim +          # Valence-Arousal (20%)
                0.15 * emotion_sim +     # Emotion alignment (15%)
                0.20 * color_sim +       # Color palette matching (20%)
                emotion_boost            # Emotion boost/penalty
            )
        else:
            final_scores = (
                0.25 * audio_sim +       # Audio features
                0.25 * va_sim +          # Valence-Arousal
                0.20 * emotion_sim +     # Emotion alignment
                0.30 * color_sim +       # Color palette matching (higher without lyrics)
                emotion_boost
            )
        
        final_scores = np.clip(final_scores, 0, 1)
        
        if self.verbose:
            top_idx = np.argmax(final_scores)
            print(f"   V-A target: ({query_valence:.2f}, {query_arousal:.2f})")
            print(f"   Top score: {final_scores[top_idx]:.3f}")
            print(f"   Using lyrics: {use_lyrics}")
        
        return self._fast_rank(final_scores, top_k, diversity_penalty)

    # ========================================================================
    # Emotion Journey — Iso-Principle-based adaptive playlist
    # ========================================================================

    def generate_emotion_journey(self, start_valence, start_arousal,
                                 end_valence, end_arousal,
                                 steps=10, smoothness=0.7):
        """
        Generate a playlist that gradually transitions from one emotional
        state to another, following the Iso Principle from music therapy.

        Research basis:
        ─────────────────────────────────────────────────────────────────
        • Iso Principle (Altshuler, 1948; Davis & Thaut, 1989):
          Music therapy technique — start by *matching* the patient's
          current emotional state, then gradually shift toward the
          target mood. Validated in clinical settings for anxiety
          reduction and mood improvement.

        • Saari et al. (2016) "The Role of Music in Mood Regulation":
          Optimal V-A shift rate is ~10-15% of total distance per step
          to avoid perceptual jarring. Larger jumps cause listener
          disengagement.

        • Baltazar & Saarikallio (2019) "Strategies and mechanisms in
          musical affect self-regulation":
          Both approach (matching) and avoidance (contrast) strategies
          are valid. The Iso Principle uses approach → gradual shift.

        • Russell (1980) Circumplex Model of Affect:
          Using V-A space (valence × arousal) as the continuous
          emotion plane ensures smooth perceptual transitions.

        • Barthet et al. (2013) "Music Emotion Recognition: From
          Content- to Context-Based Models":
          Multi-feature similarity (timbral + lyrical + emotional)
          yields smoother perceived transitions than any single signal.

        Algorithm:
        1. Compute N waypoints along a smooth Bézier curve in V-A space
           from (start_v, start_a) → (end_v, end_a).
        2. At each waypoint, find the best matching song using:
           - V-A proximity (50%): Gaussian RBF on V-A distance to waypoint
           - Emotion profile alignment (25%): cosine sim to target emotion
           - Sequential smoothness (25%): cosine sim of audio features
             with the previously selected song (Barthet et al. 2013)
        3. Apply no-repeat constraint and mild artist diversity.

        Args:
            start_valence, start_arousal: Starting emotional state [0,1]
            end_valence, end_arousal: Target emotional state [0,1]
            steps: Number of songs in the journey (6-15)
            smoothness: Bézier curve smoothness factor (0-1)

        Returns:
            dict with 'songs' (list of dicts), 'waypoints', 'journey_info'
        """
        steps = max(6, min(15, steps))

        start = np.array([start_valence, start_arousal])
        end = np.array([end_valence, end_arousal])

        # ── Waypoint generation via quadratic Bézier ─────────────────
        # Bézier control point: midpoint + perpendicular offset for
        # a more natural arc (avoids boring straight line)
        mid = (start + end) / 2
        perp = np.array([-(end[1] - start[1]), end[0] - start[0]])
        perp_norm = np.linalg.norm(perp)
        if perp_norm > 0:
            perp = perp / perp_norm
        control = mid + smoothness * 0.15 * perp

        t_values = np.linspace(0, 1, steps)
        waypoints = np.array([
            (1 - t) ** 2 * start + 2 * (1 - t) * t * control + t ** 2 * end
            for t in t_values
        ])
        # Clamp to valid V-A range
        waypoints = np.clip(waypoints, 0.0, 1.0)

        # ── Target emotion vectors per waypoint ──────────────────────
        # Interpolate emotion profile from start to end zone
        start_emo = self._va_to_emotion_vector(start)
        end_emo = self._va_to_emotion_vector(end)

        # ── Song selection with sequential coherence ─────────────────
        selected_indices = set()
        selected_artists = {}
        journey_songs = []

        prev_audio = None  # For smoothness constraint

        for step_i, wp in enumerate(waypoints):
            # V-A proximity score (Gaussian RBF, σ adaptive to step)
            # Tighter at start/end, wider in middle for more flexibility
            progress = step_i / max(1, steps - 1)
            sigma = 0.15 + 0.10 * (1 - abs(2 * progress - 1))
            va_diff = self.song_va - wp
            va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
            va_score = np.exp(-(va_dist ** 2) / (2 * sigma ** 2))

            # Emotion profile alignment
            t_emo = (1 - progress) * start_emo + progress * end_emo
            t_emo_norm = np.linalg.norm(t_emo)
            if t_emo_norm > 0:
                t_emo = t_emo / t_emo_norm
            emo_score = self.song_emotion_vec @ t_emo

            # Sequential smoothness (audio feature cosine with previous)
            smooth_score = np.ones(self.n_songs)
            if prev_audio is not None:
                smooth_score = cosine_similarity(
                    prev_audio.reshape(1, -1), self.audio_matrix
                )[0]
                smooth_score = np.clip(smooth_score, 0, 1)

            # Lyrics semantic: find songs whose lyrics match the
            # interpolated emotional zone
            lyrics_score = np.ones(self.n_songs) * 0.5
            if self.embeddings_normalized is not None:
                zone_emo = self._va_to_emotion_label(wp[0], wp[1])
                if zone_emo and 'fused_emotion' in self.df.columns:
                    mask = self.df['fused_emotion'].str.lower().str.contains(
                        zone_emo, na=False
                    )
                    if mask.sum() > 0:
                        zone_idx = np.where(mask)[0][:10]
                        centroid = self.embeddings_normalized[zone_idx].mean(0)
                        c_norm = np.linalg.norm(centroid)
                        if c_norm > 0:
                            centroid = centroid / c_norm
                            lyrics_score = (self.embeddings_normalized @ centroid + 1) / 2

            # Combined score
            combined = (
                0.40 * va_score +
                0.20 * emo_score +
                0.20 * smooth_score +
                0.20 * lyrics_score
            )

            # Penalty: already selected
            for idx in selected_indices:
                combined[idx] = -1

            # Artist diversity: reduce score for repeat artists
            if self.artists is not None:
                for idx in np.argsort(combined)[::-1][:50]:
                    art = self.artists[idx]
                    if art and art in selected_artists:
                        combined[idx] *= (1 - 0.15) ** selected_artists[art]

            best_idx = int(np.argmax(combined))
            selected_indices.add(best_idx)

            if self.artists is not None:
                art = self.artists[best_idx]
                if art:
                    selected_artists[art] = selected_artists.get(art, 0) + 1

            prev_audio = self.audio_matrix[best_idx]

            song_data = self.df.iloc[best_idx]
            _thumb = song_data.get('thumbnail_url', None)
            journey_songs.append({
                'step': step_i + 1,
                'waypoint_valence': round(float(wp[0]), 3),
                'waypoint_arousal': round(float(wp[1]), 3),
                'song_valence': round(float(self.song_va[best_idx][0]), 3),
                'song_arousal': round(float(self.song_va[best_idx][1]), 3),
                'song_index': int(best_idx),
                'track_name': str(song_data.get('track_name', '')),
                'artist': str(song_data.get(self.artist_col, 'Unknown')) if self.artist_col else 'Unknown',
                'fused_emotion': str(song_data.get('fused_emotion', '')),
                'color_hex': str(song_data.get('color_hex', '#a78bfa')),
                'track_id': str(song_data.get('track_id', '')),
                'thumbnail_url': str(_thumb) if _thumb and not pd.isna(_thumb) else None,
                'va_distance': round(float(va_dist[best_idx]), 3),
            })

        # Journey metadata
        total_va_dist = float(np.linalg.norm(end - start))
        journey_info = {
            'start': {'valence': round(float(start[0]), 3),
                      'arousal': round(float(start[1]), 3)},
            'end':   {'valence': round(float(end[0]), 3),
                      'arousal': round(float(end[1]), 3)},
            'total_va_distance': round(total_va_dist, 3),
            'steps': steps,
            'avg_step_distance': round(total_va_dist / max(1, steps - 1), 3),
        }

        return {
            'songs': journey_songs,
            'waypoints': [{'valence': round(float(w[0]), 3),
                           'arousal': round(float(w[1]), 3)} for w in waypoints],
            'journey_info': journey_info,
        }

    def _va_to_emotion_vector(self, va):
        """Convert a V-A coordinate to an approximate emotion probability vector."""
        v, a = va[0], va[1]
        vec = np.zeros(len(self.emotion_labels))
        # Map to emotion probabilities using Russell's Circumplex geometry
        mapping = {
            'happy':      (0.85, 0.7),
            'sad':        (0.15, 0.2),
            'calm':       (0.65, 0.2),
            'excited':    (0.75, 0.9),
            'angry':      (0.15, 0.85),
            'peaceful':   (0.6,  0.15),
            'melancholic':(0.25, 0.3),
            'romantic':   (0.7,  0.4),
            'hopeful':    (0.7,  0.55),
            'tense':      (0.3,  0.8),
            'nostalgic':  (0.35, 0.35),
            'passionate': (0.65, 0.85),
            'tender':     (0.6,  0.3),
        }
        for i, label in enumerate(self.emotion_labels):
            if label in mapping:
                ev, ea = mapping[label]
                dist = np.sqrt((v - ev) ** 2 + (a - ea) ** 2)
                vec[i] = np.exp(-dist * 4)
        total = vec.sum()
        if total > 0:
            vec /= total
        return vec

    def _va_to_emotion_label(self, v, a):
        """Map a V-A coordinate to the closest emotion label."""
        if v >= 0.5 and a >= 0.5:
            return 'happy' if v > 0.7 else 'excited'
        elif v < 0.5 and a >= 0.5:
            return 'angry' if a > 0.7 else 'tense'
        elif v < 0.5 and a < 0.5:
            return 'sad' if v < 0.3 else 'melancholic'
        else:
            return 'calm' if v > 0.7 else 'peaceful'

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

    def smart_context_recommend(self, hour=None, day_of_week=None,
                                 activity=None, season=None, weather=None,
                                 user_history=None, user_liked=None,
                                 count=15):
        """
        Generate context-aware recommendations combining circadian rhythm,
        user taste profile, activity context, and seasonal mood.
        """
        import math
        from datetime import datetime

        now = datetime.now()
        if hour is None:
            hour = now.hour
        if day_of_week is None:
            day_of_week = now.weekday()  # 0=Mon, 6=Sun

        # ── 1. Circadian V-A Target (Skowronek 2006) ────────────────
        # Biological arousal follows a sinusoidal pattern peaking ~14:00
        circadian_arousal = 0.5 + 0.35 * math.sin(
            (hour - 6) * math.pi / 12  # peaks at hour=12
        )
        circadian_arousal = max(0.1, min(0.95, circadian_arousal))

        # Valence follows a milder curve, higher in afternoon
        circadian_valence = 0.5 + 0.2 * math.sin(
            (hour - 4) * math.pi / 12
        )
        circadian_valence = max(0.15, min(0.9, circadian_valence))

        # Late night (23-5) → low arousal, mild valence
        if hour >= 23 or hour < 5:
            circadian_arousal = 0.2 + (hour % 23) * 0.02
            circadian_valence = 0.4

        # Weekend boost (Cunningham 2006) — slightly higher energy
        is_weekend = day_of_week >= 5
        if is_weekend:
            circadian_arousal = min(1.0, circadian_arousal + 0.08)
            circadian_valence = min(1.0, circadian_valence + 0.05)

        # ── 2. Activity Modifier (North & Hargreaves 1996) ──────────
        activity_profiles = {
            'workout':  {'arousal_shift': 0.3, 'valence_shift': 0.15,
                         'energy_min': 0.65, 'tempo_min': 0.55, 'danceability_min': 0.55},
            'study':    {'arousal_shift': -0.25, 'valence_shift': 0.0,
                         'acousticness_min': 0.4, 'instrumentalness_min': 0.15,
                         'energy_max': 0.5, 'speechiness_max': 0.15},
            'relax':    {'arousal_shift': -0.2, 'valence_shift': 0.1,
                         'acousticness_min': 0.3, 'energy_max': 0.55},
            'commute':  {'arousal_shift': 0.05, 'valence_shift': 0.1,
                         'energy_min': 0.35, 'danceability_min': 0.4},
            'party':    {'arousal_shift': 0.35, 'valence_shift': 0.25,
                         'energy_min': 0.7, 'danceability_min': 0.6, 'tempo_min': 0.5},
            'sleep':    {'arousal_shift': -0.35, 'valence_shift': -0.05,
                         'energy_max': 0.3, 'acousticness_min': 0.5, 'tempo_max': 0.35},
            'focus':    {'arousal_shift': -0.15, 'valence_shift': 0.05,
                         'instrumentalness_min': 0.1, 'speechiness_max': 0.2,
                         'energy_max': 0.55},
            'cooking':  {'arousal_shift': 0.1, 'valence_shift': 0.2,
                         'danceability_min': 0.45, 'energy_min': 0.4},
            'morning_routine': {'arousal_shift': -0.05, 'valence_shift': 0.15,
                                'energy_max': 0.65, 'acousticness_min': 0.2},
        }

        act_profile = activity_profiles.get(activity, {})
        target_arousal = circadian_arousal + act_profile.get('arousal_shift', 0)
        target_valence = circadian_valence + act_profile.get('valence_shift', 0)
        target_arousal = max(0.05, min(0.95, target_arousal))
        target_valence = max(0.05, min(0.95, target_valence))

        # ── 3. Season/Weather Modifier (Cunningham 2006) ────────────
        season_modifiers = {
            'spring': {'valence_shift': 0.08, 'acousticness_bias': -0.05},
            'summer': {'valence_shift': 0.12, 'arousal_shift': 0.08, 'acousticness_bias': -0.1},
            'autumn': {'valence_shift': -0.05, 'acousticness_bias': 0.08},
            'winter': {'valence_shift': -0.08, 'acousticness_bias': 0.12},
        }
        weather_modifiers = {
            'sunny':  {'valence_shift': 0.1, 'arousal_shift': 0.05},
            'cloudy': {'valence_shift': -0.03, 'arousal_shift': -0.03},
            'rainy':  {'valence_shift': -0.08, 'arousal_shift': -0.1, 'acousticness_bias': 0.1},
            'stormy': {'arousal_shift': 0.1, 'valence_shift': -0.05},
            'snowy':  {'valence_shift': -0.03, 'arousal_shift': -0.15, 'acousticness_bias': 0.15},
        }

        if season and season in season_modifiers:
            sm = season_modifiers[season]
            target_valence += sm.get('valence_shift', 0)
            target_arousal += sm.get('arousal_shift', 0)
        if weather and weather in weather_modifiers:
            wm = weather_modifiers[weather]
            target_valence += wm.get('valence_shift', 0)
            target_arousal += wm.get('arousal_shift', 0)

        target_arousal = max(0.05, min(0.95, target_arousal))
        target_valence = max(0.05, min(0.95, target_valence))

        # ── 4. User Taste Center (Randall & Rickard 2017) ───────────
        user_va_center = None
        user_feature_center = None
        if user_liked and len(user_liked) >= 3:
            # Compute centroid from liked songs
            liked_indices = [s.get('song_index') for s in user_liked
                            if s.get('song_index') is not None and
                            0 <= s.get('song_index', -1) < self.n_songs]
            if len(liked_indices) >= 3:
                user_va_center = np.mean(self.song_va[liked_indices], axis=0)
                user_feature_center = np.mean(self.audio_matrix[liked_indices], axis=0)

        # ── 5. Multi-signal Scoring ─────────────────────────────────
        target_va = np.array([target_valence, target_arousal])

        # Signal 1: Circadian V-A proximity (Gaussian RBF)
        va_dists = np.linalg.norm(self.song_va - target_va, axis=1)
        sigma_va = 0.25
        va_scores = np.exp(-va_dists ** 2 / (2 * sigma_va ** 2))

        # Signal 2: User taste alignment
        user_scores = np.zeros(self.n_songs)
        if user_va_center is not None:
            user_dists = np.linalg.norm(self.song_va - user_va_center, axis=1)
            user_scores = np.exp(-user_dists ** 2 / (2 * 0.3 ** 2))
        if user_feature_center is not None:
            feat_dists = np.linalg.norm(self.audio_matrix - user_feature_center, axis=1)
            user_scores = 0.6 * user_scores + 0.4 * np.exp(-feat_dists ** 2 / (2 * 0.3 ** 2))

        # Signal 3: Activity audio feature constraints
        activity_scores = np.ones(self.n_songs)
        feature_map = {
            'energy': 1, 'danceability': 2, 'acousticness': 3,
            'instrumentalness': 4, 'speechiness': 5, 'tempo': 7,
        }
        for key, value in act_profile.items():
            if '_min' in key or '_max' in key:
                feat_name = key.replace('_min', '').replace('_max', '')
                if feat_name in feature_map:
                    col_idx = feature_map[feat_name]
                    if col_idx < self.audio_matrix.shape[1]:
                        col_data = self.audio_matrix[:, col_idx]
                        if '_min' in key:
                            activity_scores *= np.where(col_data >= value, 1.0,
                                                        np.exp(-((value - col_data) / 0.15) ** 2))
                        else:
                            activity_scores *= np.where(col_data <= value, 1.0,
                                                        np.exp(-((col_data - value) / 0.15) ** 2))

        # Signal 4: Emotion profile
        target_emotion_vec = self._va_to_emotion_vector(target_va)
        emotion_scores = np.zeros(self.n_songs)
        if hasattr(self, 'song_emotion_vec') and target_emotion_vec is not None:
            norms_song = np.linalg.norm(self.song_emotion_vec, axis=1, keepdims=True)
            norms_song[norms_song == 0] = 1
            norm_target = np.linalg.norm(target_emotion_vec)
            if norm_target > 0:
                emotion_scores = (self.song_emotion_vec @ target_emotion_vec) / (
                    norms_song.flatten() * norm_target)
                emotion_scores = np.clip(emotion_scores, 0, 1)

        # Signal 5: Freshness — penalize recently played songs
        freshness = np.ones(self.n_songs)
        if user_history:
            recent_indices = set()
            for s in user_history[-30:]:
                idx = s.get('song_index')
                if idx is not None and 0 <= idx < self.n_songs:
                    recent_indices.add(idx)
            for idx in recent_indices:
                freshness[idx] = 0.3  # Heavily penalize recent songs

        # ── Weighted Fusion ──
        w_va = 0.35
        w_user = 0.25 if user_va_center is not None else 0.0
        w_activity = 0.20 if activity else 0.0
        w_emotion = 0.10
        w_freshness = 0.10

        # Redistribute unused weights proportionally
        total_w = w_va + w_user + w_activity + w_emotion + w_freshness
        if total_w > 0:
            scale = 1.0 / total_w
            w_va *= scale
            w_user *= scale
            w_activity *= scale
            w_emotion *= scale
            w_freshness *= scale

        final_scores = (
            w_va * va_scores +
            w_user * user_scores +
            w_activity * activity_scores +
            w_emotion * emotion_scores +
            w_freshness * freshness
        )

        final_scores = np.clip(final_scores, 0, 1)

        # ── Build result using _fast_rank ──
        results = self._fast_rank(final_scores, count, DIVERSITY_PENALTY)
        if results.empty:
            return {'songs': [], 'context': {}}

        songs = []
        for _, row in results.iterrows():
            idx = int(row.get('original_index', 0))
            tid = str(row.get('track_id', ''))
            artist = str(row.get(self.artist_col, '')) if self.artist_col else ''
            _thumb = row.get('thumbnail_url', None)
            songs.append({
                'song_index': idx,
                'track_name': str(row.get('track_name', '')),
                'artist': artist,
                'track_id': tid,
                'fused_emotion': str(row.get('fused_emotion', '')),
                'color_hex': str(row.get('color_hex', '#6600CC')),
                'thumbnail_url': str(_thumb) if _thumb and not pd.isna(_thumb) else None,
                'valence': float(self.song_va[idx][0]) if idx < self.n_songs else 0,
                'arousal': float(self.song_va[idx][1]) if idx < self.n_songs else 0,
                'similarity_score': float(row.get('similarity_score', 0)),
            })

        # Determine period label
        period_map = {
            range(5, 7): 'early_morning', range(7, 10): 'morning',
            range(10, 13): 'midday', range(13, 17): 'afternoon',
            range(17, 21): 'evening', range(21, 24): 'night',
        }
        period_label = 'night'
        for r, label in period_map.items():
            if hour in r:
                period_label = label
                break
        if hour < 5:
            period_label = 'late_night'

        context_info = {
            'hour': hour,
            'day_of_week': day_of_week,
            'is_weekend': is_weekend,
            'period': period_label,
            'activity': activity,
            'season': season,
            'weather': weather,
            'target_valence': round(target_valence, 3),
            'target_arousal': round(target_arousal, 3),
            'has_user_profile': user_va_center is not None,
            'circadian_valence': round(circadian_valence, 3),
            'circadian_arousal': round(circadian_arousal, 3),
            'signal_weights': {
                'circadian_va': round(w_va, 2),
                'user_taste': round(w_user, 2),
                'activity_fit': round(w_activity, 2),
                'emotion': round(w_emotion, 2),
                'freshness': round(w_freshness, 2),
            },
        }

        return {'songs': songs, 'context': context_info}

    # ========================================================================
    # Musical DNA — Personal Taste Profile Analysis
    # ========================================================================
    #
    # Scientific foundation:
    #
    # • Rentfrow & Gosling (2003) "The Do Re Mi's of Everyday Life:
    #   The Structure and Personality Correlates of Music Preferences":
    #   Created STOMP (Short Test of Music Preferences) mapping personality
    #   to 4 music dimensions: Reflective/Complex, Intense/Rebellious,
    #   Upbeat/Conventional, Energetic/Rhythmic.
    #
    # • Schedl, Zamani, Chen, Deldjoo & Elahi (2018) "Current Challenges
    #   and Visions in Music Recommender Systems Research":
    #   User modelling via aggregating audio features of consumed content
    #   is a core technique for preference profiling.
    #
    # • Greenberg, Müllensiefen, Lamb & Rentfrow (2015) "Personality
    #   predicts musical sophistication":
    #   Musical preferences cluster around empathizing (mellow, acoustic)
    #   vs systemizing (intense, complex) cognitive styles.
    #
    # • Hu & Pu (2010) "A Study on User Perception of Personality
    #   Based Recommender Systems":
    #   User taste profiles derived from listening behaviour improve
    #   perceived recommendation quality and user satisfaction.
    #
    # • Ferwerda, Tkalčič & Schedl (2017) "Personality Traits and Music
    #   Genre Preferences":
    #   Feature aggregation across liked songs creates reliable taste
    #   dimensions — variance captures exploration breadth.
    #
    # Algorithm:
    # 1. Aggregate audio features from user's liked + history songs.
    # 2. Compute 6 "DNA dimensions" (mean ± std across liked songs):
    #    - Mood Brightness (valence), Energy Drive (energy),
    #    - Rhythm Affinity (danceability + tempo), Acoustic Warmth
    #      (acousticness), Vocal Focus (1 - instrumentalness),
    #    - Lyrical Depth (sentiment variance).
    # 3. Compute Emotional Fingerprint: distribution across 13 emotions.
    # 4. Taste Diversity Index (ILD — Intra-List Diversity, Ziegler 2005):
    #    Std deviation of features — high = eclectic, low = focused.
    # 5. Temporal Patterns: dominant listening time-of-day from history.
    # 6. Generate DNA-matched recommendations (songs closest to taste center
    #    weighted by user's feature variance — explore dimensions they like).

    def compute_musical_dna(self, user_liked=None, user_history=None):
        """
        Compute a user's Musical DNA taste profile from their listening data.
        Returns a rich profile with dimensions, emotions, patterns, and
        personalized recommendations.
        """
        if not user_liked and not user_history:
            return None

        # Collect all valid song indices
        liked_indices = []
        if user_liked:
            for s in user_liked:
                idx = s.get('song_index')
                if idx is not None and 0 <= idx < self.n_songs:
                    liked_indices.append(idx)

        history_indices = []
        history_times = []
        if user_history:
            for s in user_history:
                idx = s.get('song_index')
                if idx is not None and 0 <= idx < self.n_songs:
                    history_indices.append(idx)
                    played_at = s.get('played_at', '')
                    history_times.append(played_at)

        # Combine unique indices (liked songs weighted 2x)
        all_indices = liked_indices + liked_indices + history_indices
        unique_indices = list(set(liked_indices + history_indices))

        if len(unique_indices) < 3:
            return None

        # ── 1. DNA Dimensions (Rentfrow & Gosling 2003, Ferwerda 2017) ─
        features_matrix = self.audio_matrix[unique_indices]  # (n, 11)
        va_matrix = self.song_va[unique_indices]  # (n, 2)

        # Feature name → column index in audio_matrix
        feat_idx = {}
        for i, name in enumerate(self.audio_features):
            feat_idx[name] = i

        def safe_mean(arr):
            return float(np.mean(arr)) if len(arr) > 0 else 0.5

        def safe_std(arr):
            return float(np.std(arr)) if len(arr) > 1 else 0.0

        # 6 DNA dimensions
        valence_data = features_matrix[:, feat_idx['valence']] if 'valence' in feat_idx else va_matrix[:, 0]
        energy_data = features_matrix[:, feat_idx['energy']] if 'energy' in feat_idx else np.full(len(unique_indices), 0.5)

        danceability_data = features_matrix[:, feat_idx['danceability']] if 'danceability' in feat_idx else np.full(len(unique_indices), 0.5)
        tempo_data = features_matrix[:, feat_idx['tempo']] if 'tempo' in feat_idx else np.full(len(unique_indices), 0.5)

        acousticness_data = features_matrix[:, feat_idx['acousticness']] if 'acousticness' in feat_idx else np.full(len(unique_indices), 0.5)
        instrumentalness_data = features_matrix[:, feat_idx['instrumentalness']] if 'instrumentalness' in feat_idx else np.full(len(unique_indices), 0.5)

        dimensions = {
            'mood_brightness': {
                'value': round(safe_mean(valence_data), 3),
                'spread': round(safe_std(valence_data), 3),
                'label': 'Sáng' if safe_mean(valence_data) > 0.55 else ('Trầm' if safe_mean(valence_data) < 0.4 else 'Trung tính'),
                'description': 'Xu hướng tâm trạng âm nhạc',
            },
            'energy_drive': {
                'value': round(safe_mean(energy_data), 3),
                'spread': round(safe_std(energy_data), 3),
                'label': 'Mạnh mẽ' if safe_mean(energy_data) > 0.6 else ('Nhẹ nhàng' if safe_mean(energy_data) < 0.4 else 'Cân bằng'),
                'description': 'Cường độ năng lượng ưa thích',
            },
            'rhythm_affinity': {
                'value': round(safe_mean(danceability_data * 0.6 + tempo_data * 0.4), 3),
                'spread': round(safe_std(danceability_data * 0.6 + tempo_data * 0.4), 3),
                'label': 'Sôi động' if safe_mean(danceability_data) > 0.6 else ('Chậm rãi' if safe_mean(danceability_data) < 0.4 else 'Vừa phải'),
                'description': 'Nhịp điệu và khiêu vũ',
            },
            'acoustic_warmth': {
                'value': round(safe_mean(acousticness_data), 3),
                'spread': round(safe_std(acousticness_data), 3),
                'label': 'Acoustic' if safe_mean(acousticness_data) > 0.55 else ('Electronic' if safe_mean(acousticness_data) < 0.35 else 'Hòa trộn'),
                'description': 'Âm thanh tự nhiên vs điện tử',
            },
            'vocal_focus': {
                'value': round(1.0 - safe_mean(instrumentalness_data), 3),
                'spread': round(safe_std(instrumentalness_data), 3),
                'label': 'Vocal' if safe_mean(instrumentalness_data) < 0.3 else ('Nhạc cụ' if safe_mean(instrumentalness_data) > 0.6 else 'Kết hợp'),
                'description': 'Ưu tiên giọng hát vs nhạc cụ',
            },
            'emotional_depth': {
                'value': round(safe_std(valence_data) + safe_std(energy_data), 3),
                'spread': 0,
                'label': 'Đa dạng' if (safe_std(valence_data) + safe_std(energy_data)) > 0.35 else ('Chuyên sâu' if (safe_std(valence_data) + safe_std(energy_data)) < 0.15 else 'Cân bằng'),
                'description': 'Độ phong phú cảm xúc',
            },
        }

        # ── 2. Emotional Fingerprint ────────────────────────────────────
        emotion_counts = {}
        for idx in unique_indices:
            emo = str(self.df.iloc[idx].get('fused_emotion', '')).lower()
            if emo:
                emotion_counts[emo] = emotion_counts.get(emo, 0) + 1

        total_emo = sum(emotion_counts.values())
        emotion_profile = {}
        if total_emo > 0:
            for emo, cnt in sorted(emotion_counts.items(), key=lambda x: -x[1]):
                emotion_profile[emo] = round(cnt / total_emo, 3)

        # Top 3 emotions
        top_emotions = list(emotion_profile.keys())[:3] if emotion_profile else []

        # ── 3. Taste Diversity Index (Ziegler et al. 2005 ILD) ──────────
        if len(unique_indices) > 1:
            pairwise_dists = []
            sample_idx = unique_indices[:50]  # Limit for speed
            for i in range(len(sample_idx)):
                for j in range(i + 1, len(sample_idx)):
                    dist = np.linalg.norm(
                        self.audio_matrix[sample_idx[i]] - self.audio_matrix[sample_idx[j]])
                    pairwise_dists.append(dist)
            diversity_index = float(np.mean(pairwise_dists)) if pairwise_dists else 0.0
        else:
            diversity_index = 0.0
        # Normalize to 0-1 (typical range 0-2)
        diversity_index = min(1.0, diversity_index / 1.5)

        diversity_label = 'Phiêu lưu' if diversity_index > 0.55 else (
            'Tập trung' if diversity_index < 0.3 else 'Cân bằng'
        )

        # ── 4. Temporal Patterns ────────────────────────────────────────
        hour_distribution = [0] * 24
        if history_times:
            for t in history_times:
                try:
                    if isinstance(t, str) and 'T' in t:
                        h = int(t.split('T')[1].split(':')[0])
                        hour_distribution[h % 24] += 1
                except (ValueError, IndexError):
                    pass

        total_plays = sum(hour_distribution)
        peak_hours = []
        if total_plays > 0:
            hour_pcts = [h / total_plays for h in hour_distribution]
            threshold = 1.5 / 24  # 1.5x average
            peak_hours = [i for i, p in enumerate(hour_pcts) if p > threshold]

        # ── 5. V-A Center & Artist Preferences ─────────────────────────
        va_center = np.mean(va_matrix, axis=0).tolist()

        artist_counts = {}
        for idx in unique_indices:
            if self.artist_col and self.artist_col in self.df.columns:
                artist = str(self.df.iloc[idx].get(self.artist_col, ''))
                if artist:
                    artist_counts[artist] = artist_counts.get(artist, 0) + 1
        top_artists = sorted(artist_counts.items(), key=lambda x: -x[1])[:5]

        # ── 6. DNA-matched Recommendations ──────────────────────────────
        # Weighted centre: user's mean features, with std as exploration range
        center_features = np.mean(features_matrix, axis=0)
        feature_std = np.std(features_matrix, axis=0)
        feature_std[feature_std == 0] = 0.1

        # Score each song: distance to center, weighted by 1/std
        # (dimensions user is consistent on → stricter matching;
        #  dimensions user varies on → more tolerant)
        weighted_dists = np.zeros(self.n_songs)
        for i in range(self.audio_matrix.shape[1]):
            diff = (self.audio_matrix[:, i] - center_features[i]) ** 2
            weight = 1.0 / (feature_std[i] + 0.05)
            weighted_dists += diff * weight

        dna_scores = np.exp(-weighted_dists / (2 * self.audio_matrix.shape[1]))

        # Penalize already-known songs
        for idx in set(liked_indices + history_indices):
            dna_scores[idx] *= 0.1

        recommendations = self._fast_rank(dna_scores, 20, DIVERSITY_PENALTY)
        rec_songs = []
        if not recommendations.empty:
            for _, row in recommendations.iterrows():
                idx = int(row.get('original_index', 0))
                tid = str(row.get('track_id', ''))
                artist = str(row.get(self.artist_col, '')) if self.artist_col else ''
                _thumb = row.get('thumbnail_url', None)
                rec_songs.append({
                    'song_index': idx,
                    'track_name': str(row.get('track_name', '')),
                    'artist': artist,
                    'track_id': tid,
                    'fused_emotion': str(row.get('fused_emotion', '')),
                    'color_hex': str(row.get('color_hex', '#6600CC')),
                    'thumbnail_url': str(_thumb) if _thumb and not pd.isna(_thumb) else None,
                    'match_score': float(row.get('similarity_score', 0)),
                })

        return {
            'dimensions': dimensions,
            'emotion_profile': emotion_profile,
            'top_emotions': top_emotions,
            'diversity_index': round(diversity_index, 3),
            'diversity_label': diversity_label,
            'va_center': [round(v, 3) for v in va_center],
            'hour_distribution': hour_distribution,
            'peak_hours': peak_hours,
            'top_artists': [{'name': a, 'count': c} for a, c in top_artists],
            'total_songs_analyzed': len(unique_indices),
            'liked_count': len(liked_indices),
            'history_count': len(history_indices),
            'recommendations': rec_songs,
        }

    def _fast_rank(self, scores, top_k, diversity_penalty):
        """
        Diversity-aware ranking. Dispatches to MMR, DPP, or greedy based on
        config.DIVERSITY_METHOD (default "mmr").

        MMR  — Carbonell & Goldstein 1998: λ·relevance − (1−λ)·max_sim_to_selected
        DPP  — Chen et al. 2018 fast greedy MAP
        greedy — original artist-penalty heuristic (kept for backward-compat)
        """
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
            if DIVERSITY_METHOD == "mmr":
                chosen = mmr_rerank(
                    candidates, scores, self.embeddings_normalized,
                    top_k=top_k, lambda_=DIVERSITY_LAMBDA,
                )
            else:
                chosen = dpp_greedy_map(
                    candidates, scores, self.embeddings_normalized, top_k=top_k,
                )
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

            # Centroid embedding similarity for matched subset
            matched['_centroid_sim'] = 0.0
            if self.embeddings_normalized is not None and len(matched) > 0:
                top_idx = matched.nlargest(min(10, len(matched)), '_match_score').index
                centroid = self.embeddings_normalized[top_idx].mean(axis=0)
                cn = np.linalg.norm(centroid)
                if cn > 0:
                    centroid = centroid / cn
                    mid = matched.index.tolist()
                    matched['_centroid_sim'] = (self.embeddings_normalized[mid] @ centroid + 1) / 2

            # Semantic score for matched subset
            matched['_sem'] = 0.0
            if semantic_scores is not None:
                matched['_sem'] = semantic_scores[matched.index]

            # Hybrid: keyword 35% + semantic 40% + centroid 25%
            matched['_final_score'] = (
                0.35 * matched['_kw_norm'] +
                0.40 * matched['_sem'] +
                0.25 * matched['_centroid_sim']
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

        for col in ['_match_score', '_kw_norm', '_centroid_sim', '_sem', '_final_score']:
            if col in result.columns:
                result = result.drop(columns=[col])

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
