"""Lazy-loading singleton for query encoding via multilingual-e5-large (FP16).

Loads in a background daemon thread so startup is non-blocking.
Call `preload_background()` once at startup; check `is_ready` before
`encode_query`. Falls back gracefully to text-only search on failure.
"""

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_INSTANCE: Optional["SearchEncoder"] = None
_INSTANCE_LOCK = threading.Lock()


class SearchEncoder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._ready = threading.Event()
        self._model = None
        self._tokenizer = None
        self._rw_lock = threading.Lock()

    def preload_background(self) -> None:
        t = threading.Thread(target=self._load, daemon=True, name="search-encoder-load")
        t.start()

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            logger.info("SearchEncoder: loading %s (FP16)…", self._model_name)
            tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            model = AutoModel.from_pretrained(self._model_name, torch_dtype=torch.float16)
            model.eval()

            with self._rw_lock:
                self._tokenizer = tokenizer
                self._model = model

            self._ready.set()
            logger.info("SearchEncoder: ready — semantic search enabled")
        except Exception as exc:
            logger.warning(
                "SearchEncoder: load failed (%s) — semantic search disabled", exc
            )

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def encode_query(self, text: str) -> Optional[np.ndarray]:
        """Return L2-normalized 1024-dim query embedding, or None if not ready."""
        if not self.is_ready:
            return None
        try:
            import torch

            with self._rw_lock:
                tok = self._tokenizer
                mdl = self._model

            # Match the index geometry built by tools/encode_lyrics.py exactly:
            # "query: " prefix, attention-masked mean-pool, L2-normalize, max_len=256.
            prefixed = f"query: {text}"
            with torch.no_grad():
                inputs = tok(
                    [prefixed],
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=256,
                )
                hidden = mdl(**inputs).last_hidden_state            # (1, T, 1024)
                mask = inputs["attention_mask"].unsqueeze(-1).float()  # (1, T, 1)
                emb = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)  # masked mean
                emb = torch.nn.functional.normalize(emb, p=2, dim=1)
            return emb[0].cpu().float().numpy()  # (1024,) float32
        except Exception as exc:
            logger.warning("SearchEncoder.encode_query failed: %s", exc)
            return None


def get_search_encoder() -> "SearchEncoder":
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                import config as cfg
                _INSTANCE = SearchEncoder(cfg.LYRICS_EMBED_MODEL)
    return _INSTANCE
