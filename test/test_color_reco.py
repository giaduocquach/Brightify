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


def test_config_labels_version():
    """Must use v5b+ or v6a+ labels (no LLM-only v4/v5a, no CLAP-raw labels)."""
    from config import RELABELED_EMOTIONS_FILE
    label_file = RELABELED_EMOTIONS_FILE
    valid = (
        any(f"v5{x}" in label_file for x in ["b", "c", "d", "e"])
        or any(f"v6{x}" in label_file for x in ["a", "b", "c"])
    )
    assert valid, f"Expected v5b+ or v6a+ labels, got: {label_file}"


def test_config_rrf_enabled():
    """RRF multi-colour fusion must be enabled."""
    from config import ENABLE_RRF
    assert ENABLE_RRF


# ── Color mapping tests (fast) ────────────────────────────────────────────────

ICEAS_CENTROIDS = [
    ('#BE0032', 'red',       'Q2'),   # Oklab V=0.434, A=0.906 → Q2 (anger/energetic; Jonauskaite)
    ('#F38400', 'orange',    'Q1'),   # Oklab V=0.652, A=0.854 → Q1
    ('#F3C300', 'yellow',    'Q1'),   # Oklab V=0.817, A=0.814 → Q1
    ('#FFB7C5', 'pink',      'Q1'),   # Oklab V=0.735, A=0.798 → Q1
    ('#008856', 'green',     'Q4'),   # Oklab V=0.622, A=0.496 → Q4 (calm-positive; ICEAS: 21% happy+21% calm)
    ('#0067A5', 'blue',      'Q4'),   # Oklab V=0.567, A=0.483 → Q4 (calm/peaceful; ICEAS: 25% calm+18% peaceful)
    ('#848482', 'grey',      'Q3'),   # Oklab V=0.411, A=0.320 → Q3
    ('#222222', 'black',     'Q3'),   # Oklab V=0.255, A=0.453 → Q3
    ('#9C4F96', 'purple',    'Q2'),   # Oklab V=0.478, A=0.513 → Q2
    ('#80461B', 'brown',     'Q2'),   # Oklab V=0.424, A=0.753 → Q2
    ('#F2F3F4', 'white',     'Q4'),   # Oklab V=0.591, A=0.166 → Q4
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
    """Turquoise centroid is Q4 (V>0.5, A<0.5) — calm/positive.
    Oklab (V28): V=0.668 A=0.283 — clearly Q4, no longer borderline.
    Previously HSL gave V≈0.510 (borderline). Oklab with perceptual calibration
    correctly places turquoise higher in valence (positive-calm association).
    """
    v, a = color_mapper.hsl_to_va('#3AB09E')
    assert 0.55 <= v <= 0.80, f"Turquoise centroid V={v:.3f} should be Q4 positive (0.55-0.80)"
    assert a < 0.5, f"Turquoise centroid A={a:.3f} should be < 0.5 (calm)"


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
def test_engine_arousal_distribution(rec):
    """Arousal distribution must be well-spread (not compressed).

    v6a: MERT-audio probe (DEAM, CV R²=0.58) + NRC-VAD, calibrated to DEAM std≈0.16.
    VN pop catalog skews lower-arousal, so mean may be below 0.5 — that is correct
    (not a bug). Gate: std≥0.10 prevents degenerate compression.
    """
    aro = rec.song_va[:, 1]
    std = float(np.std(aro))
    assert std >= 0.10, f"Arousal std={std:.3f} still too compressed (target ≥0.10)"


# ── Phase 3 / R1 CIELAB-valence tests (V26) ─────────────────────────────────

def test_config_cielab_flag_exists():
    """COLOR_VALENCE_CIELAB must exist as a bool in config (gated, default off until gate pass)."""
    from config import COLOR_VALENCE_CIELAB
    assert isinstance(COLOR_VALENCE_CIELAB, bool)


def test_cielab_features_available(color_mapper):
    """_cielab_features must return a 6-element array (or None if colormath missing)."""
    feat = color_mapper._cielab_features('#F38400')  # orange
    if feat is None:
        pytest.skip("colormath not available — CIELAB fallback to HSL is expected")
    assert feat.shape == (6,), f"Expected 6-element feature, got {feat.shape}"
    assert all(np.isfinite(feat)), "CIELAB features must be finite"
    assert -1.0 <= feat[4] <= 1.0, f"cos_h must be in [-1,1], got {feat[4]}"
    assert -1.0 <= feat[5] <= 1.0, f"sin_h must be in [-1,1], got {feat[5]}"


def test_cielab_valence_monotonicity_beats_hsl(color_mapper):
    """CIELAB-valence mode: L*↑ → valence↑ Spearman ρ must beat HSL baseline (0.44).

    Experiment result (tools/phase3_cielab_experiment.py): CIELAB mono=0.81, HSL=0.44.
    """
    from scipy.stats import spearmanr
    import config

    feat = color_mapper._cielab_features('#F38400')
    if feat is None:
        pytest.skip("colormath not available — cannot test CIELAB mode")

    orig_flag = config.COLOR_VALENCE_CIELAB
    config.COLOR_VALENCE_CIELAB = True
    try:
        rng = np.random.default_rng(42)
        # 200 chromatic colours with diverse L values (avoid achromatic branch s<0.12)
        hexes = [
            f'#{rng.integers(30, 225):02X}{rng.integers(80, 225):02X}'
            f'{rng.integers(30, 225):02X}'
            for _ in range(200)
        ]
        vals, L_star = [], []
        for hx in hexes:
            f = color_mapper._cielab_features(hx)
            if f is None:
                continue
            L_star.append(float(f[0]))
            vals.append(color_mapper.hsl_to_va(hx)[0])
        rho, _ = spearmanr(L_star, vals)
        assert rho > 0.44, (
            f"CIELAB mono ρ={rho:.3f} should beat HSL baseline 0.44 "
            f"(experiment: 0.81 expected)"
        )
    finally:
        config.COLOR_VALENCE_CIELAB = orig_flag


def test_cielab_va_in_unit_range(color_mapper):
    """CIELAB-valence mode: all 12 ICEAS centroids must return V-A in [0,1]."""
    import config

    feat = color_mapper._cielab_features('#F38400')
    if feat is None:
        pytest.skip("colormath not available")

    all_colors = [
        '#BE0032', '#F38400', '#F3C300', '#FFB7C5', '#008856', '#3AB09E',
        '#0067A5', '#9C4F96', '#80461B', '#F2F3F4', '#848482', '#222222',
    ]
    orig_flag = config.COLOR_VALENCE_CIELAB
    config.COLOR_VALENCE_CIELAB = True
    try:
        for hx in all_colors:
            v, a = color_mapper.hsl_to_va(hx)
            assert 0.0 <= v <= 1.0, f"CIELAB {hx}: V={v:.3f} out of [0,1]"
            assert 0.0 <= a <= 1.0, f"CIELAB {hx}: A={a:.3f} out of [0,1]"
    finally:
        config.COLOR_VALENCE_CIELAB = orig_flag


def test_cielab_red_valence_lower_than_yellow(color_mapper):
    """CIELAB-valence: red V < yellow V (ICEAS: red anger/tense, yellow happy).

    With HSL: red V≈0.56 ≈ yellow V≈0.66 (small gap).
    With CIELAB: red V≈0.35 << yellow V≈0.80 (correct scientific order,
    matching ICEAS human norms V=0.35 vs V=0.73).
    This test documents the KNOWN QUADRANT SHIFT for red (Q1→Q2 with CIELAB),
    which is scientifically correct but is why the production gate hasn't been flipped.
    """
    import config

    feat = color_mapper._cielab_features('#BE0032')
    if feat is None:
        pytest.skip("colormath not available")

    orig_flag = config.COLOR_VALENCE_CIELAB
    config.COLOR_VALENCE_CIELAB = True
    try:
        v_red, _ = color_mapper.hsl_to_va('#BE0032')
        v_yel, _ = color_mapper.hsl_to_va('#F3C300')
        assert v_red < v_yel, (
            f"CIELAB: red V={v_red:.3f} should be < yellow V={v_yel:.3f} "
            f"(ICEAS: red=anger V=0.35, yellow=happy V=0.73)"
        )
        # Document: red CIELAB V < 0.5 (Q2) — known gate blocker
        assert v_red < 0.5, (
            f"CIELAB red V={v_red:.3f} expected < 0.5 (Q2, matching ICEAS norms)"
        )
    finally:
        config.COLOR_VALENCE_CIELAB = orig_flag


def test_cielab_arousal_unchanged(color_mapper):
    """CIELAB flag must NOT affect arousal — Whiteford-HSL arousal must be stable."""
    import config

    feat = color_mapper._cielab_features('#F38400')
    if feat is None:
        pytest.skip("colormath not available")

    test_colors = ['#F38400', '#0067A5', '#BE0032', '#3AB09E', '#9C4F96']

    orig_flag = config.COLOR_VALENCE_CIELAB
    try:
        config.COLOR_VALENCE_CIELAB = False
        arousal_hsl = [color_mapper.hsl_to_va(hx)[1] for hx in test_colors]
        config.COLOR_VALENCE_CIELAB = True
        arousal_cielab = [color_mapper.hsl_to_va(hx)[1] for hx in test_colors]
    finally:
        config.COLOR_VALENCE_CIELAB = orig_flag

    for hx, a_hsl, a_cie in zip(test_colors, arousal_hsl, arousal_cielab):
        assert abs(a_hsl - a_cie) < 1e-6, (
            f"{hx}: arousal changed with CIELAB flag! "
            f"HSL={a_hsl:.4f} CIELAB={a_cie:.4f} — flag must only affect valence"
        )


def test_oklab_features_shape(color_mapper):
    """_oklab_features returns 6-element array with valid cos/sin values."""
    feat = color_mapper._oklab_features('#FF0000')
    assert feat.shape == (6,), f"Expected shape (6,), got {feat.shape}"
    assert -1.0 <= feat[4] <= 1.0, f"cos(h) out of range: {feat[4]}"
    assert -1.0 <= feat[5] <= 1.0, f"sin(h) out of range: {feat[5]}"
    assert 0.0 <= feat[0] <= 1.0, f"L out of expected range: {feat[0]}"


def test_oklab_no_colormath_needed(color_mapper):
    """_oklab_features must work even when HAS_COLORMATH=False."""
    import core.advanced_color_mapping as m
    orig = m.HAS_COLORMATH
    m.HAS_COLORMATH = False
    try:
        feat = color_mapper._oklab_features('#00FF00')
        assert feat is not None
        assert feat.shape == (6,)
    finally:
        m.HAS_COLORMATH = orig
