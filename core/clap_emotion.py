"""
CLAP zero-shot emotion classifier (Wu et al. 2023, arXiv 2211.06687).

Maps audio to the 8 fused_emotion categories used by recommendation_engine:
  excited, happy, angry, tense, sad, melancholic, peaceful, calm

Uses laion/larger_clap_music_and_speech with dual Vietnamese+English prompts
per category.  Text embeddings are pre-computed once at load time.

Usage:
    from core.clap_emotion import get_clap_emotion_predictor
    p = get_clap_emotion_predictor()
    label = p.predict("music_files/abc123.mp3")   # e.g. "calm"
    probs  = p.predict_probs("music_files/abc123.mp3")  # {"calm": 0.42, ...}
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emotion prompts (Vietnamese + English per category)
# ---------------------------------------------------------------------------
EMOTION_PROMPTS: Dict[str, list[str]] = {
    "excited":     ["bài hát vui nhộn cuồng nhiệt tràn đầy năng lượng sôi động",
                    "a very energetic upbeat exciting dance song"],
    "happy":       ["bài hát vui tươi hạnh phúc nhẹ nhàng tích cực",
                    "a cheerful happy positive light-hearted song"],
    "angry":       ["bài hát tức giận mạnh mẽ dữ dội căng thẳng heavy metal",
                    "an aggressive angry intense heavy rock song"],
    "tense":       ["nhạc căng thẳng hồi hộp lo lắng bất an",
                    "tense nervous anxious suspenseful dramatic music"],
    "sad":         ["bài hát buồn thảm thiết đau khổ u sầu sâu lắng",
                    "a deeply sad depressing sorrowful heartbreaking song"],
    "melancholic": ["bài hát man mác bâng khuâng hoài niệm nhớ nhung",
                    "a melancholic bittersweet nostalgic wistful song"],
    "peaceful":    ["nhạc thư giãn êm ái bình yên nhẹ nhàng thiền định",
                    "very calm relaxing peaceful soothing meditation music"],
    "calm":        ["nhạc nhẹ nhàng yên tĩnh dịu dàng acoustic nhẹ",
                    "calm gentle quiet tranquil acoustic music"],
}

_INSTANCE: Optional["CLAPEmotionPredictor"] = None


def get_clap_emotion_predictor() -> "CLAPEmotionPredictor":
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = CLAPEmotionPredictor()
    return _INSTANCE


class CLAPEmotionPredictor:
    """Lazy-loaded singleton CLAP emotion classifier."""

    def __init__(self) -> None:
        import config as cfg
        self._model_id = cfg.CLAP_MODEL
        self._clip_dur = cfg.CLAP_CLIP_DURATION
        self._sr = 48_000  # CLAP native sample rate
        self._cache_dir = cfg.HF_CACHE_DIR
        self._model = None
        self._processor = None
        self._text_embs: Optional[np.ndarray] = None
        self._prompt_label_idx: Optional[np.ndarray] = None
        self._labels = list(EMOTION_PROMPTS.keys())

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import ClapModel, ClapProcessor

        os.makedirs(self._cache_dir, exist_ok=True)
        logger.info(f"[CLAP] Loading {self._model_id} …")
        self._processor = ClapProcessor.from_pretrained(
            self._model_id, cache_dir=self._cache_dir,
        )
        self._model = ClapModel.from_pretrained(
            self._model_id, cache_dir=self._cache_dir,
        )
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._precompute_text_embeddings()
        logger.info(f"[CLAP] Ready on {self._device}")

    def _precompute_text_embeddings(self) -> None:
        """Compute & L2-normalise text embeddings for all prompts once."""
        import torch

        all_texts: list[str] = []
        idx_map: list[int] = []
        for i, (_, prompts) in enumerate(EMOTION_PROMPTS.items()):
            for p in prompts:
                all_texts.append(p)
                idx_map.append(i)

        raw_inputs = self._processor(
            text=all_texts, return_tensors="pt", padding=True,
        )
        # Pass only text-relevant keys to avoid audio-key collisions
        text_keys = {k: v.to(self._device) for k, v in raw_inputs.items()
                     if k in ("input_ids", "attention_mask", "token_type_ids", "position_ids")}
        with torch.no_grad():
            embs = self._model.get_text_features(**text_keys)
        # Transformers ≥5.x may wrap the result in a model output object
        if not isinstance(embs, torch.Tensor):
            for attr in ("text_embeds", "pooler_output"):
                candidate = getattr(embs, attr, None)
                if candidate is not None and isinstance(candidate, torch.Tensor):
                    embs = candidate
                    break
            else:
                embs = embs[0]
        embs = embs / embs.norm(dim=-1, keepdim=True)
        self._text_embs = embs.cpu().float().numpy()          # (n_prompts, dim)
        self._prompt_label_idx = np.array(idx_map, dtype=np.int32)

    # ------------------------------------------------------------------
    def _load_audio(self, audio_path: str) -> Optional[np.ndarray]:
        import librosa
        try:
            dur = librosa.get_duration(path=audio_path)
        except Exception:
            dur = 180.0
        offset = min(30.0, max(0.0, dur * 0.15))
        for off in (offset, 0.0):
            try:
                y, _ = librosa.load(
                    audio_path, sr=self._sr, mono=True,
                    offset=off, duration=self._clip_dur,
                )
                if len(y) >= 1024:
                    return y
            except Exception:
                pass
        logger.warning(f"[CLAP] audio load failed: {audio_path}")
        return None

    def _audio_to_label_scores(self, y: np.ndarray) -> Optional[np.ndarray]:
        """Return (n_labels,) cosine-similarity scores."""
        import torch
        try:
            raw_inputs = self._processor(
                audio=y, sampling_rate=self._sr, return_tensors="pt",
            )
            audio_keys = {k: v.to(self._device) for k, v in raw_inputs.items()
                          if k in ("input_features", "attention_mask", "is_longer")}
            with torch.no_grad():
                audio_emb = self._model.get_audio_features(**audio_keys)
            if not isinstance(audio_emb, torch.Tensor):
                for attr in ("audio_embeds", "pooler_output"):
                    candidate = getattr(audio_emb, attr, None)
                    if candidate is not None and isinstance(candidate, torch.Tensor):
                        audio_emb = candidate
                        break
                else:
                    audio_emb = audio_emb[0]
            audio_emb = audio_emb / audio_emb.norm(dim=-1, keepdim=True)
            audio_np = audio_emb.cpu().float().numpy()[0]     # (dim,)
            sims = self._text_embs @ audio_np                 # (n_prompts,)
            n_labels = len(self._labels)
            scores = np.zeros(n_labels, dtype=np.float32)
            for i in range(n_labels):
                mask = self._prompt_label_idx == i
                scores[i] = sims[mask].max()
            return scores
        except Exception as e:
            logger.warning(f"[CLAP] inference error: {e}")
            return None

    # ------------------------------------------------------------------
    def predict(self, audio_path: str) -> Optional[str]:
        """Return dominant emotion label (e.g. 'calm'), or None on failure."""
        self._load()
        y = self._load_audio(audio_path)
        if y is None:
            return None
        scores = self._audio_to_label_scores(y)
        if scores is None:
            return None
        return self._labels[int(np.argmax(scores))]

    def predict_probs(self, audio_path: str) -> Optional[Dict[str, float]]:
        """Return softmax probability dict over all 8 emotion labels."""
        self._load()
        y = self._load_audio(audio_path)
        if y is None:
            return None
        scores = self._audio_to_label_scores(y)
        if scores is None:
            return None
        exp_s = np.exp(scores - scores.max())
        probs = exp_s / exp_s.sum()
        return {lbl: float(p) for lbl, p in zip(self._labels, probs)}
