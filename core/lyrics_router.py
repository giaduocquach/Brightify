"""Lyrics style detector + encoder router for Pillar B (ViDeBERTa / ViSoBERT).

Heuristic routing per PLAN_SYSTEM_UPGRADE §4.3 Step 2:
  'social'   → uitnlp/visobert       (trained on social-media Vietnamese)
  'standard' → Fsoft-AIC/videberta-base  (DeBERTa arch, stronger Vietnamese NLP)

PhoBERT (vinai/phobert-base-v2) is the default when ENABLE_PILLAR_B=False.

Key difference vs PhoBERT: ViDeBERTa and ViSoBERT use their own SentencePiece
tokenizers — do NOT apply ViTokenizer.tokenize() before encoding with them.
"""

from __future__ import annotations

import unicodedata
from typing import Optional

# Tokens strongly associated with social-media / teen Vietnamese writing.
_TEEN_TOKENS = (
    'ko ', ' ko', '\nko', ' k ', '\nk ', 'dc ', ' dc', ' oki', 'ny ',
    ' fan', '<3', 'huhu', 'hihi', 'haha', 'hehe', 'ehe',
    ':)', ':-)', ':D', 'xd', ':((', 'tks ', ' tq ', ' mk ', ' bh ',
    ' đc ', 'thik ', ' nh ', ' cx ', ' vkl', 'vcl',
)


def detect_lyrics_style(text: str) -> str:
    """Return 'social' for teen/social-media lyrics, 'standard' otherwise.

    Classification threshold: > 3 teen tokens OR any emoji present.
    Matches ViSoBERT's training domain (UIT-ViSoSWE, social media corpus).
    """
    if not text:
        return "standard"
    lower = text.lower()
    count = sum(1 for tok in _TEEN_TOKENS if tok in lower)
    if count > 3 or _has_emoji(text):
        return "social"
    return "standard"


def _has_emoji(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        cat = unicodedata.category(ch)
        if cat in ("So", "Sm") or 0x1F000 <= cp <= 0x1FFFF or 0x2600 <= cp <= 0x27BF:
            return True
    return False


def get_encoder_name(text: str, base_encoder: str = "phobert") -> str:
    """Return the model key to use for a given lyrics string.

    When base_encoder is 'phobert' (default), always returns 'phobert'.
    When base_encoder is 'videberta' (Pillar B routing mode), returns
    'visobert' for social content or 'videberta' for standard content.

    Args:
        text: raw or cleaned lyrics string.
        base_encoder: config value (from LYRICS_ENCODER or 'phobert').
    """
    if base_encoder == "phobert":
        return "phobert"
    style = detect_lyrics_style(text)
    return "visobert" if style == "social" else "videberta"


def coverage_stats(lyrics_list: list[str]) -> dict:
    """Return routing coverage statistics for a lyrics corpus.

    Returns:
        {'total': N, 'social': M, 'social_pct': M/N*100, 'standard': N-M, ...}
    """
    total = len(lyrics_list)
    social = sum(1 for t in lyrics_list if detect_lyrics_style(t) == "social")
    return {
        "total": total,
        "social": social,
        "social_pct": round(social / total * 100, 1) if total else 0.0,
        "standard": total - social,
        "standard_pct": round((total - social) / total * 100, 1) if total else 0.0,
    }
