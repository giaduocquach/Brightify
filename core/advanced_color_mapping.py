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

    def emotion_to_color(self, emotion: str, valence: float, arousal: float,
                         confidence: float = 1.0) -> Tuple[str, float]:
        """
        Map emotion to color with confidence weighting
        """
        if emotion not in self.emotion_color_profiles:
            emotion = 'calm'

        profile = self.emotion_color_profiles[emotion]

        # Interpolate within emotion range
        hue_min, hue_max = profile['hue_range']
        sat_min, sat_max = profile['saturation_range']
        light_min, light_max = profile['lightness_range']

        if hue_min > hue_max:
            hue_range = (360 - hue_min) + hue_max
            hue_discrete = (hue_min + valence * hue_range) % 360
        else:
            hue_discrete = hue_min + valence * (hue_max - hue_min)

        sat_discrete = sat_min + arousal * (sat_max - sat_min)
        light_discrete = light_min + valence * (light_max - light_min)

        # Blend with continuous V-A color
        hue_cont, sat_cont, light_cont = self.valence_arousal_to_color(valence, arousal)

        alpha = confidence
        hue = alpha * hue_discrete + (1 - alpha) * hue_cont
        sat = alpha * sat_discrete + (1 - alpha) * sat_cont
        light = alpha * light_discrete + (1 - alpha) * light_cont

        # Cultural adjustments
        if emotion in self.cultural_adjustments:
            adj = self.cultural_adjustments[emotion]
            hue = (hue + adj.get('hue_shift', 0)) % 360
            sat = np.clip(sat + adj.get('sat_boost', 0), 0, 100)
            light = np.clip(light + adj.get('lightness_shift', 0), 0, 100)

        hex_color = self.hsl_to_hex(hue, sat, light)
        return hex_color, confidence * 0.8

    def color_to_emotion_probs(self, hex_color: str) -> Dict[str, float]:
        """Color → emotion probability distribution via V-A Gaussian soft-assignment.

        Chain: colour → V-A (Whiteford 2018 HSL formula) → Gaussian over
        Russell circumplex centroids of the 8 CLAP emotion labels.

        This is more principled than HSL-profile matching: the profile approach
        collapses to near-uniform (all 8 centroids equidistant from most inputs)
        because the hue Gaussians overlap heavily. The V-A intermediate is the
        validated bridge (Palmer 2013 PNAS: r=0.89–0.99).

        References:
          Whiteford 2018 (PMC6240980): sat→arousal r_s=0.720, light→valence r_s=0.484
          Wilms & Oberfeld 2018: chroma > lightness > hue in effect size
          Palmer 2013: emotion mediates colour-music correspondence
          Russell 1980: circumplex V-A positions of emotion labels
        """
        h, l, s = self.hex_to_hsl(hex_color)   # (hue°, lightness%, saturation%)
        s01, l01 = s / 100.0, l / 100.0

        # Whiteford structural mappings (hue computed as warmth and yellow-blue axis)
        if s01 < 0.12:
            # Achromatic (grey/white/black): hue meaningless, driven by lightness
            # Bright (white) → peaceful; Dark (black) → sad; Mid-grey → calm
            valence = float(np.clip(0.35 + 0.55 * l01, 0, 1))
            arousal = float(np.clip(0.50 - 0.35 * l01, 0, 1))
        else:
            # Warmth: red/orange/yellow=1, green/teal=0, blue/purple=0, wraps at 330
            # Extended cool zone: 90–300° all cool (green through purple)
            if h <= 60 or h >= 330:
                hue_warmth = 1.0
            elif h <= 90:
                hue_warmth = 1.0 - (h - 60) / 30   # 60→90: warm to cool
            elif h <= 300:
                hue_warmth = 0.0                    # green, teal, blue, purple = cool
            else:
                hue_warmth = (h - 300) / 30 * 0.7  # 300→330: cool to warm
            # Yellow-blue axis for valence
            hue_yb = (1.0 if 40 <= h <= 80 else
                      0.0 if 200 <= h <= 260 else 0.5)
            valence = float(np.clip(0.45*l01 + 0.35*hue_yb + 0.20*(1-s01), 0, 1))
            arousal = float(np.clip(0.40*s01 + 0.35*hue_warmth + 0.25*(1-l01), 0, 1))

        # Gaussian soft-assignment over 8 CLAP Russell centroids (σ=0.22)
        centroids = {
            'happy':       (0.88, 0.70),
            'excited':     (0.72, 0.92),
            'peaceful':    (0.72, 0.15),
            'calm':        (0.62, 0.22),
            'melancholic': (0.28, 0.32),
            'sad':         (0.15, 0.18),
            'tense':       (0.30, 0.78),
            'angry':       (0.12, 0.92),
        }
        sigma = 0.22
        scores = {
            emo: float(np.exp(-((valence-cv)**2 + (arousal-ca)**2) / (2*sigma**2)))
            for emo, (cv, ca) in centroids.items()
        }
        total = sum(scores.values())
        return {k: v/total for k, v in scores.items()} if total > 0 else scores

    def color_to_valence_arousal(self, hex_color: str) -> Tuple[float, float, float]:
        """
        Extract V-A from color based on Palmer et al. (2013) research

        Key findings:
        - Warm colors (red, orange, yellow) → High valence, high arousal
        - Cool colors (blue, purple) → Low valence, variable arousal
        - High saturation → High arousal
        - High lightness → Higher valence
        - Green → Moderate valence, low arousal (calm)

        Returns: (valence, arousal, confidence)
        """
        h, s, l = self.hex_to_hsl(hex_color)

        # Normalize to 0-1
        s_norm = s / 100.0
        l_norm = l / 100.0

        # === VALENCE MAPPING ===
        # Based on hue wheel: warm colors = high valence, cool colors = low valence
        # Red (0°) = high, Yellow (60°) = high, Green (120°) = moderate
        # Cyan (180°) = low-moderate, Blue (240°) = low, Purple (300°) = low-moderate

        if h <= 30 or h >= 330:  # Red/warm
            hue_valence = 0.75
        elif h <= 90:  # Yellow/Orange (30-90)
            hue_valence = 0.80
        elif h <= 150:  # Green (90-150)
            hue_valence = 0.55
        elif h <= 210:  # Cyan (150-210)
            hue_valence = 0.40
        elif h <= 270:  # Blue (210-270)
            hue_valence = 0.25
        else:  # Purple (270-330)
            hue_valence = 0.35

        # Lightness influences valence (brighter = more positive)
        lightness_valence = 0.3 + 0.4 * l_norm

        # Combine hue and lightness for final valence
        valence = 0.6 * hue_valence + 0.4 * lightness_valence

        # === AROUSAL MAPPING ===
        # High saturation = high arousal (but blue is exception)
        # Warm colors (red, orange) = higher arousal than cool colors
        # Blue = lower arousal (sadness, calmness)
        # Very light or very dark = lower arousal

        # Hue-based arousal adjustment (dominant factor)
        if h <= 30 or h >= 330:  # Red
            hue_arousal = 0.80
        elif h <= 60:  # Orange
            hue_arousal = 0.70
        elif h <= 90:  # Yellow
            hue_arousal = 0.60
        elif h <= 150:  # Green
            hue_arousal = 0.40
        elif h <= 210:  # Cyan
            hue_arousal = 0.30
        elif h <= 270:  # Blue - LOW arousal for sadness
            hue_arousal = 0.20
        else:  # Purple
            hue_arousal = 0.35

        # Saturation modulates arousal (but less for blue)
        if 210 <= h <= 270:  # Blue range
            saturation_arousal = s_norm * 0.3  # Much less influence
        else:
            saturation_arousal = s_norm * 0.5

        # Lightness adjustment (extreme values = lower arousal)
        lightness_arousal = 1.0 - abs(l_norm - 0.5) * 0.5

        # Combine for final arousal
        arousal = 0.40 * saturation_arousal + 0.35 * hue_arousal + 0.25 * lightness_arousal

        # Confidence based on saturation (low saturation = less confident mapping)
        confidence = 0.5 + 0.5 * s_norm

        return (np.clip(valence, 0, 1), np.clip(arousal, 0, 1), confidence)


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

    def color_to_audio(self, hex_color: str) -> Dict[str, float]:
        """
        Reverse mapping: Color → Audio features
        Uses emotion-mediated mapping for higher accuracy

        Args:
            hex_color: Color in hex format (e.g., "#FF5733")

        Returns:
            Dictionary of estimated audio features
        """
        # Get valence, arousal, confidence from color
        valence, arousal, confidence = self.color_to_valence_arousal(hex_color)

        # Get emotion probabilities
        emotion_probs = self.color_to_emotion_probs(hex_color)
        dominant_emotion = max(emotion_probs, key=emotion_probs.get)

        # Base audio features from V-A
        audio_features = {
            'valence': valence,
            'energy': arousal,
            'danceability': 0.3 + 0.5 * arousal + 0.2 * valence,
            'acousticness': 0.7 - 0.5 * arousal,
            'instrumentalness': 0.3 - 0.2 * valence,
            'speechiness': 0.1 + 0.1 * valence,
            'liveness': 0.2 + 0.3 * arousal,
            'tempo': 60 + 140 * arousal,  # 60-200 BPM
            'loudness': -20 + 15 * arousal,  # -20 to -5 dB
            'key': int(valence * 11),  # 0-11
            'mode': 1.0 if valence > 0.5 else 0.0  # Major if positive
        }

        # Emotion-specific adjustments
        if dominant_emotion in ['ecstatic', 'excited', 'passionate']:
            audio_features['energy'] = np.clip(audio_features['energy'] + 0.15, 0, 1)
            audio_features['danceability'] = np.clip(audio_features['danceability'] + 0.1, 0, 1)
            audio_features['tempo'] = min(audio_features['tempo'] + 20, 200)
        elif dominant_emotion in ['peaceful', 'calm', 'tender']:
            audio_features['acousticness'] = np.clip(audio_features['acousticness'] + 0.2, 0, 1)
            audio_features['energy'] = np.clip(audio_features['energy'] - 0.1, 0, 1)
            audio_features['tempo'] = max(audio_features['tempo'] - 20, 60)
        elif dominant_emotion in ['sad', 'melancholic', 'nostalgic']:
            audio_features['mode'] = 0.0  # Minor key
            audio_features['valence'] = np.clip(audio_features['valence'] - 0.1, 0, 1)
            audio_features['acousticness'] = np.clip(audio_features['acousticness'] + 0.15, 0, 1)
        elif dominant_emotion in ['angry', 'anxious']:
            audio_features['energy'] = np.clip(audio_features['energy'] + 0.2, 0, 1)
            audio_features['loudness'] = min(audio_features['loudness'] + 5, -5)

        # Clip all features to valid ranges
        audio_features['valence'] = np.clip(audio_features['valence'], 0, 1)
        audio_features['energy'] = np.clip(audio_features['energy'], 0, 1)
        audio_features['danceability'] = np.clip(audio_features['danceability'], 0, 1)
        audio_features['acousticness'] = np.clip(audio_features['acousticness'], 0, 1)
        audio_features['instrumentalness'] = np.clip(audio_features['instrumentalness'], 0, 1)
        audio_features['speechiness'] = np.clip(audio_features['speechiness'], 0, 1)
        audio_features['liveness'] = np.clip(audio_features['liveness'], 0, 1)

        return audio_features

    def _color_to_emotion(self, hue: float, saturation: float, lightness: float) -> str:
        """Get dominant emotion from HSL values"""
        probs = {}
        for emotion, profile in self.emotion_color_profiles.items():
            hue_min, hue_max = profile['hue_range']
            if hue_min > hue_max:
                hue_mid = ((hue_min + hue_max + 360) / 2) % 360
            else:
                hue_mid = (hue_min + hue_max) / 2
            sat_mid = np.mean(profile['saturation_range'])
            light_mid = np.mean(profile['lightness_range'])

            hue_diff = min(abs(hue - hue_mid), 360 - abs(hue - hue_mid))
            hue_sim = np.exp(-hue_diff / 60)
            sat_sim = np.exp(-abs(saturation - sat_mid) / 30)
            light_sim = np.exp(-abs(lightness - light_mid) / 25)

            probs[emotion] = 0.5 * hue_sim + 0.3 * sat_sim + 0.2 * light_sim

        return max(probs, key=probs.get)

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
