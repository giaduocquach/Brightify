"""
Image-to-Music Analysis Module
Multi-modal image understanding for music recommendation

Pipeline:
1. Dominant Color Extraction (Center-weighted K-Means)
2. CLIP-based Scene & Emotion Understanding (Zero-shot)
3. Visual Atmosphere Analysis (Brightness, Saturation, Temperature)
4. Multi-signal Fusion → Emotion Profile → Music Recommendation

Research References:
- Radford et al. (2021) "Learning Transferable Visual Models From Natural Language Supervision" (CLIP)
- Palmer et al. (2013) "Music-color associations are mediated by emotion"
- Jonauskaite et al. (2020) "Universal patterns in color-emotion associations"
- Valdez & Mehrabian (1994) "Effects of color on emotions"

Author: Brightify Team
Date: March 2026
Version: 1.0
"""

import numpy as np
import colorsys
from typing import Dict, List, Tuple, Optional
from io import BytesIO
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

# Image processing
from PIL import Image

# ML
from sklearn.cluster import KMeans

# CLIP model for scene understanding
import torch
from transformers import CLIPProcessor, CLIPModel


# ============================================================================
# Configuration
# ============================================================================

# Emotion prompts for CLIP zero-shot classification
# Using English prompts (CLIP is trained on English)
CLIP_EMOTION_PROMPTS = {
    'happy': [
        "a happy joyful scene",
        "people smiling and laughing",
        "bright cheerful atmosphere",
        "celebration and joy",
        "sunny happy day"
    ],
    'sad': [
        "a sad melancholic scene",
        "lonely person in the rain",
        "dark gloomy atmosphere",
        "feeling of sadness and loss",
        "empty desolate place"
    ],
    'peaceful': [
        "a peaceful calm landscape",
        "serene tranquil nature",
        "quiet meditation scene",
        "gentle soothing atmosphere",
        "still lake at sunset"
    ],
    'excited': [
        "an exciting energetic scene",
        "vibrant party atmosphere",
        "dynamic action and movement",
        "colorful festival celebration",
        "thrilling adventure"
    ],
    'romantic': [
        "a romantic love scene",
        "couple in beautiful sunset",
        "soft pink dreamy atmosphere",
        "candlelight dinner romance",
        "love and affection"
    ],
    'melancholic': [
        "a nostalgic melancholic scene",
        "autumn leaves falling",
        "misty morning memories",
        "old photographs and memories",
        "bittersweet reminiscence"
    ],
    'angry': [
        "an intense angry scene",
        "stormy dramatic weather",
        "fire and destruction",
        "dark aggressive atmosphere",
        "chaos and conflict"
    ],
    'calm': [
        "a calm relaxing environment",
        "zen garden meditation",
        "gentle waves on a beach",
        "soft morning light",
        "peaceful countryside"
    ],
    'longing': [
        "a scene of longing and yearning",
        "looking at distant horizon",
        "waiting at the window",
        "faraway places and dreams",
        "missing someone dear"
    ],
    'hope': [
        "a hopeful inspiring scene",
        "sunrise over mountains",
        "rainbow after the storm",
        "light breaking through clouds",
        "new beginnings and growth"
    ]
}

# Scene-to-mood mapping for additional context
SCENE_MOOD_PROMPTS = {
    'nature_calm': "peaceful nature landscape with mountains or forests",
    'nature_dramatic': "dramatic nature scene with storm or volcano",
    'urban_night': "city at night with neon lights",
    'urban_day': "bright sunny city street",
    'beach_sunset': "beautiful beach at sunset",
    'rain': "rainy day with wet streets",
    'snow': "snowy winter landscape",
    'autumn': "autumn scene with golden leaves",
    'spring': "spring with flowers blooming",
    'night_sky': "starry night sky",
    'party': "party celebration with people dancing",
    'solitude': "person alone in vast landscape",
    'couple': "romantic couple together",
    'food': "delicious food and dining",
    'animal': "cute animal in nature",
    'abstract': "abstract colorful art",
    'dark': "dark moody atmosphere",
    'bright': "bright vibrant colorful scene"
}

# Map scenes to valence-arousal
SCENE_VA_MAP = {
    'nature_calm':     (0.70, 0.20),
    'nature_dramatic': (0.35, 0.80),
    'urban_night':     (0.50, 0.65),
    'urban_day':       (0.65, 0.55),
    'beach_sunset':    (0.75, 0.25),
    'rain':            (0.30, 0.30),
    'snow':            (0.45, 0.20),
    'autumn':          (0.40, 0.30),
    'spring':          (0.80, 0.55),
    'night_sky':       (0.55, 0.20),
    'party':           (0.85, 0.90),
    'solitude':        (0.30, 0.20),
    'couple':          (0.75, 0.45),
    'food':            (0.70, 0.40),
    'animal':          (0.75, 0.45),
    'abstract':        (0.55, 0.55),
    'dark':            (0.25, 0.40),
    'bright':          (0.80, 0.65),
}

# ---------------------------------------------------------------------------
# Content type classification — determines adaptive fusion weights
# Approach: CLIP zero-shot classification (Radford et al., 2021)
# ---------------------------------------------------------------------------
CONTENT_TYPE_PROMPTS = {
    'portrait':     "a close-up portrait photograph of a person's face",
    'group_photo':  "a photograph of a group of people together",
    'selfie':       "a person taking a selfie photograph",
    'landscape':    "a wide landscape photograph of natural scenery with mountains trees or water",
    'urban':        "a photograph of city buildings and urban streets",
    'indoor':       "a photograph taken inside a room or building interior",
    'food_drink':   "a photograph of food dishes or beverages",
    'animal':       "a photograph of an animal or pet",
    'object':       "a close-up photograph of an object device or product",
    'art_abstract': "abstract art painting illustration or digital artwork",
    'event':        "a photograph of a party concert wedding or social event",
    'nature_close': "a close-up of flowers leaves or natural textures",
}

# ---------------------------------------------------------------------------
# Facial expression classification — activated when person is detected
# Based on Ekman (1992) basic emotions & Mollahosseini et al. (2019) AffectNet
# AffectNet: 450K+ manually annotated facial expression images
# ---------------------------------------------------------------------------
EXPRESSION_PROMPTS = {
    'joy':           "a person with a bright genuine smile looking very happy",
    'gentle_smile':  "a person with a gentle soft subtle smile",
    'neutral':       "a person with a calm relaxed neutral expression",
    'thoughtful':    "a person looking thoughtful contemplative deep in thought",
    'sadness':       "a person looking sad sorrowful with downcast eyes",
    'surprise':      "a person looking surprised amazed with wide eyes",
    'determination': "a person looking determined focused and serious",
    'dreamy':        "a person gazing dreamily into the distance with soft eyes",
    'laughter':      "a person laughing openly with genuine joyful laughter",
    'serenity':      "a person with a peaceful serene and completely at ease expression",
    'passion':       "a person with an intense passionate fiery expression",
    'tenderness':    "a person looking tender gentle and caring with warm eyes",
}

# Russell (1980) Circumplex Model mapping for facial expressions
EXPRESSION_VA_MAP = {
    'joy':           (0.90, 0.75),
    'gentle_smile':  (0.75, 0.35),
    'neutral':       (0.50, 0.30),
    'thoughtful':    (0.45, 0.25),
    'sadness':       (0.20, 0.25),
    'surprise':      (0.60, 0.85),
    'determination': (0.55, 0.70),
    'dreamy':        (0.60, 0.20),
    'laughter':      (0.92, 0.85),
    'serenity':      (0.70, 0.15),
    'passion':       (0.65, 0.90),
    'tenderness':    (0.72, 0.25),
}

# ---------------------------------------------------------------------------
# Lighting condition — atmospheric mood signal
# Based on Knez (2001) "Effects of colour of light on nonvisual psychological
# processes and performance" + Flynn et al. (1977) lighting/mood studies
# ---------------------------------------------------------------------------
LIGHTING_PROMPTS = {
    'golden_hour':    "warm golden sunset or sunrise lighting on a scene",
    'blue_hour':      "cool blue twilight or dusk lighting",
    'bright_daylight':"bright natural daylight with clear sunshine",
    'overcast':       "soft diffused light from an overcast cloudy sky",
    'neon':           "colorful neon lights or artificial city nightlife lighting",
    'candlelight':    "warm dim candlelight or intimate low indoor lighting",
    'moonlight':      "soft cool moonlight illuminating a night scene",
    'dramatic':       "dramatic high-contrast lighting with deep shadows",
}

LIGHTING_VA_MAP = {
    'golden_hour':     (0.75, 0.35),
    'blue_hour':       (0.45, 0.25),
    'bright_daylight': (0.70, 0.60),
    'overcast':        (0.40, 0.25),
    'neon':            (0.55, 0.75),
    'candlelight':     (0.65, 0.25),
    'moonlight':       (0.50, 0.15),
    'dramatic':        (0.35, 0.70),
}


class ImageAnalyzer:
    """
    Multi-modal image analyzer for music recommendation.
    
    Extracts:
    - Dominant colors (K-Means with spatial weighting)
    - Emotional atmosphere (CLIP zero-shot classification)
    - Visual features (brightness, saturation, contrast, temperature)
    - Scene understanding (CLIP scene classification)
    
    Outputs:
    - Color palette for color-based recommendation
    - Emotion probability distribution
    - Valence-Arousal coordinates
    - Combined mood profile
    """
    
    def __init__(self, clip_model_name: str = "openai/clip-vit-base-patch32", use_gpu: bool = True):
        self.device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        
        # Check for MPS (Apple Silicon)
        if self.device == "cpu" and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            self.device = "mps"
        
        logger.info(f"Initializing Image Analyzer (device: {self.device})...")

        # Load CLIP model
        self.clip_model = CLIPModel.from_pretrained(clip_model_name).to(self.device)
        self.clip_processor = CLIPProcessor.from_pretrained(clip_model_name)
        self.clip_model.eval()

        # Pre-compute all text embeddings
        self._precompute_emotion_embeddings()
        self._precompute_scene_embeddings()
        self._precompute_content_embeddings()
        self._precompute_expression_embeddings()
        self._precompute_lighting_embeddings()

        logger.info("Image Analyzer ready (CLIP loaded, text embeddings pre-computed)")
    
    def _extract_text_features(self, texts):
        """Extract CLIP text features, handling different transformers versions."""
        with torch.no_grad():
            inputs = self.clip_processor(text=texts, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            output = self.clip_model.get_text_features(**inputs)
            # Handle both tensor and BaseModelOutputWithPooling
            if hasattr(output, 'pooler_output'):
                return output.pooler_output
            return output
    
    def _extract_image_features(self, image):
        """Extract CLIP image features, handling different transformers versions."""
        with torch.no_grad():
            inputs = self.clip_processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            output = self.clip_model.get_image_features(**inputs)
            if hasattr(output, 'pooler_output'):
                return output.pooler_output
            return output

    def _precompute_emotion_embeddings(self):
        """Pre-compute CLIP text embeddings for all emotion prompts"""
        self.emotion_categories = list(CLIP_EMOTION_PROMPTS.keys())
        all_prompts = []
        self.emotion_prompt_ranges = {}
        
        idx = 0
        for emotion, prompts in CLIP_EMOTION_PROMPTS.items():
            self.emotion_prompt_ranges[emotion] = (idx, idx + len(prompts))
            all_prompts.extend(prompts)
            idx += len(prompts)
        
        text_features = self._extract_text_features(all_prompts)
        self.emotion_text_embeddings = text_features / text_features.norm(dim=-1, keepdim=True)
    
    def _precompute_scene_embeddings(self):
        """Pre-compute CLIP text embeddings for scene prompts"""
        self.scene_categories = list(SCENE_MOOD_PROMPTS.keys())
        scene_texts = list(SCENE_MOOD_PROMPTS.values())
        
        text_features = self._extract_text_features(scene_texts)
        self.scene_text_embeddings = text_features / text_features.norm(dim=-1, keepdim=True)

    def _precompute_content_embeddings(self):
        self.content_categories = list(CONTENT_TYPE_PROMPTS.keys())
        features = self._extract_text_features(list(CONTENT_TYPE_PROMPTS.values()))
        self.content_text_embeddings = features / features.norm(dim=-1, keepdim=True)

    def _precompute_expression_embeddings(self):
        self.expression_categories = list(EXPRESSION_PROMPTS.keys())
        features = self._extract_text_features(list(EXPRESSION_PROMPTS.values()))
        self.expression_text_embeddings = features / features.norm(dim=-1, keepdim=True)

    def _precompute_lighting_embeddings(self):
        self.lighting_categories = list(LIGHTING_PROMPTS.keys())
        features = self._extract_text_features(list(LIGHTING_PROMPTS.values()))
        self.lighting_text_embeddings = features / features.norm(dim=-1, keepdim=True)

    # ----- Unified CLIP classification ------------------------------------------

    def _classify_single_prompt(self, image_features, text_embeddings, categories,
                                temperature=0.02):
        """Generic zero-shot classifier for single-prompt-per-category dicts."""
        sims = (image_features @ text_embeddings.T).squeeze(0).cpu().numpy()
        exp_s = np.exp((sims - sims.max()) / temperature)
        probs = exp_s / exp_s.sum()
        return {cat: float(probs[i]) for i, cat in enumerate(categories)}

    def _classify_emotions(self, image_features):
        """Multi-prompt averaged emotion classification."""
        sims = (image_features @ self.emotion_text_embeddings.T).squeeze(0).cpu().numpy()
        raw = {}
        for emo in self.emotion_categories:
            s, e = self.emotion_prompt_ranges[emo]
            raw[emo] = float(sims[s:e].mean())
        arr = np.array(list(raw.values()))
        exp_s = np.exp((arr - arr.max()) / 0.02)
        probs = exp_s / exp_s.sum()
        return {emo: float(probs[i]) for i, emo in enumerate(self.emotion_categories)}

    def _classify_scenes(self, image_features):
        return self._classify_single_prompt(
            image_features, self.scene_text_embeddings, self.scene_categories)

    def _classify_content(self, image_features):
        return self._classify_single_prompt(
            image_features, self.content_text_embeddings, self.content_categories)

    def _classify_expression(self, image_features):
        return self._classify_single_prompt(
            image_features, self.expression_text_embeddings, self.expression_categories)

    def _classify_lighting(self, image_features):
        return self._classify_single_prompt(
            image_features, self.lighting_text_embeddings, self.lighting_categories)
    
    def analyze_image(self, image: Image.Image) -> Dict:
        """
        Enhanced multi-modal image analysis pipeline.

        Improvements over v1:
        - Content-type detection → adaptive fusion weights
        - Facial expression analysis when person detected
          (Ekman 1992; Mollahosseini et al. 2019 AffectNet)
        - Lighting condition analysis (Knez 2001; Flynn et al. 1977)
        - Single CLIP forward pass for all classifiers (2-5× faster)
        """
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # 1. Dominant colors (center-weighted K-Means)
        colors, weights = self._extract_dominant_colors(image, n_colors=5)

        # 2. Visual atmosphere features (brightness, saturation, contrast, warmth)
        visual_features = self._analyze_visual_features(image)

        # 3. Extract CLIP image features ONCE — reuse for every classifier
        img_clip = image.copy()
        img_clip.thumbnail((336, 336))
        image_features = self._extract_image_features(img_clip)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # 4. All CLIP classifiers on shared image features
        emotion_scores = self._classify_emotions(image_features)
        scene_scores = self._classify_scenes(image_features)
        content_scores = self._classify_content(image_features)
        expression_scores = self._classify_expression(image_features)
        lighting_scores = self._classify_lighting(image_features)

        # 5. Content-type & person detection
        content_type = max(content_scores, key=content_scores.get)
        person_types = {'portrait', 'group_photo', 'selfie', 'event'}
        person_score = sum(content_scores.get(t, 0) for t in person_types)
        has_person = person_score > 0.35

        # 6. Content-aware Valence-Arousal computation
        va = self._compute_valence_arousal(
            colors, weights, visual_features, emotion_scores, scene_scores,
            content_type=content_type, has_person=has_person,
            expression_scores=expression_scores, lighting_scores=lighting_scores,
        )

        # 7. Rich mood determination
        mood_label, mood_description = self._determine_mood(
            emotion_scores, scene_scores, va, visual_features,
            content_type=content_type, has_person=has_person,
            expression_scores=expression_scores, lighting_scores=lighting_scores,
        )

        hex_colors = [self._rgb_to_hex(c) for c in colors]
        primary_expression = max(expression_scores, key=expression_scores.get) if has_person else None
        primary_lighting = max(lighting_scores, key=lighting_scores.get)

        return {
            # Core fields (backward compatible)
            'dominant_colors': hex_colors,
            'color_weights': weights.tolist(),
            'emotion_scores': emotion_scores,
            'scene_scores': scene_scores,
            'valence': float(va[0]),
            'arousal': float(va[1]),
            'brightness': visual_features['brightness'],
            'saturation': visual_features['saturation'],
            'warmth': visual_features['warmth'],
            'contrast': visual_features['contrast'],
            'mood_label': mood_label,
            'mood_description': mood_description,
            # Enhanced analysis fields
            'content_type': content_type,
            'content_scores': content_scores,
            'has_person': has_person,
            'person_confidence': float(person_score),
            'expression': primary_expression,
            'expression_scores': expression_scores,
            'lighting': primary_lighting,
            'lighting_scores': lighting_scores,
            'color_variety': visual_features.get('color_variety', 0),
        }
    
    def _extract_dominant_colors(self, image: Image.Image, n_colors: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract dominant colors using center-weighted K-Means clustering.
        
        Center pixels are weighted more highly (human attention naturally
        focuses on the center of images per eye-tracking research).
        
        Uses spatial weighting based on 2D Gaussian centered on image center.
        """
        # Resize for speed (preserve aspect ratio)
        img = image.copy()
        img.thumbnail((256, 256))
        
        pixels = np.array(img).reshape(-1, 3).astype(np.float64)
        h, w = np.array(img).shape[:2]
        
        # Create center-weighted sampling mask (2D Gaussian)
        y_coords, x_coords = np.mgrid[0:h, 0:w]
        center_y, center_x = h / 2, w / 2
        
        # Gaussian weight: emphasize center
        sigma = min(h, w) / 3
        spatial_weights = np.exp(-((x_coords - center_x)**2 + (y_coords - center_y)**2) / (2 * sigma**2))
        spatial_weights = spatial_weights.flatten()
        
        # Weighted sampling: oversample center pixels
        n_samples = min(5000, len(pixels))
        probabilities = spatial_weights / spatial_weights.sum()
        sample_indices = np.random.choice(len(pixels), size=n_samples, p=probabilities)
        sampled_pixels = pixels[sample_indices]
        
        # K-Means clustering
        kmeans = KMeans(n_clusters=n_colors, n_init=10, max_iter=300, random_state=42)
        kmeans.fit(sampled_pixels)
        
        # Get cluster centers (dominant colors)
        centers = kmeans.cluster_centers_.astype(int)
        
        # Compute weights based on full image (not just samples)
        labels = kmeans.predict(pixels)
        # Weight by spatial importance
        cluster_weights = np.zeros(n_colors)
        for i in range(n_colors):
            mask = labels == i
            cluster_weights[i] = spatial_weights[mask].sum()
        
        # Normalize weights
        cluster_weights = cluster_weights / cluster_weights.sum()
        
        # Sort by weight (most dominant first)
        sorted_idx = np.argsort(-cluster_weights)
        centers = centers[sorted_idx]
        cluster_weights = cluster_weights[sorted_idx]
        
        # Clip to valid range
        centers = np.clip(centers, 0, 255)
        
        return centers, cluster_weights
    
    def _analyze_visual_features(self, image: Image.Image) -> Dict[str, float]:
        """
        Extract visual atmosphere features from image.
        
        Based on Valdez & Mehrabian (1994):
        - Brightness → positivity, energy
        - Saturation → emotional intensity, arousal
        - Color temperature → warmth vs coolness
        - Contrast → tension, drama
        """
        img = image.copy()
        img.thumbnail((256, 256))
        
        arr = np.array(img).astype(np.float64)
        
        # === Brightness (perceived luminance) ===
        # Using BT.709 luminance coefficients
        luminance = 0.2126 * arr[:,:,0] + 0.7152 * arr[:,:,1] + 0.0722 * arr[:,:,2]
        brightness = luminance.mean() / 255.0
        
        # === Saturation (from HSV color space) ===
        # Vectorized HSV conversion
        r, g, b = arr[:,:,0]/255.0, arr[:,:,1]/255.0, arr[:,:,2]/255.0
        cmax = np.maximum(np.maximum(r, g), b)
        cmin = np.minimum(np.minimum(r, g), b)
        delta = cmax - cmin
        
        # Saturation = delta / cmax (avoiding division by zero)
        sat = np.where(cmax > 0, delta / cmax, 0)
        saturation = sat.mean()
        
        # === Color Temperature (warm vs cool) ===
        # Based on average hue: warm (red/orange/yellow) vs cool (blue/green)
        # Simple approach: ratio of warm to cool channels
        warm_energy = (arr[:,:,0].mean() + arr[:,:,1].mean() * 0.3) / 255.0
        cool_energy = (arr[:,:,2].mean() + arr[:,:,1].mean() * 0.7) / 255.0
        warmth = warm_energy / (warm_energy + cool_energy + 1e-8)
        
        # === Contrast (standard deviation of luminance) ===
        contrast = luminance.std() / 128.0  # Normalize to ~[0, 1]
        contrast = min(contrast, 1.0)
        
        # === Color Variety (number of distinct hue regions) ===
        # Compute hue histogram
        hue = np.zeros_like(r)
        nonzero = delta > 0.01
        
        # Where R is max
        mask_r = nonzero & (cmax == r)
        hue[mask_r] = (60 * ((g[mask_r] - b[mask_r]) / (delta[mask_r] + 1e-8)) + 360) % 360
        
        # Where G is max
        mask_g = nonzero & (cmax == g)
        hue[mask_g] = 60 * ((b[mask_g] - r[mask_g]) / (delta[mask_g] + 1e-8)) + 120
        
        # Where B is max
        mask_b = nonzero & (cmax == b)
        hue[mask_b] = 60 * ((r[mask_b] - g[mask_b]) / (delta[mask_b] + 1e-8)) + 240
        
        # Hue entropy as color variety measure
        hue_hist, _ = np.histogram(hue[nonzero].flatten(), bins=12, range=(0, 360))
        hue_probs = hue_hist / (hue_hist.sum() + 1e-8)
        hue_entropy = -np.sum(hue_probs * np.log2(hue_probs + 1e-8))
        color_variety = hue_entropy / np.log2(12)  # Normalize to [0, 1]
        
        return {
            'brightness': float(np.clip(brightness, 0, 1)),
            'saturation': float(np.clip(saturation, 0, 1)),
            'warmth': float(np.clip(warmth, 0, 1)),
            'contrast': float(np.clip(contrast, 0, 1)),
            'color_variety': float(np.clip(color_variety, 0, 1)),
        }
    
    def _compute_valence_arousal(
        self,
        colors: np.ndarray,
        weights: np.ndarray,
        visual_features: Dict[str, float],
        emotion_scores: Dict[str, float],
        scene_scores: Dict[str, float],
        *,
        content_type: str = 'unknown',
        has_person: bool = False,
        expression_scores: Optional[Dict[str, float]] = None,
        lighting_scores: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float]:
        """
        Content-aware V-A computation with adaptive fusion weights.

        Fusion strategy adapts to content type:
        - Person present → facial expression is primary signal
          (Mollahosseini et al. 2019: AffectNet shows facial expressions are
          the strongest emotional cue in human perception)
        - Landscape/nature → scene context + color palette dominate
          (Palmer et al. 2013; Jonauskaite et al. 2020)
        - Abstract/art → color properties drive emotional response
          (Valdez & Mehrabian 1994)
        - Lighting universally contributes to atmospheric mood
          (Knez 2001; Flynn et al. 1977)
        """

        # === Signal 1: CLIP Emotion V-A ===
        emotion_va_map = {
            'happy': (0.85, 0.70), 'sad': (0.20, 0.20), 'peaceful': (0.70, 0.15),
            'excited': (0.80, 0.90), 'romantic': (0.72, 0.40), 'melancholic': (0.30, 0.30),
            'angry': (0.20, 0.85), 'calm': (0.65, 0.20), 'longing': (0.35, 0.40),
            'hope': (0.75, 0.55),
        }
        emo_val = sum(emotion_scores.get(e, 0) * v for e, (v, _) in emotion_va_map.items())
        emo_aro = sum(emotion_scores.get(e, 0) * a for e, (_, a) in emotion_va_map.items())

        # === Signal 2: Facial Expression V-A (if person detected) ===
        expr_val, expr_aro = 0.5, 0.5
        if has_person and expression_scores:
            expr_val = sum(expression_scores.get(e, 0) * EXPRESSION_VA_MAP.get(e, (0.5, 0.5))[0]
                          for e in expression_scores)
            expr_aro = sum(expression_scores.get(e, 0) * EXPRESSION_VA_MAP.get(e, (0.5, 0.5))[1]
                          for e in expression_scores)

        # === Signal 3: Visual Features V-A (Valdez & Mehrabian 1994) ===
        vis_val = (0.4 * visual_features['brightness']
                   + 0.3 * visual_features['warmth']
                   + 0.3 * 0.5)
        vis_aro = (0.5 * visual_features['saturation']
                   + 0.3 * visual_features['contrast']
                   + 0.2 * visual_features.get('color_variety', 0.5))

        # === Signal 4: Color Palette V-A (Palmer et al. 2013) ===
        col_val, col_aro = 0.0, 0.0
        for color, w in zip(colors, weights):
            r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            hue_deg = h * 360
            if 30 <= hue_deg <= 90:
                hue_val = 0.85
            elif hue_deg < 30 or hue_deg > 330:
                hue_val = 0.55
            elif 90 < hue_deg <= 180:
                hue_val = 0.65
            elif 180 < hue_deg <= 270:
                hue_val = 0.30
            else:
                hue_val = 0.40
            col_val += w * (0.4 * hue_val + 0.3 * v + 0.3 * s * 0.5)
            col_aro += w * (0.5 * s + 0.3 * v + 0.2 * abs(hue_deg - 180) / 180)

        # === Signal 5: Scene V-A ===
        scene_val = sum(scene_scores.get(sc, 0) * SCENE_VA_MAP.get(sc, (0.5, 0.5))[0]
                        for sc in scene_scores)
        scene_aro = sum(scene_scores.get(sc, 0) * SCENE_VA_MAP.get(sc, (0.5, 0.5))[1]
                        for sc in scene_scores)

        # === Signal 6: Lighting V-A (Knez 2001) ===
        light_val, light_aro = 0.5, 0.5
        if lighting_scores:
            light_val = sum(lighting_scores.get(l, 0) * LIGHTING_VA_MAP.get(l, (0.5, 0.5))[0]
                           for l in lighting_scores)
            light_aro = sum(lighting_scores.get(l, 0) * LIGHTING_VA_MAP.get(l, (0.5, 0.5))[1]
                           for l in lighting_scores)

        # === Content-aware adaptive fusion weights ===
        if has_person:
            fw = {'emo': 0.15, 'expr': 0.30, 'vis': 0.12, 'col': 0.10,
                  'scene': 0.18, 'light': 0.15}
        elif content_type in ('landscape', 'nature_close'):
            fw = {'emo': 0.20, 'expr': 0.00, 'vis': 0.15, 'col': 0.25,
                  'scene': 0.30, 'light': 0.10}
        elif content_type == 'art_abstract':
            fw = {'emo': 0.20, 'expr': 0.00, 'vis': 0.25, 'col': 0.35,
                  'scene': 0.10, 'light': 0.10}
        elif content_type in ('urban', 'indoor'):
            fw = {'emo': 0.30, 'expr': 0.00, 'vis': 0.15, 'col': 0.15,
                  'scene': 0.25, 'light': 0.15}
        else:
            fw = {'emo': 0.35, 'expr': 0.00, 'vis': 0.20, 'col': 0.15,
                  'scene': 0.15, 'light': 0.15}

        signals_v = [emo_val, expr_val, vis_val, col_val, scene_val, light_val]
        signals_a = [emo_aro, expr_aro, vis_aro, col_aro, scene_aro, light_aro]
        wt = [fw['emo'], fw['expr'], fw['vis'], fw['col'], fw['scene'], fw['light']]

        final_val = sum(w * v for w, v in zip(wt, signals_v))
        final_aro = sum(w * a for w, a in zip(wt, signals_a))

        return (float(np.clip(final_val, 0, 1)), float(np.clip(final_aro, 0, 1)))
    
    def _determine_mood(
        self,
        emotion_scores: Dict[str, float],
        scene_scores: Dict[str, float],
        va: Tuple[float, float],
        visual_features: Dict[str, float],
        *,
        content_type: str = 'unknown',
        has_person: bool = False,
        expression_scores: Optional[Dict[str, float]] = None,
        lighting_scores: Optional[Dict[str, float]] = None,
    ) -> Tuple[str, str]:
        """
        Content-aware mood label and rich Vietnamese description.

        Adapts narrative based on detected content:
        - Person images: describe expression and interpersonal atmosphere
        - Landscapes: emphasize natural scenery and lighting
        - Abstract art: focus on color and visual energy
        """
        valence, arousal = va

        # Primary & secondary emotion
        primary_emotion = max(emotion_scores, key=emotion_scores.get)
        primary_score = emotion_scores[primary_emotion]
        sorted_emo = sorted(emotion_scores.items(), key=lambda x: -x[1])
        secondary_emotion = sorted_emo[1][0] if len(sorted_emo) > 1 else primary_emotion

        # Top scene & lighting
        top_scene = max(scene_scores, key=scene_scores.get)
        top_lighting = max(lighting_scores, key=lighting_scores.get) if lighting_scores else None
        top_expression = max(expression_scores, key=expression_scores.get) if expression_scores else None

        # Vietnamese name maps
        emotion_vi = {
            'happy': 'vui vẻ', 'sad': 'buồn bã', 'peaceful': 'bình yên',
            'excited': 'phấn khích', 'romantic': 'lãng mạn',
            'melancholic': 'u sầu', 'angry': 'mãnh liệt',
            'calm': 'thư thái', 'longing': 'nhung nhớ', 'hope': 'hy vọng',
        }
        scene_vi = {
            'nature_calm': 'thiên nhiên yên bình', 'nature_dramatic': 'thiên nhiên hùng vĩ',
            'urban_night': 'thành phố về đêm', 'urban_day': 'phố phường nhộn nhịp',
            'beach_sunset': 'hoàng hôn bên biển', 'rain': 'cơn mưa',
            'snow': 'tuyết trắng', 'autumn': 'mùa thu vàng',
            'spring': 'mùa xuân', 'night_sky': 'bầu trời đêm',
            'party': 'tiệc tùng', 'solitude': 'cô đơn lặng lẽ',
            'couple': 'tình yêu đôi lứa', 'food': 'ẩm thực',
            'animal': 'động vật dễ thương', 'abstract': 'nghệ thuật trừu tượng',
            'dark': 'bóng tối', 'bright': 'sắc màu rực rỡ',
        }
        expression_vi = {
            'joy': 'nụ cười rạng rỡ', 'gentle_smile': 'nụ cười dịu dàng',
            'neutral': 'vẻ bình thản', 'thoughtful': 'ánh mắt trầm tư',
            'sadness': 'nỗi buồn sâu lắng', 'surprise': 'vẻ ngỡ ngàng',
            'determination': 'sự quyết tâm', 'dreamy': 'ánh mắt mơ màng',
            'laughter': 'tiếng cười sảng khoái', 'serenity': 'sự an nhiên',
            'passion': 'ngọn lửa đam mê', 'tenderness': 'sự dịu dàng ấm áp',
        }
        lighting_vi = {
            'golden_hour': 'ánh hoàng hôn vàng', 'blue_hour': 'ánh chiều tím',
            'bright_daylight': 'nắng chan hòa', 'overcast': 'trời âm u',
            'neon': 'ánh đèn neon rực rỡ', 'candlelight': 'ánh nến lung linh',
            'moonlight': 'ánh trăng dịu nhẹ', 'dramatic': 'ánh sáng kịch tính',
        }
        content_vi = {
            'portrait': 'Chân dung', 'group_photo': 'Ảnh nhóm bạn',
            'selfie': 'Ảnh selfie', 'landscape': 'Phong cảnh',
            'urban': 'Thành phố', 'indoor': 'Không gian nội thất',
            'food_drink': 'Ẩm thực', 'animal': 'Thế giới động vật',
            'object': 'Vật thể', 'art_abstract': 'Nghệ thuật trừu tượng',
            'event': 'Sự kiện', 'nature_close': 'Thiên nhiên cận cảnh',
        }

        # Build rich description
        parts: List[str] = []

        # Content type prefix
        ct_label = content_vi.get(content_type, '')
        if ct_label:
            parts.append(ct_label)

        # Person expression (when detected)
        if has_person and top_expression:
            expr_desc = expression_vi.get(top_expression, top_expression)
            parts.append(f"với {expr_desc}")

        # Primary emotion
        emo_desc = emotion_vi.get(primary_emotion, primary_emotion)
        if primary_score < 0.45 and secondary_emotion != primary_emotion:
            sec_desc = emotion_vi.get(secondary_emotion, secondary_emotion)
            parts.append(f"cảm xúc {emo_desc} pha lẫn {sec_desc}")
        else:
            parts.append(f"cảm xúc {emo_desc}")

        # Scene context
        sc_desc = scene_vi.get(top_scene, '')
        if sc_desc:
            parts.append(f"trong không gian {sc_desc}")

        # Lighting
        if top_lighting:
            lt_desc = lighting_vi.get(top_lighting, '')
            if lt_desc:
                parts.append(lt_desc)

        # Visual tone
        if visual_features['brightness'] > 0.65:
            parts.append("tông sáng tươi mới")
        elif visual_features['brightness'] < 0.35:
            parts.append("tông trầm sâu lắng")

        mood_description = ", ".join(parts)
        return primary_emotion, mood_description
    
    @staticmethod
    def _rgb_to_hex(rgb) -> str:
        """Convert RGB tuple/array to hex color string"""
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        return f"#{r:02x}{g:02x}{b:02x}".upper()


# ============================================================================
# Singleton
# ============================================================================
_image_analyzer = None

def get_image_analyzer(reload=False):
    """Get singleton ImageAnalyzer instance"""
    global _image_analyzer
    if _image_analyzer is None or reload:
        _image_analyzer = ImageAnalyzer()
    return _image_analyzer
