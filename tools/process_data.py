import os
import sys
import re
import argparse
import json
import warnings
from datetime import datetime

import pandas as pd
import numpy as np
import torch
from tqdm import tqdm
from pyvi import ViTokenizer

warnings.filterwarnings('ignore')

# Add project root to path for core imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.emotion_analysis import VietnameseEmotionLexicon
from core.advanced_color_mapping import AdvancedColorMapper
import config as app_config


DEFAULT_INPUT_FILE = 'data/vietnamese_music_complete_dataset_full.csv'
DEFAULT_OUTPUT_FILE = 'data/vietnamese_music_processed_full.csv'
DEFAULT_EMBEDDINGS_FILE = 'data/vietnamese_music_embeddings_full.npy'
DEFAULT_METADATA_FILE = 'data/embeddings_metadata.json'

PHOBERT_MODEL = app_config.PHOBERT_MODEL
MAX_SEQUENCE_LENGTH = 256
BATCH_SIZE = 16

# Audio features configuration
AUDIO_FEATURES = [
    'valence', 'energy', 'danceability', 'acousticness',
    'instrumentalness', 'speechiness', 'liveness', 'tempo',
    'loudness', 'key', 'mode', 'arousal', 'timbre_bright'
]

NORMALIZED_FEATURES = [
    'valence', 'energy', 'danceability', 'acousticness',
    'instrumentalness', 'speechiness', 'liveness',
    'arousal', 'timbre_bright'
]


# Color mapping uses AdvancedColorMapper from core/advanced_color_mapping.py


# ============================================================================
# Data Processing Functions
# ============================================================================

def load_data(input_file):
    """Load raw data from CSV file."""
    print(f"\n{'='*60}")
    print(f"[1/7] Loading data from: {input_file}")
    print(f"{'='*60}")
    
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    df = pd.read_csv(input_file)
    print(f"✅ Loaded {len(df):,} tracks with {len(df.columns)} columns")
    
    # Display basic info
    print(f"\n   Columns: {', '.join(df.columns[:10])}...")
    print(f"   Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    
    return df


def clean_data(df):
    """Clean and validate data."""
    print(f"\n{'='*60}")
    print("[2/7] Cleaning and validating data")
    print(f"{'='*60}")
    
    df_clean = df.copy()
    initial_rows = len(df_clean)
    
    # 1. Remove duplicates based on track_id
    if 'track_id' in df_clean.columns:
        duplicates = df_clean.duplicated(subset=['track_id']).sum()
        df_clean = df_clean.drop_duplicates(subset=['track_id'], keep='first')
        print(f"   - Removed {duplicates:,} duplicate tracks (by track_id)")
    
    # 1b. Remove duplicates: same song name + same artist (across different albums)
    if 'track_name' in df_clean.columns and 'primary_artist' in df_clean.columns:
        # Normalize for comparison: lowercase + strip whitespace
        df_clean['_name_norm'] = df_clean['track_name'].str.strip().str.lower()
        df_clean['_artist_norm'] = df_clean['primary_artist'].str.strip().str.lower()
        
        # Sort by popularity (desc) so we keep the most popular version
        pop_col = 'track_popularity' if 'track_popularity' in df_clean.columns else 'popularity'
        if pop_col in df_clean.columns:
            df_clean = df_clean.sort_values(pop_col, ascending=False)
        
        before = len(df_clean)
        df_clean = df_clean.drop_duplicates(subset=['_name_norm', '_artist_norm'], keep='first')
        name_dupes = before - len(df_clean)
        print(f"   - Removed {name_dupes:,} duplicate tracks (same song + artist across albums)")
        
        # Clean up temp columns
        df_clean = df_clean.drop(columns=['_name_norm', '_artist_norm'])
    
    # 2. Mark tracks without lyrics (do NOT drop them)
    if 'plain_lyrics' in df_clean.columns:
        has_text = df_clean['plain_lyrics'].notna() & (df_clean['plain_lyrics'].str.strip() != '')
        df_clean['has_lyrics'] = has_text
        without = (~has_text).sum()
        print(f"   - Marked {without:,} tracks as has_lyrics=False (kept in dataset)")
    elif 'has_lyrics' not in df_clean.columns:
        df_clean['has_lyrics'] = False
    
    # 3. Remove tracks without essential audio features
    # (Only remove if SOME tracks have features — don't wipe all if API failed)
    essential_features = ['valence', 'energy']
    available = [f for f in essential_features if f in df_clean.columns]
    if available:
        total_with_features = df_clean[available].notna().any(axis=1).sum()
        if total_with_features > 0:
            # Some tracks have features → safe to drop those that don't
            before = len(df_clean)
            df_clean = df_clean.dropna(subset=available, how='all')
            removed = before - len(df_clean)
            if removed > 0:
                print(f"   - Removed {removed:,} tracks without audio features")
        else:
            # NO tracks have audio features → fill with neutral defaults instead of dropping all
            print(f"   ⚠️ No tracks have audio features — filling with neutral defaults")
            defaults = {
                'valence': 0.5, 'energy': 0.5, 'danceability': 0.5,
                'acousticness': 0.5, 'speechiness': 0.1, 'instrumentalness': 0.0,
                'liveness': 0.2, 'loudness': -8.0, 'tempo': 120.0,
                'key': 0, 'mode': 1, 'time_signature': 4,
            }
            for col, default_val in defaults.items():
                if col in df_clean.columns:
                    df_clean[col] = df_clean[col].fillna(default_val)
    
    # 4. Reset index (critical for embedding alignment)
    df_clean = df_clean.reset_index(drop=True)
    
    # Summary
    rows_removed = initial_rows - len(df_clean)
    print(f"\n✅ Cleaning completed:")
    print(f"   - Initial: {initial_rows:,} tracks")
    print(f"   - Final: {len(df_clean):,} tracks")
    print(f"   - Removed: {rows_removed:,} ({rows_removed/initial_rows*100:.1f}%)")
    
    return df_clean


def normalize_audio_features(df):
    """Normalize audio features to valid ranges."""
    print(f"\n{'='*60}")
    print("[3/7] Normalizing audio features")
    print(f"{'='*60}")
    
    # Clip normalized features to [0, 1]
    for feature in NORMALIZED_FEATURES:
        if feature in df.columns:
            df[feature] = df[feature].clip(0, 1)
    
    # Clip key to [0, 11]
    if 'key' in df.columns:
        df['key'] = df['key'].clip(0, 11)
    
    # Clip mode to [0, 1]
    if 'mode' in df.columns:
        df['mode'] = df['mode'].round().clip(0, 1)
    
    print("✅ Audio features normalized")
    
    # Print statistics
    for feature in ['valence', 'energy', 'tempo']:
        if feature in df.columns:
            print(f"   - {feature}: mean={df[feature].mean():.3f}, range=[{df[feature].min():.2f}, {df[feature].max():.2f}]")
    
    return df


def apply_color_mapping(df):
    """Apply color mapping based on audio features using AdvancedColorMapper."""
    print(f"\n{'='*60}")
    print("[4/7] Applying color mapping (Russell's Model)")
    print(f"{'='*60}")
    
    required = ['valence', 'energy', 'tempo', 'mode', 'acousticness']
    if not all(f in df.columns for f in required):
        print("⚠️ Missing required audio features for color mapping")
        return df
    
    color_mapper = AdvancedColorMapper()
    
    tqdm.pandas(desc="   Mapping colors")
    
    def map_row(row):
        v = float(row['valence']) if not pd.isna(row['valence']) else 0.5
        a = float(row['energy']) if not pd.isna(row['energy']) else 0.5
        audio_feats = {
            'tempo': float(row['tempo']) if not pd.isna(row['tempo']) else 120,
            'mode': int(row['mode']) if not pd.isna(row['mode']) else 1,
            'energy': a,
        }
        if 'timbre_bright' in row and not pd.isna(row.get('timbre_bright')):
            audio_feats['timbre_bright'] = float(row['timbre_bright'])
        h, s, l = color_mapper.valence_arousal_to_color(v, a, audio_features=audio_feats)
        hex_color = color_mapper.hsl_to_hex(h, s, l)
        return pd.Series({
            'color_hue': h,
            'color_saturation': s,
            'color_lightness': l,
            'color_hex': hex_color
        })
    
    color_data = df.progress_apply(map_row, axis=1)
    df[['color_hue', 'color_saturation', 'color_lightness', 'color_hex']] = color_data
    
    print(f"✅ Color mapping completed")
    print(f"   - Unique colors: {df['color_hex'].nunique()}")
    
    return df


def analyze_sentiment(df):
    """Analyze lyrics sentiment using Vietnamese Emotion Lexicon."""
    print(f"\n{'='*60}")
    print("[5/7] Analyzing lyrics sentiment (Vietnamese Lexicon)")
    print(f"{'='*60}")
    
    if 'plain_lyrics' not in df.columns:
        print("⚠️ No lyrics column found, skipping sentiment analysis")
        return df
    
    lexicon = VietnameseEmotionLexicon()
    
    def clean_lyrics(text):
        if pd.isna(text) or str(text).strip() == '':
            return ''
        text = str(text)
        text = re.sub(r'\[\d+:\d+\.\d+\]', '', text)  # Remove timestamps
        text = re.sub(r'http\S+', '', text)            # Remove URLs
        return ' '.join(text.split())
    
    # Clean lyrics (only for tracks that have lyrics)
    df['lyrics_cleaned'] = df['plain_lyrics'].apply(clean_lyrics)
    
    has_lyrics_mask = df.get('has_lyrics', df['plain_lyrics'].notna() & (df['plain_lyrics'].str.strip() != ''))
    
    # Vietnamese sentiment analysis using emotion lexicon
    print("   Analyzing Vietnamese sentiment with emotion lexicon...")
    
    sentiment_compound = []
    sentiment_positive = []
    sentiment_negative = []
    sentiment_neutral = []
    
    for i, row in tqdm(df.iterrows(), total=len(df), desc="   Analyzing sentiment"):
        if not has_lyrics_mask.iloc[i] if hasattr(has_lyrics_mask, 'iloc') else not has_lyrics_mask[i]:
            sentiment_compound.append(None)
            sentiment_positive.append(None)
            sentiment_negative.append(None)
            sentiment_neutral.append(None)
            continue
        
        text = row['lyrics_cleaned']
        if not text:
            sentiment_compound.append(None)
            sentiment_positive.append(None)
            sentiment_negative.append(None)
            sentiment_neutral.append(None)
            continue
        
        # Get emotion scores from Vietnamese lexicon
        emotion_scores = lexicon.analyze_lyrics(text)
        
        # Map emotion categories to positive/negative/neutral
        positive_emotions = ['happy', 'love', 'excited', 'hope', 'peaceful']
        negative_emotions = ['sad', 'angry', 'melancholic', 'longing']
        
        pos_score = sum(emotion_scores.get(e, 0.0) for e in positive_emotions)
        neg_score = sum(emotion_scores.get(e, 0.0) for e in negative_emotions)
        total_score = pos_score + neg_score
        
        if total_score > 0:
            pos_norm = pos_score / total_score
            neg_norm = neg_score / total_score
            neu_norm = max(0.0, 1.0 - pos_norm - neg_norm)
            # Compound: ranges from -1 to 1, positive means more positive emotions
            compound = pos_norm - neg_norm
        else:
            # No emotion words found — treat as neutral
            pos_norm = 0.0
            neg_norm = 0.0
            neu_norm = 1.0
            compound = 0.0
        
        sentiment_compound.append(round(compound, 4))
        sentiment_positive.append(round(pos_norm, 4))
        sentiment_negative.append(round(neg_norm, 4))
        sentiment_neutral.append(round(neu_norm, 4))
    
    df['sentiment_compound'] = sentiment_compound
    df['sentiment_positive'] = sentiment_positive
    df['sentiment_neutral'] = sentiment_neutral
    df['sentiment_negative'] = sentiment_negative
    
    # Categorize (NULL for no-lyrics tracks)
    def categorize(compound):
        if pd.isna(compound):
            return None
        if compound >= 0.05: return 'Positive'
        elif compound <= -0.05: return 'Negative'
        return 'Neutral'
    
    df['sentiment_category'] = df['sentiment_compound'].apply(categorize)
    
    with_sentiment = df['sentiment_compound'].notna().sum()
    print(f"✅ Sentiment analysis completed")
    print(f"   - Analyzed: {with_sentiment:,} tracks with lyrics")
    print(f"   - Skipped: {len(df) - with_sentiment:,} tracks without lyrics (sentiment=NULL)")
    if with_sentiment > 0:
        print(f"   - Distribution: {dict(df['sentiment_category'].value_counts(dropna=True))}")
    
    return df


def create_engineered_features(df):
    """Create additional engineered features."""
    print(f"\n{'='*60}")
    print("[6/7] Creating engineered features")
    print(f"{'='*60}")
    
    features_created = []
    
    # Mood score (prefer DEAM arousal over energy when available)
    if 'valence' in df.columns and 'energy' in df.columns:
        arousal_col = df['arousal'] if 'arousal' in df.columns else df['energy']
        arousal_vals = arousal_col.fillna(df['energy'])
        df['mood_score'] = df['valence'] * 0.6 + arousal_vals * 0.4
        features_created.append('mood_score')
        
        # Mood quadrant (Russell's Model) — use DEAM arousal when available
        def get_quadrant(row):
            v = row['valence']
            a = row.get('arousal') if pd.notna(row.get('arousal')) else row['energy']
            if pd.isna(v) or pd.isna(a): return 'Unknown'
            if v >= 0.5 and a >= 0.5: return 'Q1: Happy/Excited'
            if v < 0.5 and a >= 0.5: return 'Q2: Angry/Tense'
            if v < 0.5 and a < 0.5: return 'Q3: Sad/Depressed'
            return 'Q4: Calm/Peaceful'
        
        df['mood_quadrant'] = df.apply(get_quadrant, axis=1)
        features_created.append('mood_quadrant')
    
    # Dance score
    if all(f in df.columns for f in ['danceability', 'energy', 'tempo']):
        df['dance_score'] = (
            df['danceability'] * 0.5 +
            df['energy'] * 0.3 +
            (df['tempo'].clip(60, 180) - 60) / 120 * 0.2
        )
        features_created.append('dance_score')
    
    # Acoustic score
    if all(f in df.columns for f in ['acousticness', 'instrumentalness']):
        df['acoustic_score'] = df['acousticness'] * 0.7 + df['instrumentalness'] * 0.3
        features_created.append('acoustic_score')
    
    # Combined positivity (audio + lyrics; NULL for no-lyrics tracks)
    if 'sentiment_compound' in df.columns and 'valence' in df.columns:
        sentiment_norm = (df['sentiment_compound'] + 1) / 2
        df['combined_positivity'] = df['valence'] * 0.6 + sentiment_norm * 0.4
        # combined_positivity stays NaN for tracks without lyrics (sentiment is NaN)
        features_created.append('combined_positivity')
    
    # Energy level category
    if 'energy' in df.columns:
        df['energy_level'] = pd.cut(
            df['energy'], bins=[0, 0.33, 0.66, 1.0],
            labels=['Low', 'Medium', 'High']
        )
        features_created.append('energy_level')
    
    # Tempo category
    if 'tempo' in df.columns:
        df['tempo_category'] = pd.cut(
            df['tempo'], bins=[0, 90, 120, 150, 300],
            labels=['Slow', 'Medium', 'Fast', 'Very Fast']
        )
        features_created.append('tempo_category')
    
    print(f"✅ Created {len(features_created)} engineered features:")
    for f in features_created:
        print(f"   - {f}")
    
    return df


def _encode_batch_mean_pool(tokenizer, model, texts, device, max_length=256):
    """Mean-pool last hidden state → (len(texts), 768) float32."""
    encoded = tokenizer(texts, padding=True, truncation=True,
                        max_length=max_length, return_tensors='pt')
    encoded = {k: v.to(device) for k, v in encoded.items()}
    with torch.no_grad():
        outputs = model(**encoded)
    attn = encoded['attention_mask']
    tok_emb = outputs.last_hidden_state
    mask_exp = attn.unsqueeze(-1).expand(tok_emb.size()).float()
    s_emb = torch.sum(tok_emb * mask_exp, 1)
    s_mask = torch.clamp(mask_exp.sum(1), min=1e-9)
    return (s_emb / s_mask).cpu().numpy()


def generate_embeddings(df, output_embeddings, output_metadata,
                        hf_cache_dir: str = "var/volumes/hf_cache"):
    """Generate lyrics embeddings with PhoBERT + ViTokenizer."""
    mode = "PhoBERT"
    print(f"\n{'='*60}")
    print(f"[7/7] Generating embeddings — {mode}")
    print(f"{'='*60}")
    
    has_lyrics_mask = df.get('has_lyrics', df['plain_lyrics'].notna() & (df['plain_lyrics'].str.strip() != ''))
    idx_with = df.index[has_lyrics_mask].tolist()
    idx_without = df.index[~has_lyrics_mask].tolist()
    enc_label = "PhoBERT"
    print(f"   Tracks with lyrics: {len(idx_with):,} → {enc_label}")
    print(f"   Tracks without lyrics: {len(idx_without):,} → audio-feature fallback")

    EMBEDDING_DIM = 768

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"   Device: {device}")
    if device.type == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")

    all_embeddings = np.zeros((len(df), EMBEDDING_DIM), dtype=np.float32)
    lyrics_col = 'lyrics_cleaned' if 'lyrics_cleaned' in df.columns else 'plain_lyrics'

    def _clean(text, segment_vi: bool = True) -> str:
        if pd.isna(text) or str(text).strip() == '':
            return ""
        text = str(text)
        text = re.sub(r'\[\d+:\d+\.\d+\]', '', text)
        text = re.sub(r'http\S+', '', text)
        text = re.sub(r'[^\w\s\u00C0-\u024F\u1E00-\u1EFF]', ' ', text, flags=re.IGNORECASE)
        text = ' '.join(text.split())[:2000]
        if segment_vi:
            text = ViTokenizer.tokenize(text)
        return text

    if idx_with:
        # --- PhoBERT ---
        print(f"   Loading model: {PHOBERT_MODEL}...")
        try:
            from transformers import AutoModel, AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(PHOBERT_MODEL)
            model = AutoModel.from_pretrained(PHOBERT_MODEL)
            model.eval()
            model.to(device)
            print(f"✅ PhoBERT loaded ({sum(p.numel() for p in model.parameters())/1e6:.1f}M params)")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            print("   Skipping embedding generation.")
            return

        lyrics_subset = df.loc[idx_with, lyrics_col].apply(
            lambda t: _clean(t, segment_vi=True)
        ).tolist()

        print(f"\n   Generating PhoBERT embeddings for {len(lyrics_subset):,} tracks...")
        for i in tqdm(range(0, len(lyrics_subset), BATCH_SIZE), desc="   PhoBERT"):
            batch = [t if t else "phông có lời" for t in lyrics_subset[i:i + BATCH_SIZE]]
            try:
                embs = _encode_batch_mean_pool(tokenizer, model, batch, device, MAX_SEQUENCE_LENGTH)
                for j, emb in enumerate(embs):
                    all_embeddings[idx_with[i + j]] = emb
            except Exception as e:
                print(f"\n   ⚠️ Error in batch {i}: {e}")

        del model, tokenizer

    # --- Fallback embeddings for no-lyrics tracks ---
    # Option A: Weighted average of 10 most similar tracks (by audio features)
    # that have real PhoBERT embeddings — keeps all embeddings in the same space.
    if idx_without and idx_with:
        print(f"\n   Generating fallback embeddings for {len(idx_without):,} tracks (nearest-neighbor avg)...")
        from sklearn.metrics.pairwise import cosine_similarity
        
        audio_cols = [c for c in AUDIO_FEATURES if c in df.columns]
        K = 10  # number of neighbors
        
        # Build audio feature matrix for tracks with lyrics
        with_audio = np.zeros((len(idx_with), len(audio_cols)), dtype=np.float32)
        for j, orig_idx in enumerate(idx_with):
            for k, col in enumerate(audio_cols):
                v = df.at[orig_idx, col]
                with_audio[j, k] = float(v) if pd.notna(v) else 0.0
        
        # Normalize audio features for cosine similarity
        norms_audio = np.linalg.norm(with_audio, axis=1, keepdims=True)
        norms_audio[norms_audio == 0] = 1
        with_audio_normed = with_audio / norms_audio
        
        for orig_idx in tqdm(idx_without, desc="   Fallback embeddings"):
            # Get audio features for this track
            feat_vec = np.zeros(len(audio_cols), dtype=np.float32)
            for k, col in enumerate(audio_cols):
                v = df.at[orig_idx, col]
                feat_vec[k] = float(v) if pd.notna(v) else 0.0
            feat_norm = np.linalg.norm(feat_vec)
            if feat_norm > 0:
                feat_vec_normed = feat_vec / feat_norm
            else:
                feat_vec_normed = feat_vec
            
            # Find K nearest by audio cosine similarity
            sims = cosine_similarity(feat_vec_normed.reshape(1, -1), with_audio_normed)[0]
            top_k_local = np.argsort(sims)[-K:]
            top_k_sims = sims[top_k_local]
            
            # Weighted average of their PhoBERT embeddings
            total_w = top_k_sims.sum()
            if total_w > 0:
                fallback = np.zeros(EMBEDDING_DIM, dtype=np.float32)
                for local_j, w in zip(top_k_local, top_k_sims):
                    fallback += w * all_embeddings[idx_with[local_j]]
                fallback /= total_w
            else:
                fallback = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            
            all_embeddings[orig_idx] = fallback
    elif idx_without:
        # No tracks with lyrics at all — use zero vectors
        print(f"\n   ⚠️ No tracks with lyrics for fallback. Using zero vectors for {len(idx_without)} tracks.")
    
    # Normalize all embeddings
    norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    all_embeddings = all_embeddings / norms
    
    # Save
    np.save(output_embeddings, all_embeddings)
    print(f"\n✅ Saved embeddings: {output_embeddings}")
    print(f"   Shape: {all_embeddings.shape}")
    print(f"   PhoBERT: {len(idx_with):,} / Fallback: {len(idx_without):,}")
    
    encoder_model = PHOBERT_MODEL
    print(f"   Encoder: {encoder_model}")
    metadata = {
        'created_at': datetime.now().isoformat(),
        'model': encoder_model,
        'num_songs': len(df),
        'embedding_dim': EMBEDDING_DIM,
        'encoded_count': len(idx_with),
        'fallback_count': len(idx_without),
        'track_ids': df['track_id'].tolist() if 'track_id' in df.columns else [],
        'track_names': df['track_name'].tolist() if 'track_name' in df.columns else []
    }
    
    with open(output_metadata, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved metadata: {output_metadata}")


def verify_data_integrity(df):
    """Verify data integrity before saving."""
    print(f"\n{'='*60}")
    print("Data Integrity Check")
    print(f"{'='*60}")
    
    errors = 0
    
    # Check track_id and track_url alignment
    if 'track_id' in df.columns and 'track_url' in df.columns:
        sample_size = min(10, len(df))
        for i in range(sample_size):
            row = df.iloc[i]
            if pd.notna(row['track_url']) and row['track_id'] not in str(row['track_url']):
                errors += 1
                print(f"   ❌ Row {i}: track_id mismatch - {row['track_name'][:30]}")
    
    if errors == 0:
        print("✅ All integrity checks passed")
    else:
        print(f"⚠️ Found {errors} issues")
    
    return errors == 0


def print_summary(df, output_file):
    """Print final processing summary."""
    print(f"\n{'='*60}")
    print("PROCESSING SUMMARY")
    print(f"{'='*60}")
    
    print(f"\n📊 Dataset Overview:")
    print(f"   - Total tracks: {len(df):,}")
    print(f"   - Total columns: {len(df.columns)}")
    print(f"   - Output file: {output_file}")
    
    if 'mood_quadrant' in df.columns:
        print(f"\n🎭 Mood Distribution:")
        for mood, count in df['mood_quadrant'].value_counts().items():
            print(f"   - {mood}: {count:,} ({count/len(df)*100:.1f}%)")
    
    if 'color_hex' in df.columns:
        print(f"\n🎨 Color Mapping:")
        print(f"   - Unique colors: {df['color_hex'].nunique()}")
        top_colors = df['color_hex'].value_counts().head(5)
        for color, count in top_colors.items():
            print(f"   - {color}: {count:,} tracks")
    
    print(f"\n🎵 Audio Features (mean values):")
    for feature in ['valence', 'energy', 'danceability', 'tempo']:
        if feature in df.columns:
            print(f"   - {feature}: {df[feature].mean():.3f}")


# ============================================================================
# Main Pipeline
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Brightify Data Processing Pipeline')
    parser.add_argument('--input', '-i', default=DEFAULT_INPUT_FILE, help='Input CSV file')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT_FILE, help='Output CSV file')
    parser.add_argument('--embeddings', '-e', default=DEFAULT_EMBEDDINGS_FILE, help='Embeddings output file')
    parser.add_argument('--metadata', '-m', default=DEFAULT_METADATA_FILE, help='Metadata output file')
    parser.add_argument('--skip-embeddings', action='store_true', help='Skip embedding generation')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing files')
    parser.add_argument('--hf-cache', default='var/volumes/hf_cache',
                        help='HuggingFace model cache dir (default: var/volumes/hf_cache)')

    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🎵 BRIGHTIFY - Data Processing Pipeline")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Check if output exists (for full pipeline only)
        if os.path.exists(args.output) and not args.force:
            print(f"\n⚠️ Output file already exists: {args.output}")
            response = input("   Overwrite? (y/n): ")
            if response.lower() != 'y':
                print("   Aborted.")
                return

        # Pipeline steps
        df = load_data(args.input)
        df = clean_data(df)
        df = normalize_audio_features(df)
        df = apply_color_mapping(df)
        df = analyze_sentiment(df)
        df = create_engineered_features(df)
        
        # Validation gate: zero NaN in essential audio feature columns
        essential = ['valence', 'energy', 'danceability']
        avail = [c for c in essential if c in df.columns]
        if avail:
            nan_count = df[avail].isna().sum().sum()
            if nan_count > 0:
                print(f"\n⚠️ VALIDATION GATE: {nan_count} NaN values found in {avail}")
                print(f"   These tracks should have been removed in collect_data.py Phase 2 DROP GATE")
            else:
                print(f"\n✅ VALIDATION GATE PASSED: zero NaN in {avail}")
        
        # Verify and save
        verify_data_integrity(df)
        
        df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"\n✅ Saved processed data: {args.output}")
        
        # Generate embeddings
        if not args.skip_embeddings:
            generate_embeddings(df, args.embeddings, args.metadata,
                                hf_cache_dir=getattr(args, 'hf_cache', 'var/volumes/hf_cache'))
        else:
            print("\n⏭️ Skipped embedding generation (--skip-embeddings)")
        
        # Summary
        print_summary(df, args.output)
        
        print(f"\n{'='*60}")
        print("✅ DATA PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"\n📁 Output files:")
        print(f"   - {args.output}")
        if not args.skip_embeddings:
            print(f"   - {args.embeddings}")
            print(f"   - {args.metadata}")
        
        print(f"\n🚀 Next steps:")
        print(f"   python -m uvicorn app:app --reload")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
