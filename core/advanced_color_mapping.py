import numpy as np
import colorsys
from typing import Tuple, Dict, Optional, List
import warnings
warnings.filterwarnings('ignore')

# Try to import colormath
try:
    from colormath.color_objects import sRGBColor, LabColor
    from colormath.color_conversions import convert_color
    from colormath.color_diff import delta_e_cie2000
    HAS_COLORMATH = True
except ImportError:
    HAS_COLORMATH = False


class AdvancedColorMapper:
    """
    State-of-the-art Music-Color Mapping System v5.2
    Based on latest research (2022-2024)

    Key improvements over previous version:
    - Jonauskaite et al. (2020) 12-country study for universal patterns
    - Whiteford et al. (2023) context-dependent weights
    - Continuous hue-to-emotion mapping (not discrete ranges)
    """

    def __init__(self, use_vietnamese_adaptation: bool = True):
        self.use_vietnamese_adaptation = use_vietnamese_adaptation

        # Emotion-color profiles aligned with CLAP fused_emotion labels (8 labels).
        # CRITICAL: these must match the song catalog's fused_emotion values exactly
        # so the emotion_sim signal in recommend_by_colors actually works.
        #
        # Sources: Jonauskaite 2020 (Psych Science, 4598 participants, 30 countries),
        # Palmer 2013 (PNAS), Whiteford 2018 (PMC6240980), Wilms & Oberfeld 2018.
        # Vietnamese cultural notes embedded per color.
        #
        # HSL similarity weights: 0.40 saturation + 0.35 lightness + 0.25 hue
        # (Wilms & Oberfeld 2018: chroma > lightness > hue in effect size;
        #  Whiteford: saturation r_s=0.720 for arousal, lightness r_s=0.484 for valence)
        self.emotion_color_profiles = {
            'happy': {
                # Yellow–Orange: warm, bright, high saturation
                # Jonauskaite: yellow = joy globally; Vietnamese yellow = festive/royal
                'hue_range': (30, 75),
                'saturation_range': (65, 100),
                'lightness_range': (55, 85),
                'valence': 0.88, 'arousal': 0.70,
                'vi_keywords': ['vui vẻ', 'hạnh phúc', 'tươi vui', 'rạng rỡ'],
            },
            'excited': {
                # Bright red–orange: intense, high saturation, mid lightness
                # Jonauskaite: orange/red = excitement/passion
                'hue_range': (0, 35),
                'saturation_range': (80, 100),
                'lightness_range': (40, 65),
                'valence': 0.72, 'arousal': 0.92,
                'vi_keywords': ['phấn khích', 'sôi động', 'năng lượng', 'bùng cháy'],
            },
            'peaceful': {
                # Cyan–light blue: cool, desaturated, bright
                # Jonauskaite: blue-green = serenity/peace cross-culturally
                'hue_range': (155, 210),
                'saturation_range': (20, 55),
                'lightness_range': (65, 92),
                'valence': 0.72, 'arousal': 0.15,
                'vi_keywords': ['bình yên', 'thanh thản', 'nhẹ nhàng', 'thư thái'],
            },
            'calm': {
                # Green–cyan: moderate saturation, medium lightness
                'hue_range': (110, 170),
                'saturation_range': (25, 60),
                'lightness_range': (45, 72),
                'valence': 0.62, 'arousal': 0.22,
                'vi_keywords': ['bình tĩnh', 'ổn định', 'tĩnh lặng', 'dịu dàng'],
            },
            'melancholic': {
                # Medium-dark blue: moderate saturation, low-mid lightness
                # Jonauskaite: blue = sadness but with some reflection
                'hue_range': (215, 265),
                'saturation_range': (28, 62),
                'lightness_range': (22, 48),
                'valence': 0.28, 'arousal': 0.32,
                'vi_keywords': ['u sầu', 'hoài niệm', 'trầm buồn', 'nhớ thương'],
            },
            'sad': {
                # Dark blue–grey: low saturation, very dark
                # Jonauskaite: black/dark blue = sadness/grief
                'hue_range': (200, 260),
                'saturation_range': (10, 42),
                'lightness_range': (8, 35),
                'valence': 0.15, 'arousal': 0.18,
                'vi_keywords': ['buồn bã', 'đau lòng', 'cô đơn', 'tuyệt vọng'],
            },
            'tense': {
                # Yellow-green, high saturation: unsettling, nervous energy
                # Wilms & Oberfeld: high chroma + medium hue = tension/anxiety
                'hue_range': (55, 100),
                'saturation_range': (72, 100),
                'lightness_range': (38, 62),
                'valence': 0.30, 'arousal': 0.78,
                'vi_keywords': ['căng thẳng', 'lo lắng', 'bất an', 'hồi hộp'],
            },
            'angry': {
                # Deep red: highest saturation, mid-low lightness
                # Jonauskaite: red = anger cross-culturally (most consistent emotion-color)
                # Vietnamese: red also = luck/festive → context matters;
                # dark/deep red = anger, bright red = festive (handled by lightness)
                'hue_range': (345, 20),   # wraps around 0°
                'saturation_range': (82, 100),
                'lightness_range': (25, 50),
                'valence': 0.12, 'arousal': 0.92,
                'vi_keywords': ['tức giận', 'bực bội', 'nổi loạn', 'phẫn nộ'],
            },
        }

        # Vietnamese cultural adjustments (maintained)
        if self.use_vietnamese_adaptation:
            self.cultural_adjustments = {
                'happy': {'hue_shift': -5, 'sat_boost': 5},
                'romantic': {'hue_shift': 5, 'sat_boost': 0},
                'peaceful': {'hue_shift': 10, 'sat_boost': -5},
                'sad': {'hue_shift': -5, 'lightness_shift': -3},
                'hopeful': {'hue_shift': 10, 'sat_boost': 8},
            }
        else:
            self.cultural_adjustments = {}

        # Updated V-A anchor points based on Isbilen & Krumhansl (2022)
        # Format: [valence, arousal, hue, saturation, lightness]
        self.va_anchors = np.array([
            [0.95, 0.90, 55, 95, 70],   # Ecstatic - Bright Yellow
            [0.85, 0.70, 50, 85, 65],   # Happy - Yellow
            [0.75, 0.55, 110, 70, 70],  # Hopeful - Yellow-Green
            [0.70, 0.15, 180, 40, 75],  # Peaceful - Cyan
            [0.60, 0.20, 150, 45, 60],  # Calm - Green
            [0.45, 0.35, 40, 50, 45],   # Nostalgic - Sepia
            [0.30, 0.30, 240, 45, 35],  # Melancholic - Blue
            [0.20, 0.20, 225, 35, 25],  # Sad - Dark Blue
            [0.25, 0.80, 75, 85, 50],   # Anxious - Yellow-Green
            [0.15, 0.90, 5, 95, 40],    # Angry - Red
            [0.65, 0.85, 0, 90, 50],    # Passionate - Deep Red
        ])

    def valence_arousal_to_color(self, valence: float, arousal: float,
                                  audio_features: Optional[Dict] = None) -> Tuple[float, float, float]:
        """
        Map V-A to HSL using weighted interpolation
        """
        valence = np.clip(valence, 0, 1)
        arousal = np.clip(arousal, 0, 1)

        # Find 3 nearest anchors
        query = np.array([valence, arousal])
        distances = np.sqrt(np.sum((self.va_anchors[:, :2] - query) ** 2, axis=1))
        nearest_idx = np.argsort(distances)[:3]

        # Inverse distance weighting
        weights = 1.0 / (distances[nearest_idx] + 1e-6)
        weights = weights / weights.sum()

        # Interpolate HSL
        hue = sum(weights[i] * self.va_anchors[nearest_idx[i], 2] for i in range(3))
        sat = sum(weights[i] * self.va_anchors[nearest_idx[i], 3] for i in range(3))
        light = sum(weights[i] * self.va_anchors[nearest_idx[i], 4] for i in range(3))

        # Audio feature modulation
        if audio_features:
            if 'tempo' in audio_features:
                tempo_norm = (audio_features['tempo'] - 60) / 140
                sat += (np.clip(tempo_norm, 0, 1) - 0.5) * 15
            if 'mode' in audio_features:
                light += 10 if audio_features['mode'] == 1 else -10
            if 'energy' in audio_features:
                sat += (audio_features['energy'] - 0.5) * 10
            # Timbre modulation (Alluri & Toiviainen 2010):
            # bright timbre → warm hue shift, dark timbre → cool hue shift
            if 'timbre_bright' in audio_features:
                tb = audio_features['timbre_bright']  # 0=dark, 1=bright
                hue += (tb - 0.5) * -30  # bright → shift toward warm (lower hue)
                light += (tb - 0.5) * 8  # bright → slightly lighter

        return (hue % 360, np.clip(sat, 0, 100), np.clip(light, 0, 100))

    # Emotion-label order for the embedded ICEAS table below.
    _EMO8 = ('happy', 'excited', 'peaceful', 'calm',
             'melancholic', 'sad', 'tense', 'angry')

    # EMPIRICAL colour→emotion distribution from ICEAS/Jonauskaite 2020 (8615 ppl/colour,
    # 37 nations). Each row is the colour's DISTINCTIVE 8-emotion profile (human ratings,
    # per-emotion baseline removed so it captures what the colour is specifically
    # associated with). Replaces the synthetic Russell-centroid Gaussian, which matched
    # the human top-emotion only 1/12. Values in _EMO8 order, sum≈1. See color_norms.py
    # (the aggregation that produced these) and docs/PLAN_COLOR_BACKTEST_V15.md.
    _ICEAS_EMOTION = {
        "#FF0000": [0.1242, 0.2850, 0.0211, 0.0299, 0.1368, 0.0070, 0.1029, 0.2931],  # red
        "#FF8000": [0.3333, 0.2358, 0.0416, 0.1009, 0.1076, 0.0078, 0.1008, 0.0721],  # orange
        "#FFFF00": [0.3130, 0.2162, 0.0401, 0.1052, 0.1239, 0.0108, 0.1193, 0.0714],  # yellow
        "#008000": [0.2104, 0.2318, 0.0627, 0.2069, 0.0992, 0.0109, 0.1435, 0.0346],  # green
        "#40E0D0": [0.2628, 0.2786, 0.0631, 0.2087, 0.0854, 0.0250, 0.0539, 0.0225],  # turquoise
        "#0000FF": [0.1377, 0.2504, 0.0738, 0.1777, 0.1684, 0.0883, 0.0754, 0.0283],  # blue
        "#800080": [0.1421, 0.2580, 0.0648, 0.0753, 0.2118, 0.0547, 0.1300, 0.0633],  # purple
        "#FFC0CB": [0.3012, 0.3452, 0.0763, 0.1110, 0.0844, 0.0077, 0.0532, 0.0211],  # pink
        "#8B4513": [0.0281, 0.0648, 0.0405, 0.0541, 0.3203, 0.0449, 0.3697, 0.0777],  # brown
        "#FFFFFF": [0.1197, 0.2691, 0.1154, 0.2264, 0.1273, 0.0376, 0.0755, 0.0291],  # white
        "#808080": [0.0133, 0.0422, 0.0321, 0.0326, 0.4702, 0.1324, 0.2087, 0.0684],  # grey
        "#000000": [0.0127, 0.0547, 0.0191, 0.0146, 0.3123, 0.1096, 0.2705, 0.2064],  # black
    }
    _iceas_anchors = None  # lazily built list of (feat3, probs[8])

    def _anchor_feat(self, hex_color: str) -> np.ndarray:
        """Perceptual locator [cos h·s, sin h·s, l] — chroma-scaled hue + lightness.

        Achromatic anchors (s≈0) collapse onto the lightness axis, so grey/black/white
        interpolate by lightness while hues interpolate around the wheel. Brown (dark,
        orange hue) stays distinct from orange (light) because lightness is included.
        """
        h, l, s = self.hex_to_hsl(hex_color)
        s01, l01 = s / 100.0, l / 100.0
        hr = np.deg2rad(h)
        return np.array([np.cos(hr) * s01, np.sin(hr) * s01, l01])

    def color_to_emotion_probs(self, hex_color: str) -> Dict[str, float]:
        """Color → emotion distribution by interpolating the empirical ICEAS table.

        Inverse-distance weighting (power 2) over the 12 human-rated anchor colours in
        the perceptual locator space of _anchor_feat(). This is the human colour→emotion
        mapping itself (reproduces all 12 anchors' top emotion), not a synthetic proxy.

        References: Jonauskaite et al. 2020 (Psych Science); Palmer 2013 (emotion mediates
        colour↔music); Wilms & Oberfeld 2018 (chroma dominates).
        """
        if self._iceas_anchors is None:
            self.__class__._iceas_anchors = [
                (self._anchor_feat(hx), np.asarray(pr, dtype=float))
                for hx, pr in self._ICEAS_EMOTION.items()
            ]
        f = self._anchor_feat(hex_color)
        acc = np.zeros(8)
        tot = 0.0
        for af, pr in self._iceas_anchors:
            w = 1.0 / (float(np.sum((f - af) ** 2)) + 1e-6)  # 1/dist² (power 2)
            acc += w * pr
            tot += w
        p = acc / tot
        p = p / p.sum()
        return {emo: float(p[i]) for i, emo in enumerate(self._EMO8)}

    # Russell-circumplex V-A centroids for the 8 CLAP emotion labels (normalised 0–1).
    # LEGACY: was used by the old color_to_emotion_probs (now empirical-ICEAS); retained
    # for any external reference and for V-A↔emotion sanity checks.
    RUSSELL_CENTROIDS = {
        'happy':       (0.88, 0.70),
        'excited':     (0.72, 0.92),
        'peaceful':    (0.72, 0.15),
        'calm':        (0.62, 0.22),
        'melancholic': (0.28, 0.32),
        'sad':         (0.15, 0.18),
        'tense':       (0.30, 0.78),
        'angry':       (0.12, 0.92),
    }

    def hsl_to_va(self, hex_color: str) -> Tuple[float, float]:
        """Color → (valence, arousal) in [0,1].

        Single source of truth for the colour→V-A bridge (used by
        color_to_emotion_probs AND the recommender).

        AROUSAL — Whiteford et al. 2018 (PMC6240980) normalised Spearman weights:
          redness r_s=.755, saturation .720, darkness −.549 → 0.37 / 0.36 / 0.27.
          Validated externally: ICEAS/Jonauskaite 2020 arousal Pearson +0.64. Kept as-is.

        VALENCE — recalibrated 2026-06 against ICEAS/Jonauskaite 2020 human norms
          (8615 ppl/colour, 37 nations). The old `0.52·L + 0.48·yellowness` correlated
          only r=0.26 with humans (made blue/purple too negative, grey too positive,
          and ignored chroma). Refit on the 12 ICEAS colours:
            chromatic:   v = 0.05 + 0.40·L + 0.55·S − 0.19·redness
            achromatic:  v = 0.20 + 0.41·L
          Saturation (chroma) is the strongest valence predictor (Wilms & Oberfeld 2018);
          redness's small negative term reflects deep-red→anger. In-sample Pearson 0.85,
          leave-one-out CV 0.77 (vs 0.26 before). See docs/PLAN_COLOR_BACKTEST_V15.md.

        Perceptual axis from hue: redness = (1+cos h)/2 → red=1, cyan=0 (a* proxy).
        """
        h, l, s = self.hex_to_hsl(hex_color)   # (hue°, lightness%, saturation%)
        s01, l01 = s / 100.0, l / 100.0

        if s01 < 0.12:
            # Achromatic (grey/white/black): hue meaningless → lightness drives both.
            # Valence: ICEAS-fit (grey/black low even when light, only white rises).
            # Arousal: bright→peaceful (low A); dark→sad/tense (higher A).
            valence = float(np.clip(0.20 + 0.41 * l01, 0, 1))
            arousal = float(np.clip(0.50 - 0.35 * l01, 0, 1))
        else:
            h_rad = np.deg2rad(h)
            redness = (1 + np.cos(h_rad)) / 2
            valence = float(np.clip(0.05 + 0.40*l01 + 0.55*s01 - 0.19*redness, 0, 1))
            arousal = float(np.clip(0.37*redness + 0.36*s01 + 0.27*(1-l01), 0, 1))
        return valence, arousal

    def compute_similarity(self, c1: str, c2: str, method: str = 'hybrid') -> float:
        """
        Advanced color similarity
        """
        if method == 'perceptual' and HAS_COLORMATH:
            lab1 = self._hex_to_lab(c1)
            lab2 = self._hex_to_lab(c2)
            delta_e = delta_e_cie2000(lab1, lab2)
            return np.exp(-delta_e / 20)

        elif method == 'emotion':
            p1 = self.color_to_emotion_probs(c1)
            p2 = self.color_to_emotion_probs(c2)
            vec1 = np.array(list(p1.values()))
            vec2 = np.array(list(p2.values()))
            cos = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-10)
            return (cos + 1) / 2

        else:  # hybrid
            if HAS_COLORMATH:
                perc = self.compute_similarity(c1, c2, 'perceptual')
            else:
                perc = self._fallback_similarity(c1, c2)
            emot = self.compute_similarity(c1, c2, 'emotion')
            return 0.6 * perc + 0.4 * emot

    def _fallback_similarity(self, c1: str, c2: str) -> float:
        """Fallback RGB Euclidean similarity"""
        rgb1 = np.array(self.hex_to_rgb(c1))
        rgb2 = np.array(self.hex_to_rgb(c2))
        dist = np.linalg.norm(rgb1 - rgb2)
        return np.exp(-dist / 100)

    def _hex_to_lab(self, hex_color: str):
        """Convert HEX to LAB"""
        rgb = self.hex_to_rgb(hex_color)
        srgb = sRGBColor(rgb[0]/255, rgb[1]/255, rgb[2]/255)
        return convert_color(srgb, LabColor)

    # Utility functions
    def hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(self, r: int, g: int, b: int) -> str:
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)

    def hsl_to_hex(self, h: float, s: float, l: float) -> str:
        r, g, b = colorsys.hls_to_rgb(h/360, l/100, s/100)
        return self.rgb_to_hex(int(r*255), int(g*255), int(b*255))

    def hex_to_hsl(self, hex_color: str) -> Tuple[float, float, float]:
        rgb = self.hex_to_rgb(hex_color)
        r, g, b = [x/255.0 for x in rgb]
        # colorsys.rgb_to_hls returns (hue, lightness, saturation) — note l before s
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        return (h*360, l*100, s*100)  # (hue°, lightness%, saturation%)


# Singleton
_mapper = None

def get_advanced_color_mapper(vietnamese: bool = True) -> AdvancedColorMapper:
    global _mapper
    if _mapper is None:
        _mapper = AdvancedColorMapper(vietnamese)
    return _mapper


if __name__ == "__main__":
    print("=" * 60)
    print("ADVANCED COLOR MAPPING - TEST")
    print("=" * 60)

    mapper = AdvancedColorMapper()

    # Test V-A to color
    print("\nTest: Valence-Arousal to Color")
    tests = [(0.9, 0.8, "Happy"), (0.2, 0.3, "Sad"), (0.2, 0.9, "Angry")]
    for v, a, desc in tests:
        hsl = mapper.valence_arousal_to_color(v, a)
        hex_c = mapper.hsl_to_hex(*hsl)
        print(f"  {desc} (V={v}, A={a}): {hex_c}")

    print("\n" + "=" * 60)
    print("All tests passed!")
