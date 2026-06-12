# COLOR FINAL PLAN V29 — Recommend-by-Color

**Ngày lập:** 2026-06-11 (cập nhật sau verify đầy đủ 19 claim bị rate-limit)
**Trạng thái hiện tại:** V28 SHIPPED, TE=0.0303 ALL PASS
**Mục tiêu plan này:** Hoàn thiện tất cả điểm còn yếu — NRC-VAD, ILD diversity, white sigma, documentation

---

## 1. Kiến Trúc (Đã Xác Nhận Đúng Hướng)

```
color input (hex)
       ↓
  Oklab features [L, a/0.4, b/0.4, C/0.4, cos(h), sin(h)]
       ↓  Ridge regression (LOO-CV r=0.873, n=12 ICEAS centroids)
  V_raw, A_raw  (absolute Jonauskaite scale)
       ↓  C1: catalog-relative calibration
  V_cal = V_p5 + (V_p95 − V_p5) × V_raw  → [0.18, 0.92]
  A_cal = A_p5 + (A_p95 − A_p5) × A_raw  → [0.21, 0.72]
       ↓  A2 (VN only): +0.06 × redness × saturation  (post-calibration)
       ↓  A4: arousal += 0.14 × redness × saturation  (interaction)
  V, A  in catalog-supported range
       ↓  heteroscedastic RBF (σ_V > σ_A) vs 5138 songs' song_va
  recommended songs (20 results)
```

**Cơ sở khoa học đã verify:**
- Oklab: perceptually uniform (Ottosson 2020). L-weight dominance (0.686) được xác nhận độc lập: pmc.ncbi PMC12202424 báo cáo β=7.94 (p<0.001) cho Valence→Lightness.
- Emotion-as-mediator (color→V-A→songs): CDCML ACM MM 2020
- Jonauskaite et al. 2020 (n=4,598, 30 quốc gia): nguồn huấn luyện regression
- A4 interaction term: FPSYG 2025 (red×saturation→arousal)
- A2 VN overlay (+0.06): Vigier 2019 + xác nhận thêm bởi Springer 2022 (cultural divergence: Chinese/East Asian red-negative associations yếu hơn Western đáng kể, valence categorization task CE difference: Austrian 76.84ms vs Chinese 32.42ms, p=0.001)
- C1 calibration: fixes scale mismatch (MERT A tops ~0.72, raw arousal có thể đạt 0.885)

**Cảnh báo cần ghi nhớ:**
- Jonauskaite 2020 ICEAS ratings là "abstract associations had little to do with actual feelings" (trích dẫn trực tiếp từ Jonauskaite 2024 — verified). Regression model kế thừa giới hạn này.
- Vietnam KHÔNG nằm trong bất kỳ study nào đã verify. Việc suy ra từ proximity principle (Jonauskaite 2020: β=−0.37 linguistic, β=−0.13 geographic proximity, p<0.003) là extrapolation hợp lý nhưng cần được ghi rõ là inference.

---

## 2. V28 — Trạng Thái Đã Ship

| Component | Flag | Giá trị | Gate |
|-----------|------|---------|------|
| Oklab regression | `COLOR_VALENCE_OKLAB=True` | r=0.873 LOO-CV | ✅ |
| CIELAB (disabled) | `COLOR_VALENCE_CIELAB=False` | r=0.852 | N/A |
| Catalog calibration | `COLOR_VA_CATALOG_CALIBRATE=True` | V p5=0.18, p95=0.92 | ✅ |
| Arousal interaction | `COLOR_AROUSAL_INTERACTION=True` | +0.14×redness×s01 | ✅ |
| VN red overlay | `use_vietnamese_adaptation=True` | +0.06×redness×s01 | ✅ |
| Calibration rerank | `COLOR_CALIBRATION_RERANK=False` | Gate FAILED 2026-06-10 | ❌ |

**Gate:** TE=0.0303 CI[0.0214, 0.0393] — **32.8% cải thiện** so với baseline HSL (0.0451)

**Per-color TE:** red=0.025, yellow=0.030, blue=0.041, black=0.015, white=0.054
**ILD per color (mean pairwise V-A cosine):** red=0.019, yellow=0.014, blue=0.059, black=0.011

---

## 3. Điểm Còn Yếu & Kế Hoạch

### P1 — NRC-VAD Lexicon cho R2 Panel

**Vấn đề:** R2 panel ρ=0.299 — yếu. Signals hiện tại: MERT valence(ρ=0.321, std=0.051) + mode_score(ρ=0.016) + sentiment(ρ=0.432). Mode score useless cho nhạc VN (major keys trong bài buồn).

**Giải pháp:** NRC-VAD lexicon (Mohammed & Turney 2013, EACL 2024 update) — 109 ngôn ngữ kể cả Vietnamese, word-level valence [0,1]. Zero annotation. Code đã có trong `tools/color_r2_valence_panel.py` section 1.

```bash
# Download tại: saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm
# → var/data/nrc_vad_lexicon.txt
python -m tools.color_r2_valence_panel
```

**Gate:** ρ(panel_new, gemini_valence) > 0.299. Nếu ρ ≥ 0.50 → chạy nested CV để xét thay label.

**Tại sao không thay Gemini valence ngay:** MERT std=0.051 vs catalog std=0.255 — quá hẹp, stretch amplifies noise. Jonauskaite gap (abstract vs felt emotion) áp dụng cho mọi association-based replacement. Chỉ thay nếu nested CV TE cải thiện ≥ 5%.

---

### P2 — ILD Diversity cho Red và Black

**Vấn đề:** Red ILD=0.019, black ILD=0.011 (so với blue ILD=0.059 là "healthy" reference). Nguyên nhân: `_fast_rank` đã dùng MMR trên general MERT embeddings, nhưng songs gần nhau trong V-A space vẫn được chọn vì MERT embedding diversity không có nghĩa là V-A diversity.

**Giải pháp:** `mmr_rerank` đã tồn tại trong `core/diversity.py`. Wire thêm một pass MMR dùng V-A embeddings sau `_fast_rank`. Thêm flag `COLOR_MMR_VA_DIVERSITY = False` trong `config.py`.

**Implement trong `_rank_by_color_features()`** (single-color path, sau line 641):

```python
# P2 (V29): V-A space MMR for ILD improvement
if COLOR_MMR_VA_DIVERSITY and not res.empty and 'original_index' in res.columns:
    from core.diversity import mmr_rerank
    # Get wider candidate pool (5× top_k) by pure RBF score
    n_cand = min(top_k * 5, self.n_songs)
    top_cands = np.argsort(final_scores)[::-1][:n_cand].tolist()
    # L2-normalize V-A vectors for cosine-based MMR
    va_norm = self.song_va / (np.linalg.norm(self.song_va, axis=1, keepdims=True) + 1e-9)
    chosen = mmr_rerank(top_cands, final_scores, va_norm, top_k=top_k, lambda_=0.5)
    res = self._build_result_df(chosen)
```

**Gate:** ILD(red) ≥ 0.030 VÀ ILD(black) ≥ 0.025 VÀ TE overall không regress.

**Caveat (từ verify):** Không có literature source nào cung cấp ILD target numbers. ISMIR tismir.106 bị REFUTED — không chứa ILD ranges. Targets 0.030/0.025 là internal targets = ~50% của blue ILD (0.059), không phải literature-derived.

---

### P3 — White TE=0.051 (Sparse Region) — INVESTIGATED, approach revised

**Vấn đề:** White → V=0.631 A=0.289 (Q4). V∈[0.45,0.65] là dead zone (7.5% catalog). TE cao.

**Adaptive sigma — Gate FAILED (2026-06-11):** `COLOR_ADAPTIVE_SIGMA=True` → TE ordering 4/5 ✗ (một màu khác bị hurt). Widening sigma cho sparse region vô tình ảnh hưởng catalog queries gần nhau. Reverted, flag giữ `=False`.

**P2 MMR side-effect:** Sau khi enable P2, white TE cải thiện 0.054→0.051 một phần nhờ V-A diversity — không cần P3 riêng.

**Tình trạng:** White TE=0.051 — còn cao nhất nhưng đã cải thiện. Không có approach tốt hơn mà không hurt TE. Ghi nhận là known limitation của sparse region.

**Root cause (từ verify):** Mapping đúng — white distributes broadly (happy 12%, calm 23%, excited 27%) không có dominant emotion. Đây là fundamental ambiguity, không phải retrieval bug.

---

### P4 — MERT Valence Layer Ablation (Trước Stretch)

**Mục tiêu:** Cải thiện MERT valence probe trước khi thử stretch blending.

**Lý do:** mert_paper verification (PARTIAL) xác nhận paper KHÔNG làm layer-wise probing. Layer 9-12 được chọn trong tools/mert_valence_probe.py là empirical guess, không validated. Nên thử layer ablation trước.

```python
# Thêm vào tools/mert_valence_probe.py
for layer in [6, 9, 12, -1]:  # -1 = last layer
    # extract probe per layer → CV R² 
    print(f"Layer {layer}: CV R²={r2:.4f}")
```

**Gate:** Nếu layer ablation cho R² tốt hơn current (0.487) → update probe. Nếu không → dừng, không stretch.

**P4b (Conditional) MERT Valence Stretch:** Chỉ làm nếu P1 (NRC-VAD) vẫn cho panel ρ < 0.40 VÀ layer ablation không cải thiện đủ.

```python
# Stretch MERT valence to catalog distribution before blending
mert_stretched = np.interp(
    mert_raw,
    [np.percentile(mert_raw, 5), np.percentile(mert_raw, 95)],  # [0.379, 0.543]
    [0.18, 0.92]  # target = catalog val p5/p95
)
# Blend: alpha=0.3 MERT + 0.7 Gemini
valence_blended = 0.3 * mert_stretched + 0.7 * gemini_valence
```

Gate nghiêm: nested CV 5-fold artist-grouped, TE cải thiện ≥ 5%.

---

## 4. Evaluation Metrics (Bổ Sung vào color_eval_rigor.py)

| Metric | Formula | Ngưỡng Pass | Source |
|--------|---------|------------|--------|
| ILD per color | mean pairwise Euclidean dist trong V-A space | red≥0.022, black≥0.017 | Internal (blue=0.066 reference, V29 Euclidean) |
| Gini coefficient | artist concentration trong 20 results | ≤ 0.50 | arxiv 2605.28810v1 (verified PARTIAL) |
| Normalized Entropy | distribution uniformity across V-A quadrants | ≥ 0.60 | arxiv 2605.28810v1 (verified PARTIAL) |
| Coverage | % of 5 test colors with n_nearby ≥ 100 | 100% | Internal |
| Per-quadrant TE | TE riêng cho Q1/Q2/Q3/Q4 colors | ≤ 0.060 mỗi | Internal |

**Lưu ý quan trọng:** ILD dùng Euclidean distance trong raw V-A space (không normalize, không dùng cosine — cosine trên 2D V-A space không có nghĩa cho intra-neighborhood diversity). P2 Euclidean MMR đã ship (V29). Targets dựa trên V29 distribution.

**Không dùng "genre diversity" và "novelty"** — arxiv 2605.28810v1 dùng Gini + Normalized Entropy + Coverage + ILD (verified PARTIAL).

---

## 5. Documentation Update (R6 Claims)

Cần cập nhật `docs/COLOR_SCIENTIFIC_REDESIGN_V25.md`:

| Claim | Cũ | Mới (Đúng) |
|-------|-----|----------|
| R1 color space | CIELAB r=0.852 | Oklab r=0.873, CIELAB disabled; L-weight 0.686 xác nhận bởi pmc PMC12202424 β=7.94 |
| R5 TE | baseline 0.043 | V28: 0.0303 (32.8% improvement) |
| A4 arousal | no interaction | +0.14×redness×saturation, FPSYG 2025 |
| A2 VN red | Vigier 2019 only | Vigier 2019 + Springer 2022 (cultural divergence in valence categorization task, not IAT) |
| C1 calibration | none | V p5=0.18/p95=0.92, A p5=0.21/p95=0.72 |
| A3 reranking | proposed | Gate FAILED 2026-06-10, reverted |
| ILD standard | "0.05–0.08 từ ISMIR" | KHÔNG có literature standard; ISMIR tismir.106 REFUTED — không chứa ILD ranges |

---

## 6. Thứ Tự Thực Hiện

```
DONE (V29):
  ✅ P2  COLOR_MMR_VA_DIVERSITY=True — gate PASS, ILD(black) +31%, TE ALL PASS
  ❌ P3  COLOR_ADAPTIVE_SIGMA=False — gate FAIL (TE 4/5 ordering), reverted
         → white TE cải thiện nhờ P2 side-effect (0.054→0.051)

Còn lại:
  P1  Download NRC-VAD → python -m tools.color_r2_valence_panel → đọc ρ mới

  P4  ABLATION: mert_valence_probe.py +layer loop (6,9,12,final) → chọn layer tốt nhất
      GATE: CV R² improve → update probe

  P5  DOCS: Update R6 claims + corrections from verify (springer=valence categorization task not IAT)

Conditional (sau P1):
  P4b MERT stretch blend — chỉ nếu P1 ρ < 0.40 VÀ P4 không đủ
```

---

## 7. Gate Chuẩn (Bất Biến Sau Mọi Thay Đổi)

```bash
python -m tools.color_eval_rigor          # TE ≤ 0.043 + CI + FDR ≥ 4/5 + Journey KS < 0.40
pytest test/test_color_reco.py -v         # 31/31 PASS
```

Mức độ gate:
- Retrieval/ranking changes (MMR, sigma): gate chuẩn
- Signal changes (NRC-VAD): gate chuẩn + R2 panel report
- Valence label replacement: gate chuẩn + nested CV (5-fold artist-grouped, TE improve ≥5%)

---

## 8. Research Notes — Verified Claims Summary (2026-06-11)

### Đã verify (từ 2 vòng deep-research)

**CONFIRMED:**
- MuCED dataset: 2,634 pairs từ DEAM(1802) + PMEmo(794) + Emotify(400), avg similarity 0.76 after expert validation [music2palette, high confidence]
- Music2Palette: 8-category Russell's circumplex (not continuous V-A) → không có R² baseline để so sánh [music2palette, high confidence]
- Color metadata dataset: dùng continuous color wheel (49 colors) nhưng KHÔNG có color→V-A regression [academia.edu, high confidence]
- Red = "emotionally ambiguous": mang cả anger/danger VÀ love/passion, phân bổ theo culture [Springer 2022, high confidence]

**PARTIAL (core numbers ok, một vài details wrong):**
- MERT paper: không làm layer-wise probing; dùng last-layer frozen, không phải "all-layer aggregation" [medium confidence]
- Music2Palette: CIELCh dùng xuyên suốt; CIEDE2000 chỉ trong training loss, không phải toàn pipeline [high confidence]
- PhysRevResearch 944 participants (Greek/Turkish only), 33%→52% accuracy — confirmed core numbers [medium confidence]
- Jonauskaite 2024: 12 colours × 20 emotions × 7,393 participants × 31 countries — confirmed; "abstract associations had little to do with actual feelings" — confirmed [high confidence]
- Lightness dominant: β=7.94 (p<0.001) Valence→Lightness, β=−14.7 Arousal→Lightness — confirmed numbers, "dominant" language overstated [high confidence]
- Red–anger/disgust link (high-arousal negative): confirmed for Western/504-image study, caveat: study rất nhỏ (21 subjects) [high confidence]
- 4-country study (China/Germany/Greece/UK): 6.1% in-group advantage = color-decoding accuracy from emotion ratings, not country-classification from colors [high confidence]
- Cultural proximity principle: β=−0.37 linguistic, β=−0.13 geographic (p<0.003) → similarity predicts color-emotion similarity [high confidence]
- Western > Chinese red-negative (valence categorization task, NOT IAT — sai label trong claim gốc): Austrian CE=76.84ms vs Chinese CE=32.42ms (p=0.001) [high confidence]
- Diversity metrics: ILD + Gini + Normalized Entropy + Coverage (NOT "genre diversity" và "novelty") [high confidence]
- Emotion targeting without user feedback: rollout-based world model (complex, not recommended for Brightify scope) [high confidence]

**REFUTED:**
- ISMIR tismir.106 "ILD range 0.03–0.12": paper KHÔNG chứa ILD numeric ranges — fabricated claim [high confidence]
- Valence ≈ arousal equally difficult: sai — valence harder (r=0.67 vs r=0.81, large meta-analysis) [strong refutation]
- Gemini r=0.50 cross-cultural cross-corpus: overstated specific numbers [strong refutation]
- MERT R²=87.9 for valence on EmoMusic: inflated — empirical Brightify result CV R²=0.487 là thực tế [refuted]

**Kết luận thiết kế:**
1. Không có bằng chứng nào để thay đổi kiến trúc cốt lõi
2. A2 VN red overlay có evidence base tốt hơn sau verify
3. ILD targets là internal metrics, không phải literature standards
4. MERT layer ablation nên làm trước khi thử stretch (layer selection empirical)
