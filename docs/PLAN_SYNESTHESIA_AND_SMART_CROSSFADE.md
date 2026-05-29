# 🌈🎚️ Implementation Plan — Synesthesia Live + Smart Crossfade

**Ngày lập:** 29/05/2026
**Phạm vi:** Triển khai 2 tính năng mới (visual + audio) dựa trên research papers SOTA
**Trạng thái backend hiện tại:** MERT-v1-95M đã wire trong `core/mert_encoder.py`; cos/sin equal-power crossfade đã đúng toán học trong `player.js:1060–1135`; pipeline có sẵn `valence`, `arousal`, `tempo`, `key`, `mode`, `energy`, `loudness` per song

---

## 🎯 TL;DR

| Feature | Ước tính tổng | Phase 1 (ship nhanh) | Phase 2 (full) | Phase 3 (optional) |
|---|---|---|---|---|
| 🌈 Synesthesia Live | 5–7 ngày | 4–6h (per-song color drift) | 3–5 ngày (per-segment live painting) | 1 tuần (WebGL grain) |
| 🎚️ Smart Crossfade | 7–10 ngày | 1–2 ngày (smart policy) | 2–3 ngày (LUFS normalization) | 4–6 ngày (cue points + beat-align) |

**Roadmap khuyến nghị**: Phase 1 cả 2 tính năng trước (ship trong 1 tuần với wow factor lớn), rồi Phase 2 song song.

---

# PHẦN A — SYNESTHESIA LIVE 🌈

## A1. Cơ sở khoa học

### A1.1 Công thức V-A → Color (validated)

**Palmer & Schloss (2013) "Music–color associations are mediated by emotion"** — PNAS, 18 classical excerpts × 37 colors × ~100 participants US+MX. Replicated 2018, 2022.

Công thức chính (chuyển sang HSL rồi render Oklch):
```
H = 60 - 180 * (1 - V)  +  30 * A * sign(0.5 - V)   # yellow→blue axis, red pull at high A
S = 0.35 + 0.55 * A                                  # 35–90 % saturation
L = 0.30 + 0.45 * V                                  # 30–75 % lightness
```
- V, A ∈ [0,1]
- Sai số ±5°/±5% so với regression của Palmer
- Khớp với `emotion_color_profiles` đã có trong `core/advanced_color_mapping.py:34–80`

**Jonauskaite et al. (2020)** — N=4,598 × 30 quốc gia. Confirm hue mapping invariant ở mức r=0.88. **VN trong cluster SE-Asia → hue offset −5° warm side** (config flag `SYNESTHESIA_CULTURE = "vi"`).

### A1.2 Per-segment V-A extraction (key innovation)

**MERT-v1-95M + ridge head trên DEAM** — published numbers:
- R² ≈ 0.62 arousal, 0.52 valence trên DEAM (SOTA trên benchmark này)
- Layer-7 hidden states mạnh nhất cho emotion task
- Native 24 kHz, 75 Hz frame rate
- Brightify đã có `core/mert_encoder.py` — chỉ cần thêm `extract_windows()` method

**Procedure**:
1. Switch từ mean-pooling per song → sliding window 5s với 50% overlap (75 Hz × 5s = 375 frames → average-pool → 768-d vector/window)
2. Train ridge regression head trên DEAM `valence_continuous.csv` / `arousal_continuous.csv` (1,802 clips, ~30 phút CPU training)
3. Lưu thành table `song_segments(song_id, t_start, t_end, valence, arousal, hex)` — ~600 segments × 4,300 songs ≈ 2.6M rows (<200MB)

**Browser fallback** (nếu cần real-time cho user-uploaded MP3): Essentia.js + Meyda.js + MTG arousal/valence MusiCNN model — ~30–50ms inference per 3s chunk.

### A1.3 Color rendering smoothness

- **Color space**: **Oklab/Oklch** (Ottosson 2020) — perceptually uniform, no dead-grey midpoints, CSS4 native (Chrome 111+, Firefox 113+, Safari 16.2+, 93% global support). Native `color-mix(in oklch, ...)`.
- **Temporal smoothing**: **One-Euro Filter** (Casiez et al. CHI 2012) — beats EMA. Params đề xuất với V-A 0.2Hz sampling: `mincutoff = 0.15 Hz`, `β = 0.02`. Filter V, A *trước* khi convert color (không smooth trong RGB/HSL — sinh grey midpoints).
- **Render**: Canvas2D radial-gradient là đủ. Chỉ upgrade WebGL nếu cần particle/grain.

## A2. Plan triển khai 3 phase

### Phase 1 — Static colored backdrop (4–6h, ship liền)
**Mục tiêu**: Background slowly drifting two-stop Oklch radial gradient dựa trên V-A per-song có sẵn.

**Files**:
- New: `static/js/synesthesia.js` (~150 dòng)
- New: `static/js/oklab.js` (~50 dòng utility)
- Modify: `static/js/player.js` — hook vào `onTrackChange` callback

**No backend changes**. Chỉ dùng `song.valence`, `song.arousal` đã có sẵn.

### Phase 2 — Per-segment live painting (3–5 ngày, BIG payoff)
**Mục tiêu**: Màu screen theo emotional arc của bài real-time.

**Backend work** (~2 ngày):
1. New file `tools/train_va_head.py` — train ridge regression head trên DEAM
2. New file `tools/extract_segment_emotion.py` — reuse `core/mert_encoder.py` với sliding windows
3. Alembic migration: `song_segments(song_id FK, t_start FLOAT, t_end FLOAT, valence FLOAT, arousal FLOAT, hex TEXT)` + index `(song_id, t_start)`
4. Add as Phase 5.5 trong `tools/pipeline.py`
5. New route `GET /api/recommend/segments/{song_id}` trả mảng segments

**Ingest** (~1 ngày): 4,300 songs × ~6h MERT CPU → parallelize 4 workers ≈ 1.5h thực

**Frontend work** (~2 ngày):
- Extend `synesthesia.js`: One-Euro filter (~40 dòng port từ casiez/OneEuroFilter), Oklab interpolation (~30 dòng), `requestAnimationFrame` loop
- Đọc segments khi load track, sync với `audio.currentTime`

### Phase 3 — Live spectral overlay (1 tuần, OPTIONAL)
**Mục tiêu**: Real-time feeling với FFT-driven grain/pulse trên gradient.

- Meyda.js FFT → spectral centroid → micro hue shift
- Loudness RMS → radial gradient inner radius
- Tempo-locked beat detection → subtle pulse
- Optional: 1 Butterchurn preset port sang WebGL shader

**Diminishing returns**. Ship Phase 2 trước, lấy feedback rồi quyết.

## A3. Files sẽ touch

- `core/mert_encoder.py` — add `extract_windows()` method
- `core/advanced_color_mapping.py` — add `va_to_oklch(v, a)` helper
- `tools/` — new `extract_segment_emotion.py`, `train_va_head.py`
- `db/models.py` + Alembic migration — `SongSegment` table
- `api/recommend.py` — `/api/recommend/segments/{song_id}` route
- `static/js/` — new `synesthesia.js`, `oklab.js`, `one_euro.js`; hook từ `player.js`
- `config.py` — `SYNESTHESIA_*` config block (`SYNESTHESIA_CULTURE = "vi"`, sampling rate, filter params)

---

# PHẦN B — SMART CROSSFADE 🎚️

## B1. Critique 15s fixed crossfade hiện tại

`_startCrossfade()` ở `player.js:1072-1135` đúng về toán (cos/sin equal-power) nhưng policy có **5 lỗi định lượng**:

1. **15s quá dài cho ~80% Vpop ballad** — Spotify default 5–6s general, 6–12s EDM. Vpop ballad có outro vocal → 15s overlap = vocal đè vocal = đục, ướt
2. **Không BPM matching = "train wreck"** — Vande Veire & De Bie 2018: mix seamless cần BPM delta ±6%. Random pair > 6% delta → polyrhythm 15s
3. **Không key matching = harmonic dissonance** — Camelot Wheel: ~20% các cặp key tương thích. Random transition → 80% clash
4. **Không loudness normalization** — Spotify target −14 LUFS (ITU-R BS.1770). MP3 từ yt-dlp không normalize → variance ±6 LU → volume jump audible mà cos/sin không che được
5. **Fixed cue point (last 15s − skip 10s intro)** — Zehren et al. 2020: novelty curves đạt 96% agreement với expert. Heuristic của Brightify fade vào outro silence/applause/clap

**Kết hợp 5 lỗi**: trên >50% random adjacent pairs, 15s default *tệ hơn hard cut*.

## B2. Architectural design: `smart_crossfade()`

Function mới = **policy engine** quyết 4 số + 1 cặp cue, hand off sang kernel cos/sin có sẵn (kernel ĐÚNG, giữ nguyên).

```javascript
// Returns { duration_s, fadeOutStartAt_s, fadeInStartAt_s, gainA, gainB, curve }
function planCrossfade(trackA, trackB, userBaseVolume) {
  // ── 1. Feature deltas ──────────────────────────
  const dTempo = Math.abs(trackA.tempo - trackB.tempo) / trackA.tempo;
  const dEnergy = Math.abs(trackA.energy - trackB.energy);
  const sameQuad = trackA.mood_quadrant === trackB.mood_quadrant;
  const keyCompat = camelotCompatible(trackA.key, trackA.mode,
                                      trackB.key, trackB.mode);

  // ── 2. Duration policy (Bittner 2017 + Spotify) ─────
  let duration = 6.0;
  if (sameQuad && dTempo < 0.06 && keyCompat >= 0.7) duration = 10.0;
  if (dTempo > 0.10 || dEnergy > 0.4) duration = 3.0;
  if (trackA.energy > 0.75 && trackB.energy > 0.75) duration = 8.0;
  duration = Math.max(2.0, Math.min(12.0, duration));

  // ── 3. Cue points (Zehren 2020) ─────────────────
  const fadeOutStart = trackA.fade_out_cue_s
      ?? Math.max(0, trackA.duration - duration - 5);
  const fadeInStart = trackB.fade_in_cue_s
      ?? (trackB.duration > 45 ? 10 : 0);

  // ── 4. Loudness-matched gains (ITU-R BS.1770) ──
  const TARGET_LUFS = -14;
  const gainA = userBaseVolume * dbToLin(TARGET_LUFS - (trackA.loudness_lufs ?? -14));
  const gainB = userBaseVolume * dbToLin(TARGET_LUFS - (trackB.loudness_lufs ?? -14));
  const clamp = v => Math.min(1.0, Math.max(0, v));

  // ── 5. Curve (linear cho very-similar, equal-power default) ─
  const correlated = sameQuad && dTempo < 0.03 && keyCompat === 1.0;
  const curve = correlated ? 'linear' : 'equal-power';

  return {
    duration_s: duration,
    fadeOutStartAt_s: fadeOutStart,
    fadeInStartAt_s: fadeInStart,
    gainA: clamp(gainA), gainB: clamp(gainB),
    curve,
  };
}

function camelotCompatible(keyA, modeA, keyB, modeB) {
  const camA = toCamelot(keyA, modeA);  // {n: 1-12, letter: 'A'|'B'}
  const camB = toCamelot(keyB, modeB);
  if (camA.n === camB.n && camA.letter === camB.letter) return 1.0;
  if (camA.n === camB.n) return 0.8;                             // mode flip
  if (camA.letter === camB.letter &&
      (Math.abs(camA.n - camB.n) === 1 ||
       Math.abs(camA.n - camB.n) === 11)) return 0.7;            // adjacent +wrap
  return 0.4;
}

function dbToLin(db) { return Math.pow(10, db / 20); }
```

## B3. Camelot Wheel lookup (`key` 0-11 + `mode` 0/1 → Camelot)

```javascript
const CAMELOT_MAP = {
  // Major (mode=1)
  '0,1': {n:8,letter:'B'},  '1,1': {n:3,letter:'B'},  '2,1': {n:10,letter:'B'},
  '3,1': {n:5,letter:'B'},  '4,1': {n:12,letter:'B'}, '5,1': {n:7,letter:'B'},
  '6,1': {n:2,letter:'B'},  '7,1': {n:9,letter:'B'},  '8,1': {n:4,letter:'B'},
  '9,1': {n:11,letter:'B'}, '10,1':{n:6,letter:'B'},  '11,1':{n:1,letter:'B'},
  // Minor (mode=0)
  '0,0': {n:5,letter:'A'},  '1,0': {n:12,letter:'A'}, '2,0': {n:7,letter:'A'},
  '3,0': {n:2,letter:'A'},  '4,0': {n:9,letter:'A'},  '5,0': {n:4,letter:'A'},
  '6,0': {n:11,letter:'A'}, '7,0': {n:6,letter:'A'},  '8,0': {n:1,letter:'A'},
  '9,0': {n:8,letter:'A'},  '10,0':{n:3,letter:'A'},  '11,0':{n:10,letter:'A'},
};
function toCamelot(key, mode) {
  return CAMELOT_MAP[`${key},${mode}`] || {n:1, letter:'A'};
}
```

## B4. Plan triển khai 3 phase

### Phase 1 — Smart policy (1–2 ngày, behind feature flag)
**Mục tiêu**: 70% perceived improvement, ZERO pipeline change.

- Implement `planCrossfade()` + `camelotCompatible()` + `CAMELOT_MAP` trong `static/js/player.js`
- Replace fixed 15s với `planCrossfade().duration_s`
- Vẫn dùng `audio.volume` (chưa rewire Web Audio)
- Feature flag: `localStorage.bf_smart_crossfade = true`
- A/B test với existing users

### Phase 2 — Loudness normalization (2–3 ngày, big subjective lift)
**Mục tiêu**: Xóa volume-jump artifact — single biggest quality win.

**Backend**:
- Alembic migration: thêm `loudness_lufs FLOAT` column vào `songs` table
- `tools/extract_audio_features.py`: thêm `pyloudnorm.Meter(rate).integrated_loudness(audio)` (~10 dòng)
- Backfill 4,300 songs: ~1–2h batch
- `api/music.py`: include `loudness_lufs` trong song response

**Frontend**:
- Rewire player: `AudioContext → MediaElementSource → GainNode → destination` (~30 dòng)
- Set gains từ `planCrossfade()` thay vì `audio.volume`

### Phase 3 — Cue points + beat-align (4–6 ngày, OPTIONAL pro-DJ feel)
**Mục tiêu**: Pro-DJ cueing cho ~30% catalog (danceable subset).

**Backend**:
- Alembic migration: `fade_out_cue_s FLOAT`, `fade_in_cue_s FLOAT`, `downbeat_times_json TEXT` (gzip-compressible)
- `tools/process_data.py` Phase 6: librosa `agglomerative` segmentation hoặc `msaf`
  - Last boundary trước outro silence → `fade_out_cue_s`
  - First boundary sau intro silence → `fade_in_cue_s`
- Đối với danceable (Q1/Q2 + danceability > 0.7): trích `librosa.beat.beat_track` → downbeat_times

**Frontend**:
- Đọc cue points; snap fade start to nearest downbeat cho danceable tracks

## B5. KHÔNG nên làm (over-engineering traps)

1. ❌ **Real-time time-stretching cho BPM-match** — SoundTouchJS WSOLA artifacts trên vocals khi stretch > 6%; CPU 2x. Đối với streaming app (không phải DJ tool) → ưu tiên SKIP incompatible-tempo pairs trong queue ordering, không stretch
2. ❌ **GAN-based transition model** (Chen et al. 2021/2022) — offline only, train trên EDM, gain marginal so với policy + LUFS đã có
3. ❌ **Real-time stem separation** (djay Pro Neural Mix) — browser inference 100–300ms/s audio (2026 hardware) → không viable
4. ❌ **Compute novelty curves client-side** — O(n²) SSM freeze main thread. Luôn precompute offline
5. ❌ **ML-based mix quality scoring** — không có feedback signal (thumbs up/down) thì không validate được; heuristic Section B2 là baseline mạnh

## B6. Files sẽ touch

- `static/js/player.js:1060-1180` — replace `_startCrossfade()` + `_completeCrossfade()`
- `static/js/player.js` (new section) — add `planCrossfade()`, `camelotCompatible()`, `CAMELOT_MAP`, `toCamelot()`, `dbToLin()`
- `config.py` — `CROSSFADE_TARGET_LUFS = -14`, duration bands, Camelot compatibility scores
- `tools/extract_audio_features.py` — `pyloudnorm` integrated-loudness
- `tools/process_data.py` — structural segmentation cue extraction (Phase 3)
- `db/models.py` + Alembic migrations — `loudness_lufs`, `fade_out_cue_s`, `fade_in_cue_s`, `downbeat_times_json`
- `api/music.py` — expose new fields

---

# PHẦN C — ROADMAP CHUNG (Tổng hợp 2 features)

## C1. Suggested execution order (theo thứ tự "ship first, polish later")

### Week 1 — Quick wins phase 1 cả 2 features
| Day | Task | Output |
|---|---|---|
| 1 | Synesthesia Phase 1 (per-song color drift) | Background paints song-level color |
| 2 | Crossfade Phase 1 (smart policy) | Adaptive 3–12s duration, Camelot key compat |
| 3 | QA + bug fix | Both shipped behind feature flags |

### Week 2 — Phase 2 backend work (song song được)
| Day | Synesthesia | Crossfade |
|---|---|---|
| 4 | Train DEAM V-A head | Add `loudness_lufs` column + pyloudnorm |
| 5 | `extract_segment_emotion.py` + migration | Backfill LUFS for 4,300 songs |
| 6 | Run ingest (parallel 4 workers) | Web Audio GainNode rewire |
| 7 | API route + frontend integration | QA volume normalization |
| 8 | One-Euro filter + Oklab interpolation | — |
| 9 | QA + polish | — |

### Week 3 — Optional Phase 3 (chỉ làm nếu Phase 2 thành công)
- Synesthesia WebGL particle layer (5 ngày)
- Crossfade cue points + beat-align (4–6 ngày)

## C2. Shared infrastructure investments

| Investment | Hỗ trợ Synesthesia | Hỗ trợ Crossfade |
|---|---|---|
| Alembic migration framework | ✅ SongSegment table | ✅ Loudness/cue columns |
| Pipeline Phase 5.5/6 extension | ✅ MERT segment extraction | ✅ pyloudnorm + librosa segmentation |
| Web Audio API in frontend | △ Phase 3 grain only | ✅ Phase 2 GainNode required |
| Feature flag system | ✅ enable/disable visual | ✅ A/B test smart vs old |

→ **Khuyến nghị**: Build feature flag system + Web Audio refactor ở Week 1 luôn (1 ngày), tận dụng cho cả 2 features Phase 2.

## C3. Validation strategy

### Synesthesia
- **Subjective**: 5-10 user thử Phase 2, hỏi: "Có cảm giác màu khớp với mood bài không?" (1-5 Likert)
- **Performance**: Lighthouse score, FPS Chrome DevTools — phải ≥ 55 FPS trên iPhone 12 / mid-range laptop
- **No regression**: Existing player UX không slow xuống

### Crossfade
- **A/B test**: feature flag → so sánh skip rate / next-track engagement
- **ABX listening test**: 3+ người chấm điểm "smart vs 15s default" trên 20 random Vpop pairs
- **Holdout**: Phase 2 ABX phải đạt ≥ 70% prefer smart trước khi merge Phase 3

## C4. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| MERT inference 4,300 songs quá lâu | Med | Parallel 4 workers, có thể overnight |
| pyloudnorm encode lại MP3 sai BPM | Low | Chỉ MEASURE, không re-encode |
| One-Euro filter param sai → flicker | Low | Param chuẩn từ paper, có thể tune live |
| Web Audio rewire break existing player | Med | Feature flag, fallback `audio.volume` |
| User không nhận ra cải tiến crossfade | Med | Đối chiếu A/B metric + ABX test |
| Synesthesia tăng battery drain mobile | Low | Canvas2D Phase 2, không WebGL; pause khi tab background |

---

## NGUỒN THAM KHẢO

### Synesthesia Live
- [Palmer & Schloss 2013 — Music–color associations are mediated by emotion (PNAS)](https://www.pnas.org/doi/full/10.1073/pnas.1212562110)
- [Whiteford et al. 2018 — Color, Music, and Emotion: Bach to the Blues (i-Perception)](https://journals.sagepub.com/doi/10.1177/2041669518808535)
- [Jonauskaite et al. 2020 — Universal Patterns in Color-Emotion Associations (Psych Science)](https://journals.sagepub.com/doi/10.1177/0956797620948810)
- [Li et al. 2023 — MERT: Acoustic Music Understanding Model (arXiv 2306.00107)](https://arxiv.org/abs/2306.00107)
- [MERT-v1-95M HuggingFace](https://huggingface.co/m-a-p/MERT-v1-95M)
- [DEAM dataset](https://cvml.unige.ch/databases/DEAM/)
- [Music2Emo unified emotion recognition (arXiv 2502.03979)](https://arxiv.org/abs/2502.03979)
- [Essentia.js — MTG audio analysis](https://mtg.github.io/essentia.js/)
- [Meyda.js feature extraction](https://meyda.js.org/)
- [Ottosson — Oklab perceptual color space](https://bottosson.github.io/posts/oklab/)
- [MDN oklab() CSS function](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/oklab)
- [Casiez et al. 2012 — 1€ Filter (CHI)](https://gery.casiez.net/publications/CHI2012-casiez.pdf)
- [OneEuroFilter implementations](https://github.com/casiez/OneEuroFilter)
- [Butterchurn WebGL visualizer](https://github.com/jberg/butterchurn)
- [amertx/spotify-visualizer (React + Three.js)](https://github.com/amertx/spotify-visualizer)
- [Spotify Canvas reference](https://artists.spotify.com/en/canvas)

### Smart Crossfade
- [Vande Veire & De Bie 2018 — Seamless mix for D&B](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8)
- [GitHub aida-ugent/dnb-autodj](https://github.com/aida-ugent/dnb-autodj)
- [Bittner et al. 2017 — Automatic Playlist Sequencing and Transitions (ISMIR)](https://rachelbittner.weebly.com/uploads/3/2/1/8/32182799/bittner_ismir-playlist_2017.pdf)
- [Spotify Research — Automatic Playlist Sequencing](https://research.atspotify.com/publications/automatic-playlist-sequencing-and-transitions)
- [Davies et al. 2013 — AutoMashUpper (ISMIR)](https://archives.ismir.net/ismir2013/paper/000077.pdf)
- [Zehren et al. 2020 — Automatic Cue Point Detection (arXiv 2007.08411)](https://arxiv.org/abs/2007.08411)
- [Chen et al. 2021/2022 — DJ Transitions with GANs (arXiv 2110.06525)](https://arxiv.org/abs/2110.06525)
- [Foote 2000 — Audio novelty segmentation](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html)
- [Cliff 2005 — hpDJ HPL Technical Report HPL-2005-88](https://www.hpl.hp.com/techreports/2005/HPL-2005-88.html)
- [Spotify Loudness Normalization (artists support)](https://support.spotify.com/us/artists/article/loudness-normalization/)
- [Camelot Wheel reference (Mark Davis / Mixed In Key)](https://dj.studio/blog/camelot-wheel)
- [Audacity Manual — Fade and Crossfade](https://manual.audacityteam.org/man/fade_and_crossfade.html)
- [SoundTouchJS — WSOLA time-stretch](https://github.com/cutterbl/SoundTouchJS/)
- [Algoriddim djay Pro Neural Mix](https://www.algoriddim.com/neural-mix)
- [Princeton 2024 — Supervised Learning for DJ Transitions](https://theses-dissertations.princeton.edu/entities/publication/86237923-6f8a-4172-a6e7-d639e97d38d1)
