"""Per-recommendation "why" explanations + colour→emotion bridge.
Pure JSON-safe formatters extracted from MusicRecommender (behaviour-preserving).
The recommender passes its arrays + the colour mapper + the emotion-VI map in
(no engine/config import → one-directional)."""
import numpy as np
import pandas as pd


def build_color_why(original_indices, cva, va_s, src_hex, *, song_va, fused_emotion, emo_vi):
    """Per-rec "why this song" for recommend-by-color (V-A-only scorer → mood closeness).
    `fused_emotion`: the df['fused_emotion'] Series, or None if the column is absent."""
    cval, caro = float(cva[0]), float(cva[1])
    _has_fe = fused_emotion is not None
    out = []
    for i in original_indices:
        i = int(i)
        sv, sa = float(song_va[i, 0]), float(song_va[i, 1])
        song_emo = ''
        if _has_fe:
            _fe = fused_emotion.iloc[i]
            song_emo = '' if pd.isna(_fe) else str(_fe).lower()
        va_match = round(float(va_s[i]), 3)
        song_emo_vi = emo_vi.get(song_emo, song_emo)
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


def build_similar_why(seed_idx, rec_indices, *, song_va, mert_matrix, lyrics_emb,
                      fused_emotion, emo_vi, sigma_v, sigma_a):
    """Per-rec "why this song" for recommend_by_song (audio / mood / lyrics signals)."""
    _sv = sigma_v
    _sa = sigma_a
    _has_fe = fused_emotion is not None

    seed_emo = ''
    if _has_fe:
        _fe = fused_emotion.iloc[seed_idx]
        seed_emo = '' if pd.isna(_fe) else str(_fe).lower()

    seed_mert = mert_matrix[seed_idx] if mert_matrix is not None else None
    seed_lyrics = lyrics_emb[seed_idx] if lyrics_emb is not None else None
    seed_va = song_va[seed_idx]

    out = []
    for i in rec_indices:
        i = int(i)

        mert_score = 0.5
        if seed_mert is not None:
            raw = float(mert_matrix[i] @ seed_mert)
            mert_score = round((raw + 1.0) / 2.0, 3)   # [-1,1] → [0,1]

        dv = float(song_va[i, 0] - seed_va[0])
        da = float(song_va[i, 1] - seed_va[1])
        va_score = round(float(np.exp(-0.5 * ((dv / _sv)**2 + (da / _sa)**2))), 3)

        lyrics_score = 0.5
        if seed_lyrics is not None:
            raw_l = float(lyrics_emb[i] @ seed_lyrics)
            lyrics_score = round((raw_l + 1.0) / 2.0, 3)

        rec_emo = ''
        if _has_fe:
            _fe2 = fused_emotion.iloc[i]
            rec_emo = '' if pd.isna(_fe2) else str(_fe2).lower()

        seed_emo_vi = emo_vi.get(seed_emo, seed_emo)
        rec_emo_vi = emo_vi.get(rec_emo, rec_emo)

        same_mood = (seed_emo and rec_emo and seed_emo == rec_emo)
        if mert_score >= 0.95:
            if same_mood:
                reason = f"Âm nhạc rất gần — cùng tâm trạng {rec_emo_vi or ''} và chất nhạc"
            else:
                reason = "Âm nhạc rất tương đồng (timbre, nhịp điệu, hòa âm)"
            top_signal = "audio"
        elif va_score >= 0.70 and same_mood:
            reason = f"Cùng tâm trạng {rec_emo_vi or ''} và phong cách âm nhạc tương tự"
            top_signal = "mood"
        elif mert_score >= 0.90:
            reason = "Phong cách âm nhạc tương tự — cùng thể loại và cảm giác"
            top_signal = "audio"
        elif lyrics_score >= 0.85 and mert_score >= 0.88:
            reason = "Cùng phong cách nhạc và chủ đề lời bài hát"
            top_signal = "audio+lyrics"
        else:
            reason = "Âm nhạc và tâm trạng tương tự"
            top_signal = "audio"

        out.append({
            'reason':        reason,
            'top_signal':    top_signal,
            'audio_score':   mert_score,
            'mood_score':    va_score,
            'lyrics_score':  lyrics_score,
            'seed_emotion':  seed_emo,
            'seed_emotion_vi': seed_emo_vi,
            'song_emotion':  rec_emo,
            'song_emotion_vi': rec_emo_vi,
            'same_mood':     same_mood,
        })
    return out


def build_bridge(color_hexes, color_mapper, emo_vi):
    """Colour→emotion bridge for UI display (no song matching). For each colour: its
    inferred top emotion (CLAP label + Vietnamese name) and V-A point."""
    if isinstance(color_hexes, str):
        color_hexes = [color_hexes]
    bridge = []
    for color in list(color_hexes)[:3]:
        try:
            v, a = color_mapper.hsl_to_va(color)
            probs = color_mapper.color_to_emotion_probs(color)
            top = max(probs.items(), key=lambda x: x[1])[0]
            bridge.append({
                'hex': color,
                'emotion': top,
                'emotion_vi': emo_vi.get(top, top),
                'valence': round(float(v), 2),
                'arousal': round(float(a), 2),
            })
        except (ValueError, KeyError, TypeError):
            continue
    return bridge
