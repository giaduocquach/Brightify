# V-A Redesign V6 — Thiết kế Valence-Arousal chuẩn khoa học, không LLM, không dữ liệu người

*Soạn 2026-06-11. Bản đầy đủ sau 8 deep-research stream + code grounding.*
*Kế thừa `project_va_redesign_v6`, `project_mer_science`, `project_color_final_v26`.*

---

## 0. Triết lý nền (chốt với chủ dự án 2026-06-11)

> **Hệ thống là nhạc Việt Nam, NHƯNG chuẩn cảm xúc–màu sắc dùng nghiên cứu quốc tế phổ quát — KHÔNG chế riêng cho người Việt.** Lý do: cảm xúc về cơ bản là phổ quát. Không có dữ liệu người, không fine-tune.

**Bằng chứng phổ quát (research-grounded, mạnh):**
| Trục | Phổ quát | Culture-specific | Nguồn |
|------|----------|------------------|-------|
| Color→emotion | **~88%** (r=.88) | ~12% | Jonauskaite 30 nước/4598 người |
| Emotion recognition | **~90.7%** | 9.3% in-group | Elfenbein & Ambady meta 97 studies |
| V-A circumplex | cấu trúc phổ quát | chỉ vị trí từ ngữ | Russell 7+ cultures; GlobalMood 59 nước |
| **Màu-cảm xúc VN** | **ALIGN universal** (blue=love, red=arousal/mixed, black=fear) | — | VN youth study; East-Asian gần universal |

→ **Dùng chuẩn quốc tế (ICEAS/Jonauskaite cho màu, Russell V-A cho cảm xúc) là hợp lý khoa học.** Refinement VN chỉ là bậc-2 (~9-12%), KHÔNG nền tảng.

**PHÂN BIỆT QUAN TRỌNG (cân bằng lại optimism — đừng nhầm):**
- **Cảm xúc & color→emotion: PHỔ QUÁT** → dùng chuẩn quốc tế tự tin, không cần validate VN.
- **Mapping audio→V-A: PHỤ THUỘC CORPUS** → universality của *cảm xúc* ≠ universality của *mapping học trên 1 corpus cụ thể*. Cross-corpus transfer **có thể sụp đổ** (EmoMusic→WCMED R²=−0.84, tệ hơn random; áp DEAM→VN dự kiến giảm 40-60% R²). **Phải validate transfer, KHÔNG giả định.**
- **Lyrics→V-A:** ngôn ngữ khác nhưng emotion-word norms phổ quát (NRC-VAD đa ngôn ngữ, EmoBank qua XLM-R cross-lingual giải quyết phần ngôn ngữ).

**Cứu cánh kiến trúc:** recommend-by-color KHÔNG cần V-A *tuyệt đối* đúng trên nhạc VN — chỉ cần *thứ tự tương đối* đủ tốt cho **TE gate**. Đây là yêu cầu yếu hơn cross-corpus R² tuyệt đối → vì sao TE là metric chính đúng đắn.

---

## 1. Mục tiêu

1. **Bỏ Gemini** khỏi V-A labels (5138 bài) — hiện V=70%Gemini+30%MERT, A=100%Gemini.
2. Thay bằng pipeline **audio + lyrics**, chuẩn quốc tế, không LLM.
3. **Bỏ VN-overlay** (`use_vietnamese_adaptation`) để thuần-universal — TE gate phán xử (xem §3).
4. Mục tiêu construct: catalog **r(V,A) → 0.05–0.10** (vs Gemini 0.313 entangled).
5. Không giảm chất lượng recommend-by-color: **TE ≤ 0.0245** giữ nguyên.

**Động cơ bỏ Gemini:** entanglement r(V,A)=0.313 (arousal lấy sai modality = lyrics-Gemini thay vì audio) + reproducibility/cost/dependency.

---

## 2. Tài sản đã có (verified 2026-06-11)

| Signal | File | Trạng thái | Hợp lệ |
|--------|------|-----------|--------|
| MERT arousal probe | `tools/mert_arousal_probe.py` | ✅ viết xong; `deam_mert.npy` sẵn | DEAM Ridge CV R²≈0.58 |
| `data/mert_arousal.json` | — | ❌ chưa sinh | output P1 |
| MERT valence probe | `tools/mert_valence_probe.py` | ✅ **DEAM-trained, KHÔNG circular** | CV R²=0.502 (layer9) |
| `data/mert_valence.json` | ✅ (5138, std=0.051) | audio-valence, ρ=0.704 vs Gemini (cross-check) |
| NRC-VAD lexicon | `var/data/nrc_vad_lexicon.txt` | ✅ 54801, [-1,1] | V+A+D |
| NRC-VAD scorer | `color_r2_valence_panel.py:_load_nrc_vad` | ✅ chỉ valence (cột1) | cần mở rộng arousal (cột2) |
| DEAM all-layers | `data/external/deam/deam_mert_all_layers.npy` | ✅ (1802,12,768) | ablation + cross-corpus |
| Gate harness | `tools/color_eval_rigor.py` | ✅ TE+CI+FDR+journey KS+ILD | gate cứng |
| VN-overlay | `core/advanced_color_mapping.py:382` | ⚠️ `use_vietnamese_adaptation=True` (+0.06 redness) | XUNG ĐỘT universal-only |
| Label hiện tại | `data/emotion_labels_v5d.json` | ✅ baseline để beat |

**3 signal valence độc lập không-LLM sẵn sàng:** MERT-audio (DEAM) ⟂ NRC-VAD(lyrics) + EmoBank-probe(lyrics, cần build).

---

## 3. Giải quyết mâu thuẫn VN-overlay (universal-only)

**Phát hiện:** `use_vietnamese_adaptation=True` (mặc định) — có per-color note (line 119) + **A2 valence += 0.06·redness·s01** (line 382, V28). Mâu thuẫn: V26 R3 đã chốt "thuần-global KHÔNG overlay" nhưng V28 lại bật A2.

**Phán quyết V6 (theo triết lý universal + bằng chứng):** màu-cảm xúc VN align universal, A2 chỉ là refinement bậc-2 (~9-12%) → **TEST bỏ overlay**:
- Set `use_vietnamese_adaptation=False`, chạy `color_eval_rigor`.
- Nếu TE giữ (≤0.0245) → **BỎ overlay** (đơn giản hơn + thuần-universal + giải mâu thuẫn). Khuyến nghị mặc định.
- Nếu TE xấu rõ rệt → overlay bắt tín hiệu local thật; document tension, để chủ dự án quyết (giữ vì empirical, hay bỏ vì purity).

---

## 4. Kiến trúc V6 (đề xuất, literature-grounded)

```
AROUSAL  (audio-dominant — arousal chính xác hơn on-corpus, Eerola meta r=.81 audio):
  A = 0.80 · MERT_arousal_probe(audio, DEAM)     # mert_arousal.json
    + 0.20 · NRC-VAD_arousal(lyrics lexicon)     # cột 2

VALENCE  (lyrics-leaning ensemble — valence generalize cross-corpus tốt hơn):
  V = wA · MERT_valence_probe(audio, DEAM R²=0.50)   # mert_valence.json
    + wL1· NRC-VAD_valence(lyrics, orthogonal)
    + wL2· EmoBank_probe(lyrics, XLM-R frozen)        # MỚI — P2b
  audio≈0.3 / lyrics≈0.7, TUNE bằng TE gate (grid/SLSQP), KHÔNG hardcode.
```

**Cơ sở:**
- Audio:lyrics **80:20 arousal**, **~30:70 valence** (arXiv:2405.01988; audio-only valence ceiling r=0.41-0.59).
- **Late fusion > early fusion**; fixed weights near-optimal (SLSQP similar-song) → KHÔNG cần adaptive gating.
- **Frozen probe transfer TỐT HƠN fine-tune** cross-corpus (arXiv:2202.10054 +7% OOD; xác nhận lại bởi cross-corpus MER study) — phù hợp "không fine-tune".
- MERT layer: arousal all-layers mean-pool (R²=0.58); valence layer9 (CV R²=0.502) — giữ theo ablation nội bộ.
- **Ensemble modality độc lập** (audio ⟂ lyrics): đồng thuận = corroboration thật (thay human GT ta không có).

---

## 5. Backtest — bộ metric 2 tầng (các metrics phù hợp)

### Tầng A — Chất lượng V-A label (intrinsic, trên benchmark CÓ nhãn)
Chạy trên DEAM/PMEmo/EmoBank held-out — nơi ta CÓ ground truth quốc tế.

| Metric | Vai trò | Range | Target | Ghi chú |
|--------|---------|-------|--------|---------|
| **CCC** (V & A riêng) | **CHÍNH** — chuẩn AVEC dimensional emotion | [-1,1] | tham chiếu DEAM in-domain ~0.5-0.8 | phạt bias+scale, hơn Pearson/R² |
| RMSE | sai số tuyệt đối | [0,∞] | thấp | CCC che được nếu lỗi nhất quán |
| Pearson r | độ mạnh tuyến tính | [-1,1] | chẩn đoán | tách noise vs bias |
| KS (distribution) | calibration phân phối | [0,1] | <0.10 | tránh nén range |
| **Cross-corpus CCC** | train DEAM → test PMEmo | [-1,1] | report drop honest | đo transfer thật |
| **Wasserstein/JS** (DEAM ↔ VN-catalog predicted V-A) | **transfer-risk proxy** | [0,∞] | nhỏ = an toàn | **tính được KHÔNG cần nhãn VN** |

> **CẨN TRỌNG:** target CCC≥0.80 chỉ áp cho in-domain CÓ human GT. Ta KHÔNG có VN GT → CCC chỉ đo trên **DEAM/PMEmo held-out** (trần intrinsic của probe), KHÔNG đo trên catalog VN. Trên VN dựa Tầng B + construct validity.

### Tầng B — Chất lượng recommend (downstream, trên catalog VN, human-free) — GATE CHÍNH
Đã có trong `color_eval_rigor.py`, bổ sung diversity.

| Metric | Vai trò | Target | Trạng thái |
|--------|---------|--------|-----------|
| **TE** (Euclidean+Mahalanobis) | targeting error V-A | **≤ 0.0245** | ✅ có |
| Bootstrap CI (10k) | không báo point estimate | report | ✅ có (Schnabel 2022) |
| BH-FDR vs 5 baselines | beats random/pop/valence-only/arousal-only/nearest-VA | sig | ✅ có |
| Journey KS + mean_t | uniform path A→B | KS<0.40, t∈[0.35,0.65] | ✅ có |
| ILD | intra-list diversity | informational | ✅ có |
| **Gini + Coverage + Entropy** | catalog fairness/breadth | Gini≥0.60, Cov≥0.50 | ⚠️ thêm nếu thiếu |

### Tầng C — Construct validity (bất biến lý thuyết, human-free)
- **r(V,A) catalog → 0.05–0.10** (vs Gemini 0.313) = bằng chứng decoupling chính.
- A vs tempo/energy: ρ > 0 (broken-arousal có ρ=0.03).
- V vs major/minor mode: kỳ vọng dương — test, KHÔNG ép (VN major-key-sad, panel mode ρ≈0.016).
- **Inter-signal corroboration:** ρ(NRC-VAD_V, EmoBank_V) + agreement audio-V vs lyrics-V = **validity proxy mạnh nhất** (2 phương pháp độc lập, không qua người, không qua Gemini).

### Phương pháp luận
- **Artist-grouped 5-fold nested CV** mọi nơi (chống leakage; cùng nghệ sĩ → cùng fold). Bắt buộc cho valence label replacement.
- Report cross-corpus tách riêng, thừa nhận domain shift (theo cross-corpus literature).

---

## 6. Kế hoạch theo Phase (mỗi phase ship riêng, gated)

### Phase 0 — Harness + baseline (chống tautology, TRƯỚC khi đổi label)
- [ ] `tools/va_intrinsic_eval.py`: CCC/RMSE/Pearson/KS cho probe trên DEAM/PMEmo held-out + cross-corpus DEAM→PMEmo + Wasserstein(DEAM, catalog-pred).
- [ ] Mở rộng `color_eval_rigor.py`: thêm Gini/Coverage/Entropy + construct-validity block (r(V,A), A-vs-tempo, inter-signal ρ).
- [ ] Snapshot baseline v5d → `va_baseline_v5d.json` (TE=0.0245, r(V,A)=0.313).
- [ ] Test bỏ VN-overlay (§3).

**Gate:** harness chạy, baseline ghi nhận. Không đổi label.

### Phase 1 — Arousal → audio (ROI cao nhất, sẵn sàng NGAY, ship riêng)
- [ ] `python -m tools.mert_arousal_probe train` → `data/mert_arousal.json` (CCC/R² trên DEAM + backtest vs tempo/energy đã có).
- [ ] `tools/nrc_vad_score.py` — tách shared util, đọc cả valence+arousal (DRY).
- [ ] `emotion_labels_v6a.json`: **A = 0.80·MERT + 0.20·NRC-VAD**, de-compress std≈0.16; **V giữ v5d** (cô lập biến).
- [ ] Gate: TE ≤ 0.0245 **VÀ** r(V,A) ↓ rõ (0.313 → <0.20).

**Quan trọng nhất — một mình sửa lỗi modality arousal.**

### Phase 2 — Valence → non-LLM ensemble (khó, gated chặt)
- [ ] **2a NRC-VAD valence:** verify path VN (lexicon English → bản VN / dịch / từ VN). Panel ρ=0.318 hiện chạy bằng gì?
- [ ] **2b EmoBank probe (MỚI):** tải EmoBank (10k câu VAD); `tools/emobank_valence_probe.py` — XLM-R-large hoặc VN-SBERT **frozen** → Ridge/MLP probe; CCC trên EmoBank held-out (lit r_V≈0.81). Apply zero-shot cross-lingual lên VN lyrics → `data/emobank_valence.json`. Cảnh báo Anglocentric bias.
- [ ] **2c ensemble + tune:** `V = wA·MERT + wL1·NRC + wL2·EmoBank`, tune trên **TE** (không Gemini). `emotion_labels_v6b.json` (A từ v6a). De-compress nếu cần.
- [ ] Gate: **TE ≤ 0.0245** + nested artist-grouped CV + r(V,A) orthogonal + inter-signal corroboration.

**Nếu 2c FAIL:** document negative. Fallback A = arousal-audio + valence-Gemini (v6a). Fallback B = nhận trần offline → P4.

### Phase 3 — Ship + honesty
- [ ] Pass → `config.RELABELED_EMOTIONS_FILE = emotion_labels_v6b.json`; UI data-va update nếu cần; commit; memory.
- [ ] §Honesty: CLAIM ĐƯỢC = "dùng chuẩn quốc tế universally-validated (Jonauskaite r=.88, Russell, AVEC-CCC), TE giữ, r(V,A) orthogonal, signal độc lập corroborate, cross-corpus transfer report honest". KHÔNG CLAIM = "validated accuracy tuyệt đối trên người Việt" (không có VN GT — và theo universality, KHÔNG CẦN, nhưng cũng KHÔNG được phóng đại).

### Phase 4 — Trần thật (tùy chọn, human-free vẫn làm được)
- Benchmark **MuQ** thay MERT (outperforms MERT emotion 2025) — rủi ro domain gap (similar-song: MuQ FAIL). Human-free.
- **Music2Emo v1.0** (HF `amaai-lab/music2emo`, MERT+KD, hỗ trợ VA) — external baseline human-free.
- Multi-dataset probe: train trên DEAM+PMEmo+EmoMusic đồng thời (cross-corpus literature: robust hơn).
- ~~Annotate VN + fine-tune~~ — chặn (không dữ liệu người); và theo universality không bắt buộc.

---

## 7. Cạm bẫy đã biết (similar-song + color + cross-corpus)

| Đừng làm | Bằng chứng |
|----------|-----------|
| ViSoBERT/PhoBERT off-shelf cho lyrics valence | ρ=0.03 (social media ≠ lyrics) |
| Fine-tune MERT/encoder | cross-corpus: frozen > fine-tuned; similar-song metric head FAIL |
| Compress/project embedding | 128-dim bottleneck giết mood (SimCSE/whiten/aug FAIL) |
| LLM judge validate non-LLM | GPT-4o-mini <0.7 acc vs human |
| **Giả định cross-corpus transfer OK** | **EmoMusic→WCMED R²=−0.84; phải đo Wasserstein + report drop** |
| Báo Pearson r thay CCC cho V-A | r bỏ qua bias; CCC là chuẩn AVEC |
| Song-level CV (không artist-grouped) | leakage +5-15% (cùng nghệ sĩ rò rỉ) |
| Hardcode trọng số | tune bằng TE |
| Để std nén truyền xuống | journey KS degrade (V30: 0.135→0.226) |
| ProtonX/embedding "ra V-A" trực tiếp | sai — chỉ semantic; cần probe trên VAD |
| VN-overlay khi đã chọn universal | §3 — test bỏ, TE phán xử |

**Encoder cho EmoBank-probe (nếu cần):** `dangvantuan/vietnamese-embedding` (768-d, STS 84.87%, đã có trong stack) cho semantic VN; **XLM-R-large** cho VA regression + cross-lingual từ EmoBank. Thử cả hai, chọn theo CCC + TE.

---

## 8. Thứ tự thực thi

| Bước | Việc | Effort | Rủi ro | Gain |
|------|------|--------|--------|------|
| P0 | Harness 2 tầng + baseline + test bỏ overlay | ~2-3h | thấp | nền backtest + giải mâu thuẫn |
| **P1** | **Arousal probe → v6a (A=audio)** | **~30-60min** | **thấp** | **sửa entanglement; r(V,A)↓; ship riêng** |
| P2a | Verify NRC-VAD VN path | ~30min | thấp | clarify |
| P2b | EmoBank XLM-R probe (mới) | ~2-3h | trung | lyrics-valence không-LLM |
| P2c | Ensemble + tune TE | ~2h | **cao** (có thể fail) | bỏ Gemini-valence |
| P3 | Ship + honesty | ~1h | thấp | — |
| P4 | MuQ/Music2Emo/multi-dataset | ngày | — | trần |

**Khuyến nghị:** P0 → **P1** (high-confidence milestone độc lập). P2 gated chặt; fail thì giữ v6a honest.

---

## 9. Gate bất biến (mọi thay đổi label)
1. `color_eval_rigor` — TE ≤ 0.0245, ordering, FDR, journey KS<0.40, ILD, +Gini/Coverage.
2. Structural battery T1–T4.
3. Valence label replacement → **thêm** nested artist-grouped 5-fold CV, TE giữ/improve.
4. Construct validity: r(V,A)→orthogonal, A-vs-tempo dương, inter-signal corroborate.
5. Intrinsic (probe): CCC trên DEAM/PMEmo held-out + Wasserstein(DEAM,catalog) report.
6. KHÔNG per-piece, KHÔNG calibrate một phía, KHÔNG giả định cross-corpus.
