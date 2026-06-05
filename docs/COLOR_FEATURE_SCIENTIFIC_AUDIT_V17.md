# Recommend-by-Colour — Audit khoa học toàn diện (V17)

Date: 2026-06-03. Phương pháp: 5 luồng deep-research đối chiếu paper + audit code + audit dữ liệu.
Mục tiêu: xét từng bước nhỏ nhất xem đã đúng/tối ưu theo khoa học chưa, tìm lỗi, đề xuất nâng cấp.

---

## TL;DR — Phán quyết tổng

**Cốt lõi đúng:** trục **Valence-Arousal làm cầu nối màu↔nhạc** là phần được khoa học chống lưng vững nhất (Whiteford 2018). Bộ 12 màu, đếm 12 ô, cap 3 màu — đều hợp lý.

**Nhưng có vấn đề nghiêm trọng làm giảm chất lượng thực tế:**
1. 🔴 **Embedding lời (PhoBERT vanilla mean-pool) gần như nhiễu cho retrieval** — mà nó chiếm **35%** điểm số.
2. 🔴 **Hex thuần sai** (làm lệch arousal/valence) — nên dùng centroid tri giác.
3. 🔴 **Hòa trộn = trung bình → "muddy middle"**, mâu thuẫn ý định union.
4. 🔴 **Dữ liệu lệch nặng** (47% sad) → màu sáng pool mỏng.
5. 🟠 Tune trọng số trên **n=12 không có giá trị thống kê**; σ=0.20 vô căn cứ; novelty proxy sai bản chất; chưa có gold-set tiếng Việt.
6. 🟡 Vài lỗi code cụ thể (max_length 512, đường ảnh dùng công thức cũ, 8-cảm-xúc trùng V-A).

---

## PHẦN 1 — Input: số màu, từng màu, cap

### 1.1 Đếm 12 ô — ✅ TỐI ƯU
- Hick's Law: chi phí log, 8→12 chỉ +~0.3 bit. "Miller 7±2" là trí nhớ tuần tự, **không** áp cho lưới nhìn-thấy. Choice-overload: meta-analysis Scheibehenne 2010 (50 thí nghiệm) **hiệu ứng ≈ 0**.
- *Giữ 12.* Nâng cấp nhẹ: **nhóm warm/cool/neutral** để giảm thời gian quét (đòn bẩy Hick thật).

### 1.2 Bộ màu Berlin&Kay 11 + turquoise — ✅ TỐI ƯU
- Đúng bộ stimulus của Jonauskaite 2020 (cơ sở dữ liệu màu-cảm xúc lớn nhất). Không có bộ 12 nào validate tốt hơn.

### 1.3 Hex thuần sRGB — 🔴 SAI (nghiêm trọng nhất phần màu)
- "Đỏ nguyên mẫu" của con người (World Color Survey) ≈ Munsell 5R 4/14 ≈ **#B30F24** (đỏ sẫm), KHÔNG phải `#FF0000`. Tương tự blue/green.
- `#FF0000`, `#FFFF00`… bị **ghim saturation 100%** → công thức arousal (trọng số sat 0.36–0.40) **đọc vống arousal** cho mọi màu; vàng ở L=50% **đọc hụt valence** (lightness→positivity).
- Dữ liệu ICEAS đo trên **patch Munsell**, không phải primary. Hex hiển thị phải == hex đưa vào tính.
- **Fix:** thay 12 hex bằng **centroid ISCC-NBS "vivid/strong"** (Kelly&Judd 1955; sRGB Centore 2016) hoặc focal WCS. Vừa hết garish vừa đúng lookup.

### 1.4 Cap 3 màu — ✅ TỐI ƯU
- Palmer 2013 dùng multi-color; ≥4 màu trung bình hóa về xám/trung tính. Giữ 3.

---

## PHẦN 2 — Mô hình cảm xúc: số cảm xúc, categorical vs dimensional

### 2.1 8 cảm xúc {happy,excited,peaceful,calm,melancholic,sad,tense,angry} — 🟡 AD-HOC + TRÙNG
- Thực chất là **8 octant của Russell circumplex dán nhãn** — không phải taxonomy nhạc.
- Cho NHẠC, taxonomy validate là **GEMS** (Zentner 2008, 9 yếu tố: wonder, transcendence, tenderness, nostalgia… — nhạc hiếm gây "giận/sợ" thật) hoặc **Hevner 8 cluster** (music-native). Bộ hiện tại mang `angry/tense` (hiếm trong nhạc) mà THIẾU nostalgia/tenderness/wonder.
- Eerola & Vuoskoski 2011 + replication 2023: **dimensional ≥ discrete**; discrete kém ở ca khó; categorical mang **ít** thông tin hơn V-A.
- Vì 8 nhãn này **suy ra từ cùng input HSL** với V-A → **double-counting** (V-A + bản sao lossy của V-A). Đây là lý do tuner đẩy emotion→0.10.
- **Fix:** lấy **V-A làm biểu diễn chính để match**; hạ 8 nhãn xuống **chỉ làm nhãn hiển thị** (render từ V-A), không làm tín hiệu match song song. Nếu giữ category cho người đọc → đổi sang **Hevner 8** và gọi là "tâm trạng biểu đạt", không phải "cảm xúc cảm nhận". *Test:* tương quan 8-vec với V-A trên anchor; nếu >0.9 tái dựng được → bỏ khỏi scoring.

### 2.2 Cầu nối màu→V-A→nhạc — ✅ ĐÚNG (phần vững nhất)
- Whiteford 2018: V-A **trung gian** match nhạc↔màu; cảm xúc nằm ở **saturation (72%) + lightness (68%)**, không phải hue. → vindicates V-A leg.

### 2.3 Nội suy IDW power-2 trong [cos·S, sin·S, L] — 🟠 YẾU
- Không gian HSL **không đều tri giác**; CLAUDE.md của chính dự án yêu cầu **CIEDE2000** → IDW-trong-HSL **mâu thuẫn nội bộ**.
- 12 anchor cho toàn không gian màu → IDW "bullseye", phần lớn query bị 1–2 anchor chi phối, độ phân giải thấp, không ngoại suy.
- **Fix:** đổi khoảng cách sang **CIELAB+CIEDE2000 hoặc OKLab**; thay IDW bằng **regressor mượt (Gaussian Process / RBF regression / ridge)** có uncertainty. *Test:* leave-one-anchor-out.

### 2.4 "Phổ quát r=.88" — 🟡 ĐỌC VỐNG
- Jonauskaite 2020: r=.88 là **tương đồng PATTERN giữa trung bình quốc gia**, KHÔNG phải bất biến cá nhân; chính paper chứng minh **quốc gia dự đoán thêm** ngoài phần phổ quát. VN không nằm trong 30 nước.
- Term `−0.19·redness` (đỏ→valence thấp) đúng theo ICEAS global (đỏ≈giận) **nhưng ngược với VN** (đỏ=may/tích cực).
- *Lưu ý:* chủ dự án **chủ động chọn thuần-global** (loại overlay VN). Đây là **đánh đổi có ý thức**, không phải lỗi — nhưng nên ghi rõ và (in-sample Pearson 0.85 → đổi sang CV honest).

---

## PHẦN 3 — Mô hình MIR: arousal (MERT), valence (LLM), DEAM

### 3.1 MERT cho arousal — ✅ HỢP LÝ (gần SOTA) nhưng để rơi điểm
- Tốt hơn hẳn Essentia handcrafted + CLAP zero-shot. Nhưng **R²=0.58 chỉ trung bình-khá** trên DEAM (band 0.50–0.67; SOTA Music2Emo ~**0.62**).
- Nguyên nhân: dùng **MERT-95M + Ridge tuyến tính** (cả backbone nhỏ lẫn head tuyến tính đều hụt).
- **Fix:** MERT-330M/MuQ-large; **gộp nhiều layer (5+6)**; head MLP; train trên **DEAM+PMEmo+EmoMusic** gộp; báo RMSE+Pearson cạnh R².

### 3.2 Tách valence←lời / arousal←audio — 🟠 ĐÚNG HƯỚNG, SAI CÁCH
- Hướng đúng (arousal từ audio, lời giúp valence — Hu&Downie, Yang&Chen). Nhưng **literature khuyên FUSION, không phải tách cứng** (Delbouys 2018: fusion cải thiện valence rõ).
- **Lỗi do tách cứng:** bài instrumental / thiếu lời → **không có tín hiệu valence**.
- **Fix:** late-fusion (audio→valence + lời→valence), thêm lời→arousal, fallback audio cho bài không lời.

### 3.3 LLM (Qwen3-8B) chấm valence — 🟠 ỔN nhưng chưa calibrate
- LLM giỏi sentiment thô (SST-2 ~93%) nhưng **kém calibrate ở thang số liên tục** (neo số tròn, nén thang) và **chưa validate trên tiếng Việt** (GlobalMood: LLM tụt mạnh ở nội dung phi-Tây).
- **Fix:** đừng hỏi số 0–1 trực tiếp → **rubric rời 5–7 bậc** + self-consistency + **isotonic calibrate** trên gold-set Việt; cân nhắc distill sang PhoBERT.

### 3.4 DEAM — 🔴 RỦI RO validity
- 1.802 bài **nhạc Tây**, annotator MTurk, **agreement valence thấp** (trần R² valence ~0.5 do nhiễu nhãn). Áp lên catalog Việt **không có validation in-domain nào**.
- Comment code "Eerola 2026 R²≈0.81" là **in-domain**, không phải transfer → **nói vống**.
- **Fix (đòn bẩy cao nhất toàn hệ):** **xây gold-set V-A tiếng Việt** (100–300 bài, ≥5 rater, báo ICC/Krippendorff). Một artifact này validate cùng lúc 3.1/3.3/3.4.

---

## PHẦN 4 — NLP tiếng Việt (retrieval lời)

### 4.1 PhoBERT vanilla mean-pool — 🔴🔴 LỖI LỚN NHẤT TOÀN FEATURE
- SBERT (Reimers 2019): mean-pool BERT thô **kém cả GloVe** cho STS; **anisotropy** (Li 2020) làm mọi câu trông giống nhau → **cosine gần như ngẫu nhiên**.
- `phobert-base-v2` là **checkpoint MLM, không phải sentence-encoder**. VN-MTEB: ngay cả PhoBERT đã fine-tune (sup-SimCSE-VN) chỉ **12% retrieval**, vs **bge-m3 ~40%**, **m-e5 ~41%**.
- → Tín hiệu `lyr_s` (chiếm **0.35** điểm) **phần lớn là nhiễu**.
- **Fix (ưu tiên #1, hiệu quả nhất):** thay encoder sang **`dangvantuan/vietnamese-embedding`** (giữ PhoBERT family + pyvi, STS 84–88) hoặc **`bge-m3`** (retrieval VN tốt nhất, không cần segment). Re-embed toàn bộ lời.

### 4.2 Query = trung bình 4 keyword — 🟠 YẾU + nhân lỗi 4.1
- Trung bình embedding cụm ngắn → vector mờ; **lệch độ dài/domain** với lời bài dài. Tác vụ query→doc **bất đối xứng**.
- **Fix:** dùng **câu prompt tự nhiên** ("Một bài hát với cảm xúc phấn khích, sôi động…") hoặc **exemplar lời thật** (pseudo-relevance, in-domain); thêm prefix query:/passage: (E5/BGE).

### 4.3 Word-segmentation — ✅ ĐÚNG (có caveat)
- PhoBERT cần segment (đúng). Nhưng pyvi ≠ RDRSegmenter (segmenter lúc pretrain) — lệch nhẹ; lời nhạc/slang/code-switch làm segment nhiễu.

### 4.4 Best practice — thiếu 2 tầng
- Hiện 1 tầng bi-encoder. SOTA = **bi-encoder fine-tuned → cross-encoder rerank** (ViRanker/PhoRanker cho tiếng Việt).

---

## PHẦN 5 — Phương pháp xếp hạng

### 5.1 RBF σ=0.20 — 🟠 vô căn cứ + quá hẹp
- σ nên đặt bằng **median heuristic** (Garreau 2017) hoặc tune trong CV, không gõ tay.
- JND của V-A ≈ 0.2–0.25 → **toàn bộ falloff của kernel nằm trong sàn nhiễu nhãn** (phân biệt mịn hơn nhãn cho phép).
- Euclidean **isotropic** sai: V-A tương quan hình chữ V (Kuppens 2013) → nên **Mahalanobis** theo covariance.

### 5.2 Tune trọng số trên n=12 — 🔴 KHÔNG GIÁ TRỊ THỐNG KÊ
- IR cần ~50+ query (TREC). n=12 + grid-argmax + bootstrap **trên chính 12 query đó** = selection-on-test-set, winner's-curse → CI không đúng, Δ thật gần như không phân biệt được với default.
- boost(0.12)/penalty(0.08) là **tham số tự do KHÔNG được tune**, cộng thêm ngoài simplex.
- **Fix:** mở rộng ≥50 query (lưới hue/L/S, không chỉ 12 tên màu); **nested leave-one-colour-out CV**; regularize về uniform; gộp boost/penalty vào tune hoặc bỏ. Hiện tại nên **ghi rõ trọng số là prior chưa tune**.

### 5.3 Blend = trung bình V-A — 🔴 MUDDY MIDDLE (mâu thuẫn ý định)
- Trung bình tọa độ affect → **về tâm trung tính**; đỏ+xanh → nhạc nhàng nhàng không khớp màu nào. Mâu thuẫn comment "union" trong code.
- **Fix:** chấm **từng màu riêng rồi fuse danh sách** bằng **RRF / CombMNZ** (hạ tầng RRF đã có sẵn!) hoặc **max-over-prototypes**. Centroid chỉ để hiển thị nhãn. Backtest cặp màu đối nghịch xem top-k có chứa CẢ hai mood không.

### 5.4 Novelty = tần suất artist — 🟠 SAI BẢN CHẤT
- Đây là **artifact thu thập dữ liệu** (scrape bao nhiêu bài/artist), không phải popularity nghe thật. Artist nhiều bài niche → bị coi "mainstream"; superstar 1 bài → "deep cut" (có thể **đảo ngược**). Min-max dễ vỡ vì outlier.
- **Fix:** dùng **view count YouTube per-track** (pipeline đã có thể có); nếu không → **content-novelty** (khoảng cách tới centroid catalog / mật độ kNN embedding); rank-normalize; áp nhẹ (Steck 2011); **đừng gọi là "popularity"**.

### 5.5 MMR — 🟡 ổn nhưng sai không gian
- MMR đa dạng hóa trên **embedding LỜI**, trong khi query là **mood màu** → lệch trục. Nên đa dạng trên **V-A + audio/timbre**. Đa màu nên dùng **calibrated recommendation** (Steck 2018) để phân bố mood khớp tỉ lệ màu chọn. DPP đã implement sẵn — benchmark vs MMR. λ=0.7 chưa tune.

---

## PHẦN 6 — Lỗi code cụ thể (xác nhận)

| # | Lỗi | File | Mức |
|---|-----|------|-----|
| B1 | `encode_lyrics(max_length=512)` vượt giới hạn vị trí PhoBERT (**256**) → lời >256 token lỗi/clip | `core/emotion_analysis.py:364` | 🟠 |
| B2 | Đường ảnh dùng `color_to_valence_arousal` (Palmer cũ) thay vì `hsl_to_va` (mới) — 2 công thức màu→VA | `recommendation_engine.py:988` | 🟠 |
| B3 | 8-emotion leg double-count V-A (tuner đã hạ xuống 0.10) | scoring | 🟡 |
| B4 | `color_mapper` tạo `vietnamese=True` (cultural_adjustments bật, dù chỉ ảnh hưởng đường ngược) | `:45` | 🟡 |

## PHẦN 7 — Vấn đề dữ liệu (lớn)
- Phân bố nhãn: **sad 47%, tense 20%** (= 67%); excited 2%, angry 1%, peaceful 1%. Valence trung bình catalog **0.33** (thiên buồn).
- → màu sáng (vàng/cam/hồng) pool ~15–18%, màu trầm đấu 67% → **gợi ý màu sáng yếu hơn**.
- one-hot emo trên nhãn lệch ⇒ ít giá trị phân biệt (khớp với tuner).
- **Fix:** cân nhắc re-label calibration (ngưỡng "sad" có thể over-assign); hoặc cân bằng/được-trọng-số theo nghịch tần suất; mở rộng catalog nhạc vui.

---

## PHẦN 8 — Roadmap nâng cấp (ưu tiên theo đòn bẩy)

| Ưu tiên | Hạng mục | Công sức | Tác động |
|---|---|---|---|
| **P0** | **Thay encoder lời** (dangvantuan/bge-m3) + re-embed | Trung | 🔴 Rất cao — sửa 35% điểm đang nhiễu |
| **P0** | **Gold-set V-A tiếng Việt** (100–300 bài, ≥5 rater) | Cao | 🔴 Mở khóa mọi validation thật |
| **P1** | **Blend → RRF/CombMNZ** (hạ tầng RRF đã có) | Thấp | 🔴 Sửa muddy-middle, cheap |
| **P1** | **Hex → centroid ISCC-NBS/WCS** (display==scored) | Thấp | 🔴 Sửa lệch arousal/valence + đẹp hơn |
| **P1** | **V-A làm canonical, 8-emotion → chỉ nhãn** | Trung | 🟠 Bỏ double-count |
| **P2** | Query = câu prompt/exemplar thay vì avg keyword | Thấp | 🟠 |
| **P2** | σ median-heuristic + Mahalanobis; tune trong CV | Thấp | 🟠 |
| **P2** | Novelty: view-count per-track hoặc content-novelty | Trung | 🟠 |
| **P2** | IDW → CIEDE2000/OKLab + regressor | Trung | 🟠 |
| **P3** | MERT-330M + multi-layer + MLP + multi-dataset | Cao | 🟡 |
| **P3** | Late-fusion valence + instrumental fallback | Trung | 🟡 |
| **P3** | Cross-encoder rerank (ViRanker/PhoRanker) | Trung | 🟡 |
| **P3** | Mở rộng eval ≥50 query + nested CV (bỏ over-claim n=12) | Trung | 🟡 |
| **fix** | B1 max_length=256; B2 thống nhất hsl_to_va; B4 vietnamese=False | Thấp | 🟢 |

**Nguyên tắc xuyên suốt:** không claim quá bằng chứng (n=12, in-sample Pearson, "phổ quát", transfer 0.81) — đổi sang số CV honest + gold-set Việt.

---

## Nguồn chính (load-bearing)
Whiteford 2018 i-Perception (V-A trung gian) · Palmer&Schloss 2013 PNAS · Jonauskaite 2020 Psych Sci (r=.88, nation-residual) · Eerola&Vuoskoski 2011 + 2023 (dimensional≥discrete) · Zentner 2008 GEMS · Hevner 1936 · Kelly&Judd 1955 ISCC-NBS / Centore 2016 · Kay&Regier 2003 WCS · Reimers&Gurevych 2019 SBERT · Li 2020 BERT-flow · VN-MTEB 2025 · dangvantuan/vietnamese-embedding · bge-m3 · Nguyen&Nguyen 2020 PhoBERT · Li 2024 MERT (ICLR) · Kang&Herremans 2025 Music2Emo · Aljanaki 2017 DEAM · Delbouys 2018 · Hu&Downie 2010 · Yang&Chen 2012 · GlobalMood 2025 · Wang 2024 (LLM sentiment) · Garreau 2017 (median heuristic) · Kuppens 2013 (V-A anisotropy) · Fox&Shaw 1994 (CombSUM/MNZ) · Cormack 2009 (RRF) · Abdollahpouri 2019 · Steck 2011/2018 · Carbonell&Goldstein 1998 (MMR) · Chen 2018 (DPP) · Scheibehenne 2010 · Iyengar&Lepper 2000.
</content>
