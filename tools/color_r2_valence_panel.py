"""R2 — Decoupled valence validation panel (V27 updated).

Problem: valence labels = Gemini-only; risk of Gemini judge circularity
  (Kriegeskorte 2009 double-dipping). Current corroboration: XLM-R ρ=0.263 (weak).

This tool builds a panel from independent signals (priority: most to least informative):
  1. NRC-VAD lexicon (EACL 2024; word-level valence, 109 langs incl VN) — if available
     at var/data/nrc_vad_lexicon.txt. Download free from saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm
  2. Major-minor mode score (var/runtime/features/mode_scores.json) — if extracted
  3. sentiment_compound / sentiment_positive - sentiment_negative (fallback)

Panel vs Gemini agreement: Spearman ρ, Pearson r.
Mismatch log: songs where |panel - gemini_valence| > 0.30 → candidates for review.

Calibration gate: only update valence labels if color_eval_rigor TE improves
under artist-grouped nested CV. Otherwise: report for human review.

Run: python -m tools.color_r2_valence_panel [--save-mismatches]
"""
import json, os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_REPORT   = "var/runtime/backtest/reports/color_r2_valence_panel.json"
OUT_MISMATCH = "var/runtime/backtest/reports/color_r2_mismatch_songs.json"
MISMATCH_THRESHOLD = 0.30  # |panel - valence| > this → flagged
NRC_VAD_PATH = "var/data/nrc_vad_lexicon.txt"
MODE_SCORES_PATH = "var/runtime/features/mode_scores.json"
MERT_VALENCE_PATH = "data/mert_valence.json"

os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
os.makedirs("var/data", exist_ok=True)


def _load_nrc_vad(path: str) -> dict:
    """Load NRC-VAD-Lexicon.txt → {word: valence_score [0,1]}.

    Expected format (tab-separated):
      Word  Valence  Arousal  Dominance
    Valence column normalized to [0,1] in the lexicon.
    """
    lexicon = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('Word'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    word = parts[0].lower().strip()
                    try:
                        val = float(parts[1])
                        lexicon[word] = val
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return lexicon


def _nrc_vad_score(lyrics: str, lexicon: dict) -> float:
    """Mean NRC-VAD valence over matched words. Returns NaN if no match."""
    if not lexicon or not isinstance(lyrics, str):
        return float('nan')
    tokens = lyrics.lower().split()
    scores = [lexicon[t] for t in tokens if t in lexicon]
    return float(np.mean(scores)) if scores else float('nan')


def _normalize_to_01(x: np.ndarray, percentile_clip: float = 1.0) -> np.ndarray:
    """Robust min-max normalisation with percentile clipping."""
    lo = np.percentile(x, percentile_clip)
    hi = np.percentile(x, 100 - percentile_clip)
    if hi <= lo:
        return np.full_like(x, 0.5, dtype=float)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0).astype(float)


def build_panel_score(df) -> tuple:
    """Build valence_panel [0,1] from independent signals. Returns (panel, signal_names).

    Priority: NRC-VAD > mode_score > sentiment (all available signals are averaged).
    """
    signals = []
    signal_names = []

    # 1. NRC-VAD zero-shot (highest quality if lexicon available)
    nrc_lexicon = _load_nrc_vad(NRC_VAD_PATH)
    if nrc_lexicon:
        lyrics_col = next((c for c in ['lyrics', 'lyrics_cleaned', 'lyrics_clean', 'lyric', 'plain_lyrics'] if c in df.columns), None)
        if lyrics_col:
            nrc_scores = np.array([
                _nrc_vad_score(str(row), nrc_lexicon)
                for row in df[lyrics_col].fillna('')
            ])
            valid = np.isfinite(nrc_scores)
            if valid.sum() > 50:
                nrc_norm = _normalize_to_01(np.where(valid, nrc_scores, np.nanmedian(nrc_scores)))
                signals.append(nrc_norm)
                signal_names.append(f'nrc_vad ({valid.sum()} matched)')

    # 2. MERT-valence probe (A1.3, V27; audio-derived, zero annotation)
    if os.path.exists(MERT_VALENCE_PATH):
        with open(MERT_VALENCE_PATH) as f:
            mert_dict = json.load(f)
        if 'track_id' in df.columns and len(mert_dict) > 100:
            mert_arr = np.array([mert_dict.get(str(tid), np.nan) for tid in df['track_id']])
            valid = np.isfinite(mert_arr)
            if valid.sum() > 100:
                mert_norm = _normalize_to_01(np.where(valid, mert_arr, np.nanmedian(mert_arr)))
                signals.append(mert_norm)
                signal_names.append(f'mert_valence ({valid.sum()} tracks)')

    # 3. Major-minor mode score (audio-derived, zero annotation)
    if os.path.exists(MODE_SCORES_PATH):
        with open(MODE_SCORES_PATH) as f:
            mode_dict = json.load(f)
        if 'track_id' in df.columns and len(mode_dict) > 100:
            mode_arr = np.array([mode_dict.get(tid, np.nan) for tid in df['track_id']])
            valid = np.isfinite(mode_arr)
            if valid.sum() > 100:
                mode_norm = _normalize_to_01(np.where(valid, mode_arr, np.nanmedian(mode_arr)))
                signals.append(mode_norm)
                signal_names.append(f'mode_score ({valid.sum()} tracks)')

    # 4. Sentiment compound / pos-neg (fallback)
    if 'sentiment_compound' in df.columns:
        sc = df['sentiment_compound'].values.astype(float)
        signals.append(_normalize_to_01(sc))
        signal_names.append('sentiment_compound')
    if 'sentiment_positive' in df.columns and 'sentiment_negative' in df.columns:
        pn = (df['sentiment_positive'].values - df['sentiment_negative'].values).astype(float)
        signals.append(_normalize_to_01(pn))
        signal_names.append('sentiment_pos-neg')

    if not signals:
        return np.full(len(df), np.nan), []

    panel = np.mean(signals, axis=0)
    return panel, signal_names


def compute_agreement(panel: np.ndarray, gemini_valence: np.ndarray) -> dict:
    from scipy.stats import spearmanr, pearsonr
    mask = np.isfinite(panel) & np.isfinite(gemini_valence)
    n = mask.sum()
    if n < 10:
        return {'error': f'Too few valid pairs ({n})'}
    rho, p_rho = spearmanr(panel[mask], gemini_valence[mask])
    pear, p_pear = pearsonr(panel[mask], gemini_valence[mask])
    mae = float(np.mean(np.abs(panel[mask] - gemini_valence[mask])))
    return {
        'n_valid': int(n),
        'spearman_rho': round(float(rho), 4),
        'spearman_p': round(float(p_rho), 6),
        'pearson_r': round(float(pear), 4),
        'mae': round(mae, 4),
        'baseline_xlmr_rho': 0.263,
        'improvement_over_baseline': float(rho) > 0.263,
    }


def find_mismatches(df, panel: np.ndarray, gemini_valence: np.ndarray,
                    threshold: float = MISMATCH_THRESHOLD) -> list[dict]:
    """Return songs with large panel↔Gemini disagreement."""
    mismatches = []
    for i in range(len(df)):
        if not (np.isfinite(panel[i]) and np.isfinite(gemini_valence[i])):
            continue
        diff = abs(float(panel[i]) - float(gemini_valence[i]))
        if diff > threshold:
            row = df.iloc[i]
            mismatches.append({
                'index': int(i),
                'track_name': str(row.get('track_name', '')),
                'artists': str(row.get('artists', '')),
                'panel_valence': round(float(panel[i]), 3),
                'gemini_valence': round(float(gemini_valence[i]), 3),
                'diff': round(diff, 3),
                'fused_emotion': str(row.get('fused_emotion', '')),
            })
    return sorted(mismatches, key=lambda x: -x['diff'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save-mismatches', action='store_true')
    args, _ = parser.parse_known_args()

    from core.recommendation_engine import get_recommender
    print("Loading catalog...")
    rec = get_recommender()
    df  = rec.df

    print(f"Catalog: {rec.n_songs} songs\n")

    panel, signal_names = build_panel_score(df)
    gemini_valence = df['valence'].values.astype(float)

    agreement = compute_agreement(panel, gemini_valence)
    mismatches = find_mismatches(df, panel, gemini_valence)

    print("=" * 60)
    print("R2 VALENCE PANEL — DECOUPLED CORROBORATION")
    print("=" * 60)
    print(f"Panel signals: {' + '.join(signal_names) if signal_names else 'none'}")
    print(f"Independence: NO Gemini involvement in sentiment computation\n")

    if 'error' in agreement:
        print(f"ERROR: {agreement['error']}")
    else:
        print(f"Panel vs Gemini valence:")
        print(f"  Spearman ρ = {agreement['spearman_rho']:.4f}  "
              f"(p={agreement['spearman_p']:.4g})")
        print(f"  Pearson  r = {agreement['pearson_r']:.4f}")
        print(f"  MAE        = {agreement['mae']:.4f}")
        print(f"  Baseline (XLM-R alone): ρ = {agreement['baseline_xlmr_rho']}")
        imp = agreement['improvement_over_baseline']
        print(f"  Improvement over baseline: {'YES ✓' if imp else 'NO ✗'}")
        print()
        if imp:
            print("  → Calibration candidate: run color_eval_rigor under nested CV")
            print("    to confirm TE improvement before updating valence labels.")
        else:
            print("  → Panel weaker than current XLM-R baseline.")
            print("    Recommendation: keep Gemini valence; use mismatch log for")
            print("    targeted human review of flagged songs.")

    n_mismatch = len(mismatches)
    pct = 100 * n_mismatch / rec.n_songs
    print(f"\nMismatches |panel - gemini| > {MISMATCH_THRESHOLD}: "
          f"{n_mismatch} songs ({pct:.1f}%)")
    if mismatches:
        print("\nTop 10 most disagreeing songs:")
        for m in mismatches[:10]:
            direction = ('panel_high' if m['panel_valence'] > m['gemini_valence']
                         else 'panel_low')
            print(f"  {m['track_name'][:30]:30} | {m['artists'][:20]:20} | "
                  f"panel={m['panel_valence']:.2f} gem={m['gemini_valence']:.2f} "
                  f"Δ={m['diff']:.2f} ({direction})")

    rho = agreement.get('spearman_rho', 0)
    beats_baseline = isinstance(rho, float) and rho > 0.263
    print()
    print("=" * 60)
    if beats_baseline:
        print("VERDICT: IMPROVED — panel beats XLM-R baseline (ρ=0.263)")
        print(f"  Panel ρ = {rho:.4f} > 0.263  Next: nested CV gate to confirm TE")
    else:
        print("VERDICT: DIAGNOSTIC ONLY — not replacing Gemini valence")
        print(f"  Panel ρ = {rho:.4f} ≤ 0.263 (XLM-R baseline)")
        print(f"  Gate: TE improvement under nested CV required to update labels")
    print("=" * 60)

    out = {
        'panel_signals': signal_names,
        'independence': 'No Gemini involvement in panel pipeline',
        'agreement': agreement,
        'n_mismatches': n_mismatch,
        'mismatch_threshold': MISMATCH_THRESHOLD,
        'verdict': 'diagnostic_only',
        'action': 'keep_gemini_valence',
        'top_10_mismatches': mismatches[:10],
    }

    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nsaved → {OUT_REPORT}")

    if args.save_mismatches and mismatches:
        with open(OUT_MISMATCH, 'w', encoding='utf-8') as f:
            json.dump(mismatches, f, indent=2, ensure_ascii=False)
        print(f"saved → {OUT_MISMATCH} ({len(mismatches)} songs)")


if __name__ == "__main__":
    main()
