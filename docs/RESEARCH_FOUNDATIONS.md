# Brightify — Nền Tảng Nghiên Cứu Học Thuật

> **Mục đích**: Tài liệu hóa toàn bộ các nghiên cứu học thuật được sử dụng làm nền tảng cho thuật toán và pipeline xử lý trong hệ thống Brightify.

---

## 1. Tổng Quan Nền Tảng Nghiên Cứu

Brightify v7.1 tích hợp kết quả từ **20+ nghiên cứu học thuật** trong các lĩnh vực:
- Tâm lý học cảm xúc (Emotion Psychology)
- Truy vấn thông tin âm nhạc (Music Information Retrieval — MIR)
- Xử lý ngôn ngữ tự nhiên tiếng Việt (Vietnamese NLP)
- Thị giác máy tính (Computer Vision)
- Tâm lý màu sắc (Color Psychology)
- Liệu pháp âm nhạc (Music Therapy)

---

## 2. Mô Hình Cảm Xúc

### 2.1. Russell's Circumplex Model of Affect (Russell, 1980)

**Sử dụng tại**: `config.py`, `recommendation_engine.py`, `emotion_analysis.py`, `db/models.py`

**Mô tả**: Mô hình Circumplex biểu diễn cảm xúc trong không gian 2 chiều:
- **Valence** (X-axis): Tích cực ↔ Tiêu cực (0.0–1.0)
- **Arousal** (Y-axis): Kích thích ↔ Thư giãn (0.0–1.0)

**Áp dụng cụ thể**: Brightify chia không gian V-A thành 4 quadrant:

| Quadrant | Tên | Valence | Arousal | Ví dụ cảm xúc |
|---|---|---|---|---|
| Q1 | Happy/Excited | Cao | Cao | vui, phấn khích |
| Q2 | Angry/Tense | Thấp | Cao | tức giận, căng thẳng |
| Q3 | Sad/Depressed | Thấp | Thấp | buồn, trầm cảm |
| Q4 | Calm/Peaceful | Cao | Thấp | bình yên, thư thái |

**Đánh giá**: ✅ Áp dụng chính xác theo lý thuyết gốc. Quadrant boundaries được xác định rõ ràng trong `config.py` (`MOOD_QUADRANTS`). Tuy nhiên, ranh giới cứng (0.50) có thể gây mất tự nhiên ở vùng biên → có thể cải thiện bằng fuzzy boundaries.

### 2.2. Thayer's Two-Dimensional Energy-Stress Model (Thayer, 1989)

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_mood()`

**Mô tả**: Mở rộng Russell model cho audio features — kết hợp energy (năng lượng) và stress (căng thẳng) để mô tả trạng thái tâm lý khi nghe nhạc.

**Áp dụng**: Hệ thống sử dụng `fused_valence` và `fused_energy` (kết hợp audio + lyrics) làm tọa độ V-A cho mỗi bài hát, sau đó tính khoảng cách Gaussian tới V-A mục tiêu.

---

## 3. Xử Lý Ngôn Ngữ Tự Nhiên Tiếng Việt

### 3.1. PhoBERT (Nguyen & Nguyen, 2020)

**Paper**: "PhoBERT: Pre-trained language models for Vietnamese" (Findings of EMNLP 2020)

**Sử dụng tại**: `emotion_analysis.py` — `EmotionClassifier`

**Mô hình**: `vinai/phobert-base-v2` (135M parameters)

**Pipeline xử lý**:
```
Input text → pyvi.ViTokenizer.tokenize() → PhoBERT tokenizer → 
PhoBERT encoder → Attention pooling → 768-dim embedding
```

**Áp dụng trong Brightify**:
1. **Lyrics embedding**: Mã hóa lời bài hát thành vector 768-dim cho similarity search
2. **Emotion classification**: Ánh xạ embedding → circumplex V-A space
3. **Semantic search**: Tìm bài hát theo ý nghĩa ngữ cảnh (không chỉ keyword)

**Đánh giá**: ✅ PhoBERT là state-of-the-art cho NLP tiếng Việt. Việc sử dụng attention pooling thay vì chỉ CLS token là một cải tiến tốt, giúp capture toàn bộ ngữ cảnh lời bài hát dài.

### 3.2. Hybrid Lyrics Search (Tự phát triển)

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_lyrics_keywords()`

**Phương pháp**:
- **Khi có keyword match**: Semantic(40%) + Keyword(35%) + Centroid(25%)
- **Khi không có keyword match**: Pure PhoBERT semantic search (100%)

**Centroid embedding**: Tính centroid từ top-10 keyword-matched songs → cosine similarity → bias kết quả về "cụm" bài hát liên quan.

**Trích dẫn liên quan**: Kim et al. (2024) — "Lyrics-aware multimodal music recommendation" khuyến nghị lyrics weight ≥ 30% khi lời bài hát khả dụng.

---

## 4. Truy Vấn Thông Tin Âm Nhạc (MIR)

### 4.1. Timbral Similarity (Berenzweig et al., 2004)

**Paper**: "Large-Scale Content-Based Collaborative Recommendation for Listening"

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_song()`

**Features**: Energy, Loudness, Acousticness, Instrumentalness, Timbre Brightness
**Weight**: 25% trong tổng similarity score

**Đánh giá**: ✅ Đúng theo MIR literature. Timbral features là nền tảng cho content-based music recommendation.

### 4.2. Rhythmic Similarity (Gouyon et al., 2004)

**Paper**: Rhythmic pattern analysis for music similarity

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_song()`

**Features**: Danceability, Tempo (normalized), Time Signature, Liveness
**Weight**: 20% trong tổng similarity score

### 4.3. Tonal Similarity (Harte et al., 2006)

**Paper**: Tonal content analysis for music recommendation

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_song()`

**Features**: Key, Mode, Speechiness, Valence, Energy
**Weight**: 15% trong tổng similarity score

### 4.4. 7-Signal Song Similarity Fusion (Zhang et al., 2024)

**Paper**: "Multimodal fusion for music recommendation"

**Sử dụng tại**: `recommend_by_song()` — Trọng số fusion mặc định

| Signal | Weight | Source |
|---|---|---|
| Timbral | 25% | Berenzweig 2004 |
| Rhythmic | 20% | Gouyon 2004 |
| Tonal | 15% | Harte 2006 |
| Lyrics (PhoBERT) | 18% | Nguyen & Nguyen 2020 |
| V-A proximity | 8% | Russell 1980 |
| Emotion vector | 7% | Tự phát triển |
| Mood agreement | 7% | Tự phát triển |

**Adaptive weighting**: Nếu bài hát thiếu lyrics hoặc embeddings, trọng số được redistribute sang audio signals. Đây là một cải tiến tốt so với fixed-weight approaches.

### 4.5. MMR-lite Ranking (Flexer et al., 2006; Carbonell & Goldstein, 1998)

**Sử dụng tại**: `recommendation_engine.py` — `_fast_rank()`

**Phương pháp**:
- Maximal Marginal Relevance đơn giản hóa
- Artist diversity penalty: escalating per repeat (score × (1−penalty)^count)
- Mood novelty bonus: +3% cho mood chưa xuất hiện trong danh sách
- O(k·C) complexity, C = 3·top_k candidates → <1ms cho k=30

---

## 5. Tâm Lý Màu Sắc (Color Psychology)

### 5.1. Palmer et al. (2013) — Color-Music Associations

**Paper**: "Music–color associations are mediated by emotion"

**Sử dụng tại**: `advanced_color_mapping.py`

**Áp dụng**: Ánh xạ audio features → HSL color space:
- Valence → Hue: Cao (vàng-xanh lá) ↔ Thấp (xanh dương-tím)
- Energy → Saturation: Cao (bão hòa) ↔ Thấp (pastel)
- Mood → Lightness: Tích cực (sáng) ↔ Tiêu cực (tối)

### 5.2. Jonauskaite et al. (2020) — Cross-Cultural Color-Emotion

**Paper**: "Universal patterns in color–emotion associations across countries"

**Sử dụng tại**: `advanced_color_mapping.py` — `_build_emotion_color_profiles()`

**Mô tả**: Nghiên cứu cross-cultural (12 quốc gia, 4,598 tham gia) xác định ánh xạ phổ quát giữa màu sắc và cảm xúc.

**13 emotion-color profiles** trong Brightify:
| Emotion | Hue Range | Saturation | Lightness |
|---|---|---|---|
| Happy | 40–60° (Warm yellow) | 70–95% | 55–75% |
| Sad | 210–250° (Blue) | 30–55% | 25–45% |
| Angry | 0–15° (Red) | 75–100% | 35–55% |
| Peaceful | 120–160° (Green) | 40–65% | 55–75% |
| Love | 330–355° (Pink-Rose) | 60–85% | 50–70% |
| ... | ... | ... | ... |

### 5.3. CIEDE2000 Perceptual Color Distance

**Standard**: CIE Technical Committee, CIE 142-2001

**Sử dụng tại**: `recommendation_engine.py` — `_ciede2000_distance()`

**Mô tả**: Khoảng cách màu sắc được cảm nhận bởi mắt người, chính xác hơn nhiều so với Euclidean distance trong RGB space.

**Thư viện**: `colormath.color_diff.delta_e_cie2000`

**Áp dụng**: So sánh màu sắc gợi ý với màu đầu vào, sử dụng CIEDE2000 thay vì delta_E_76 (CIE 1976). Đây là một quyết định kỹ thuật chính xác — CIEDE2000 xử lý tốt hơn vùng blue-purple và vùng saturation thấp.

---

## 6. Thị Giác Máy Tính (Computer Vision)

### 6.1. CLIP (Radford et al., 2021)

**Paper**: "Learning Transferable Visual Models From Natural Language Supervision"

**Sử dụng tại**: `image_analysis.py` — `ImageAnalyzer`

**Model**: `openai/clip-vit-base-patch32`

**Áp dụng zero-shot classification**:
- **Emotion detection**: 50 text prompts (10 emotions × 5 prompts) → softmax → top emotions
- **Scene classification**: 18 scene types
- **Content type**: 12 content categories
- **Expression recognition**: 12 facial expressions (Ekman 1992 + AffectNet)
- **Lighting conditions**: 8 lighting types

**Đánh giá**: ✅ Sử dụng CLIP cho zero-shot classification là approach hiện đại và linh hoạt. Multi-prompt averaging (5 prompts/emotion) giúp giảm bias của individual prompts. Tuy nhiên, CLIP ViT-B/32 có thể được nâng cấp lên ViT-L/14 cho accuracy tốt hơn (trade-off: inference time).

### 6.2. Ekman's Basic Emotions (Ekman, 1992)

**Paper**: "An Argument for Basic Emotions"

**Sử dụng tại**: `image_analysis.py` — expression classification

**6 cảm xúc cơ bản** + 6 mở rộng: happy, sad, angry, surprised, fearful, disgusted + contemplative, amused, serene, confused, tired, neutral

### 6.3. Center-Weighted K-Means Color Extraction

**Sử dụng tại**: `image_analysis.py` — `_extract_dominant_colors()`

**Phương pháp**: K-Means clustering trên pixel colors, với Gaussian spatial weighting (trung tâm ảnh có trọng số cao hơn). Đây là cải tiến so với standard K-Means vì subject của ảnh thường ở trung tâm.

---

## 7. Liệu Pháp Âm Nhạc (Music Therapy)

### 7.1. Iso Principle (Altshuler, 1948; Heiderscheit & Madson, 2015)

**Paper**: Heiderscheit & Madson (2015) — "Use of the Iso Principle as a Central Method in Mood Management: A Music Psychotherapy Clinical Case Study"

**Sử dụng tại**: `recommendation_engine.py` — `generate_emotion_journey()`

**Nguyên lý**: "Bắt đầu từ tâm trạng hiện tại của người nghe, sau đó dẫn dắt dần tới trạng thái cảm xúc mong muốn."

**Triển khai trong Brightify**:
1. Định nghĩa start V-A và end V-A
2. Tạo trajectory theo **Quadratic Bézier Curve** trong V-A space
   - Control point: midpoint với arousal boost (+15%) → trajectory tự nhiên, tránh đi thẳng
3. Chia trajectory thành N waypoints (6–15 bước)
4. Tại mỗi waypoint, tìm bài hát gần nhất trong V-A space bằng 4-signal scoring:
   - V-A distance (50%), Emotion (20%), Audio (20%), Mood agreement (10%)
5. Quỹ đạo tạo ra playlist có sự chuyển biến cảm xúc mượt mà

**Đánh giá**: ✅ Đây là một tính năng rất độc đáo và có giá trị thực tiễn. Bézier curve là một lựa chọn thông minh cho trajectory — tránh chuyển đổi cảm xúc đột ngột. Arousal boost ở control point mô phỏng "peak" tự nhiên của hành trình cảm xúc.

### 7.2. Circadian Rhythm (Randler & Schaal, 2010)

**Paper**: "Morningness–eveningness, habitual sleep-wake variables and cortisol level"

**Sử dụng tại**: `recommendation_engine.py` — `smart_context_recommend()`

**8 giai đoạn trong ngày**:
| Giai đoạn | Giờ | Valence | Arousal | Mô tả |
|---|---|---|---|---|
| Dawn | 5–7h | 0.50 | 0.35 | Nhẹ nhàng, thức dậy |
| Early Morning | 7–9h | 0.60 | 0.55 | Tràn đầy năng lượng |
| Morning | 9–11h | 0.65 | 0.65 | Tập trung |
| Midday | 11–14h | 0.55 | 0.50 | Bình ổn |
| Afternoon | 14–17h | 0.60 | 0.60 | Hoạt bát |
| Evening | 17–20h | 0.55 | 0.45 | Thư giãn |
| Night | 20–23h | 0.45 | 0.35 | Trầm lắng |
| Late Night | 23–5h | 0.40 | 0.25 | Ru ngủ |

---

## 8. Fusion & Weighting Research

### 8.1. Multimodal Fusion Weights

Hệ thống sử dụng nhiều bộ trọng số tùy theo loại query:

| Query Type | Audio | Lyrics | V-A | Emotion | Color | Source |
|---|---|---|---|---|---|---|
| Color | 25% | 35% | 20% | 20% | — | Palmer 2013 |
| Song | 25/20/15% | 18% | 8% | 7% | 7% | Zhang 2024 |
| Image | 20% | 25% | 20% | 15% | 20% | Tự phát triển |
| Mood | — | — | 100% | — | — | Russell 1980 |
| Context | 35% | 25% | — | 10% | — | Randler 2010 |

### 8.2. Hu & Downie (2010)

**Paper**: "When lyrics outperform audio for music mood classification"

**Sử dụng tại**: `recommendation_engine.py` — `recommend_by_mood()`

**Insight chính**: Lyrics features outperform audio features cho mood classification khi lyrics khả dụng. Brightify áp dụng bằng cách cho lyrics weight cao (35%) trong color queries.

---

## 9. Đánh Giá Tổng Quan Nền Tảng Nghiên Cứu

### Điểm mạnh
1. **Phủ sóng rộng**: Hệ thống tích hợp nghiên cứu từ 5+ lĩnh vực khác nhau
2. **Trích dẫn trong code**: Mỗi phương thức đều có docstring với citation → dễ trace back
3. **Áp dụng đúng**: Các paper được áp dụng đúng nguyên lý, không chỉ name-dropping
4. **Adaptive fusion**: Trọng số tự điều chỉnh dựa trên data availability → robust hơn fixed weights
5. **Iso Principle**: Tính năng Emotion Journey là original và có giá trị thực tiễn cao

### Điểm cần cải thiện
1. **Thiếu ablation study**: Chưa có kết quả so sánh hiệu quả của từng tín hiệu (nên chạy backtest riêng từng signal)
2. **Trọng số hardcoded**: Weights dựa trên paper nhưng chưa được fine-tune trên dataset thực tế của Brightify → nên có weight optimization pipeline
3. **Vietnamese cultural calibration**: Ánh xạ color-emotion dựa trên cross-cultural study (Jonauskaite 2020) nhưng chưa có Vietnamese-specific calibration data
4. **Model versioning**: PhoBERT v2 có thể được nâng cấp khi VINAI release version mới
5. **CLIP language gap**: Prompts cho CLIP là tiếng Anh, có thể mất nuance khi phân tích ảnh với context Việt Nam
