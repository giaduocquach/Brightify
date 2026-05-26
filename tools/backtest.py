"""
Backtest evaluation module for Brightify recommendation system.

Implements 10 evaluation metrics covering accuracy, diversity, coverage,
consistency, and performance. Based on standard IR/RecSys evaluation
methodology (Herlocker et al. 2004, Shani & Gunawardana 2011).

Usage:
    from tools.backtest import RecommendationEvaluator, sanitize_for_json
    evaluator = RecommendationEvaluator(recommender)
    report = evaluator.precision_at_k_by_quadrant(top_k=10)
"""

import time
import math
import numpy as np
import pandas as pd
from itertools import product

from config import (
    MOOD_QUADRANTS, MOOD_KEYWORDS,
    WEIGHTS_COLOR_QUERY_WITH_LYRICS,
    DIVERSITY_PENALTY, MIN_SIMILARITY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------

def sanitize_for_json(obj):
    """Convert numpy/pandas types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return sanitize_for_json(obj.to_dict())
    if isinstance(obj, pd.DataFrame):
        return sanitize_for_json(obj.to_dict(orient='records'))
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


# ---------------------------------------------------------------------------
# Test colour palettes for each mood quadrant
# ---------------------------------------------------------------------------

# Representative hex colours per quadrant (derived from emotion_color_profiles)
_QUADRANT_COLORS = {
    'Q1': ['#FFD700', '#FFA500', '#FFEB3B', '#FF9800', '#F4C430'],  # Yellow/Orange — happy/excited
    'Q2': ['#FF0000', '#CC0000', '#B22222', '#DC143C', '#8B0000'],  # Red — angry/tense
    'Q3': ['#1E3A5F', '#2C3E7B', '#2E4057', '#1B2A4A', '#3B4D6B'],  # Dark Blue — sad
    'Q4': ['#90EE90', '#7EC8E3', '#A8D8EA', '#87CEEB', '#B2DFDB'],  # Light Blue/Green — calm
}


class RecommendationEvaluator:
    """Evaluate the Brightify recommendation engine across 10 metrics."""

    def __init__(self, recommender):
        self.rec = recommender
        self.n_songs = len(recommender.df)
        self.df = recommender.df
        self._rng = np.random.RandomState(42)

    # -----------------------------------------------------------------------
    # 1. Precision@K by mood quadrant
    # -----------------------------------------------------------------------

    def precision_at_k_by_quadrant(self, top_k=10):
        """
        For each mood quadrant, use representative colours to query,
        then measure what fraction of returned songs belong to the
        expected quadrant (by V-A position).

        Returns:
            dict with per-quadrant precision and weighted average.
        """
        results = {}
        total_precision = 0.0
        total_queries = 0

        for qname, qinfo in MOOD_QUADRANTS.items():
            v_lo, v_hi = qinfo['valence']
            e_lo, e_hi = qinfo['energy']
            colors = _QUADRANT_COLORS.get(qname, ['#808080'])

            q_precisions = []
            for color in colors:
                recs = self.rec.recommend_by_colors([color], top_k=top_k)
                if recs.empty:
                    continue
                # Check how many recs fall in the expected quadrant
                hits = 0
                for _, row in recs.iterrows():
                    idx = int(row.get('original_index', 0))
                    v, a = self.rec.song_va[idx]
                    if v_lo <= v <= v_hi and e_lo <= a <= e_hi:
                        hits += 1
                q_precisions.append(hits / len(recs))

            avg_prec = float(np.mean(q_precisions)) if q_precisions else 0.0
            results[qname] = {
                'name': qinfo['name'],
                'precision': round(avg_prec, 4),
                'n_queries': len(q_precisions),
            }
            total_precision += avg_prec
            total_queries += 1

        avg = round(total_precision / max(total_queries, 1), 4)
        return {
            'per_quadrant': results,
            'average_precision': avg,
            'interpretation': _rate(avg, 0.3, 0.5, 0.7),
        }

    # -----------------------------------------------------------------------
    # 2. nDCG@K (Normalised Discounted Cumulative Gain)
    # -----------------------------------------------------------------------

    def ndcg_at_k(self, top_k=10):
        """
        Sample random songs, recommend similar ones, and use V-A proximity
        as the ground-truth relevance score.  Measure how well the engine
        ranks the most relevant songs near the top.

        Returns:
            dict with average nDCG and per-sample details.
        """
        n_samples = min(50, self.n_songs)
        sample_ids = self._rng.choice(self.n_songs, n_samples, replace=False)
        ndcgs = []

        for sid in sample_ids:
            recs = self.rec.recommend_by_song(int(sid), top_k=top_k)
            if recs.empty:
                continue

            # Relevance = exp(-VA_distance) so closer songs = higher relevance
            query_va = self.rec.song_va[sid]
            rels = []
            for _, row in recs.iterrows():
                idx = int(row.get('original_index', 0))
                dist = np.sqrt(np.sum((self.rec.song_va[idx] - query_va) ** 2))
                rels.append(np.exp(-dist * 3))

            dcg = sum(r / np.log2(i + 2) for i, r in enumerate(rels))
            ideal = sorted(rels, reverse=True)
            idcg = sum(r / np.log2(i + 2) for i, r in enumerate(ideal))
            ndcgs.append(dcg / idcg if idcg > 0 else 0.0)

        avg_ndcg = float(np.mean(ndcgs)) if ndcgs else 0.0
        return {
            'average_ndcg': round(avg_ndcg, 4),
            'n_samples': len(ndcgs),
            'std': round(float(np.std(ndcgs)), 4) if ndcgs else 0.0,
            'interpretation': _rate(avg_ndcg, 0.5, 0.7, 0.85),
        }

    # -----------------------------------------------------------------------
    # 3. Emotional Coherence
    # -----------------------------------------------------------------------

    def emotional_coherence(self, top_k=10):
        """
        For multiple colour queries, measure how tight the recommended
        songs' V-A values cluster around the query centroid.
        Lower spread = more coherent.

        Returns:
            dict with average coherence score (1 = perfectly coherent).
        """
        all_colors = [c for colors in _QUADRANT_COLORS.values() for c in colors]
        coherences = []

        for color in all_colors:
            recs = self.rec.recommend_by_colors([color], top_k=top_k)
            if recs.empty:
                continue

            # Query V-A (color_to_valence_arousal returns (v, a, confidence))
            va_tuple = self.rec.color_mapper.color_to_valence_arousal(color)
            qva = np.array([va_tuple[0], va_tuple[1]])

            # Rec V-A
            rec_vas = []
            for _, row in recs.iterrows():
                idx = int(row.get('original_index', 0))
                rec_vas.append(self.rec.song_va[idx])
            rec_vas = np.array(rec_vas)

            # Coherence = 1 - avg_distance_to_query (capped at 1)
            dists = np.sqrt(np.sum((rec_vas - qva) ** 2, axis=1))
            coherence = max(0.0, 1.0 - float(np.mean(dists)))
            coherences.append(coherence)

        avg = float(np.mean(coherences)) if coherences else 0.0
        return {
            'average_coherence': round(avg, 4),
            'n_queries': len(coherences),
            'std': round(float(np.std(coherences)), 4) if coherences else 0.0,
            'interpretation': _rate(avg, 0.4, 0.6, 0.8),
        }

    # -----------------------------------------------------------------------
    # 4. Intra-list Diversity
    # -----------------------------------------------------------------------

    def intra_list_diversity(self, top_k=10):
        """
        Measure diversity within recommendation lists:
        - Artist diversity: unique artists / list size
        - Emotion diversity: unique emotions / list size
        - Audio spread: std of audio features across recommendations

        Returns:
            dict with artist, emotion, and audio diversity metrics.
        """
        all_colors = [c for colors in _QUADRANT_COLORS.values() for c in colors]
        artist_divs = []
        emotion_divs = []
        audio_spreads = []

        for color in all_colors:
            recs = self.rec.recommend_by_colors([color], top_k=top_k)
            if recs.empty:
                continue

            # Artist diversity
            artist_col = self.rec.artist_col
            if artist_col and artist_col in recs.columns:
                unique_artists = recs[artist_col].nunique()
                artist_divs.append(unique_artists / len(recs))

            # Emotion diversity
            if 'fused_emotion' in recs.columns:
                unique_emotions = recs['fused_emotion'].nunique()
                emotion_divs.append(unique_emotions / len(recs))

            # Audio feature spread
            indices = [int(r.get('original_index', 0)) for _, r in recs.iterrows()]
            if indices:
                audio_sub = self.rec.audio_matrix[indices]
                spread = float(np.mean(np.std(audio_sub, axis=0)))
                audio_spreads.append(spread)

        avg_artist = float(np.mean(artist_divs)) if artist_divs else 0.0
        avg_emotion = float(np.mean(emotion_divs)) if emotion_divs else 0.0
        avg_audio = float(np.mean(audio_spreads)) if audio_spreads else 0.0

        # Combined diversity score (higher is better, but too high means incoherent)
        combined = 0.5 * avg_artist + 0.3 * avg_emotion + 0.2 * min(avg_audio / 0.15, 1.0)
        return {
            'artist_diversity': round(avg_artist, 4),
            'emotion_diversity': round(avg_emotion, 4),
            'audio_spread': round(avg_audio, 4),
            'combined_score': round(combined, 4),
            'interpretation': _rate(combined, 0.3, 0.5, 0.7),
        }

    # -----------------------------------------------------------------------
    # 5. Catalog Coverage
    # -----------------------------------------------------------------------

    def catalog_coverage(self, top_k=10):
        """
        Run diverse queries and track how many unique songs appear across
        all recommendation lists.  Higher coverage = less popularity bias.

        Returns:
            dict with coverage ratio and unique songs count.
        """
        seen = set()

        # Color queries
        for colors in _QUADRANT_COLORS.values():
            for color in colors:
                recs = self.rec.recommend_by_colors([color], top_k=top_k)
                for _, row in recs.iterrows():
                    seen.add(int(row.get('original_index', 0)))

        # Mood queries
        for mood in list(MOOD_KEYWORDS.keys())[:6]:
            recs = self.rec.recommend_by_mood(mood, top_k=top_k)
            for _, row in recs.iterrows():
                seen.add(int(row.get('original_index', 0)))

        # Song-based queries (random sample)
        sample_ids = self._rng.choice(self.n_songs, min(20, self.n_songs), replace=False)
        for sid in sample_ids:
            recs = self.rec.recommend_by_song(int(sid), top_k=top_k)
            for _, row in recs.iterrows():
                seen.add(int(row.get('original_index', 0)))

        coverage = len(seen) / self.n_songs
        return {
            'unique_songs': len(seen),
            'total_songs': self.n_songs,
            'coverage_ratio': round(coverage, 4),
            'interpretation': _rate(coverage, 0.05, 0.15, 0.30),
        }

    # -----------------------------------------------------------------------
    # 6. Color–Emotion Alignment
    # -----------------------------------------------------------------------

    def color_emotion_alignment(self):
        """
        Use the 13 canonical emotion colours from emotion_color_profiles.
        For each emotion, generate its representative colour, query the engine,
        and check what fraction of results have the *same* (or adjacent)
        fused_emotion.

        Returns:
            dict with per-emotion alignment scores.
        """
        profiles = self.rec.color_mapper.emotion_color_profiles
        results = {}
        scores = []

        # Build adjacency map (emotions close in V-A space)
        emotions = sorted(profiles.keys())
        va_map = {e: (profiles[e]['valence'], profiles[e]['arousal']) for e in emotions}

        for emotion in emotions:
            p = profiles[emotion]
            # Generate representative colour for this emotion
            h = (p['hue_range'][0] + p['hue_range'][1]) / 2
            s = (p['saturation_range'][0] + p['saturation_range'][1]) / 2
            l = (p['lightness_range'][0] + p['lightness_range'][1]) / 2
            color = _hsl_to_hex(h, s, l)

            recs = self.rec.recommend_by_colors([color], top_k=15)
            if recs.empty:
                results[emotion] = {'hit_rate': 0.0, 'adjacent_rate': 0.0}
                continue

            # Exact match + adjacent emotion match
            exact_hits = 0
            adjacent_hits = 0
            target_v, target_a = va_map[emotion]

            for _, row in recs.iterrows():
                rec_emotion = row.get('fused_emotion', '')
                if rec_emotion == emotion:
                    exact_hits += 1
                elif rec_emotion in va_map:
                    rv, ra = va_map[rec_emotion]
                    dist = np.sqrt((rv - target_v) ** 2 + (ra - target_a) ** 2)
                    if dist < 0.3:
                        adjacent_hits += 1

            n = len(recs)
            hit_rate = exact_hits / n
            adj_rate = (exact_hits + adjacent_hits) / n
            results[emotion] = {
                'hit_rate': round(hit_rate, 4),
                'adjacent_rate': round(adj_rate, 4),
                'color_used': color,
            }
            scores.append(adj_rate)

        avg = float(np.mean(scores)) if scores else 0.0
        return {
            'per_emotion': results,
            'average_alignment': round(avg, 4),
            'interpretation': _rate(avg, 0.2, 0.4, 0.6),
        }

    # -----------------------------------------------------------------------
    # 7. Similar-Song Consistency (Symmetry)
    # -----------------------------------------------------------------------

    def similar_song_consistency(self):
        """
        For random song pairs (A, B): if B appears in rec(A), does A also
        appear in rec(B)?  Perfect symmetry is not expected (order changes),
        but high overlap indicates consistent similarity modelling.

        Returns:
            dict with symmetry rate and overlap statistics.
        """
        n_samples = min(40, self.n_songs)
        sample_ids = self._rng.choice(self.n_songs, n_samples, replace=False)
        top_k = 15

        # Build recommendation sets
        rec_sets = {}
        for sid in sample_ids:
            recs = self.rec.recommend_by_song(int(sid), top_k=top_k)
            if not recs.empty:
                rec_sets[int(sid)] = set(int(r.get('original_index', 0)) for _, r in recs.iterrows())

        symmetric_hits = 0
        total_pairs = 0
        overlaps = []

        ids = list(rec_sets.keys())
        for a in ids:
            for b in rec_sets[a]:
                if b in rec_sets:
                    total_pairs += 1
                    if a in rec_sets[b]:
                        symmetric_hits += 1
                    # Jaccard overlap of rec(a) and rec(b)
                    inter = len(rec_sets[a] & rec_sets[b])
                    union = len(rec_sets[a] | rec_sets[b])
                    if union > 0:
                        overlaps.append(inter / union)

        symmetry_rate = symmetric_hits / max(total_pairs, 1)
        avg_overlap = float(np.mean(overlaps)) if overlaps else 0.0
        return {
            'symmetry_rate': round(symmetry_rate, 4),
            'avg_jaccard_overlap': round(avg_overlap, 4),
            'total_pairs_tested': total_pairs,
            'interpretation': _rate(symmetry_rate, 0.1, 0.25, 0.45),
        }

    # -----------------------------------------------------------------------
    # 8. Weight Grid Search
    # -----------------------------------------------------------------------

    def weight_grid_search(self, top_k=10):
        """
        Grid search over [audio, lyrics, VA, emotion] weight space.
        For each combination, measure emotional coherence and quadrant
        precision. Find the weight set that maximises a combined score.

        Returns:
            dict with best weights, current weights comparison, and grid.
        """
        # Coarse grid: step 0.15, sum = 1.0 (keeps runtime reasonable)
        candidates = _generate_weight_candidates(4, step=0.15, min_w=0.10)
        if len(candidates) > 50:
            idx = self._rng.choice(len(candidates), 50, replace=False)
            candidates = [candidates[i] for i in idx]

        # Always include the current weights as a candidate
        current_weights = list(WEIGHTS_COLOR_QUERY_WITH_LYRICS)
        candidates.append(tuple(current_weights))

        # Test colours (one per quadrant)
        test_colors = {
            'Q1': '#FFD700',
            'Q2': '#CC0000',
            'Q3': '#1E3A5F',
            'Q4': '#90EE90',
        }

        current_weights = list(WEIGHTS_COLOR_QUERY_WITH_LYRICS)
        best_score = -1
        best_weights = current_weights
        current_score = None
        grid_results = []

        for weights in candidates:
            combined = 0.0
            n_queries = 0
            for qname, color in test_colors.items():
                qinfo = MOOD_QUADRANTS[qname]
                v_lo, v_hi = qinfo['valence']
                e_lo, e_hi = qinfo['energy']

                recs = self._recommend_with_custom_weights([color], list(weights), top_k)
                if recs.empty:
                    continue

                # Precision
                hits = 0
                dists = []
                for _, row in recs.iterrows():
                    idx = int(row.get('original_index', 0))
                    v, a = self.rec.song_va[idx]
                    if v_lo <= v <= v_hi and e_lo <= a <= e_hi:
                        hits += 1
                    qva_tuple = self.rec.color_mapper.color_to_valence_arousal(color)
                    qva = np.array([qva_tuple[0], qva_tuple[1]])
                    dist = np.sqrt((v - qva[0]) ** 2 + (a - qva[1]) ** 2)
                    dists.append(dist)

                precision = hits / len(recs)
                coherence = max(0.0, 1.0 - float(np.mean(dists)))
                combined += 0.6 * precision + 0.4 * coherence
                n_queries += 1

            if n_queries > 0:
                score = combined / n_queries
            else:
                score = 0.0

            entry = {'weights': [round(w, 2) for w in weights], 'score': round(score, 4)}
            grid_results.append(entry)

            if score > best_score:
                best_score = score
                best_weights = list(weights)

            # Track current weights' score
            if _weights_close(weights, current_weights):
                current_score = score

        # Sort grid by score descending
        grid_results.sort(key=lambda x: x['score'], reverse=True)

        return {
            'best_weights': [round(w, 2) for w in best_weights],
            'best_score': round(best_score, 4),
            'current_weights': [round(w, 2) for w in current_weights],
            'current_score': round(current_score, 4) if current_score is not None else None,
            'improvement': round(best_score - (current_score or best_score), 4),
            'top_10': grid_results[:10],
            'total_tested': len(grid_results),
            'interpretation': 'optimal' if best_score > 0.6 else 'acceptable' if best_score > 0.4 else 'needs_tuning',
        }

    # -----------------------------------------------------------------------
    # 9. Mood Keyword Accuracy
    # -----------------------------------------------------------------------

    def mood_keyword_accuracy(self, top_k=10):
        """
        For each mood keyword (happy, sad, calm, …), recommend songs and
        check what fraction fall in the expected mood quadrant.

        Returns:
            dict with per-keyword accuracy and average.
        """
        results = {}
        accuracies = []

        for mood, (expected_q, target_v, target_a) in MOOD_KEYWORDS.items():
            recs = self.rec.recommend_by_mood(mood, top_k=top_k)
            if recs.empty:
                results[mood] = {'quadrant': expected_q, 'accuracy': 0.0}
                continue

            qinfo = MOOD_QUADRANTS[expected_q]
            v_lo, v_hi = qinfo['valence']
            e_lo, e_hi = qinfo['energy']

            hits = 0
            va_dists = []
            for _, row in recs.iterrows():
                idx = int(row.get('original_index', 0))
                v, a = self.rec.song_va[idx]
                if v_lo <= v <= v_hi and e_lo <= a <= e_hi:
                    hits += 1
                va_dists.append(np.sqrt((v - target_v) ** 2 + (a - target_a) ** 2))

            acc = hits / len(recs)
            results[mood] = {
                'quadrant': expected_q,
                'accuracy': round(acc, 4),
                'avg_va_distance': round(float(np.mean(va_dists)), 4),
            }
            accuracies.append(acc)

        avg = float(np.mean(accuracies)) if accuracies else 0.0
        return {
            'per_keyword': results,
            'average_accuracy': round(avg, 4),
            'interpretation': _rate(avg, 0.3, 0.5, 0.7),
        }

    # -----------------------------------------------------------------------
    # 10. Response Time Benchmark
    # -----------------------------------------------------------------------

    def response_time_benchmark(self):
        """
        Time each recommendation method (ms) over multiple calls.

        Returns:
            dict with per-method timing statistics.
        """
        timings = {}

        # Color recommendation
        timings['recommend_by_colors'] = _time_fn(
            lambda: self.rec.recommend_by_colors(['#FF5733'], top_k=10), n=5)

        # Song recommendation
        sid = int(self._rng.choice(self.n_songs))
        timings['recommend_by_song'] = _time_fn(
            lambda: self.rec.recommend_by_song(sid, top_k=10), n=5)

        # Mood recommendation
        timings['recommend_by_mood'] = _time_fn(
            lambda: self.rec.recommend_by_mood('happy', top_k=10), n=5)

        # Lyrics recommendation
        timings['recommend_by_lyrics'] = _time_fn(
            lambda: self.rec.recommend_by_lyrics_keywords('tình yêu', top_k=10), n=3)

        # Journey
        timings['emotion_journey'] = _time_fn(
            lambda: self.rec.generate_emotion_journey(0.2, 0.2, 0.8, 0.8, steps=5), n=3)

        avg = float(np.mean([v['median_ms'] for v in timings.values()]))
        return {
            'per_method': timings,
            'average_ms': round(avg, 2),
            'interpretation': 'fast' if avg < 100 else 'acceptable' if avg < 500 else 'slow',
        }

    # -----------------------------------------------------------------------
    # Overall score aggregation
    # -----------------------------------------------------------------------

    def _compute_overall_score(self, metrics: dict) -> dict:
        """
        Compute a weighted overall evaluation score from all metrics.
        Each metric is normalised to [0, 1] and weighted by importance.

        Returns:
            dict with score (0-100), grade, and breakdown.
        """
        weights_map = {
            'precision_at_k': ('average_precision', 0.20),
            'ndcg': ('average_ndcg', 0.15),
            'emotional_coherence': ('average_coherence', 0.15),
            'intra_list_diversity': ('combined_score', 0.10),
            'catalog_coverage': ('coverage_ratio', 0.05),
            'color_emotion_alignment': ('average_alignment', 0.10),
            'similar_song_consistency': ('symmetry_rate', 0.05),
            'mood_keyword_accuracy': ('average_accuracy', 0.15),
            'response_time': ('average_ms', 0.05),
        }

        breakdown = {}
        total_weight = 0.0
        weighted_sum = 0.0

        for metric_key, (value_key, weight) in weights_map.items():
            if metric_key not in metrics:
                continue
            raw = metrics[metric_key].get(value_key, 0)
            if raw is None:
                continue

            # Normalise: time is inverse (lower = better), else higher = better
            if metric_key == 'response_time':
                # 50ms → 1.0, 500ms → 0.1
                norm = max(0.0, min(1.0, 1.0 - (raw - 50) / 450))
            elif metric_key == 'catalog_coverage':
                # Coverage >30% is excellent for our dataset size
                norm = min(1.0, raw / 0.30)
            else:
                norm = min(1.0, max(0.0, raw))

            breakdown[metric_key] = {
                'raw': round(raw, 4) if isinstance(raw, float) else raw,
                'normalised': round(norm, 4),
                'weight': weight,
                'contribution': round(norm * weight, 4),
            }
            weighted_sum += norm * weight
            total_weight += weight

        score = (weighted_sum / total_weight * 100) if total_weight > 0 else 0
        grade = _score_to_grade(score)

        return {
            'score': round(score, 1),
            'grade': grade,
            'breakdown': breakdown,
        }

    # -----------------------------------------------------------------------
    # Custom-weight recommendation (for /api/backtest/test-weights)
    # -----------------------------------------------------------------------

    def _recommend_with_custom_weights(self, color_hexes, weights, top_k=10):
        """
        Replicate recommend_by_colors with a custom weight vector.

        Args:
            color_hexes: list of hex colour strings
            weights: [audio_w, lyrics_w, va_w, emotion_w] — need not sum to 1
            top_k: number of results
        Returns:
            DataFrame matching recommend_by_colors output format.
        """
        rec = self.rec
        if isinstance(color_hexes, str):
            color_hexes = [color_hexes]

        # Normalise weights to sum to 1
        w = np.array(weights, dtype=float)
        w_sum = w.sum()
        if w_sum > 0:
            w = w / w_sum
        else:
            w = np.array([0.25, 0.35, 0.20, 0.20])
        w_audio, w_lyrics, w_va, w_emotion = w

        # --- Compute query features (mirrors recommend_by_colors) ---
        query_va = []
        query_audio = []
        query_emotion = np.zeros(len(rec.emotion_labels))
        query_lyrics_vecs = []
        preferred_emotions = set()

        for color in color_hexes:
            try:
                va = rec.color_mapper.color_to_valence_arousal(color)
                query_va.append([va[0], va[1]])
                audio_dict = rec.color_mapper.color_to_audio(color)
                audio_vec = np.array([audio_dict.get(f, 0.5) for f in rec.audio_features])
                query_audio.append(audio_vec)
                emotion_probs = rec.color_mapper.color_to_emotion_probs(color)
                for i, emo in enumerate(rec.emotion_labels):
                    query_emotion[i] += emotion_probs.get(emo, 0)
                if rec.embeddings_normalized is not None and 'fused_emotion' in rec.df.columns:
                    top_emotion = max(emotion_probs.items(), key=lambda x: x[1])[0]
                    mask = rec.df['fused_emotion'] == top_emotion
                    if mask.sum() > 0:
                        indices = np.where(mask)[0][:5]
                        avg = rec.embeddings_normalized[indices].mean(axis=0)
                        query_lyrics_vecs.append(avg)
            except (ValueError, KeyError, TypeError):
                query_va.append([0.5, 0.5])
                query_audio.append(np.full(len(rec.audio_features), 0.5))

        va_centroid = np.mean(query_va, axis=0)
        audio_centroid = np.mean(query_audio, axis=0)
        query_emotion /= len(color_hexes)
        es = query_emotion.sum()
        if es > 0:
            query_emotion /= es

        # Determine preferred emotions from quadrant
        valence, arousal = va_centroid
        if valence >= 0.5 and arousal >= 0.5:
            preferred_emotions = {'happy', 'excited', 'passionate'}
        elif valence < 0.5 and arousal >= 0.5:
            preferred_emotions = {'angry', 'tense', 'excited'}
        elif valence < 0.5 and arousal < 0.5:
            preferred_emotions = {'sad', 'melancholic', 'nostalgic'}
        else:
            preferred_emotions = {'calm', 'peaceful', 'romantic', 'tender'}

        # --- Compute similarities ---
        from sklearn.metrics.pairwise import cosine_similarity as _cos_sim

        # Audio
        audio_sim = _cos_sim(audio_centroid.reshape(1, -1), rec.audio_matrix)[0]
        audio_sim = np.clip(audio_sim, 0, 1)

        # V-A
        va_diff = rec.song_va - va_centroid
        va_dist = np.sqrt(np.sum(va_diff ** 2, axis=1))
        va_sim = np.exp(-va_dist * 3)

        # Emotion
        qn = np.linalg.norm(query_emotion)
        if qn > 0:
            sn = np.linalg.norm(rec.song_emotion_vec, axis=1)
            dots = rec.song_emotion_vec @ query_emotion
            emotion_sim = dots / (sn * qn + 1e-10)
            emotion_sim = (emotion_sim + 1) / 2
        else:
            emotion_sim = np.ones(rec.n_songs) * 0.5

        # Lyrics
        if query_lyrics_vecs and rec.embeddings_normalized is not None:
            lc = np.mean(query_lyrics_vecs, axis=0)
            ln = np.linalg.norm(lc)
            if ln > 0:
                lc /= ln
            lyrics_sim = rec.embeddings_normalized @ lc
            lyrics_sim = (lyrics_sim + 1) / 2
            lyrics_sim = np.clip(lyrics_sim, 0, 1)
        else:
            lyrics_sim = np.ones(rec.n_songs) * 0.5

        # Emotion boost
        emotion_boost = np.zeros(rec.n_songs)
        if 'fused_emotion' in rec.df.columns:
            for idx in range(rec.n_songs):
                se = rec.df.iloc[idx].get('fused_emotion', '')
                if se in preferred_emotions:
                    emotion_boost[idx] = 0.12

        # Weighted fusion
        final_scores = (
            w_audio * audio_sim +
            w_lyrics * lyrics_sim +
            w_va * va_sim +
            w_emotion * emotion_sim +
            emotion_boost
        )
        final_scores = np.clip(final_scores, 0, 1)

        return rec._fast_rank(final_scores, top_k, DIVERSITY_PENALTY)


# ===========================================================================
# Utility helpers
# ===========================================================================

def _time_fn(fn, n=5):
    """Run fn n times and return timing statistics in ms."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return {
        'median_ms': round(float(np.median(times)), 2),
        'mean_ms': round(float(np.mean(times)), 2),
        'min_ms': round(float(np.min(times)), 2),
        'max_ms': round(float(np.max(times)), 2),
        'n_runs': n,
    }


def _rate(value, low, mid, high):
    """Human-readable quality interpretation."""
    if value >= high:
        return 'excellent'
    if value >= mid:
        return 'good'
    if value >= low:
        return 'acceptable'
    return 'needs_improvement'


def _score_to_grade(score):
    """Convert 0-100 score to letter grade."""
    if score >= 90:
        return 'A+'
    if score >= 80:
        return 'A'
    if score >= 70:
        return 'B'
    if score >= 60:
        return 'C'
    if score >= 50:
        return 'D'
    return 'F'


def _hsl_to_hex(h, s, l):
    """Convert HSL (h=0-360, s=0-100, l=0-100) to hex string."""
    import colorsys
    h_norm = (h % 360) / 360
    s_norm = max(0, min(100, s)) / 100
    l_norm = max(0, min(100, l)) / 100
    r, g, b = colorsys.hls_to_rgb(h_norm, l_norm, s_norm)
    return '#{:02X}{:02X}{:02X}'.format(int(r * 255), int(g * 255), int(b * 255))


def _generate_weight_candidates(n_dims, step=0.10, min_w=0.05):
    """Generate all weight vectors of n_dims that sum to 1.0 with given step."""
    steps = int(round(1.0 / step))
    candidates = []
    min_steps = max(1, int(round(min_w / step)))

    def _recurse(remaining_steps, depth, current):
        if depth == n_dims - 1:
            if remaining_steps >= min_steps:
                current.append(remaining_steps * step)
                candidates.append(tuple(current))
                current.pop()
            return
        for s in range(min_steps, remaining_steps - min_steps * (n_dims - depth - 1) + 1):
            current.append(s * step)
            _recurse(remaining_steps - s, depth + 1, current)
            current.pop()

    _recurse(steps, 0, [])
    return candidates


def _weights_close(w1, w2, tol=0.02):
    """Check if two weight vectors are approximately equal."""
    if len(w1) != len(w2):
        return False
    return all(abs(a - b) < tol for a, b in zip(w1, w2))
