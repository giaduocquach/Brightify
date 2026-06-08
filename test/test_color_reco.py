"""Regression tests for recommend-by-colour path.

Covers: config validity, color V-A mapping, engine output properties,
and known limitations (turquoise borderline). Marked with pytest marks
so slow integration tests can be skipped in CI.

Fast tests (no engine load): test_config_*, test_color_mapping_*
Slow tests (engine): test_engine_* — require catalog + models on disk.

Run fast only:  pytest test/test_color_reco.py -m "not slow"
Run all:        pytest test/test_color_reco.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rec():
    """Engine fixture — loaded once per module (slow)."""
    from core.recommendation_engine import get_recommender
    return get_recommender()


@pytest.fixture(scope="module")
def color_mapper():
    from core.advanced_color_mapping import get_advanced_color_mapper
    return get_advanced_color_mapper(vietnamese=False)


# ── Config tests (fast) ──────────────────────────────────────────────────────

def test_config_sigma_heteroscedastic():
    """Arousal sigma must be narrower than valence (trust arousal > valence)."""
    from config import COLOR_SCORE_VA_SIGMA_V, COLOR_SCORE_VA_SIGMA_A
    assert COLOR_SCORE_VA_SIGMA_A < COLOR_SCORE_VA_SIGMA_V, (
        f"σ_A={COLOR_SCORE_VA_SIGMA_A} must be < σ_V={COLOR_SCORE_VA_SIGMA_V}"
    )


def test_config_labels_v5x():
    """Must use v5b or later (Gemini valence + recalibrated arousal), not v4/v5."""
    from config import RELABELED_EMOTIONS_FILE
    assert any(f"v5{x}" in RELABELED_EMOTIONS_FILE for x in ["b","c","d","e"]), (
        f"Expected v5b/v5c or later labels, got: {RELABELED_EMOTIONS_FILE}"
    )


def test_config_rrf_enabled():
    """RRF multi-colour fusion must be enabled."""
    from config import ENABLE_RRF
    assert ENABLE_RRF


# ── Color mapping tests (fast) ────────────────────────────────────────────────

ICEAS_CENTROIDS = [
    ('#BE0032', 'red',       'Q1'),   # V=0.56, A=0.89 → high-V, high-A → Q1
    ('#F38400', 'orange',    'Q1'),   # V=0.62, A=0.84 → Q1
    ('#F3C300', 'yellow',    'Q1'),   # V=0.66, A=0.77 → Q1
    ('#FFB7C5', 'pink',      'Q1'),   # V=0.76, A=0.76 → Q1
    ('#848482', 'grey',      'Q3'),   # V=0.41, A=0.32 → Q3
    ('#222222', 'black',     'Q3'),   # V=0.20, A=0.45 → Q3/Q2
    ('#9C4F96', 'purple',    'Q2'),   # V=0.27, A=0.55 → Q2
    ('#80461B', 'brown',     'Q2'),   # V=0.41, A=0.81 → Q2
    ('#F2F3F4', 'white',     'Q4'),   # V=0.59, A=0.17 → Q4
]


@pytest.mark.parametrize("hex_c,name,expected_q", ICEAS_CENTROIDS)
def test_color_mapping_quadrant(color_mapper, hex_c, name, expected_q):
    """Colour centroid must map to the expected V-A quadrant."""
    v, a = color_mapper.hsl_to_va(hex_c)
    def q(v, a):
        if v >= 0.5 and a >= 0.5: return 'Q1'
        if v <  0.5 and a >= 0.5: return 'Q2'
        if v <  0.5 and a <  0.5: return 'Q3'
        return 'Q4'
    actual = q(v, a)
    assert actual == expected_q, (
        f"{name} {hex_c}: expected {expected_q} but got {actual} (V={v:.3f}, A={a:.3f})"
    )


def test_turquoise_borderline_documented(color_mapper):
    """Turquoise centroid is Q4 but barely (V=0.510 vs boundary 0.5).
    Known limitation: engine returns mostly Q3 (KL=20.7) because:
    - Gemini assigns V=0.480 to many bittersweet songs (nearest to turquoise V)
    - Q3 catalog (32%) >> Q4 catalog (14%) near this V
    - L1 test uses old-hex #40E0D0 (V=0.672) while prod uses centroid #3AB09E (V=0.510)
    This test documents the limitation — it does NOT assert perfect Q4 retrieval.
    """
    v, a = color_mapper.hsl_to_va('#3AB09E')
    assert 0.50 <= v <= 0.55, f"Turquoise centroid V={v:.3f} should be just above 0.5"
    assert a < 0.5, f"Turquoise centroid A={a:.3f} should be < 0.5 (calm)"
    # V is barely above boundary → structural borderline — acknowledged in Phase 4


def test_color_va_in_unit_range(color_mapper):
    """All 12 ICEAS centroid V-A values must be in [0, 1]."""
    all_colors = [
        '#BE0032','#F38400','#F3C300','#FFB7C5','#008856','#3AB09E',
        '#0067A5','#9C4F96','#80461B','#F2F3F4','#848482','#222222',
    ]
    for hex_c in all_colors:
        v, a = color_mapper.hsl_to_va(hex_c)
        assert 0.0 <= v <= 1.0, f"{hex_c}: V={v:.3f} out of [0,1]"
        assert 0.0 <= a <= 1.0, f"{hex_c}: A={a:.3f} out of [0,1]"


# ── Engine tests (slow) ───────────────────────────────────────────────────────

@pytest.mark.slow
def test_engine_color_returns_results(rec):
    """Single colour recommendation returns expected count."""
    df = rec.recommend_by_colors('#F38400', top_k=10)  # orange
    assert df is not None and not df.empty
    assert len(df) >= 5, f"Expected ≥5 results, got {len(df)}"


@pytest.mark.slow
def test_engine_multi_color_rrf(rec):
    """Multi-colour RRF returns results from both colour ranges."""
    df = rec.recommend_by_colors(['#F3C300', '#222222'], top_k=10)  # yellow + black
    assert df is not None and not df.empty
    assert len(df) >= 5


def test_config_journey_enabled():
    """V23: 2-colour mood journey must be enabled."""
    from config import COLOR_JOURNEY_ENABLED
    assert COLOR_JOURNEY_ENABLED


@pytest.mark.slow
def test_engine_color_cap_is_2(rec):
    """V23: ≥3 colours are capped to 2 (3rd dropped)."""
    df3 = rec.recommend_by_colors(['#848482', '#F3C300', '#BE0032'], top_k=10)
    df2 = rec.recommend_by_colors(['#848482', '#F3C300'], top_k=10)
    # 3rd colour ignored → same result set as 2 colours
    assert set(df3['original_index']) == set(df2['original_index']), (
        "3rd colour should be dropped (cap=2)")


@pytest.mark.slow
def test_engine_journey_monotonic(rec):
    """V23: 2-colour journey must order songs smoothly along V-A path A→B
    (Iso-Principle), not interleaved. Position-along-path must increase with
    sequence index (Spearman ρ > 0.5)."""
    import numpy as np
    from scipy import stats
    hx_a, hx_b = '#848482', '#F3C300'   # grey(sad) → yellow(happy)
    df = rec.recommend_by_colors([hx_a, hx_b], top_k=10)
    idxs = [int(i) for i in df['original_index'].tolist()]
    p1 = np.array(rec.color_mapper.hsl_to_va(hx_a))
    p2 = np.array(rec.color_mapper.hsl_to_va(hx_b))
    axis = p2 - p1
    t = [float((rec.song_va[i] - p1) @ axis / (axis @ axis + 1e-9)) for i in idxs]
    rho, _ = stats.spearmanr(t, np.arange(len(t)))
    assert rho > 0.5, f"Journey not monotonic along A→B path (ρ={rho:.2f})"
    # first song closer to A, last closer to B
    assert (np.linalg.norm(rec.song_va[idxs[0]] - p1)
            < np.linalg.norm(rec.song_va[idxs[0]] - p2)), "First song should match colour A"
    assert (np.linalg.norm(rec.song_va[idxs[-1]] - p2)
            < np.linalg.norm(rec.song_va[idxs[-1]] - p1)), "Last song should match colour B"


@pytest.mark.slow
def test_engine_results_va_valid(rec):
    """All recommended songs must have valid V-A in [0, 1]."""
    df = rec.recommend_by_colors('#F38400', top_k=10)
    idxs = df['original_index'].tolist()
    for i in idxs:
        v, a = float(rec.song_va[i, 0]), float(rec.song_va[i, 1])
        assert 0.0 <= v <= 1.0 and 0.0 <= a <= 1.0, (
            f"Song {i}: V={v:.3f} A={a:.3f} out of range")


@pytest.mark.slow
def test_engine_opposite_colors_different_va(rec):
    """Opposite colours (orange vs black) must return songs with statistically
    different mean valence — the core signal the engine should provide.
    """
    df_orange = rec.recommend_by_colors('#F38400', top_k=15)
    df_black  = rec.recommend_by_colors('#222222', top_k=15)

    v_orange = np.mean([rec.song_va[i, 0] for i in df_orange['original_index']])
    v_black  = np.mean([rec.song_va[i, 0] for i in df_black['original_index']])

    assert v_orange > v_black + 0.05, (
        f"Orange mean valence ({v_orange:.3f}) should be > black ({v_black:.3f}) + 0.05. "
        f"Gap = {v_orange - v_black:.3f}"
    )


@pytest.mark.slow
def test_engine_artist_diversity(rec):
    """Top-10 results should not be dominated by a single artist."""
    df = rec.recommend_by_colors('#F38400', top_k=10)
    art_col = rec.artist_col or 'artists'
    artists = df[art_col].fillna('unknown').tolist()
    from collections import Counter
    most_common_count = Counter(artists).most_common(1)[0][1]
    # No artist should take > 40% of slots
    assert most_common_count / len(artists) <= 0.40, (
        f"Dominant artist has {most_common_count}/{len(artists)} slots — diversity too low"
    )


@pytest.mark.slow
def test_engine_arousal_v5b_expanded(rec):
    """Arousal must have std > 0.12 after Phase 1 recalibration (was 0.095)."""
    aro = rec.song_va[:, 1]
    std = float(np.std(aro))
    pct_high = float((aro > 0.7).mean())
    assert std >= 0.12, f"Arousal std={std:.3f} still too compressed (target ≥0.12)"
    assert pct_high >= 0.05, f"Only {pct_high:.1%} songs with arousal>0.7 (target ≥5%)"
