"""Wrap MusicRecommender + expose feature matrices for backtest metrics.

`original_index` is the stable 0-based row position in the dataframe,
which is also the integer argument that recommend_by_song() accepts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import List, Optional


class Catalog:
    """Adapter over core.recommendation_engine.MusicRecommender.

    All backtest modules access song features through this object — not
    through the recommender directly — so the interface stays stable even
    if the recommender's internals change.
    """

    def __init__(self, recommender) -> None:
        self.rec = recommender
        # Ensure the dataframe has a clean 0-based integer index that
        # matches all pre-computed feature arrays.
        self.df: pd.DataFrame = recommender.df.reset_index(drop=True)
        self.n: int = len(self.df)

        # --- Feature matrices (same objects as recommender; no copy) ---
        # PhoBERT 768-dim, L2-normalised for fast cosine sim.
        self.embeddings_normalized: Optional[np.ndarray] = recommender.embeddings_normalized

        # Full audio feature matrix (timbral+rhythmic+tonal combined, normalised).
        self.audio_matrix: np.ndarray = recommender.audio_matrix

        # V-A fused array (n_songs, 2) — [valence, arousal] blended from
        # color and fused_valence/energy. This is what the engine uses internally.
        self.song_va: np.ndarray = recommender.song_va

        # Emotion probability vectors (n_songs, n_emotions).
        self.song_emotion_vec: np.ndarray = recommender.song_emotion_vec
        self.emotion_labels: List[str] = recommender.emotion_labels

        # Artist column name (may be None if undetected)
        self.artist_col: Optional[str] = recommender.artist_col

        # Raw BPM from CSV (not normalised — needed for TempoCoherence).
        if 'tempo' in self.df.columns:
            self.tempo: np.ndarray = self.df['tempo'].fillna(0).values.astype(float)
        else:
            self.tempo = np.zeros(self.n)

        # color_hex strings for CIEDE2000 computation.
        if 'color_hex' in self.df.columns:
            self.color_hex: np.ndarray = self.df['color_hex'].fillna('').values
        else:
            self.color_hex = np.array([''] * self.n)

        # Fused emotion labels (string, one per song) — set after
        # MusicRecommender._analyze_lyrics_emotions() runs at init.
        if 'fused_emotion' in self.df.columns:
            self.fused_emotion: np.ndarray = self.df['fused_emotion'].fillna('').values
        else:
            self.fused_emotion = np.array([''] * self.n)

    @classmethod
    def load(cls) -> "Catalog":
        """Load (or reuse) the singleton MusicRecommender and wrap it."""
        from core.recommendation_engine import get_recommender
        rec = get_recommender()
        return cls(rec)

    @classmethod
    def load_with_embeddings(cls, embeddings_path: str) -> "Catalog":
        """Load a fresh MusicRecommender with a custom embeddings file.

        Used by Pillar B backtest to compare PhoBERT vs ViDeBERTa/ViSoBERT
        without mutating the singleton used by the live app.
        """
        import config as cfg
        from core.recommendation_engine import MusicRecommender
        rec = MusicRecommender(
            data_path=cfg.PROCESSED_FILE,
            embeddings_path=embeddings_path,
            verbose=False,
        )
        return cls(rec)

    @classmethod
    def load_with_mert(cls, mert_embeddings_path: str) -> "Catalog":
        """Load a fresh MusicRecommender with MERT embeddings active (Pillar A)."""
        import config as cfg
        import core.recommendation_engine as _eng

        old_flag = _eng.ENABLE_MERT
        old_path = _eng.MERT_EMBEDDINGS_FILE
        _eng.ENABLE_MERT = True
        _eng.MERT_EMBEDDINGS_FILE = mert_embeddings_path
        try:
            from core.recommendation_engine import MusicRecommender
            rec = MusicRecommender(
                data_path=cfg.PROCESSED_FILE,
                embeddings_path=cfg.EMBEDDINGS_FILE_PILLAR_B if cfg.ENABLE_PILLAR_B else cfg.EMBEDDINGS_FILE,
                verbose=False,
            )
        finally:
            _eng.ENABLE_MERT = old_flag
            _eng.MERT_EMBEDDINGS_FILE = old_path
        return cls(rec)

    # ------------------------------------------------------------------
    # Unified recommend interface used by all baselines and the runner
    # ------------------------------------------------------------------

    def recommend_by_song(
        self,
        seed_idx: int,
        top_k: int = 10,
        weights=None,
    ) -> List[int]:
        """Return list of top_k recommended song original_indices."""
        result = self.rec.recommend_by_song(
            seed_idx,
            top_k=top_k,
            weights=weights,
        )
        if result is None or (hasattr(result, 'empty') and result.empty):
            return []
        return result['original_index'].tolist()
