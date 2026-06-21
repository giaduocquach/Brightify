"""
MERT-v1-95M audio embedding encoder (Li et al. 2023, arXiv 2306.00107).

Extracts 768-dim L2-normalised embeddings from MP3 files by:
  1. Loading audio at 24 kHz (MERT native sample rate)
  2. Taking two representative 15-second clips per song
  3. Running the model with output_hidden_states=True
  4. Pooling hidden states (single layer OR mean across a list of layers — Phase 1)
  5. Mean-pooling over time → clip embedding
  6. Averaging over clips → song embedding
  7. L2-normalising → (768,) float32 unit-norm

Multi-layer mode (layers=list): mean over selected hidden-state layers THEN mean over
time — mathematically identical to mean over time first (operations commute), so the
output is still 768-dim and drop-in compatible with the single-layer pipeline.

Literature basis (Phase 1 — arXiv:2604.20847, Li et al. 2023 probing):
  Lower layers (1-4): timbral / pitch
  Middle layers (5-8): rhythmic / tempo
  Upper layers (9-12): genre / emotion / musical semantics
  Mean across all 12 layers captures the full spectrum.

Usage:
    from tools.mert_encoder import get_mert_encoder
    enc = get_mert_encoder()
    emb = enc.extract("music_files/foo.mp3")   # (768,) float32 unit-norm
    # Multi-layer (explicit):
    enc_ml = MERTEncoder(layers=list(range(1, 13)))
    emb_ml = enc_ml.extract("music_files/foo.mp3")
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
    """Lazy-initialised wrapper around MERT-v1-95M.

    layers: int  → single hidden-state index (backward-compat, default from config)
            list → mean across those hidden-state indices (multi-layer, Phase 1)
            None → read MERT_LAYERS from config (list) or fall back to MERT_LAYER (int)
    """

    def __init__(self, layers=None) -> None:
        import config as cfg
        self._model_id  = cfg.MERT_MODEL
        self._clip_dur  = cfg.MERT_CLIP_DURATION
        self._sr        = 24_000
        self._cache_dir = cfg.HF_CACHE_DIR
        self._model     = None
        self._processor = None

        if layers is None:
            ml = getattr(cfg, "MERT_LAYERS", None)
            self._layers = ml if ml is not None else cfg.MERT_LAYER
        else:
            self._layers = layers

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
        """Return 768-dim unit-norm embedding, or None on failure.

        For speed we sample two 15-second clips per song:
          - Clip A: from 30 s offset (or song start for short tracks)
          - Clip B: from 75 s offset (if the song is long enough)
        This covers verse + pre-chorus for most Vietnamese pop/ballad tracks
        while keeping CPU cost at ~0.85 s/song (vs. ~6 s for the full song).
        """
        import librosa
        import torch

        self._load()
        clip_len = int(self._clip_dur * self._sr)

        # Choose representative offsets based on song duration
        try:
            total_dur = librosa.get_duration(path=mp3_path)
        except Exception:
            total_dur = 180.0  # assume 3 min if unknown

        offsets = [min(30.0, max(0.0, total_dur * 0.15))]
        if total_dur > 90.0:
            offsets.append(min(75.0, total_dur * 0.45))

        clips = []
        for offset in offsets:
            try:
                y, _ = librosa.load(
                    mp3_path, sr=self._sr, mono=True,
                    offset=offset, duration=self._clip_dur,
                )
                if len(y) >= 400:
                    clips.append(y)
            except Exception as e:
                logger.warning(f"[MERT] audio load failed {mp3_path} @{offset}s: {e}")

        if not clips:
            # Last-resort: load first clip_len samples from the beginning
            try:
                y, _ = librosa.load(mp3_path, sr=self._sr, mono=True, duration=self._clip_dur)
                if len(y) >= 400:
                    clips = [y]
            except Exception as e:
                logger.warning(f"[MERT] audio load failed {mp3_path}: {e}")
                return None

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
                # hidden_states: tuple of (1, T, 768) tensors, length = 13
                # (input embedding at index 0 + 12 transformer layers at 1-12)
                layers = self._layers
                if isinstance(layers, int):
                    # Single-layer (backward-compat)
                    h = out.hidden_states[layers]        # (1, T, 768)
                    emb = h.mean(dim=1).squeeze(0).cpu().numpy()  # (768,)
                else:
                    # Multi-layer: stack → (L, 1, T, 768), mean over L then T
                    # Mean(layers) then Mean(time) == Mean(time) then Mean(layers)
                    # — operations commute, result is (768,).
                    stacked = torch.stack(
                        [out.hidden_states[i] for i in layers], dim=0
                    )                                    # (L, 1, T, 768)
                    emb = stacked.mean(dim=0).mean(dim=1).squeeze(0).cpu().numpy()
                chunk_embs.append(emb)

        if not chunk_embs:
            return None

        song_emb = np.mean(chunk_embs, axis=0).astype(np.float32)
        norm = np.linalg.norm(song_emb)
        if norm < 1e-9:
            return None
        return song_emb / norm
