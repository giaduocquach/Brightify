---
name: vietnamese-nlp
description: Guide for working with Vietnamese NLP in Brightify. Use when modifying emotion analysis, lyrics processing, PhoBERT embeddings, or Vietnamese text handling.
user-invocable: false
---

# Vietnamese NLP Conventions

## Word Segmentation
Vietnamese requires word segmentation before tokenization. Multi-syllable words are separated by spaces in written Vietnamese but form single semantic units.

```python
from pyvi import ViTokenizer
# "Hôm nay trời đẹp quá" → "Hôm_nay trời đẹp quá"
segmented = ViTokenizer.tokenize(text)
```

Always segment before PhoBERT:
```python
segmented_text = ViTokenizer.tokenize(raw_lyrics)
tokens = phobert_tokenizer(segmented_text, max_length=512, truncation=True)
```

## Emotion Lexicon
- Located in `core/emotion_analysis.py` → `VietnameseEmotionLexicon`
- 730+ words across 13 emotion categories
- Includes: Gen-Z slang (iu, sad, flex), Southern variants (vui ghê, buồn hết sức), loanwords
- Emotion categories: happiness, sadness, anger, fear, surprise, disgust, love, hope, nostalgia, loneliness, pride, gratitude, calm

## Vietnamese Text Normalization
- Handle diacritics: à, á, ả, ã, ạ (5 tones per vowel)
- Lowercase before processing
- Remove extra whitespace
- Handle common abbreviations: k (không), dc (được), r (rồi)

## PhoBERT Notes
- Model: `vinai/phobert-base` (config.py: PHOBERT_MODEL)
- Max sequence length: 512 tokens
- Output: 768-dimensional embeddings
- Batch size: 32 (configurable in config.py)
- Vietnamese BPE tokenizer — handles syllable structure natively

## Emotion-Valence Mapping
Russell's Circumplex coordinates for each emotion:
- happiness → high valence, high arousal
- sadness → low valence, low arousal
- anger → low valence, high arousal
- calm → moderate valence, low arousal
- love → high valence, moderate arousal
