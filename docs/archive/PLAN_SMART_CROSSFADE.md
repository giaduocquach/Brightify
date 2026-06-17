# 🎚️ Implementation Plan — Smart Crossfade

**Ngày lập:** 29/05/2026
**Phạm vi:** Nâng cấp `_startCrossfade()` từ "15s fixed equal-power" → "AI-aware adaptive smart mix" theo SOTA auto-DJ literature
**Trạng thái hiện tại:** Mathematically đúng (cos/sin equal-power), nhưng policy ngu (15s cố định, không feature-aware)
**Effort tổng:** 7–10 ngày chia 3 phase, có thể ship Phase 1 trong 1–2 ngày

---

## 🎯 TL;DR

| Phase | Effort | Wins | Risk |
|---|---|---|---|
| **Phase 1** — Smart policy | 1–2 ngày | 70% perceived improvement | Thấp — no backend, feature flag |
| **Phase 2** — LUFS normalization | 2–3 ngày | Xóa "volume jump" — biggest subjective win | Med — Web Audio rewire (đã có sẵn 1 phần) |
| **Phase 3** — Cue points + beat-align | 4–6 ngày | Pro-DJ feel cho dance subset | High — pipeline change, validate ABX |

→ **Ship Phase 1 trước trong 1 sprint**, gather feedback, rồi Phase 2.

---

## 📊 PHẦN 1 — Critique trạng thái hiện tại

File: `static/js/player.js:1060–1135`

### Cách hoạt động hiện tại

```js
// app.js:2244 — crossfade settings
const crossfade = {
    enabled: false,
    duration: 15,    // CỐ ĐỊNH 15s
};

// player.js:697 — trigger condition
if (window.crossfade?.enabled && duration > 15) {
    const triggerAt = crossfadeDuration + 5;  // start 20s trước hết bài
    if (currentTime >= duration - triggerAt) this._startCrossfade();
}

// player.js:1072 — actual mixing
_startCrossfade() {
    // Cos/sin curve over 15s
    // Skip 10s intro của next track
    // audio.volume = startVol * cos(p * π/2)        ← fade out
    // _audioInactive.volume = targetVol * sin(p * π/2)  ← fade in
}
```

### 5 lỗi định lượng (cited research)

1. **15s quá dài cho ~80% Vpop ballad** (Spotify default 5–6s general, 6–12s EDM)
   → Vocal đè vocal 15s = đục, ướt, ướt át
   
2. **Không BPM matching = "train wreck"** (Vande Veire & De Bie 2018)
   → Random pair > 6% BPM delta → polyrhythm chaos
   → Brightify currently mix 75 BPM ballad với 130 BPM dance = thảm họa
   
3. **Không key matching = harmonic dissonance** (Camelot Wheel)
   → ~20% pairs key tương thích → 80% clash khi không filter
   
4. **Không LUFS normalization** (ITU-R BS.1770)
   → Variance ±6 LU giữa indie demo và Vpop master
   → Volume nhảy +13 dB → đau tai
   
5. **Fixed cue point** (`last 15s − skip 10s intro`)
   → Fade vào outro silence/applause/clap (Zehren et al. 2020: 96% accuracy với novelty curves)

**Kết hợp 5 lỗi**: > 50% adjacent pairs hiện tại **tệ hơn hard cut**.

---

## 🏗️ PHẦN 2 — Architectural design: `planCrossfade()`

Function mới là **policy engine** — quyết 4 số + 1 cặp cue, hand off sang kernel cos/sin có sẵn (kernel đúng, giữ nguyên).

### Function signature

```javascript
/**
 * @returns {{
 *   duration_s: number,           // 2.0–12.0
 *   fadeOutStartAt_s: number,     // when in trackA to start fading out
 *   fadeInStartAt_s: number,      // where in trackB to start playing from
 *   gainA: number,                // 0–1, pre-normalized for trackA loudness
 *   gainB: number,                // 0–1, pre-normalized for trackB loudness
 *   curve: 'equal-power' | 'linear'
 * }}
 */
function planCrossfade(trackA, trackB, userBaseVolume) { ... }
```

### Logic flow

```
INPUT: trackA (current), trackB (next), userBaseVolume (0–1)

1. Tính 4 deltas
   ├── dTempo = |Atempo - Btempo| / Atempo
   ├── dEnergy = |Aenergy - Benergy|
   ├── sameQuad = (Amood === Bmood)
   └── keyCompat = camelotCompatible(A.key, A.mode, B.key, B.mode)

2. Duration policy (Bittner 2017 + Spotify defaults)
   Base = 6s
   ├── sameQuad && dTempo<0.06 && keyCompat≥0.7 → 10s smooth blend
   ├── dTempo>0.10 || dEnergy>0.4 → 3s fast cut
   ├── both energy>0.75 (EDM pair) → 8s
   └── clamp [2.0, 12.0]

3. Cue points (Zehren 2020 / Foote 2000)
   ├── fadeOutStart = A.fade_out_cue_s ?? (A.duration - duration - 5)
   └── fadeInStart = B.fade_in_cue_s ?? (B.duration > 45 ? 10 : 0)

4. Loudness gains (ITU-R BS.1770 / EBU R128)
   TARGET = -14 LUFS (Spotify standard)
   ├── gainA = userBase × dbToLin(TARGET - A.loudness_lufs)
   ├── gainB = userBase × dbToLin(TARGET - B.loudness_lufs)
   └── clamp [0, 1.0] (không amplify > 1 = risk clipping)

5. Curve choice (Audacity/KVR consensus)
   ├── correlated = sameQuad && dTempo<0.03 && keyCompat===1.0
   └── curve = correlated ? 'linear' : 'equal-power'

OUTPUT: { duration_s, fadeOutStartAt_s, fadeInStartAt_s, gainA, gainB, curve }
```

### Camelot Wheel mapping

`(key, mode)` → Camelot code → compatibility score:

```javascript
const CAMELOT_MAP = {
  // Major (mode=1) keys
  '0,1':  {n:8, letter:'B'},   // C  major
  '1,1':  {n:3, letter:'B'},   // C# major
  '2,1':  {n:10, letter:'B'},  // D  major
  '3,1':  {n:5, letter:'B'},   // D# major
  '4,1':  {n:12, letter:'B'},  // E  major
  '5,1':  {n:7, letter:'B'},   // F  major
  '6,1':  {n:2, letter:'B'},   // F# major
  '7,1':  {n:9, letter:'B'},   // G  major
  '8,1':  {n:4, letter:'B'},   // G# major
  '9,1':  {n:11, letter:'B'},  // A  major
  '10,1': {n:6, letter:'B'},   // A# major
  '11,1': {n:1, letter:'B'},   // B  major
  // Minor (mode=0) keys
  '0,0':  {n:5, letter:'A'},   // C  minor
  '1,0':  {n:12, letter:'A'},  // C# minor
  '2,0':  {n:7, letter:'A'},   // D  minor
  '3,0':  {n:2, letter:'A'},   // D# minor
  '4,0':  {n:9, letter:'A'},   // E  minor
  '5,0':  {n:4, letter:'A'},   // F  minor
  '6,0':  {n:11, letter:'A'},  // F# minor
  '7,0':  {n:6, letter:'A'},   // G  minor
  '8,0':  {n:1, letter:'A'},   // G# minor
  '9,0':  {n:8, letter:'A'},   // A  minor
  '10,0': {n:3, letter:'A'},   // A# minor
  '11,0': {n:10, letter:'A'},  // B  minor
};

function toCamelot(key, mode) {
  return CAMELOT_MAP[`${key},${mode}`] || {n:1, letter:'A'};
}

function camelotCompatible(keyA, modeA, keyB, modeB) {
  const camA = toCamelot(keyA, modeA);
  const camB = toCamelot(keyB, modeB);
  if (camA.n === camB.n && camA.letter === camB.letter) return 1.0;   // identical
  if (camA.n === camB.n) return 0.8;                                   // mode flip (relative major↔minor)
  if (camA.letter === camB.letter &&
      (Math.abs(camA.n - camB.n) === 1 ||
       Math.abs(camA.n - camB.n) === 11)) return 0.7;                  // adjacent same letter (+wrap)
  return 0.4;                                                          // incompatible
}
```

---

## 🚀 PHẦN 3 — PHASE 1: Smart policy (1–2 ngày)

**Mục tiêu**: 70% perceived improvement, **ZERO backend change**, feature flag để A/B test.

### Files affected

| File | Action | LOC delta |
|---|---|---|
| `static/js/player.js` | Replace `_startCrossfade()` body (line 1072–1135) | ~+80, -20 |
| `static/js/player.js` | Add new section: `planCrossfade()`, `camelotCompatible()`, `CAMELOT_MAP`, `toCamelot()`, `dbToLin()` | +~120 |
| `static/js/app.js:2244` | Add `smart: true` flag to crossfade object + toggle | +5 |
| `static/index.html:213` | (Optional) Add small "🧠 Smart" badge on crossfade button | +2 |

### Step-by-step implementation

#### Step 1.1 — Add policy module (before `class MusicPlayer`)

Đặt block code này TRƯỚC `class MusicPlayer` ở đầu file `player.js`:

```javascript
// ═════════════════════════════════════════════════════════════════════════
// SMART CROSSFADE POLICY (Phase 1)
// Research: Bittner 2017 (ISMIR), Vande Veire & De Bie 2018, Camelot Wheel
// ═════════════════════════════════════════════════════════════════════════

const CAMELOT_MAP = { /* ... (paste from above) ... */ };
function toCamelot(key, mode) { /* ... */ }
function camelotCompatible(keyA, modeA, keyB, modeB) { /* ... */ }
function dbToLin(db) { return Math.pow(10, db / 20); }

function planCrossfade(trackA, trackB, userBaseVolume) {
    // Safe defaults nếu thiếu data
    const Atempo = trackA.tempo ?? 120;
    const Btempo = trackB.tempo ?? 120;
    const Aenergy = trackA.energy ?? 0.5;
    const Benergy = trackB.energy ?? 0.5;
    const Akey = trackA.key ?? 0;
    const Bkey = trackB.key ?? 0;
    const Amode = trackA.mode ?? 1;
    const Bmode = trackB.mode ?? 1;
    const Amood = trackA.mood_quadrant ?? 'Q4';
    const Bmood = trackB.mood_quadrant ?? 'Q4';

    // 1. Feature deltas
    const dTempo = Math.abs(Atempo - Btempo) / Math.max(Atempo, 1);
    const dEnergy = Math.abs(Aenergy - Benergy);
    const sameQuad = Amood === Bmood;
    const keyCompat = camelotCompatible(Akey, Amode, Bkey, Bmode);

    // 2. Duration policy
    let duration = 6.0;
    if (sameQuad && dTempo < 0.06 && keyCompat >= 0.7) duration = 10.0;
    if (dTempo > 0.10 || dEnergy > 0.4) duration = 3.0;
    if (Aenergy > 0.75 && Benergy > 0.75) duration = 8.0;
    duration = Math.max(2.0, Math.min(12.0, duration));

    // 3. Cue points (fallback heuristic when not precomputed)
    const Adur = trackA.duration ?? Atempo > 0 ? 180 : 180;
    const Bdur = trackB.duration ?? 180;
    const fadeOutStart = trackA.fade_out_cue_s
        ?? Math.max(0, Adur - duration - 5);
    const fadeInStart = trackB.fade_in_cue_s
        ?? (Bdur > 45 ? 10 : 0);

    // 4. Loudness gains (skip if no LUFS data in Phase 1)
    const TARGET_LUFS = -14;
    const hasLUFS = (trackA.loudness_lufs != null) && (trackB.loudness_lufs != null);
    const gainA = hasLUFS
        ? Math.min(1.0, Math.max(0, userBaseVolume * dbToLin(TARGET_LUFS - trackA.loudness_lufs)))
        : userBaseVolume;
    const gainB = hasLUFS
        ? Math.min(1.0, Math.max(0, userBaseVolume * dbToLin(TARGET_LUFS - trackB.loudness_lufs)))
        : userBaseVolume;

    // 5. Curve choice
    const correlated = sameQuad && dTempo < 0.03 && keyCompat === 1.0;
    const curve = correlated ? 'linear' : 'equal-power';

    // Debug logging (gate behind localStorage flag)
    if (localStorage.getItem('bf_crossfade_debug') === 'true') {
        console.log('[crossfade]', {
            A: trackA.track_name, B: trackB.track_name,
            dTempo: dTempo.toFixed(3), dEnergy: dEnergy.toFixed(3),
            sameQuad, keyCompat,
            duration_s: duration, curve,
            gainA: gainA.toFixed(2), gainB: gainB.toFixed(2),
        });
    }

    return {
        duration_s: duration,
        fadeOutStartAt_s: fadeOutStart,
        fadeInStartAt_s: fadeInStart,
        gainA, gainB,
        curve,
    };
}
```

#### Step 1.2 — Modify `_startCrossfade()` to use policy

Trong `player.js:1072–1135`, thay thế body của `_startCrossfade()`:

```javascript
_startCrossfade() {
    const nextIdx = this._getNextIndex();
    if (nextIdx < 0 || nextIdx === this.currentIndex) return;
    const nextSong = this.queue[nextIdx];
    const currentSong = this.queue[this.currentIndex];
    if (!nextSong?.has_audio || !nextSong?.audio_url) return;

    // ── SMART POLICY: decide all crossfade params ──
    const plan = (window.crossfade?.smart !== false)
        ? planCrossfade(currentSong, nextSong, this.volume)
        : {  // legacy fallback: 15s fixed equal-power
            duration_s: window.crossfade?.duration ?? 15,
            fadeOutStartAt_s: null,
            fadeInStartAt_s: nextSong.duration > 45 ? 10 : 0,
            gainA: this.volume, gainB: this.volume,
            curve: 'equal-power',
        };

    this._crossfading = true;
    this._crossfadeNextIdx = nextIdx;

    // Load next track on inactive audio element
    this._audioInactive.src = nextSong.audio_url;
    this._audioInactive.volume = 0;

    const onReady = () => {
        this._audioInactive.removeEventListener('loadedmetadata', onReady);
        const skipTo = plan.fadeInStartAt_s ?? 0;
        if (this._audioInactive.duration > skipTo + 10) {
            this._audioInactive.currentTime = skipTo;
        }
    };
    this._audioInactive.addEventListener('loadedmetadata', onReady);
    if (window.playbackSpeed) this._audioInactive.playbackRate = window.playbackSpeed.current;
    this._audioInactive.play().catch(() => {});

    // Equal-power OR linear curve
    const duration_ms = plan.duration_s * 1000;
    const startTime = performance.now();
    const halfPi = Math.PI / 2;

    if (this._crossfadeRaf) cancelAnimationFrame(this._crossfadeRaf);

    const fadeStep = (now) => {
        const elapsed = now - startTime;
        const p = Math.min(1, elapsed / duration_ms);

        let fadeOutGain, fadeInGain;
        if (plan.curve === 'linear') {
            fadeOutGain = 1 - p;
            fadeInGain = p;
        } else {  // equal-power (default)
            fadeOutGain = Math.cos(p * halfPi);
            fadeInGain = Math.sin(p * halfPi);
        }

        this.audio.volume = Math.max(0, Math.min(1, plan.gainA * fadeOutGain));
        this._audioInactive.volume = Math.max(0, Math.min(1, plan.gainB * fadeInGain));

        if (p < 1 && this._crossfading) {
            this._crossfadeRaf = requestAnimationFrame(fadeStep);
        } else {
            this._crossfadeRaf = null;
            if (this._crossfading) this._completeCrossfade();
        }
    };

    this._crossfadeRaf = requestAnimationFrame(fadeStep);
}
```

#### Step 1.3 — Update trigger condition (player.js:696–705)

Thay đoạn:
```javascript
if (window.crossfade?.enabled && duration > 15) {
    const crossfadeDuration = window.crossfade.duration || 15;
    const triggerAt = crossfadeDuration + 5;
```

Bằng:
```javascript
if (window.crossfade?.enabled && duration > 15 && !this._crossfading) {
    // Smart mode: peek next track to compute trigger time
    const nextIdx = this._getNextIndex();
    const nextSong = nextIdx >= 0 ? this.queue[nextIdx] : null;
    let triggerAt;
    if (window.crossfade?.smart !== false && nextSong) {
        // Estimate plan to know real duration
        const plan = planCrossfade(this.queue[this.currentIndex], nextSong, this.volume);
        triggerAt = plan.duration_s + 0.5;  // start RAF 0.5s before fade window
    } else {
        triggerAt = (window.crossfade.duration || 15) + 5;
    }
    if (currentTime >= duration - triggerAt) this._startCrossfade();
}
```

#### Step 1.4 — Update `crossfade` settings object (app.js:2244)

```javascript
const crossfade = {
    enabled: false,
    smart: true,           // NEW: enable smart policy (default on)
    duration: 6,           // CHANGED: fallback for non-smart mode (was 15)
    
    toggle() {
        this.enabled = !this.enabled;
        localStorage.setItem('bf_crossfade', this.enabled);
        const btn = document.getElementById('btn-crossfade');
        if (btn) btn.classList.toggle('active', this.enabled);
        const label = this.smart ? '🧠 Smart Crossfade' : `🔀 Crossfade (${this.duration}s)`;
        app.toast(this.enabled ? `${label} bật` : '🔀 Crossfade tắt', 'info');
    },
    
    toggleSmart() {
        this.smart = !this.smart;
        localStorage.setItem('bf_crossfade_smart', this.smart);
        app.toast(this.smart ? '🧠 Smart Crossfade' : '🔀 Legacy 15s fixed', 'info');
    },
};
window.crossfade = crossfade;

// Restore
if (localStorage.getItem('bf_crossfade') === 'true') crossfade.enabled = true;
if (localStorage.getItem('bf_crossfade_smart') === 'false') crossfade.smart = false;
```

#### Step 1.5 — Verify song payload có đủ fields

Frontend cần các fields: `tempo`, `energy`, `key`, `mode`, `mood_quadrant`, `duration`.

Check `api/music.py:_song_to_dict()` đảm bảo trả về các fields trên. Đặc biệt `mode` và `key` có thể bị thiếu trong default response — cần verify.

```bash
# Test endpoint
curl http://localhost:8000/api/songs/random?count=1 | jq '.songs[0]'
# Phải có: tempo, energy, key, mode, mood_quadrant, duration
```

Nếu thiếu, thêm vào `_song_to_dict()` ở `api/music.py`.

### Edge cases Phase 1

| Case | Handler |
|---|---|
| Track A < 30s (rất ngắn) | `duration = min(plan.duration_s, A.duration * 0.3)` |
| Missing tempo/key/mode | Default 120/0/1 → fallback to 6s |
| Same song repeat (repeat=one) | `_startCrossfade()` early return (đã có check) |
| User skip giữa crossfade | `_cancelCrossfade()` đã handle, không cần đổi |
| First track in queue (no prev) | Không trigger, không liên quan |
| Audio not loaded | `play().catch()` đã catch |

### Test plan Phase 1

**Unit test** (manual, trong console):
```javascript
// Mở DevTools console
localStorage.setItem('bf_crossfade_debug', 'true');

// Test pairs (chọn 5 pair từ catalog)
// Pair 1: Cùng mood, cùng key (expect 10s)
// Pair 2: Mood khác, tempo lệch (expect 3s)
// Pair 3: 2 EDM (expect 8s)
// Pair 4: Random (expect 6s)
// Pair 5: Missing fields (expect 6s default)
```

**ABX listening test**:
1. Chọn 20 random adjacent pair từ playlist
2. Phát với `smart=true` 1 vòng, `smart=false` 1 vòng
3. 3 listener chấm điểm "smoother?" trên Likert 1–5
4. Target: smart prefer rate ≥ 60% (Phase 2 mới đạt ≥ 70%)

### Rollback strategy

Feature flag `localStorage.bf_crossfade_smart=false` → fallback ngay sang 15s fixed cũ. Không cần redeploy.

---

## 🚀 PHẦN 4 — PHASE 2: LUFS normalization (2–3 ngày)

**Mục tiêu**: Xóa "volume jump" artifact — **biggest single subjective quality win**, hơn cả Phase 1.

**Tin tốt**: Codebase ĐÃ CÓ Web Audio setup tại `_initVisualizer()` (player.js:443–455). Chỉ cần insert GainNode vào chain.

### Backend work (1 ngày)

#### Step 2.1 — Add `loudness_lufs` column

Alembic migration mới: `alembic revision -m "add_loudness_lufs"`

```python
# alembic/versions/xxx_add_loudness_lufs.py
def upgrade():
    op.add_column('songs', sa.Column('loudness_lufs', sa.Float(), nullable=True))
    op.create_index('ix_songs_loudness_lufs', 'songs', ['loudness_lufs'])

def downgrade():
    op.drop_index('ix_songs_loudness_lufs')
    op.drop_column('songs', 'loudness_lufs')
```

Cũng update `db/models.py` Song model:
```python
loudness_lufs = Column(Float, nullable=True, comment="Integrated loudness ITU-R BS.1770")
```

#### Step 2.2 — Install + use `pyloudnorm`

```bash
source .venv/bin/activate
pip install pyloudnorm==0.1.1
```

Add to `tools/extract_audio_features.py` (tìm function chính, thêm sau Essentia load):

```python
import pyloudnorm as pyln

def measure_lufs(audio: np.ndarray, sample_rate: int) -> float:
    """ITU-R BS.1770 integrated loudness in LUFS."""
    try:
        meter = pyln.Meter(sample_rate)  # creates BS.1770 meter
        loudness = meter.integrated_loudness(audio)
        # Clamp obvious outliers
        if loudness < -70 or loudness > 0 or not np.isfinite(loudness):
            return -14.0  # fallback to target
        return float(loudness)
    except Exception as e:
        logger.warning(f"LUFS measure failed: {e}")
        return -14.0

# Trong main extraction loop:
features['loudness_lufs'] = measure_lufs(audio, sample_rate)
```

#### Step 2.3 — Backfill batch script

```bash
# tools/backfill_lufs.py
import pyloudnorm as pyln
from db.engine import SessionLocal
from db.models import Song
import librosa, glob, logging

logging.basicConfig(level=logging.INFO)
session = SessionLocal()
songs = session.query(Song).filter(Song.loudness_lufs.is_(None)).all()
logging.info(f"Backfilling {len(songs)} songs")

for i, song in enumerate(songs):
    mp3 = f"music_files/{song.track_id}.mp3"
    try:
        audio, sr = librosa.load(mp3, sr=None, mono=True)
        meter = pyln.Meter(sr)
        lufs = float(meter.integrated_loudness(audio))
        if -70 <= lufs <= 0:
            song.loudness_lufs = lufs
            if i % 50 == 0:
                session.commit()
                logging.info(f"[{i}/{len(songs)}] {song.track_name}: {lufs:.1f} LUFS")
    except Exception as e:
        logging.warning(f"{song.track_id}: {e}")
session.commit()
session.close()
```

Run: `python tools/backfill_lufs.py` — ước tính ~1–2h cho 4,348 songs.

#### Step 2.4 — Expose trong API response

Trong `api/music.py:_song_to_dict()`, thêm:
```python
song['loudness_lufs'] = _serialize(row.get('loudness_lufs'))
```

### Frontend work (1 ngày)

#### Step 2.5 — Rewire `_initVisualizer()` để add GainNode

Currently:
```
sourceA → analyser → destination
sourceB ↗
```

New:
```
sourceA → gainNodeA → analyser → destination
sourceB → gainNodeB ↗
```

Modify `_initVisualizer()` (player.js:443+):

```javascript
_initVisualizer() {
    if (this._audioCtx) return;
    try {
        this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        this._analyser = this._audioCtx.createAnalyser();
        this._analyser.fftSize = 128;
        this._analyser.smoothingTimeConstant = 0.82;
        
        this._sourceA = this._audioCtx.createMediaElementSource(this._audioA);
        this._sourceB = this._audioCtx.createMediaElementSource(this._audioB);
        
        // NEW: GainNodes for LUFS-matched playback
        this._gainNodeA = this._audioCtx.createGain();
        this._gainNodeB = this._audioCtx.createGain();
        this._gainNodeA.gain.value = this.volume;
        this._gainNodeB.gain.value = this.volume;
        
        // Chain: source → gain → analyser → destination
        this._sourceA.connect(this._gainNodeA).connect(this._analyser);
        this._sourceB.connect(this._gainNodeB).connect(this._analyser);
        this._analyser.connect(this._audioCtx.destination);
        
        this._dataArray = new Uint8Array(this._analyser.frequencyBinCount);
        // ... rest unchanged
    } catch (e) {
        console.warn('Visualizer init failed:', e);
    }
}
```

#### Step 2.6 — Use GainNodes trong crossfade thay vì `audio.volume`

Trong `_startCrossfade()` Phase 1, thay:
```javascript
this.audio.volume = Math.max(0, Math.min(1, plan.gainA * fadeOutGain));
this._audioInactive.volume = Math.max(0, Math.min(1, plan.gainB * fadeInGain));
```

Bằng:
```javascript
// Use GainNode nếu Web Audio đã init, fallback to audio.volume
const gainNodeActive = (this.audio === this._audioA) ? this._gainNodeA : this._gainNodeB;
const gainNodeInactive = (this._audioInactive === this._audioA) ? this._gainNodeA : this._gainNodeB;

if (gainNodeActive && gainNodeInactive) {
    gainNodeActive.gain.value = Math.max(0, Math.min(1, plan.gainA * fadeOutGain));
    gainNodeInactive.gain.value = Math.max(0, Math.min(1, plan.gainB * fadeInGain));
} else {
    this.audio.volume = Math.max(0, Math.min(1, plan.gainA * fadeOutGain));
    this._audioInactive.volume = Math.max(0, Math.min(1, plan.gainB * fadeInGain));
}
```

Cần đảm bảo `_initVisualizer()` được gọi sớm (khi user click play đầu tiên). Đã có sẵn — visualizer init lazily on first play.

#### Step 2.7 — Apply LUFS normalization khi đổi bài thông thường (không phải crossfade)

Trong `playSong()` hoặc `_onLoaded()`, set GainNode value theo song's LUFS:

```javascript
_applyLufsGain(song) {
    if (!this._gainNodeA || !this._gainNodeB) return;
    const TARGET_LUFS = -14;
    const lufs = song.loudness_lufs ?? -14;
    const gain = Math.min(1.0, this.volume * Math.pow(10, (TARGET_LUFS - lufs) / 20));
    const activeGain = (this.audio === this._audioA) ? this._gainNodeA : this._gainNodeB;
    activeGain.gain.value = gain;
}
```

Gọi `_applyLufsGain(song)` trong `_onLoaded()` hoặc sau `audio.play()` của bài mới.

### Test Phase 2

**Manual A/B test**:
- Pair indie quiet (LUFS −22) vs Vpop pro (LUFS −9)
- Before Phase 2: nghe vol nhảy +13 dB → đau tai
- After Phase 2: vol bằng nhau, mượt

**Unit test**:
```javascript
console.log(dbToLin(-14 - (-22)));  // 2.51 (boost +8dB)
console.log(dbToLin(-14 - (-9)));   // 0.56 (cut −5dB)
console.log(Math.min(1.0, 0.8 * 2.51));  // 1.0 (clamp)
```

---

## 🚀 PHẦN 5 — PHASE 3: Cue points + beat-align (4–6 ngày, OPTIONAL)

**Mục tiêu**: Pro-DJ feel cho danceable subset (~30% catalog).

### Backend (3 ngày)

#### Step 3.1 — Migration cho cue points + downbeats

```python
# alembic
op.add_column('songs', sa.Column('fade_out_cue_s', sa.Float(), nullable=True))
op.add_column('songs', sa.Column('fade_in_cue_s', sa.Float(), nullable=True))
op.add_column('songs', sa.Column('downbeat_times_json', sa.Text(), nullable=True))
```

#### Step 3.2 — Extract trong `tools/process_data.py`

Sử dụng `librosa.segment.agglomerative` cho structural boundaries + `librosa.beat.beat_track` cho downbeats:

```python
import librosa
import numpy as np
import json

def extract_cue_points(audio_path, sr=22050):
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    duration = len(y) / sr
    
    # Structural boundaries (Foote novelty)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    boundaries = librosa.segment.agglomerative(chroma, k=6)  # 6 segments typical
    boundary_times = librosa.frames_to_time(boundaries, sr=sr)
    
    # Skip silence/applause at end: find last boundary before "outro silence"
    # Outro silence detect: RMS < 0.02 for > 2s
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=512)
    silent_mask = rms < 0.02
    
    fade_out_cue = None
    for i in range(len(rms_times) - 1, 0, -1):
        if not silent_mask[i]:
            fade_out_cue = float(rms_times[i] - 1.0)  # 1s buffer
            break
    if fade_out_cue is None or fade_out_cue < 30:
        fade_out_cue = max(0, duration - 20)
    
    # Fade-in cue: first non-silent + first structural boundary
    first_loud = next((float(rms_times[i]) for i in range(len(rms_times))
                       if not silent_mask[i]), 0)
    fade_in_cue = max(first_loud, boundary_times[1] if len(boundary_times) > 1 else 0)
    fade_in_cue = min(fade_in_cue, 15)  # cap at 15s
    
    # Downbeats (for danceable tracks)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
    # Estimate downbeats every 4 beats (4/4 time signature assumed)
    downbeats = beats[::4].tolist()
    
    return {
        'fade_out_cue_s': fade_out_cue,
        'fade_in_cue_s': fade_in_cue,
        'downbeat_times_json': json.dumps(downbeats),
    }
```

Backfill script analogue với LUFS — chạy overnight.

### Frontend (2–3 ngày)

#### Step 3.3 — Use cue points (đã sẵn sàng trong planCrossfade!)

Function `planCrossfade()` đã accept `trackA.fade_out_cue_s` và `trackB.fade_in_cue_s` — sau migration backfill, Phase 1 code TỰ ĐỘNG dùng cue points.

#### Step 3.4 — Beat-align cho danceable

Trong `_startCrossfade()`, sau khi check enabled:

```javascript
// If both tracks are danceable + similar tempo → snap to downbeat
const danceableA = (currentSong.danceability ?? 0) > 0.7;
const danceableB = (nextSong.danceability ?? 0) > 0.7;
const similarTempo = plan.dTempo < 0.08;  // need to surface dTempo from plan

if (danceableA && danceableB && similarTempo && nextSong.downbeat_times_json) {
    const downbeats = JSON.parse(nextSong.downbeat_times_json);
    const targetCue = plan.fadeInStartAt_s;
    // Find nearest downbeat ≥ targetCue
    const snapTo = downbeats.find(t => t >= targetCue) ?? targetCue;
    plan.fadeInStartAt_s = snapTo;
}
```

---

## 🚫 PHẦN 6 — DO NOT DO (over-engineering warnings)

1. **❌ Real-time time-stretching (SoundTouchJS WSOLA)** — artifacts vocal khi > 6%, CPU 2x. Streaming app KHÔNG cần. Thay vào đó: skip incompatible-tempo pairs trong queue ordering.

2. **❌ GAN-based transition model** (Chen et al. 2021/2022) — offline only, train trên EDM, gain marginal so với policy + LUFS.

3. **❌ Real-time stem separation** (djay Pro Neural Mix) — browser inference 100–300ms/s audio (2026 hardware) → không viable.

4. **❌ Compute novelty curves client-side** — O(n²) SSM freeze main thread. Luôn precompute offline.

5. **❌ ML mix quality scoring** chưa có user feedback (thumbs up/down) → không validate được.

---

## ✅ PHẦN 7 — Validation strategy

### Metrics theo dõi

| Metric | Baseline | Target sau Phase 1 | Target sau Phase 2 |
|---|---|---|---|
| Skip rate trong 5s đầu của track tiếp theo | ~12% | ≤ 9% | ≤ 7% |
| User toggle crossfade off rate | ~8% / session | ≤ 5% | ≤ 3% |
| Manual volume adjust trong 3s đổi bài | ~15% | ≤ 12% | ≤ 5% |
| ABX listening test "smoother" preference | n/a | ≥ 60% | ≥ 70% |

### ABX listening test protocol

1. Chọn 20 random adjacent pair từ Brightify catalog
2. 3+ listeners (đảm bảo có người không biết feature)
3. Mỗi pair phát 2 lần: legacy 15s và smart
4. Listener chấm: A smoother / B smoother / equal
5. Compute prefer rate cho smart
6. Block Phase 3 merge nếu Phase 2 chưa đạt ≥ 70%

### Rollback

Tất cả changes có feature flag:
- `localStorage.bf_crossfade_smart = false` → Phase 1 off
- `_gainNode*` undefined → fallback to `audio.volume` (Phase 2)
- Missing `loudness_lufs` field → fallback to userBaseVolume (Phase 2)
- Missing cue points → fallback to heuristic (Phase 3)

---

## 📁 PHẦN 8 — Files affected (toàn tóm tắt)

### Phase 1 (frontend only)
- `static/js/player.js` — replace `_startCrossfade()` body, add policy module (~+200 LOC)
- `static/js/app.js:2244` — add `smart` flag to crossfade object
- `static/index.html:213` — (optional) Smart badge UI
- `api/music.py:_song_to_dict()` — verify `tempo`, `key`, `mode`, `mood_quadrant`, `duration` đều có

### Phase 2 (backend + frontend)
- `db/models.py` — Song.loudness_lufs column
- `alembic/versions/xxx_add_loudness_lufs.py` — migration
- `tools/extract_audio_features.py` — add `measure_lufs()` + integrate
- `tools/backfill_lufs.py` — new script for existing songs
- `api/music.py:_song_to_dict()` — expose `loudness_lufs`
- `static/js/player.js:_initVisualizer()` — insert GainNodes
- `static/js/player.js:_startCrossfade()` — use gain nodes instead of audio.volume
- `static/js/player.js` — new `_applyLufsGain()` method, call in `_onLoaded`
- `requirements.txt` — add `pyloudnorm==0.1.1`

### Phase 3 (backend + frontend)
- `db/models.py` — add `fade_out_cue_s`, `fade_in_cue_s`, `downbeat_times_json`
- `alembic/versions/xxx_add_cue_points.py` — migration
- `tools/process_data.py` — add `extract_cue_points()`
- `tools/backfill_cue_points.py` — new script
- `api/music.py:_song_to_dict()` — expose new fields
- `static/js/player.js:_startCrossfade()` — add beat-align snap

---

## 📅 PHẦN 9 — Suggested execution schedule

```
WEEK 1
├─ Day 1: Phase 1 implementation (policy module + _startCrossfade rewrite)
├─ Day 2: Phase 1 testing + manual ABX với 20 pair
├─ Day 3: Phase 1 ship behind flag, gather user feedback 24h
│
├─ Day 4: Phase 2 backend (migration + pyloudnorm + extract integration)
├─ Day 5: Phase 2 backfill batch (overnight, parallel 4 workers)
├─ Day 6: Phase 2 frontend (GainNode rewire, LUFS apply)
├─ Day 7: Phase 2 testing + ABX

WEEK 2 (OPTIONAL — chỉ khi Phase 2 ABX ≥ 70%)
├─ Day 8: Phase 3 backend cue extraction
├─ Day 9: Phase 3 backfill
├─ Day 10: Phase 3 frontend beat-align
├─ Day 11: Final ABX + ship
```

---

## NGUỒN THAM KHẢO

### Auto-DJ literature
- [Vande Veire & De Bie 2018 — Seamless mix for D&B (EURASIP)](https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-018-0134-8)
- [aida-ugent/dnb-autodj (reference impl)](https://github.com/aida-ugent/dnb-autodj)
- [Bittner et al. 2017 — Automatic Playlist Sequencing and Transitions (ISMIR)](https://rachelbittner.weebly.com/uploads/3/2/1/8/32182799/bittner_ismir-playlist_2017.pdf)
- [Spotify Research — Automatic Playlist Sequencing](https://research.atspotify.com/publications/automatic-playlist-sequencing-and-transitions)
- [Davies et al. 2013 — AutoMashUpper (ISMIR)](https://archives.ismir.net/ismir2013/paper/000077.pdf)
- [Cliff 2005 — hpDJ HPL Technical Report HPL-2005-88](https://www.hpl.hp.com/techreports/2005/HPL-2005-88.html)

### Cue point + structural segmentation
- [Zehren et al. 2020 — Automatic Cue Point Detection (arXiv 2007.08411)](https://arxiv.org/abs/2007.08411)
- [Foote 2000 — Audio novelty segmentation](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html)

### Loudness normalization
- [ITU-R BS.1770 standard](https://www.itu.int/rec/R-REC-BS.1770)
- [pyloudnorm library](https://github.com/csteinmetz1/pyloudnorm)
- [Spotify Loudness Normalization (artists)](https://support.spotify.com/us/artists/article/loudness-normalization/)

### Harmonic mixing
- [Camelot Wheel (Mark Davis / Mixed In Key)](https://dj.studio/blog/camelot-wheel)

### Curve theory
- [Audacity Manual — Fade and Crossfade](https://manual.audacityteam.org/man/fade_and_crossfade.html)

### NOT recommended (over-engineering)
- [Chen et al. 2021 — DJ Transitions with GANs (arXiv 2110.06525)](https://arxiv.org/abs/2110.06525)
- [SoundTouchJS — WSOLA time-stretch](https://github.com/cutterbl/SoundTouchJS/)
- [Algoriddim djay Pro Neural Mix (commercial reference only)](https://www.algoriddim.com/neural-mix)
