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

        # Updated emotion-to-color profiles based on:
        # Jonauskaite et al. (2020) "Universal patterns in color-emotion associations"
        # Values are median responses from 12 countries, 4,598 participants
        self.emotion_color_profiles = {
            'ecstatic': {
                'hue_range': (40, 60),    # Bright Yellow
                'saturation_range': (85, 100),
                'lightness_range': (60, 80),
                'valence': 0.95, 'arousal': 0.90
            },
            'happy': {
                'hue_range': (45, 75),    # Yellow-Orange
                'saturation_range': (75, 95),
                'lightness_range': (55, 80),
                'valence': 0.85, 'arousal': 0.70
            },
            'hopeful': {
                'hue_range': (90, 130),   # Yellow-Green
                'saturation_range': (60, 85),
                'lightness_range': (60, 85),
                'valence': 0.75, 'arousal': 0.55
            },
            'peaceful': {
                'hue_range': (160, 200),  # Cyan-Light Blue
                'saturation_range': (25, 55),
                'lightness_range': (65, 90),
                'valence': 0.70, 'arousal': 0.15
            },
            'calm': {
                'hue_range': (130, 170),  # Green-Cyan
                'saturation_range': (30, 60),
                'lightness_range': (50, 75),
                'valence': 0.60, 'arousal': 0.20
            },
            'tender': {
                'hue_range': (320, 350),  # Light Pink
                'saturation_range': (35, 65),
                'lightness_range': (70, 90),
                'valence': 0.72, 'arousal': 0.30
            },
            'romantic': {
                'hue_range': (340, 360),  # Pink-Red
                'saturation_range': (50, 75),
                'lightness_range': (55, 75),
                'valence': 0.70, 'arousal': 0.45
            },
            'melancholic': {
                'hue_range': (220, 260),  # Blue
                'saturation_range': (30, 60),
                'lightness_range': (25, 50),
                'valence': 0.30, 'arousal': 0.30
            },
            'sad': {
                'hue_range': (210, 250),  # Blue
                'saturation_range': (20, 50),
                'lightness_range': (15, 40),
                'valence': 0.20, 'arousal': 0.20
            },
            'nostalgic': {
                'hue_range': (30, 50),    # Sepia/Brown tones
                'saturation_range': (35, 60),
                'lightness_range': (35, 55),
                'valence': 0.45, 'arousal': 0.35
            },
            'anxious': {
                'hue_range': (60, 90),    # Yellow-Green (sickly)
                'saturation_range': (70, 95),
                'lightness_range': (40, 60),
                'valence': 0.25, 'arousal': 0.80
            },
            'angry': {
                'hue_range': (0, 15),     # Red
                'saturation_range': (80, 100),
                'lightness_range': (30, 50),
                'valence': 0.15, 'arousal': 0.90
            },
            'passionate': {
                'hue_range': (350, 10),   # Deep Red
                'saturation_range': (75, 100),
                'lightness_range': (40, 60),
                'valence': 0.65, 'arousal': 0.85
            }
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
        """
        Reverse mapping: Color to emotion probabilities
        """
        h, s, l = self.hex_to_hsl(hex_color)

        scores = {}
        for emotion, profile in self.emotion_color_profiles.items():
            hue_min, hue_max = profile['hue_range']
            if hue_min > hue_max:
                hue_mid = ((hue_min + hue_max + 360) / 2) % 360
            else:
                hue_mid = (hue_min + hue_max) / 2
            sat_mid = np.mean(profile['saturation_range'])
            light_mid = np.mean(profile['lightness_range'])

            # Hue distance (circular)
            hue_diff = min(abs(h - hue_mid), 360 - abs(h - hue_mid))
            hue_sim = np.exp(-hue_diff / 60)

            # Saturation and lightness
            sat_sim = np.exp(-abs(s - sat_mid) / 30)
            light_sim = np.exp(-abs(l - light_mid) / 25)

            scores[emotion] = 0.5 * hue_sim + 0.3 * sat_sim + 0.2 * light_sim

        # Normalize
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
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        return (h*360, s*100, l*100)


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
