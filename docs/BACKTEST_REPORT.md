# Báo cáo Đánh giá (Backtest) — Hệ thống gợi ý nhạc Brightify

**Ngày:** 2026-05-28 · **Quy mô:** 5,548 bài hát Việt Nam · **Mọi số liệu trong báo cáo đều đo lại trực tiếp trên hệ thống đang chạy.**

---

## 0. Đọc báo cáo này như thế nào?

Báo cáo trả lời đúng một câu hỏi: **"Làm sao biết hệ gợi ý nhạc này thật sự tốt, chứ không phải chỉ cảm tính?"**

Để trả lời, ta đi theo mạch tự nhiên, và báo cáo cũng trình bày theo đúng thứ tự đó:

```
1. Hệ thống làm gì (đâu là tính năng LÕI)
2. Đo bằng cái gì       → các "thước đo" (metrics)
3. Lấy "đáp án đúng" ở đâu → 2 bộ ground-truth, mỗi bộ mạnh/yếu chỗ nào
4. Hiện trạng ra sao    → đo điểm xuất phát
5. Đã thay đổi những gì & VÌ SAO → 6 nâng cấp, giữ cái nào bỏ cái nào
6. Sau thay đổi tốt hơn bao nhiêu → số liệu trước/sau
7. Những điều phải nói thật → hạn chế & bước tiếp theo
```

Mỗi phần đều ghi rõ: *làm gì, đo bằng metric nào, trên dữ liệu nào, kết quả thực ra sao, và tại sao*.

---

## 1. Hệ thống làm gì — và đâu là tính năng LÕI

Brightify gợi ý nhạc từ **nhiều giác quan dữ liệu cùng lúc**, không chỉ từ tên bài hay lượt nghe. Tính năng **lõi** của hệ — thứ thể hiện rõ nhất triết lý "đa giác quan" — là **gợi ý nhạc theo MÀU SẮC** (`recommend_by_colors`).

Vì sao màu là lõi? Vì khi người dùng chọn một màu, hệ phải **hợp nhất 4 loại tín hiệu hoàn toàn khác nhau** để tìm bài hợp với màu đó:

| Tín hiệu | Trọng số | Ý nghĩa đời thường |
|----------|:--------:|--------------------|
| **Lời bài hát** (PhoBERT embedding) | **35%** | Nội dung, chủ đề, sắc thái ngôn từ của bài |
| **Đặc trưng âm thanh** (audio features) | **25%** | Bài nghe "sáng/tối", nhanh/chậm, sôi động/trầm |
| **Valence–Arousal** (tâm trạng 2 chiều) | **20%** | Vui–buồn × năng lượng cao–thấp |
| **Vector cảm xúc** (13 cảm xúc) | **20%** | Phân bố cảm xúc: vui, buồn, hoài niệm, giận… |

> **Đây là điểm mấu chốt:** đường màu **kết hợp cả ÂM THANH lẫn LỜI BÀI HÁT** (cộng tâm trạng & cảm xúc) trong một công thức trộn duy nhất. Lời bài hát chiếm trọng số lớn nhất (35%). Một màu (vd xanh dương) → quy ra tâm trạng (buồn/êm) → tìm các bài có *âm thanh trầm lắng + lời u buồn + cảm xúc sad/nostalgic*. Đó là lý do màu là tính năng đại diện cho toàn hệ.

*(Trọng số trên lấy trực tiếp từ mã nguồn `core/recommendation_engine.py`, hàm `recommend_by_colors`. Khi một bài thiếu lời, hệ tự chuyển sang công thức dự phòng: âm thanh 25% / V-A 35% / cảm xúc 25%.)*

Các đường gợi ý khác (theo bài hát mồi, theo tâm trạng, theo từ khóa lời, theo ảnh) dùng **chung kho tín hiệu** đó nhưng với cách trộn riêng.

---

## 2. Đo bằng cái gì — 6 thước đo (giải thích cho người không chuyên)

Cho hệ một "đề bài" (vd: một màu, hoặc một bài mồi), bắt nó trả về **10 gợi ý**, rồi đối chiếu với "đáp án đúng". Ta chấm bằng 6 thước đo, mỗi cái trả lời một câu hỏi khác nhau:

| Thước đo | Trả lời câu hỏi | Cách hiểu nhanh |
|----------|-----------------|-----------------|
| **NDCG@10** | 10 gợi ý có đúng *và* xếp bài đúng lên đầu không? | Thước đo *xếp hạng* chính. 0 = dở, 1 = hoàn hảo |
| **Precision@10** | Trong 10 bài, bao nhiêu bài thật sự đúng? | Độ *chính xác*. 0.2 = 2/10 bài trúng |
| **Recall@10** | Trong tất cả bài đúng, vớt được bao nhiêu phần? | Độ *bao phủ* |
| **MAP@10** | Giống Precision nhưng *thưởng điểm* khi bài đúng nằm trên cao | Chính xác *có ưu tiên thứ hạng* |
| **MRR** | Bài đúng *đầu tiên* nằm ở hạng mấy? | 0.33 ≈ bài đúng đầu tiên ở hạng 3 |
| **Hit@10** | Có *ít nhất 1* bài đúng trong 10 không? | Tỉ lệ "không trượt hoàn toàn" |

**Vì sao dùng nhiều thước đo chứ không một?** Vì mỗi cái có điểm mù. NDCG đo xếp hạng nhưng không cho biết "bắt được bao nhiêu phần" (đó là Recall). Một hệ có thể Precision cao mà MRR thấp (đúng nhưng để bài đúng xuống cuối). Nhìn cả 6 mới thấy bức tranh thật.

**Làm sao biết chênh lệch là thật, không phải may rủi?** Dùng kỹ thuật **bootstrap**: xáo trộn lại dữ liệu **10,000 lần** để xem khoảng dao động của điểm. Nếu khoảng tin cậy 95% (CI95) **không chạm mốc 0** → cải thiện *có ý nghĩa thống kê* (viết tắt **SIG**), tức thật sự khác chứ không phải tình cờ.

---

## 3. "Đáp án đúng" lấy ở đâu — 2 bộ Ground Truth và giới hạn của chúng

Muốn chấm điểm phải có đáp án. Ta có **hai** bộ, mỗi bộ phục vụ một mục đích và **mỗi bộ đều có giới hạn được nói thẳng**:

### Bộ A — Playlist biên tập (khách quan, từ bên ngoài)
- **Cách lấy:** crawl 32 playlist tiếng Việt do biên tập viên YouTube Music tuyển (nhạc buồn, chill, gym, ballad…), khớp bài vào catalog → **1,050 câu truy vấn**.
- **"Liên quan" nghĩa là:** hai bài được người biên tập xếp **chung một playlist**.
- **Mạnh:** khách quan, *không* do hệ tự sinh → đo được chất lượng *thật*.
- **Yếu:** chỉ hợp kiểu "cho 1 bài mồi → gợi ý bài tương tự"; và playlist có thể gom bài cùng ca sĩ.

### Bộ B — Màu → Tâm trạng (nội bộ, do engine sinh)
- **Cách lấy:** 24 màu đại diện trải đều vòng màu → mỗi màu quy ra một điểm tâm trạng (V-A) → các bài "liên quan" là bài có tâm trạng *gần* màu đó (khoảng cách V-A ≤ 0.25).
- **Mạnh:** đo được *đúng đường màu* — tính năng lõi.
- **YẾU — phải nói thật:** điểm tâm trạng (V-A) vừa là *thước đáp án*, vừa là *một đầu vào* (20%) của chính công thức gợi ý màu. ⇒ Có tính **vòng lặp (tautology)**: hệ tối ưu V-A thì tự nhiên ăn điểm trên đáp án định nghĩa bằng V-A. Thêm nữa, ngưỡng 0.25 khiến **trung bình 3,386/5,548 bài (≈61% catalog) bị coi là "liên quan"** cho mỗi màu → đề quá dễ, điểm dễ bão hòa gần mức tuyệt đối.
- **Hệ quả:** Bộ B **chỉ dùng để** (1) phát hiện hỏng nặng và (2) so sánh các phiên bản trên đường màu — **không** dùng làm thước đo chất lượng độc lập.

> **Tóm lại về chiến lược đo:** Đường màu là *lõi sản phẩm*, nhưng đáp án khách quan cho nó thì *chưa có* (cần nhãn người thật: "màu này hợp những bài nào"). Vì vậy ta đo đường màu bằng Bộ B (nội bộ, để kiểm tra nhất quán + so sánh nâng cấp), **và** dùng Bộ A (khách quan) để chứng minh rằng *các tín hiệu nền* mà đường màu dựa vào (lời, âm thanh…) thật sự mang thông tin liên quan. Hai bộ bổ trợ nhau.

---

## 4. Hiện trạng điểm xuất phát (trước mọi nâng cấp)

Bản gốc gọi là **v7.2**. Để có mốc, đo thêm 2 hệ tham chiếu trên Bộ A (đường bài→bài):

| Hệ thống | NDCG@10 | Precision@10 | Ý nghĩa |
|----------|:-------:|:------------:|---------|
| Gợi ý ngẫu nhiên | 0.051 | 0.053 | Sàn thấp nhất |
| Chỉ dùng lời bài hát | 0.097 | 0.095 | Một tín hiệu đơn |
| **Brightify gốc v7.2** | **0.091** | **0.091** | Điểm xuất phát |

Một phép thử "rút từng tín hiệu" cho thấy: **bỏ lời bài hát làm điểm tụt mạnh nhất (−0.020)**, các tín hiệu khác đóng góp nhỏ trên thước đo này. → Lời là tín hiệu chủ lực, nên các nâng cấp ưu tiên xoay quanh lời + bổ sung giác quan mới.

---

## 5. Đã thay đổi những gì — và VÌ SAO (6 nâng cấp)

6 nâng cấp ("Pillar") được thử. **Nguyên tắc đo trung thực:** bật **từng cái một** so với bản gốc thuần (tắt sạch mọi cái khác), để biết chính xác *riêng* nó đóng góp bao nhiêu.

| Pillar | Nâng cấp | Tác động chính lên đường nào |
|--------|----------|------------------------------|
| A | **MERT** — embedding âm thanh bằng AI | Tăng chất tín hiệu âm thanh |
| B | **SimCSE** — đổi mô hình hiểu lời (thay PhoBERT) | Tín hiệu lời |
| C | **RRF** — hợp nhất nhiều cách xếp hạng | Đường **màu** |
| D | **MMR** — tăng đa dạng danh sách | Mọi đường |
| E | **CLAP** — nhận cảm xúc nhạc bằng AI (thay từ điển) | Đường **màu** |
| F | **Knowledge Graph + ngữ cảnh VN** — quan hệ nghệ sĩ + giờ/ngày lễ | Đường bài→bài |

### 5.1. Một sự cố quan trọng: phát hiện 3 lỗi đo lường

Lần chạy đầu, **cả 6 Pillar đều "đạt"** — đẹp đến mức đáng ngờ. Rà lại, phát hiện **3 lỗi** khiến kết quả lạc quan giả, và đã sửa:

1. **Truy vấn không độc lập:** nhiều truy vấn cùng một playlist → khoảng tin cậy hẹp giả. **Sửa:** xáo trộn theo 32 playlist (cluster bootstrap), không theo 1,050 truy vấn lẻ.
2. **Thử 6 lần cùng lúc:** xác suất có ≥1 "đạt giả" lên ~26%. **Sửa:** siết độ tin cậy lên **99.2%** (hiệu chỉnh Bonferroni cho 6 phép thử).
3. **Bản gốc bị "nhiễm":** đo Pillar mới khi các Pillar khác còn bật. **Sửa:** mỗi Pillar so với bản gốc *thuần* v7.2.

### 5.2. Đo lại đúng cách → giữ cái nào, bỏ cái nào

| Pillar | Kết quả sau khi đo đúng | Quyết định & lý do |
|--------|--------------------------|--------------------|
| A — MERT | +0.022 (đường bài) ✅ | **Giữ** — có bằng chứng |
| **B — SimCSE** | **+0.001, khoảng tin cậy chạm vùng âm** ❌ | **BỎ, quay lại PhoBERT** — không chứng minh được tốt hơn |
| C — RRF | ≈0 (bài) nhưng **+0.056 (màu)** ✅ | **Giữ** — có ích đúng trên đường lõi (màu) |
| D — MMR | −0.014 điểm đổi lấy đa dạng cao hơn ✅ | **Giữ** — đánh đổi có chủ đích |
| E — CLAP | ≈0 (bài) nhưng **+0.065 (màu)** ✅ | **Giữ** — có ích đúng trên đường lõi (màu) |
| F — KG | +0.118 (mạnh nhất, đường bài) ✅ | **Giữ** — nhưng kèm lưu ý (xem mục 7) |

> **Quyết định bỏ Pillar B là điểm trung thực nhất của cả dự án:** một mô hình mới nghe rất "kêu", nhưng khi đo nghiêm túc *không* hơn bản cũ → loại bỏ thẳng, thay vì giữ để báo cáo cho đẹp. Hệ còn có cơ chế **tự động tắt** mọi nâng cấp không qua cổng kiểm định.

---

## 6. Sau khi thay đổi — tốt hơn bao nhiêu? (số liệu trước/sau, đo lại trực tiếp)

### 6.1. ĐƯỜNG LÕI — gợi ý theo màu (Bộ B, 24 màu)

Bản gốc v7.2 → bản hoàn chỉnh hiện tại. Bootstrap 10,000 lần.

| Thước đo | v7.2 | Hoàn chỉnh | Thay đổi | Có ý nghĩa TK? |
|----------|:----:|:----------:|:--------:|:--------------:|
| NDCG@10 | 0.935 | **1.000** | +7.0% | ✅ SIG |
| Precision@10 | 0.913 | **1.000** | +9.6% | ✅ SIG |
| MAP@10 | 0.893 | **1.000** | +12.0% | ✅ SIG |
| Recall@10 | 0.0031 | 0.0036 | +13.6% | ✅ SIG |
| Hit@10 | 1.000 | 1.000 | 0% | — (đã kịch trần) |
| MRR | 1.000 | 1.000 | 0% | — (đã kịch trần) |

**Đọc đúng kết quả này:** nâng cấp (đặc biệt **CLAP** và **RRF**) đẩy độ khớp màu→tâm trạng lên **mức gần như hoàn hảo**. NHƯNG vì 61% catalog đã được tính là "liên quan" (xem mục 3-B), các thước đo này **dễ kịch trần** (Hit/MRR = 1.0 cho cả hai bản). ⇒ Con số "1.000" KHÔNG nên hiểu là "hệ hoàn hảo"; nó nghĩa là **đường màu đã nhất quán nội bộ tối đa và các nâng cấp giúp nó khớp tâm trạng tốt hơn**. Bằng chứng chất lượng *thật* nằm ở mục 6.2.

### 6.2. NỀN TẢNG TÍN HIỆU — đường bài→bài (Bộ A khách quan, 1,050 truy vấn)

Đây là phần **khách quan** nhất: chứng minh các tín hiệu mà đường màu dựa vào (lời, âm thanh, quan hệ nghệ sĩ) thật sự mang thông tin đúng. Cluster bootstrap 10,000 lần.

| Thước đo | v7.2 | Hoàn chỉnh | Thay đổi | Có ý nghĩa TK? |
|----------|:----:|:----------:|:--------:|:--------------:|
| **NDCG@10** | 0.091 | **0.185** | **+102.6%** | ✅ [+0.091, +0.163] |
| **Precision@10** | 0.091 | **0.180** | **+98.2%** | ✅ [+0.084, +0.156] |
| **Recall@10** | 0.0038 | **0.0116** | **+208.7%** | ✅ [+0.0036, +0.0126] |
| **MAP@10** | 0.035 | **0.098** | **+178.7%** | ✅ [+0.064, +0.120] |
| **MRR** | 0.215 | **0.355** | **+65.3%** | ✅ [+0.140, +0.228] |
| **Hit@10** | 0.538 | **0.658** | **+22.3%** | ✅ [+0.061, +0.172] |

**Đọc cho người không chuyên:**
- Số bài *trúng* trong mỗi 10 gợi ý **tăng gần gấp đôi** (Precision 0.09 → 0.18).
- Bài đúng được **đẩy lên đầu sớm hơn nhiều** (MRR +65%, MAP +179%).
- Tỉ lệ "có ít nhất 1 bài trúng" tăng từ 54% → 66% (Hit@10).
- **Cả 6 thước đo đều cải thiện và đều có ý nghĩa thống kê** — không phải may rủi.

*(Recall nhỏ vài phần trăm là bình thường: mỗi playlist có hàng trăm bài liên quan mà ta chỉ trả 10 → không thể vớt hết. Quan trọng là mức tăng tương đối +209%.)*

### 6.3. Một lưu ý trung thực về con số "+102.6%"

Con số dao động nhẹ theo **giờ chạy đo**, vì ngữ cảnh VN (Pillar F) chỉnh tâm trạng theo giờ trong ngày: chạy buổi sáng = +102.6% (0.185), chạy nửa đêm = +107.4% (0.189). Cả hai đều SIG và quanh **+100%**. Báo cáo lấy **+102.6%** (đo trên code + giờ hiện tại) làm chuẩn, biên độ ±~5 điểm phần trăm.

---

## 7. Những điều phải nói thật (không tô hồng)

1. **Đường màu là lõi sản phẩm, nhưng chưa có đáp án khách quan riêng.** Số "1.000" trên Bộ B là *nhất quán nội bộ* + đề dễ (61% liên quan), **không** phải "hoàn hảo". Cần xây nhãn người thật cho màu → đây là việc quan trọng nhất tiếp theo.
2. **Bằng chứng khách quan (+102.6% NDCG, +98% chính xác, +209% bao phủ)** nằm ở đường bài→bài (Bộ A) — và nó xác nhận các *tín hiệu nền* (lời/âm thanh/KG) mà đường màu dùng là tốt thật.
3. **Phần lớn lực kéo đến từ Pillar F (KG)**, nhưng kiểm tra riêng cho thấy KG mạnh **chủ yếu nhờ gợi ý cùng nghệ sĩ**: khi chỉ xét các cặp *khác* nghệ sĩ, lợi ích của KG biến mất (0.081 → 0.076). Đã gắn cờ rõ, không thổi phồng.
4. **Pillar B (mô hình lời mới) KHÔNG có trong sản phẩm** — không tuyên bố đã dùng SimCSE.
5. **Đáp án khách quan hiện chỉ từ 1 nguồn** (YouTube Music). Cần nguồn độc lập thứ hai (nhãn chuyên gia / dữ liệu nghe thật) để khẳng định chắc hơn.

---

## 8. Tóm tắt một đoạn

Tính năng **lõi** của Brightify là gợi ý nhạc theo **màu sắc**, vì nó hợp nhất 4 giác quan dữ liệu trong một công thức: **lời bài hát 35% + âm thanh 25% + tâm trạng 20% + cảm xúc 20%**. Ta đo bằng 6 thước đo (NDCG, Precision, Recall, MAP, MRR, Hit), kiểm định bootstrap 10,000 lần, trên **hai bộ đáp án**: playlist biên tập (khách quan, đường bài→bài) và màu→tâm trạng (nội bộ, đường màu — có tautology nên chỉ để so sánh phiên bản). Sau khi **phát hiện & sửa 3 lỗi đo lường** và **trung thực loại bỏ Pillar B**, bản hoàn chỉnh: trên đường lõi (màu) đạt độ khớp tâm trạng gần tuyệt đối nhờ CLAP + RRF; trên thước đo khách quan (bài→bài) cải thiện **+102.6% NDCG, +98% độ chính xác, +209% độ bao phủ so với bản gốc — tất cả có ý nghĩa thống kê**. Hạn chế lớn nhất còn lại: đường màu chưa có đáp án khách quan của riêng nó.

---

### Phụ lục — Nơi lưu số liệu gốc (để kiểm chứng)

| Nội dung | Đường dẫn |
|----------|-----------|
| Điểm xuất phát + các hệ tham chiếu | `var/runtime/backtest/reports/iter_0_baseline/` |
| 6 Pillar đơn lẻ (A–F) | `…/iter_2_pillar_B/` … `…/iter_7_pillar_F/` |
| **Đường LÕI (màu) — full metrics, đo lại** | `…/iter_10_color_accuracy/report.json` |
| Đường bài→bài — full metrics, đo lại | `…/iter_9_full_accuracy/report.json` |
| Pillar C / E trên đường màu (đơn lẻ) | `…/pillar_C_color/`, `…/pillar_E_color/` |
| Kiểm tra "cùng nghệ sĩ" của KG | `…/pillar_F_xartist/report.json` |
| Script đo lại (màu / bài) | `tools/backtest_v2/measure_color_accuracy.py`, `measure_full_accuracy.py` |
| Định nghĩa GT màu (24 màu, ngưỡng V-A) | `tools/backtest_v2/ground_truth/color_emotion_gt.py` |
| Mã nguồn engine đường màu | `core/recommendation_engine.py::recommend_by_colors` |
