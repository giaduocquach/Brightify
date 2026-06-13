# Brightify Pipeline Redesign Proposal
## Giải quyết vấn đề mất 83.7% dữ liệu tại Phase 2

**Ngày:** Tháng 3/2026  
**Vấn đề:** ReccoBeats API và Spotify audio-features API đều đã chết → 19,430 tracks giảm xuống 3,167 (mất 16,263 tracks)

---

## 1. Tóm tắt vấn đề

### Nguyên nhân gốc
- **Spotify audio-features API**: Deprecated tháng 11/2024, trả về HTTP 403
- **ReccoBeats API**: Chết, trả về `{"content":[]}`
- **Hệ quả**: Phase 5 (process_data) DROP GATE loại bỏ mọi track không có `valence` + `energy`
- **Kết quả**: Chỉ 3,167/19,430 tracks (16.3%) có audio features từ cache cũ được giữ lại

### Dữ liệu hệ thống THỰC SỰ cần

| Mức độ | Trường | Nguồn hiện tại | Dùng cho |
|--------|--------|----------------|----------|
| **BẮT BUỘC** | `valence` | ReccoBeats ❌ | Mọi recommendation mode, color mapping, mood quadrants |
| **BẮT BUỘC** | `energy` | ReccoBeats ❌ | Mọi recommendation mode, color mapping, mood quadrants |
| **BẮT BUỘC** | `danceability` | ReccoBeats ❌ | Rhythmic similarity, featured songs scoring |
| **BẮT BUỘC** | `tempo` | ReccoBeats ❌ | Rhythmic similarity, color mapping, normalization |
| **BẮT BUỘC** | `key`, `mode` | ReccoBeats ❌ | Tonal similarity, color mapping |
| **BẮT BUỘC** | `loudness` | ReccoBeats ❌ | Timbral similarity |
| Cao | `acousticness` | ReccoBeats ❌ | Timbral similarity, image-based rec |
| Cao | `instrumentalness` | ReccoBeats ❌ | Timbral similarity |
| Cao | `speechiness` | ReccoBeats ❌ | Timbral similarity |
| Cao | `liveness` | ReccoBeats ❌ | Rhythmic similarity |
| Cao | PhoBERT embeddings | OK ✅ | 28-35% weight, lyrics similarity |
| Cao | `lyrics_cleaned` | LRCLIB ✅ | Keyword matching, fused emotion |
| Trung bình | `color_hex` | Computed (từ valence/energy) | Color-based recommendation |
| Thấp | `time_signature` | ReccoBeats ❌ | Không dùng trực tiếp trong engine |

**→ 10/14 trường quan trọng đều phụ thuộc API đã chết**

---

## 2. Giải pháp đề xuất: Essentia — Trích xuất local từ file MP3

### 2.1 Essentia là gì?

**Essentia** là thư viện C++/Python mã nguồn mở của Music Technology Group (Universitat Pompeu Fabra, Barcelona) cho phân tích và trích xuất đặc trưng âm nhạc.

- **License**: AGPL v3 (miễn phí cho dự án học thuật/phi thương mại). License thương mại có sẵn nếu cần.
- **Chi phí**: **MIỄN PHÍ** cho dự án đồ án/nghiên cứu
- **Ngôn ngữ**: C++ core + Python bindings
- **Cài đặt**: `pip install essentia` hoặc `pip install essentia-tensorflow`
- **Chạy**: Hoàn toàn offline, trên máy local, KHÔNG phụ thuộc API bên ngoài

### 2.2 Mapping: Spotify/ReccoBeats features → Essentia equivalents

| Feature cần | Essentia solution | Model/Algorithm | Output |
|-------------|-------------------|-----------------|--------|
| **valence** | Pre-trained regression model | `deam-msd-musicnn` hoặc `emomusic-msd-musicnn` | Continuous value (1-9 scale, normalize về 0-1) |
| **energy/arousal** | Pre-trained regression model | `deam-msd-musicnn` hoặc `emomusic-msd-musicnn` | Continuous value (1-9 scale, normalize về 0-1) |
| **danceability** | Pre-trained classifier | `danceability-discogs-effnet` | Probability (0-1), dùng trực tiếp |
| **tempo (BPM)** | TempoCNN | `deeptemp-k16` | BPM trực tiếp (30-286 BPM) |
| **key** | HPCP + Key algorithm | `essentia.standard.Key` | Key letter (map về 0-11) |
| **mode** | HPCP + Key algorithm | `essentia.standard.Key` | major=1, minor=0 |
| **loudness** | MusicExtractor / EBU R128 | `lowlevel.loudness_ebu128.integrated` | dB LUFS |
| **acousticness** | Mood classifier | `mood_acoustic-discogs-effnet` | Probability (0-1) |
| **instrumentalness** | Voice/instrumental classifier | `voice_instrumental-discogs-effnet` | Probability instrumental (0-1) |
| **speechiness** | Derived from voice detection | `voice_instrumental` inverse | 1 - P(instrumental) × speech_factor |
| **liveness** | Spectral analysis | MusicExtractor `lowlevel.spectral_complexity` | Normalized value |
| **time_signature** | Beat tracking | `RhythmExtractor2013` | Beats per bar |

### 2.3 Pre-trained Models có sẵn (quan trọng nhất)

#### Arousal/Valence Regression Models
Đây là giải pháp chính cho `valence` và `energy`:

| Model | Dataset | Input | Output | Note |
|-------|---------|-------|--------|------|
| `deam-msd-musicnn` | DEAM (1,802 tracks) | Audio 16kHz | valence + arousal [1-9] | Phổ biến nhất |
| `deam-audioset-vggish` | DEAM | Audio 16kHz | valence + arousal [1-9] | Nặng hơn, có thể chính xác hơn |
| `emomusic-msd-musicnn` | emoMusic (744 tracks) | Audio 16kHz | valence + arousal [1-9] | Dataset nhỏ hơn |
| `muse-msd-musicnn` | MuSe | Audio 16kHz | valence + arousal [1-9] | Alternative |

→ **Khuyến nghị**: Dùng `deam-msd-musicnn` (nhẹ, dataset lớn) hoặc ensemble 2 models lấy trung bình.

#### Danceability & Mood Classifiers
| Model | Classes | Dùng cho |
|-------|---------|----------|
| `danceability-discogs-effnet` | danceable / not_danceable | `danceability` |
| `mood_happy-discogs-effnet` | happy / non_happy | Bổ sung mood analysis |
| `mood_sad-discogs-effnet` | sad / non_sad | Bổ sung mood analysis |
| `mood_relaxed-discogs-effnet` | relaxed / non_relaxed | Bổ sung mood analysis |
| `mood_aggressive-discogs-effnet` | aggressive / non_aggressive | Bổ sung mood analysis |
| `mood_acoustic-discogs-effnet` | acoustic / non_acoustic | `acousticness` |
| `voice_instrumental-discogs-effnet` | instrumental / voice | `instrumentalness` |

### 2.4 Code ví dụ: Trích xuất features từ MP3

```python
import essentia.standard as es
import numpy as np

def extract_audio_features(mp3_path: str) -> dict:
    """Trích xuất tất cả audio features từ file MP3 bằng Essentia."""
    
    features = {}
    
    # 1. Load audio
    audio_16k = es.MonoLoader(filename=mp3_path, sampleRate=16000)()
    audio_44k = es.MonoLoader(filename=mp3_path, sampleRate=44100)()
    audio_11k = es.MonoLoader(filename=mp3_path, sampleRate=11025)()
    
    # 2. Valence + Energy (arousal) — DEAM model
    valence_arousal = es.TensorflowPredictMusiCNN(
        graphFilename='models/deam-msd-musicnn-2.pb',
        output='model/Identity'
    )(audio_16k)
    # Output shape: (N_patches, 2) — column 0 = valence, column 1 = arousal
    va_mean = np.mean(valence_arousal, axis=0)
    features['valence'] = float(np.clip((va_mean[0] - 1) / 8, 0, 1))  # normalize 1-9 → 0-1
    features['energy'] = float(np.clip((va_mean[1] - 1) / 8, 0, 1))   # normalize 1-9 → 0-1
    
    # 3. Danceability
    dance_preds = es.TensorflowPredictMusiCNN(
        graphFilename='models/danceability-discogs-effnet-1.pb',
        output='model/Softmax'
    )(audio_16k)
    features['danceability'] = float(np.mean(dance_preds[:, 0]))  # P(danceable)
    
    # 4. Tempo
    global_bpm, _, _ = es.TempoCNN(
        graphFilename='models/deeptemp-k16-3.pb'
    )(audio_11k)
    features['tempo'] = float(global_bpm)
    
    # 5. Key + Mode
    # Use HPCP-based key detection
    hpcp_key = compute_key(audio_44k)
    features['key'] = hpcp_key['key_number']  # 0-11
    features['mode'] = hpcp_key['mode']       # 1=major, 0=minor
    
    # 6. Loudness (EBU R128)
    extractor = es.MusicExtractor()
    pool, _ = extractor(mp3_path)
    features['loudness'] = float(pool['lowlevel.loudness_ebu128.integrated'])
    
    # 7. Acousticness
    acoustic_preds = es.TensorflowPredictMusiCNN(
        graphFilename='models/mood_acoustic-discogs-effnet-1.pb'
    )(audio_16k)
    features['acousticness'] = float(np.mean(acoustic_preds[:, 0]))
    
    # 8. Instrumentalness
    vocal_preds = es.TensorflowPredictMusiCNN(
        graphFilename='models/voice_instrumental-discogs-effnet-1.pb'
    )(audio_16k)
    features['instrumentalness'] = float(np.mean(vocal_preds[:, 0]))
    
    # 9. Speechiness (inverse of instrumentalness, scaled)
    features['speechiness'] = float(1.0 - features['instrumentalness']) * 0.5
    
    # 10. Liveness (from spectral complexity)
    features['liveness'] = float(pool.get('lowlevel.spectral_complexity.mean', 0.2))
    
    # 11. Time signature (from beat tracking)
    rhythm = es.RhythmExtractor2013(method="multifeature")
    bpm, beats, confidence, _, intervals = rhythm(audio_44k)
    features['time_signature'] = 4  # default, can be improved
    
    return features


def compute_key(audio_44k):
    """Trích xuất key và mode từ audio."""
    key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    key_extractor = es.KeyExtractor(profileType='edma')
    key, scale, strength = key_extractor(audio_44k)
    
    return {
        'key_number': key_names.index(key) if key in key_names else 0,
        'mode': 1 if scale == 'major' else 0,
        'strength': float(strength)
    }
```

---

## 3. Pipeline mới đề xuất

### 3.1 So sánh Pipeline cũ vs mới

```
PIPELINE CŨ (7 phases):                    PIPELINE MỚI (7 phases):
═══════════════════════                     ═══════════════════════
Phase 1: Spotify Metadata                   Phase 1: Spotify Metadata (giữ nguyên)
Phase 2: Audio Features (ReccoBeats ❌)     Phase 2: Audio Download (từ Phase 7 cũ)
Phase 3: Lyrics (LRCLIB)                    Phase 3: Audio Features (MỚI - Essentia local)
Phase 4: EDA                                Phase 4: Lyrics (LRCLIB - giữ nguyên)
Phase 5: Feature Engineering                Phase 5: EDA (giữ nguyên)
Phase 6: DW Seed                            Phase 6: Feature Engineering (giữ nguyên)
Phase 7: Audio Download                     Phase 7: DW Seed (giữ nguyên)
```

### 3.2 Lý do thay đổi thứ tự

**Phase 2 mới (Audio Download) phải chạy trước Phase 3 mới (Audio Features)** vì Essentia cần file MP3 vật lý để phân tích. Trước đây download MP3 là bước cuối vì nó không cần thiết cho pipeline xử lý, nhưng bây giờ audio features CẦN MP3 files.

### 3.3 Chiến lược xử lý tracks KHÔNG CÓ MP3

Không phải mọi track đều download được MP3. Chiến lược fallback:

1. **Có MP3** (~60-70%): Trích xuất đầy đủ features bằng Essentia
2. **Không có MP3 nhưng có cache cũ**: Dùng features từ `audio_features.json` cache
3. **Không có MP3 và không có cache**: Điền neutral defaults (đã được `process_data.py` hỗ trợ)
   - valence=0.5, energy=0.5, danceability=0.5, etc.
   - Track vẫn được giữ lại (KHÔNG bị drop)

### 3.4 Dự kiến kết quả

| Metric | Pipeline cũ | Pipeline mới |
|--------|-------------|--------------|
| Tracks sau Phase 1 | 19,430 | 19,430 |
| **Tracks có audio features** | **3,167 (16.3%)** | **~13,000-14,000 (67-72%)** |
| Tracks bị DROP | 16,263 | ~0 (giữ tất cả, fill defaults) |
| Tracks có lyrics | 2,305 | ~2,305+ |
| Tracks có MP3 | ~1,825 | ~12,000-14,000 |
| Tổng tracks vào DW | 3,070 | **~18,000-19,000** |

**→ Tăng từ ~3,000 lên ~18,000 tracks trong hệ thống (6x improvement)**

---

## 4. Phân tích chi tiết từng Phase

### Phase 1: Spotify Metadata — GIỮ NGUYÊN ✅

**Trạng thái**: Hoạt động tốt  
**API**: Spotify Web API  
**Chi phí**: Miễn phí (cần Spotify Developer account)  
**Thay đổi**: Không

Spotify Web API vẫn hoạt động bình thường cho metadata (track info, album art, artist info, search). Chỉ endpoint `audio-features` bị deprecated.

**Cải thiện tiềm năng**:
- Bổ sung MusicBrainz cross-reference (miễn phí, open-source) để mở rộng metadata
- AcoustID fingerprinting có thể dùng sau khi có MP3 để verify/enrich metadata

### Phase 2 (MỚI): Audio Download

**Trạng thái hiện tại**: Đang là Phase 7, hoạt động tốt  
**Tool**: yt-dlp + YouTube Music search  
**Chi phí**: Miễn phí  
**Thay đổi**: Di chuyển lên đầu pipeline

**Lưu ý pháp lý**: 
- yt-dlp download từ YouTube — nằm trong vùng xám pháp lý
- Dùng cho mục đích nghiên cứu/học thuật → được chấp nhận theo fair use
- KHÔNG phân phối lại các file audio
- Chỉ dùng nội bộ trong hệ thống recommendation

### Phase 3 (MỚI): Audio Features via Essentia

**Trạng thái**: MỚI HOÀN TOÀN  
**Tool**: Essentia + pre-trained TensorFlow models  
**Chi phí**: Miễn phí (AGPL v3)  
**Thay đổi**: Thay thế ReccoBeats API bằng local extraction

**Models cần download** (một lần, tổng ~500MB):
```
models/
├── deam-msd-musicnn-2.pb          # Valence + Arousal regression (~3MB)
├── deam-msd-musicnn-2.json
├── danceability-discogs-effnet-1.pb # Danceability classifier (~20MB)
├── danceability-discogs-effnet-1.json
├── mood_acoustic-discogs-effnet-1.pb # Acousticness (~20MB)
├── mood_acoustic-discogs-effnet-1.json
├── voice_instrumental-discogs-effnet-1.pb # Instrumentalness (~20MB)
├── voice_instrumental-discogs-effnet-1.json
├── deeptemp-k16-3.pb              # Tempo estimation (~1.3MB)
└── deeptemp-k16-3.json
```

**Performance ước tính**:
- ~2-5 giây/track trên CPU (tất cả models)
- ~19,000 tracks × 3s = ~16 giờ (có thể batch/parallel)
- Có thể dùng GPU nếu có (nhanh hơn 5-10x)

### Phase 4: Lyrics — GIỮ NGUYÊN ✅

**Trạng thái**: Hoạt động tốt  
**API**: LRCLIB  
**Chi phí**: Miễn phí, không rate limit, không cần API key  
**Thay đổi**: Chỉ đổi số phase (3 → 4)

**Cải thiện tiềm năng**:
- Bổ sung Genius API (free tier, cần API key) cho tracks LRCLIB không có
- Genius có coverage tốt hơn cho nhạc Việt
- NhacCuaTui / ZingMP3 có lyrics Việt rất nhiều nhưng không có public API

### Phase 5: EDA — GIỮ NGUYÊN ✅
### Phase 6: Feature Engineering — GIỮ NGUYÊN ✅

**Thay đổi nhỏ**: Sửa DROP GATE trong `process_data.py`:
- Hiện tại: Drop tracks thiếu cả `valence` VÀ `energy`
- Đề xuất: **Không drop bất kỳ track nào** — fill neutral defaults cho TẤT CẢ tracks thiếu features
- Lý do: Với Essentia, phần lớn tracks sẽ có features. Tracks còn lại vẫn có giá trị (có lyrics, embeddings)

### Phase 7: DW Seed — GIỮ NGUYÊN ✅

---

## 5. Tổng hợp chi phí & pháp lý

### Chi phí

| Thành phần | Chi phí | Ghi chú |
|------------|---------|---------|
| Spotify Web API | Miễn phí | Developer account, metadata only |
| Essentia + Models | Miễn phí | AGPL v3, academic use OK |
| LRCLIB | Miễn phí | Không cần API key |
| yt-dlp | Miễn phí | Open-source |
| PhoBERT | Miễn phí | Open-source (VinAI) |
| PostgreSQL + pgvector | Miễn phí | Open-source |
| **TỔNG** | **$0** | |

### Pháp lý

| Thành phần | License | Rủi ro | Ghi chú |
|------------|---------|--------|---------|
| Essentia | AGPL v3 | Thấp | Miễn phí cho nghiên cứu/phi thương mại. Nếu deploy thương mại → cần license thương mại |
| Essentia Models | CC BY-NC-SA 4.0 | Thấp | Non-commercial → OK cho đồ án. Thương mại → cần license riêng |
| yt-dlp audio download | Vùng xám | Trung bình | Fair use cho nghiên cứu. Không phân phối file. Chỉ dùng nội bộ |
| LRCLIB | Mở | Thấp | Public API, khuyến khích sử dụng |
| Spotify API | Terms of Service | Thấp | Tuân thủ ToS: cache < 30 ngày, hiển thị attribution |
| PhoBERT | MIT | Rất thấp | Mở hoàn toàn |

**Kết luận pháp lý**: Toàn bộ stack là miễn phí và hợp pháp cho dự án đồ án/nghiên cứu. Nếu triển khai thương mại, cần lưu ý license AGPL của Essentia và CC BY-NC-SA của models.

---

## 6. Implementation Plan

### Bước 1: Cài đặt Essentia & download models
```bash
pip install essentia-tensorflow
# Download models từ https://essentia.upf.edu/models/
```

### Bước 2: Tạo module `tools/extract_features.py`
- Wrapper function trích xuất tất cả features từ MP3
- Checkpoint support (resume nếu bị gián đoạn)
- Batch processing

### Bước 3: Sửa `tools/pipeline.py`
- Đổi thứ tự phases: download trước, extract features sau
- Phase 2 mới = download_music
- Phase 3 mới = extract_features (Essentia)

### Bước 4: Sửa `tools/collect_data.py`
- Loại bỏ ReccoBeats/Spotify audio-features code
- Import từ extract_features module thay thế

### Bước 5: Sửa `tools/process_data.py`
- Loại bỏ DROP GATE cho audio features
- Giữ TẤT CẢ tracks, fill defaults cho tracks thiếu

### Bước 6: Test mode (50 tracks)
### Bước 7: Production run (full 19,430 tracks)

---

## 7. Lựa chọn thay thế (nếu không dùng Essentia)

### Option B: librosa + scikit-learn
- **Pro**: Thư viện Python phổ biến, dễ cài
- **Con**: Không có pre-trained models cho valence/energy, phải tự train
- **Con**: Cần dataset annotated để train (không có sẵn)
- **Kết luận**: Không khả thi vì thiếu training data cho mood/valence regression

### Option C: Chỉ dùng PhoBERT embeddings (bỏ audio features)
- **Pro**: Không cần MP3, không cần API, đã có sẵn
- **Con**: Mất 30-45% recommendation accuracy (audio features là backbone)
- **Con**: Color mapping không hoạt động (cần valence/energy)
- **Con**: Mood quadrants không hoạt động
- **Kết luận**: Không khả thi — phá vỡ core features của hệ thống

### Option D: Neutral defaults cho tất cả
- **Pro**: Zero effort, giữ tất cả tracks
- **Con**: Mọi track có cùng valence=0.5, energy=0.5 → recommendation vô nghĩa
- **Con**: Color mapping cho ra cùng 1 màu cho tất cả tracks
- **Kết luận**: Không khả thi — equivalent to random recommendation

### Option E: Tìm API thay thế khác
- Spotify audio-features đã chết, ReccoBeats cũng chết
- AcousticBrainz (Mozilla): **Cũng đã shutdown** (tháng 4/2022)
- Không còn free API nào cung cấp Spotify-style audio features
- **Kết luận**: Không khả thi — thời đại free audio feature APIs đã kết thúc

**→ Essentia (Option A) là giải pháp duy nhất khả thi, miễn phí, và bền vững.**

---

## 8. Kết luận & Khuyến nghị

### Khuyến nghị chính: Triển khai Essentia

1. **Giải quyết triệt để** vấn đề 83.7% data loss
2. **Miễn phí** hoàn toàn cho dự án học thuật
3. **Không phụ thuộc API** — chạy offline, không sợ deprecated
4. **Chất lượng cao** — pre-trained models từ top MIR research lab (MTG-UPF)
5. **Tương thích** — output format tương đương Spotify audio features
6. **Bền vững** — open-source, cộng đồng active, models liên tục cập nhật

### Requirement duy nhất: Cần có MP3 files
- Pipeline mới YÊU CẦU download MP3 trước khi extract features
- Tracks không có MP3 → dùng cache cũ hoặc neutral defaults
- Coverage dự kiến: 60-70% tracks có MP3 = 60-70% tracks có real features

### Tiếp theo
Xác nhận phương án và tiến hành implementation.
