"""Pillar C — Cross-encoder reranker (lazy singleton).

Uses sentence-transformers CrossEncoder for two-stage retrieval:
  Stage 1: Fast approximate retrieval (BM25 / embedding ANN)
  Stage 2: Cross-encoder rescores top candidates with full query-document attention.

Model default: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
  — Multilingual MiniLM-v2 fine-tuned on MS-MARCO (26 languages incl. Vietnamese).
  — 12 layers, 384 hidden, ~66M params; fast on CPU.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from loguru import logger

_reranker_instance: Optional["CrossEncoderReranker"] = None


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers.cross_encoder import CrossEncoder
        self.model = CrossEncoder(model_name, max_length=256)
        self.model_name = model_name

    def rerank(
        self,
        query: str,
        passages: List[str],
        indices: List[int],
        top_k: int,
    ) -> List[int]:
        """
        Score (query, passage) pairs; return top_k original indices reranked.

        Args:
            query: search query text.
            passages: one text per candidate (track_name + lyrics snippet).
            indices: original dataset indices corresponding to passages.
            top_k: number of results to return.

        Returns:
            Subset of `indices`, reordered by cross-encoder score.
        """
        if not passages:
            return indices[:top_k]
        pairs = [(query, p) for p in passages]
        scores = self.model.predict(pairs, show_progress_bar=False)
        order = np.argsort(scores)[::-1][:top_k]
        return [indices[i] for i in order]


def get_reranker(model_name: str) -> Optional[CrossEncoderReranker]:
    """Return the cached reranker singleton; load on first call, return None on failure."""
    global _reranker_instance
    if _reranker_instance is None:
        try:
            _reranker_instance = CrossEncoderReranker(model_name)
            logger.info(f"[Reranker] Loaded {model_name}")
        except Exception as e:
            logger.warning(f"[Reranker] Failed to load {model_name}: {e} — reranking disabled")
    return _reranker_instance
