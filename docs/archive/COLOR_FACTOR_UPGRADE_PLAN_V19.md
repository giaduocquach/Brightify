# Plan update — Các YẾU TỐ gợi ý trên cơ sở khoa học (V19)

Date: 2026-06-03. Tổng hợp 9 luồng deep-research (toàn dự án) + 2 luồng chuyên về FACTOR. Trọng tâm:
**factor nào đưa vào điểm số gợi ý, vì sao, weight thế nào** — tất cả dựa trên cái đã được kiểm chứng.
Không phụ thuộc gold-set bespoke.

---

## 0. Verdict factor (hội tụ, có trích dẫn)

**Mọi tương ứng màu↔nhạc được TRUNG GIAN HOÀN TOÀN bởi V-A.** Whiteford 2018 (i-Perception): *mọi*
tương ứng tri-giác trực tiếp (saturation↔energy, lightness↔loudness…) **biến mất** sau khi loại cảm
xúc (−.568≤rs≤+.489, p>.05); 2 factor affective (arousal+valence) giải thích 58-72% biến thiên màu.
Palmer 2013 (PNAS): r=.89–.99 — và **dùng nhạc KHÔNG LỜI** (cố ý loại lyrics khỏi confound).

→ **Factor matching cốt lõi = khoảng cách V-A. Hết.** Lyrics & emotion-category **không** phải factor
matching riêng.

---

## 1. Factor set ĐÍCH (xếp theo bằng chứng)

### Lớp A — Dựng V-A mỗi phía (từ feature đã validate)
**Song → V-A** (đây là chỗ "audio features + lyrics emotion" sống):
| Trục | Feature | Bằng chứng | Sức |
|---|---|---|---|
| **Arousal** | tempo, loudness/energy, onset-rate/articulation, timbral-brightness | Gomez&Danuser 2007; Coutinho 2011 | MẠNH (~80% dự đoán được) |
| **Valence** | **mode (major/minor) + harmonic consonance** + **lyrics sentiment** | Hunter&Schellenberg; Gomez&Danuser; **Delbouys 2018, Hu&Downie 2010** | YẾU từ audio (~17%) → **lyrics là đòn bẩy chính cho valence** |

**Color → V-A** (ICEAS): lightness→valence(+)&arousal; saturation→arousal(+); warmth(đỏ-vàng)→
valence (trục vàng/xanh yếu hơn → weight thấp). (Palmer 2013; Whiteford 2018.)

### Lớp B — Matching (chỉ MỘT factor cốt lõi)
| # | Factor | Trạng thái |
|---|---|---|
| 1 | **Khoảng cách V-A (RBF heteroscedastic)** — toàn bộ metric match | ✅ VALIDATED, primary, dominant |
| 2 | *(tùy chọn)* timbre-brightness ↔ color-lightness, term NHỎ riêng | 🟡 SPECULATIVE (semantic-mediated, R²≈0.02-0.14) — A/B test, không core |

### Loại bỏ khỏi matching (có cơ sở):
- ❌ **lyric-semantic cosine (0.35 hiện tại):** Palmer/Whiteford loại lyrics; **không có kênh
  màu→lyric-theme được validate**. Encoder PhoBERT mean-pool còn là *near-noise* (anisotropy, Li 2020).
  → lyrics chuyển vào **valence** (vai trò đã validate), KHÔNG match cosine trực tiếp.
- ❌ **emotion-category cosine (0.10):** double-count V-A (category là construction trên V-A core
  affect — Russell 1980). Xác nhận bằng VIF + ablation rồi xóa.
- ➡️ **boost/penalty:** chuyển thành *business rule* tách khỏi mô hình affective; ablate.

> Lưu ý mở rộng (Alvarado 2025): color-emotion **vượt 2D** (có dominance + hiệu ứng discrete). Chỉ thêm
> trục **dominance** nếu gán nhãn được song-dominance (hiện chưa) → để TƯƠNG LAI, không phải bây giờ.

---

## 2. Heteroscedastic RBF (mã hóa "tin arousal hơn valence")

```
d²(song, color) = (Δarousal / σ_A)²  +  (Δvalence / σ_V)²        với σ_A < σ_V
va_s = exp(−½ · d²)
```
- σ_A hẹp (arousal tin: audio-driven, ~80% dự đoán được), σ_V rộng (valence yếu ~17%, nhiễu).
- Cơ sở: literature (Yang/Eerola arousal≫valence predictability) — KHÔNG cần gold-set.
- σ chọn bằng **median heuristic** trên phân bố song-V-A mỗi trục (Garreau 2017), tinh chỉnh trong CV.

---

## 3. Weighting — cách tune defensible (sửa lỗi n=12 + circular)

**Prior evidence-proportional:** V-A là factor áp đảo (prior từ 58% variance share Whiteford); **không
có weight lyric riêng, không weight emotion riêng**. Nếu vẫn tune:
- **Distant label = editorial mood playlist** (Nhạc Buồn/Vui/Chill/Sôi động → Q1-Q4), de-noise đa nguồn.
- **Artist-grouped NESTED CV** (không artist nào ở cả train+test — chống leakage; CEUR Vol-4045).
- ≤3 tham số, **simplex-constrained**, pre-register metric (nDCG@k), báo CI.
- **Baseline phải thắng = "V-A only"**; weight nào không thắng V-A-only out-of-group → bỏ.
→ Cách này diệt cả overfit n=12 lẫn circularity.

---

## 4. Validation (không gold-set bespoke — xem V18b)
- **Battery cấu trúc label-free** (gate thường trực): discriminant màu đối nghịch · monotonicity ·
  commensurability `a≈1,b≈0` · audit skew 47% · round-trip.
- **Editorial-playlist quadrant** (metric end-to-end chính, artist-grouped, macro-F1/balanced).
- **Cross-corpus** song→V-A (PMEmo/EmoMusic) cho component arousal/valence.
- Ablation: bỏ từng factor dưới grouped-CV → giữ chỉ factor thắng V-A-only.

---

## 5. Lộ trình update (từng bước verifiable, rủi ro thấp→cao)

| # | Bước | Nội dung | Gate | Phụ thuộc data người? |
|---|---|---|---|---|
| **F1** | **Battery cấu trúc + editorial grouped-CV harness** | Dựng nền validation non-circular (label-free + editorial artist-grouped) | tự chạy được | KHÔNG |
| **F2** | **Ablation factor hiện tại** | Đo trên F1: V-A-only vs +lyr vs +emo. Kỳ vọng: bỏ emo (double-count) + lyr-cosine (noise) không hại | nDCG grouped-CV | KHÔNG |
| **F3** | **Matching = V-A heteroscedastic only** | Bỏ lyr-cosine & emo-cosine khỏi `_color_score`; σ_A<σ_V median-heuristic; boost/penalty→rule riêng | F1 battery + editorial ≥ baseline cũ | KHÔNG |
| **F4** | **Song-valence = lyrics + audio(mode/harmony) fusion** | Đưa lyrics vào VALENCE (vai trò validate); audio-valence từ mode/harmony; late-fusion w_lyr>w_audio | cross-corpus + editorial quadrant | KHÔNG |
| **F5** | *(tùy chọn)* timbre-brightness↔lightness term nhỏ | A/B trên editorial; chỉ giữ nếu thắng | ablation | KHÔNG |
| **F6** | *(tương lai)* dominance axis | chỉ khi gán nhãn được song-dominance | — | (cần data) |

**Khác biệt lớn vs hiện tại:** `_color_score` từ `0.35 lyr + 0.55 va + 0.10 emo + boost − pen` →
**chỉ còn V-A heteroscedastic** (lyrics nuôi valence, không phải factor riêng). Đơn giản hơn, đúng khoa
học hơn, mỗi factor đều có bằng chứng.

**Nguyên tắc:** mỗi bước gate bằng **editorial grouped-CV (end-to-end) + battery cấu trúc**, KHÔNG bằng
metric per-piece hay GT circular. Không bước nào cần thu thập người mới.

---

## 6. Bắt đầu từ đâu
**F1 trước** (nền validation non-circular) — vì không có nó thì F2/F3 không đo được đáng tin. Rồi F2
(ablation, xác nhận bỏ emo+lyr-cosine an toàn) → F3 (matching V-A-only) → F4 (lyrics→valence). F1+F2
không đụng production, an toàn tuyệt đối.

## Nguồn chính
Palmer 2013 PNAS · Whiteford 2018 i-Perception (mediation decisive) · Gomez&Danuser 2007 · Coutinho 2011 ·
Hunter&Schellenberg · Eerola&Vuoskoski 2011 · Delbouys 2018 ISMIR · Hu&Downie 2010 · Li 2020 EMNLP
(anisotropy) · Russell 1980 · Alvarado 2025 · Garreau 2017 · CEUR Vol-4045 (artist-grouped eval) ·
Çano MoodyLyrics 2017 · Laurier 2009 (tags→Russell quadrants).
</content>
