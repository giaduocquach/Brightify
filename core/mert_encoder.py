"""
MERT-v1-95M audio embedding encoder (Li et al. 2023, arXiv 2306.00107).

Extracts 768-dim L2-normalised embeddings from MP3 files by:
  1. Loading audio at 24 kHz (MERT native sample rate)
  2. Chunking into MERT_CLIP_DURATION-second segments
  3. Running the model and extracting layer MERT_LAYER hidden states
  4. Mean-pooling over time → chunk embedding
  5. Averaging over all chunks → song embedding
  6. L2-normalising

Usage:
    from core.mert_encoder import get_mert_encoder
    enc = get_mert_encoder()
    emb = enc.extract("music_files/foo.mp3")   # (768,) float32 unit-norm
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_INSTANCE: Optional["MERTEncoder"] = None


def get_mert_encoder() -> "MERTEncoder":
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MERTEncoder()
    return _INSTANCE


class MERTEncoder:
    """Lazy-initialised singleton wrapper around MERT-v1-95M."""

    def __init__(self) -> None:
        import config as cfg
        self._model_id = cfg.MERT_MODEL
        self._layer    = cfg.MERT_LAYER
        self._clip_dur = cfg.MERT_CLIP_DURATION
        self._sr       = 24_000
        self._cache_dir = cfg.HF_CACHE_DIR
        self._model    = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoFeatureExtractor, AutoModel

        os.makedirs(self._cache_dir, exist_ok=True)
        logger.info(f"[MERT] Loading {self._model_id} …")
        self._processor = AutoFeatureExtractor.from_pretrained(
            self._model_id, trust_remote_code=True, cache_dir=self._cache_dir,
        )
        self._model = AutoModel.from_pretrained(
            self._model_id, trust_remote_code=True, cache_dir=self._cache_dir,
        )
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        logger.info(f"[MERT] Ready on {self._device}")

    def extract(self, mp3_path: str) -> Optional[np.ndarray]:
        """Return 768-dim unit-norm embedding, or None on failure."""
        import librosa
        import torch

        self._load()
        try:
            y, _ = librosa.load(mp3_path, sr=self._sr, mono=True)
        except Exception as e:
            logger.warning(f"[MERT] audio load failed {mp3_path}: {e}")
            return None

        clip_len = int(self._clip_dur * self._sr)
        # Split into non-overlapping clips; ensure at least one clip
        clips = [y[i:i + clip_len] for i in range(0, max(1, len(y) - clip_len + 1), clip_len)]
        if not clips:
            clips = [y]

        chunk_embs = []
        with torch.no_grad():
            for clip in clips:
                if len(clip) < 400:      # too short for the model
                    continue
                inputs = self._processor(
                    clip, sampling_rate=self._sr, return_tensors="pt",
                )
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
                out = self._model(**inputs, output_hidden_states=True)
                # hidden_states: tuple of (1, T, 768) tensors, length = num_layers + 1
                h = out.hidden_states[self._layer]   # (1, T, 768)
                emb = h.mean(dim=1).squeeze(0).cpu().numpy()  # (768,)
                chunk_embs.append(emb)

        if not chunk_embs:
            return None

        song_emb = np.mean(chunk_embs, axis=0).astype(np.float32)
        norm = np.linalg.norm(song_emb)
        if norm < 1e-9:
            return None
        return song_emb / norm
