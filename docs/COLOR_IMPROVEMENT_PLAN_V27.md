# COLOR IMPROVEMENT PLAN V27

**Ngày:** 2026-06-10
**Dựa trên:** deep-research 5 góc (A1–A5) · sources từ EACL/AAAI/PLOS/JEP:G/FPSYG 2024-2026
**Scope:** Không cần dữ liệu người dùng · không cần annotation mới

---

## Tóm tắt từ deep-research

| Angle | Vấn đề | Kết quả nghiên cứu | Quyết định |
|---|---|---|---|
| A1 | Valence yếu (ρ=0.263 XLM-R, ρ=0.135 sentiment) | NRC-VAD 109 lang · major-minor mode 45% var · MERT lớp 9-12 | ✅ IMPLEMENT |
| A2 | Red/VN văn hoá (gate fail, V=0.35) | Red VN = love 29 vs anger 35 (Vigier 2019) · không có override rõ ràng | ❌ DOC ONLY |
| A3 | Catalog Q3-skew (35% sad) | Calibration reranking đủ mà không cần user data | ✅ IMPLEMENT |
| A4 | Chroma linear (nonlinear ignored) | redness×s01 interaction · β arousal→lightness=-14.7 | ✅ IMPLEMENT (gate-gated) |
| A5 | CIELAB blue-hue distortion | Oklab drop-in · re-fit cần sau CIELAB gate pass | 🟡 DEFER (sau A1) |

---

## A1 — Valence signal cải thiện (ROI: ★★★ CAO NHẤT)

### Vấn đề
- Gemini là nguồn valence duy nhất (tautology risk)
- Corroboration hiện tại: XLM-R ρ=0.263, sentiment ρ=0.135 — cả hai yếu
- Không có VN sentence-level valence labels

### Research findings

**A1-a: NRC-VAD zero-shot** (EACL 2024, arXiv:2402.02113)
- Fine-tune XLM-R / mDeBERTa trên **NRC-VAD lexicon** (Mood–Valence word-level, 109 ngôn ngữ kể cả Vietnamese)
- Không cần sentence-level labels; training signal = từng từ trong lexicon
- Áp dụng: lyric → XLM-R(NRC-VAD) → valence_vad ∈ [-5, 5] → normalize [0,1]
- Thay thế sentiment_compound trong R2 panel

**A1-b: Major-minor mode** (~45% variance, cross-cultural, arXiv study 2025)
- Major = valence cao, Minor = valence thấp — replicated Tây+Á
- Từ audio: `librosa.key_and_mode()` hoặc Krumhansl-Schmuckler profiles trên chroma vectors
- Output: `mode_score ∈ [0,1]` (0=minor, 1=major) hoặc continuous "major-minorness"
- Zero annotation needed; thêm vào feature engineering (Phase 6 pipeline)
- Tham khảo: AAAI 2026 MoGE (arXiv:2512.17946), Journals SPMS 2025

**A1-c: MERT deeper layers cho valence**
- MERT-95M: valence benefits from layers 9-12 (harmonic/tonal context), R²≈0.60 on DEAM
- Hiện tại: arousal probe dùng final layer; valence probe chưa có
- Thêm: `mert_valence_probe.py` (đối xứng `mert_arousal_probe.py`), fine-tune trên DEAM/EmoMusic layer 9-12

### Plan A1

**Bước A1.1 — Major-minor mode feature** (không cần model mới, ROI cao nhất/nhanh nhất)

```python
# tools/extract_mode_features.py
import librosa
import numpy as np

def compute_mode_score(audio_path: str) -> float:
    """
    Returns major-minorness ∈ [0,1] from Krumhansl-Schmuckler profiles.
    1.0 = strongly major (high valence), 0.0 = strongly minor (low valence).
    """
    y, sr = librosa.load(audio_path, sr=None)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    # Pearson with major vs minor Krumhansl-Kessler profiles
    major = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    minor = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
    r_maj = np.corrcoef(chroma_mean, np.roll(major, 0))[0,1]
    r_min = np.corrcoef(chroma_mean, np.roll(minor, 0))[0,1]
    # max over all 12 keys
    for k in range(1, 12):
        r_maj = max(r_maj, np.corrcoef(chroma_mean, np.roll(major, k))[0,1])
        r_min = max(r_min, np.corrcoef(chroma_mean, np.roll(minor, k))[0,1])
    return float(np.clip((r_maj - r_min + 1) / 2, 0, 1))
```

Thêm `mode_score` vào catalog CSV, dùng như additional feature cho valence.

**Bước A1.2 — NRC-VAD zero-shot panel** (thay sentiment trong R2)

```python
# Trong tools/color_r2_valence_panel.py: thêm nrc_vad_score()
# NRC-VAD downloadable miễn phí từ nrc-vad.ca
# Tokenize lyrics → average word-level VAD scores → valence_vad_panel
```

Gate: `ρ(valence_vad_panel, gemini_valence) > 0.263` → cải thiện → tái chạy `color_eval_rigor.py`

**Bước A1.3 — MERT valence probe** (sau A1.1 + A1.2 xanh)

```bash
# Tạo tools/mert_valence_probe.py (đối xứng mert_arousal_probe.py)
# DEAM dataset (1802 clips) hoặc EmoMusic — cả hai public
# Fine-tune linear head trên MERT layer 9-12 (frozen) → valence
# Cross-validate ρ, lưu probe vào models_cache/mert_valence_probe.pkl
```

**Verify A1:** Sau mỗi bước chạy `color_eval_rigor.py` — TE ≤ 0.043 + CI overlap.

---

## A2 — Red/Văn hoá VN (ROI: ❌ Không đủ evidence cho override)

### Research findings
- Vigier 2019 (n=85 VN youth): red → love 29, anger 35 — **không rõ ràng positive**
- Jonauskaite 2020: universal r=.88, nation modulates above baseline — mức ảnh hưởng nhỏ
- Chinese consumers 2023: red ≠ purchase preference (blue wins in spatial tasks)
- "The good, the bad, and the red" (Psych Research 2022): red implicit valence cross-culturally still mixed

### Kết luận
**Không implement VN cultural override cho red.** Evidence không đủ mạnh để justify positive-valence shift:
- Red VN = cả love VÀ anger (roughly equal)
- Trong context nhạc, red=anger/energetic là hợp lý hơn red=luck
- CIELAB cho red V=0.354 (Q2) có thể đúng về mặt âm nhạc

**Action:** Document trong code — thêm comment vào `advanced_color_mapping.py`:

```python
# Cultural note: Vietnamese red = luck/celebration culturally, but in
# music-emotion context red → energetic/angry (cross-cultural; Vigier 2019 VN
# youth: love=29, anger=35 for red). CIELAB V=0.35 for red is musically valid.
# R3 Vietnamese cultural overlay deferred pending stronger quantitative evidence.
```

---

## A3 — Catalog skew mitigation (ROI: ★★ MEDIUM)

### Vấn đề
- Q3=35.5% sad, excited=3.3%, angry=2.3% — catalog dominated by slow/sad songs
- MMR đã có (λ=0.7) — giải quyết một phần
- Còn lại: khi color map vào Q1 (excited), rất ít bài → TE tăng

### Research findings (arXiv:2212.14464 + arXiv:2208.10192)
- **Calibration reranking**: đảm bảo distribution mood của recommendations ≈ target distribution
- Hoạt động pure post-processing — không cần user data
- Greedy submodular coverage: ~40% catalog coverage mà không drop relevance đáng kể

### Plan A3 — Calibration step sau MMR

```python
# Trong core/recommendation_engine.py, hàm recommend_by_colors()
# Sau MMR step, thêm:

def _calibration_rerank(top_k_df, target_va, song_va_full, n=10, alpha=0.3):
    """
    Boost underrepresented quadrant coverage.
    alpha: weight trade-off relevance vs coverage (default 0.3).
    target distribution = uniform over 4 quadrants.
    """
    # ... greedy selection maximising quadrant diversity
```

**Config flag:**
```python
COLOR_CALIBRATION_RERANK = False  # A3: enable calibration reranking
COLOR_CALIBRATION_ALPHA  = 0.3   # relevance vs diversity trade-off
```

Gate: `color_eval_rigor.py` TE không regress; xem TE per-colour cho Q1 (excited).

---

## A4 — Nonlinear chroma interaction (ROI: ★★ MEDIUM, gate-gated)

### Research findings

**FPSYG 2025** (doi:10.3389/fpsyg.2025.1593928):
- Valence→chroma: β=2.74, p<0.001
- Valence→lightness: β=7.94, p<0.001
- Arousal→lightness: β=-14.70, p<0.001
- **Arousal×dominance→chroma**: d=0.74, p<0.001 (interaction — không linear)
- High red + high chroma + low lightness → highest arousal

**JEP:General 2024** (doi:10.1037/xge0001484):
- Chroma effect on valence: modulated by arousal (highest chroma = positive + high-arousal)
- Không có simple chroma→valence; cần interaction

**Bach-to-Blues 2018** (Whiteford et al.):
- Arousal→saturation r_s=0.720 (strongest predictor)
- V+A joint R²=72.2% for saturation

### Plan A4 — Interaction term cho arousal

**Thử thêm redness×s01 interaction:**

```python
# Trong hsl_to_va() chromatic branch
# Hiện tại:
arousal = float(np.clip(0.37*redness + 0.36*s01 + 0.27*(1-l01), 0, 1))

# Thử thêm:
arousal = float(np.clip(0.37*redness + 0.36*s01 + 0.27*(1-l01)
                        + 0.15*redness*s01, 0, 1))
# → Điều chỉnh coefficients (a+b+c+d ≈ 1) rồi gate
```

Gate bắt buộc: `color_eval_rigor.py` TE ≤ 0.043 + T1–T4 PASS + journey mono ≥ 0.896.

**Thử quadratic chroma cho valence** (Wilms&Oberfeld, sau CIELAB gate pass):

```python
# Thay: 0.55*s01
# Bằng: 0.55*s01 - 0.30*s01**2  (đỉnh tại s≈0.92)
```

Chỉ giữ nếu TE cải thiện clear (CI non-overlap với current).

---

## A5 — Oklab color space (ROI: ★ LOW-MEDIUM, defer)

### Research findings

- **Oklab** (Björn Ottosson): eliminates CIELAB blue hue shift; Euclidean distance ≈ perceived distance
- **Oklch+** (arXiv:2606.05255): further improvement; hue angle H more stable than CIELAB a*/b*
- Oklab formula: simple linear transform từ sRGB → linear sRGB → XYZ → Oklab
- Không cần colormath; ~10 dòng code

### Plan A5 — Sau CIELAB gate pass, thay `_cielab_features()` bằng `_oklab_features()`

```python
def _oklab_features(self, hex_color: str) -> np.ndarray:
    """[L, a, b, C, cos(h), sin(h)] in Oklab space."""
    rgb = self.hex_to_rgb(hex_color)
    # sRGB → linear
    r, g, b = [(c/255)**2.2 for c in rgb]
    # linear sRGB → XYZ (D65)
    X = 0.4124*r + 0.3576*g + 0.1805*b
    Y = 0.2126*r + 0.7152*g + 0.0722*b
    Z = 0.0193*r + 0.1192*g + 0.9505*b
    # XYZ → LMS
    l_  = (0.8189*X + 0.3619*Y - 0.1288*Z)**(1/3)
    m_  = (0.0329*X + 0.9293*Y + 0.0361*Z)**(1/3)
    s_  = (0.0482*X + 0.2643*Y + 0.6338*Z)**(1/3)
    # LMS → Oklab
    L = 0.2104*l_ + 0.7936*m_ - 0.0040*s_
    a = 1.9779*l_ - 2.4285*m_ + 0.4505*s_
    b = 0.0259*l_ + 0.7827*m_ - 0.8086*s_
    C = float(np.sqrt(a**2 + b**2))
    h = float(np.arctan2(b, a))
    return np.array([L, a/0.4, b/0.4, C/0.4, np.cos(h), np.sin(h)])
```

Re-run `phase3_cielab_experiment.py` với Oklab features → nếu r > 0.852 → flip flag.

**Lưu ý:** Do Oklab có scale khác CIELAB, weights `_W_VALENCE_CIELAB` phải re-derive.

---

## Thứ tự thực thi và dependencies

```
A1.1 mode_score feature    → thêm vào CSV + R2 panel → verify
A1.2 NRC-VAD zero-shot     → cải thiện R2 panel ρ > 0.263 → verify
A1.3 MERT valence probe    → thay Gemini nếu TE gate pass → verify
A4   interaction term      → gate: color_eval_rigor → giữ nếu pass
A3   calibration reranking → gate: TE + Q1 per-colour TE → verify
A5   Oklab                 → sau CIELAB gate pass → re-experiment
A2   Red/VN overlay        → deferred (no evidence, doc only)
```

---

## Gate bất biến (kế thừa từ V26)

Mọi thay đổi signal/weight:
1. `python -m tools.color_eval_rigor` → TE ≤ 0.043 + CI overlap + FDR ≥ 4/5
2. `python -m tools.color_structural_battery` → T1–T4 ALL PASS
3. `python -m tools.color_journey_sequencing` → mono ρ ≥ 0.896
4. Không đạt → revert + ghi negative result

---

## Không làm

- Joint color-audio embedding (cần paired VN data)
- Deep model cho V-A regression (MER meta: NN không trội hơn linear)
- Thêm cultural overlay bất kỳ màu nào khác ngoài red (không đủ evidence)
- Re-label emotion từ Gemini (valence panel phải cải thiện TE trước)
- Oklab trước khi CIELAB gate pass (premature)
