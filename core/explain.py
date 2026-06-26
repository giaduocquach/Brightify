"""Per-recommendation "why" explanations + colour→emotion bridge.
Pure JSON-safe formatters extracted from MusicRecommender (behaviour-preserving).
The recommender passes its arrays + the colour mapper + the emotion-VI map in
(no engine/config import → one-directional)."""
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


def build_song_why(results, *, seed_emotion, seed_va, seed_tempo, emo_vi):
    """Per-rec "why this song" for recommend-by-song.

    Honest about the fusion: similarity is audio-dominant (MuQ 0.76) + V-A mood (0.16)
    + lyrics (0.08), so the primary signal is always acoustic; mood-match and tempo
    proximity are surfaced when they corroborate. `results` is the result DataFrame
    (has fused_emotion / valence / arousal / tempo / similarity_score per row)."""
    import numpy as np
    sv, sa = (float(seed_va[0]), float(seed_va[1])) if seed_va is not None else (None, None)
    se = (str(seed_emotion).lower() if seed_emotion else '')
    out = []
    for _, row in results.iterrows():
        emo = row.get('fused_emotion')
        emo = '' if (emo is None or pd.isna(emo)) else str(emo).lower()
        same_mood = bool(emo) and emo == se
        reason = 'Chất âm (giai điệu, hoà âm) tương đồng với bài gốc'
        if same_mood:
            reason = f"Chất âm tương đồng và cùng tâm trạng ({emo_vi.get(emo, emo)})"
        why = {
            'reason': reason,
            'top_signal': 'audio',
            'similarity': round(float(row.get('similarity_score', 0.0)), 3),
            'same_mood': same_mood,
            'song_emotion': emo,
            'song_emotion_vi': emo_vi.get(emo, emo),
        }
        # Tempo proximity (display only) when both BPMs are known.
        st = row.get('tempo')
        if seed_tempo is not None and st is not None and not pd.isna(st) and not pd.isna(seed_tempo):
            why['tempo_delta'] = round(abs(float(st) - float(seed_tempo)), 1)
        if sv is not None:
            rv, ra = row.get('valence'), row.get('arousal')
            if rv is not None and ra is not None and not pd.isna(rv) and not pd.isna(ra):
                why['mood_match'] = round(float(np.exp(-0.5 * (
                    ((float(rv) - sv) / 0.22) ** 2 + ((float(ra) - sa) / 0.14) ** 2))), 3)
        out.append(why)
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
