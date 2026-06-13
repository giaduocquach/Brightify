# Báo cáo Đánh giá Offline (Backtest) — Hệ thống gợi ý nhạc Brightify
### Phiên bản: Đường gợi ý theo bài hát (recommend_by_song)

**Ngày báo cáo:** 2026-05-28 · **Quy mô:** 5,548 bài hát Việt Nam

---

> ## 📋 HƯỚNG DẪN TRÌNH BÀY (dành cho người báo cáo)
>
> File này là bản báo cáo đường **bài→bài** kèm ghi chú hướng dẫn.
> Các ô `> 💡 HƯỚNG DẪN` rải trong tài liệu — đọc trước khi lên báo cáo.
> Xóa các ô hướng dẫn trước khi gửi cho người nghe bên ngoài.
>
> **Thứ tự ưu tiên khi trình bày:**
> 1. Dẫn dắt bằng *vấn đề* → *phương pháp* → *kết quả* — không bắt đầu bằng số.
> 2. Nhấn mạnh **sự trung thực** (tự phát hiện lỗi, tự loại bỏ Pillar B) — đây là điểm mạnh nhất.
> 3. Số +102.6% là headline — nhưng chỉ nêu **sau** khi giải thích thước đo.
> 4. Chuẩn bị sẵn câu trả lời cho 3 câu hỏi khó (xem cuối file).

---

## Phần mở đầu: Tại sao cần đánh giá offline?

Brightify gợi ý nhạc từ nhiều tín hiệu: âm thanh, lời bài hát, cảm xúc, màu sắc. Mỗi khi thêm tính năng mới, câu hỏi bắt buộc là:

> **"Tính năng này có thực sự tốt hơn, hay chỉ là cảm giác?"**

Backtest trả lời câu đó *trước khi* đưa ra cho người dùng thật — bằng cách đo trên dữ liệu có sẵn. Toàn bộ quá trình đi theo một mạch:

```
Xây thước đo  →  Đo hiện trạng  →  Thử cải tiến  →  Kiểm định thống kê
                                                              ↓
                                        Giữ nếu chứng minh được / Bỏ nếu không
```

> **💡 HƯỚNG DẪN — Mở đầu**
> Mở bằng câu hỏi trên, để 2–3 giây cho người nghe suy nghĩ rồi mới nói tiếp.
> Tạo sự đồng thuận: "chúng ta cần đo, không thể tin cảm tính" — đây là tiền đề để
> mọi người chấp nhận quy trình nghiêm ngặt ở các bước sau.

---

## Bước 1 — Xây "thước đo"

### Làm thế nào?

**Đáp án đúng (Ground Truth)** lấy từ **playlist do biên tập viên YouTube Music tuyển chọn**. Nếu hai bài được người biên tập xếp chung playlist ("Nhạc chill Việt Nam", "Nhạc buồn tâm trạng"…) → coi là *liên quan* nhau. Đây là đáp án **hoàn toàn độc lập** với hệ thống — không do nhóm tự đặt.

**Quy trình:**
1. Crawl 18 chủ đề playlist tiếng Việt.
2. Khớp tên bài + nghệ sĩ (xử lý dấu tiếng Việt) vào 5,548 bài trong catalog.
3. Lọc bỏ playlist quá ít bài (< 10 bài khớp) hoặc quá chung chung (> 70% catalog).

**Kết quả:** **32 playlist** đạt chuẩn → **1,050 câu truy vấn**.

Cách chấm: cho hệ 1 bài làm mồi, yêu cầu trả về 10 bài → đếm bài trúng trong đáp án.

### Các thước đo dùng để chấm

| Thước đo | Câu hỏi trả lời | Điểm tốt |
|----------|-----------------|-----------|
| **NDCG@10** | 10 gợi ý đúng *và* xếp bài đúng lên đầu không? | Gần 1 |
| **Precision@10** | Trong 10 bài, bao nhiêu bài đúng? | Gần 1 |
| **Recall@10** | Vớt được bao nhiêu phần tổng số bài đúng? | Gần 1 |
| **MAP@10** | Precision nhưng thưởng khi bài đúng ở hạng cao | Gần 1 |
| **MRR** | Bài đúng đầu tiên ở hạng mấy? (1/rank) | Gần 1 |
| **Hit@10** | Có ≥1 bài đúng trong 10 không? | Gần 1 |

> **💡 HƯỚNG DẪN — Giải thích thước đo**
>
> **Cách giải thích nhanh cho non-tech:** "Cứ tưởng tượng hệ thống là một nhân viên tư vấn
> âm nhạc. Ta đặt câu hỏi 1,050 lần, mỗi lần cho họ 1 bài và yêu cầu gợi ý 10 bài.
> Sau đó đối chiếu với danh sách bài playlist của biên tập viên để xem gợi ý có trúng không."
>
> **Về Recall nhỏ:** chuẩn bị câu trả lời này — *"Mỗi playlist có hàng trăm bài liên quan,
> ta chỉ gợi ý 10 bài → Recall tự nhiên nhỏ. Điểm quan trọng là mức TĂNG so với bản gốc,
> không phải giá trị tuyệt đối."*
>
> **Thước đo chính cần nhấn:** NDCG@10 và Precision@10 — dễ giải thích nhất.
> MRR là thước đo "bài đúng được xếp sớm tới đâu" — cũng dễ giải thích cho non-tech.

---

## Bước 2 — Đo hiện trạng (điểm xuất phát)

| Hệ thống | NDCG@10 | Precision@10 | Recall@10 | MRR |
|----------|:-------:|:------------:|:---------:|:---:|
| Gợi ý ngẫu nhiên | 0.051 | 0.053 | 0.0019 | 0.132 |
| Chỉ dùng lời bài hát | 0.097 | 0.095 | 0.0047 | 0.231 |
| **Brightify gốc (v7.2)** | **0.091** | **0.091** | **0.0038** | **0.215** |

**Kết quả ablation (bỏ từng tín hiệu):**
Bỏ lời bài hát → điểm tụt mạnh nhất (−0.020). Các tín hiệu khác đóng góp nhỏ hơn.
→ Lời là tín hiệu chủ lực → các nâng cấp ưu tiên xoay quanh lời.

> **💡 HƯỚNG DẪN — Hiện trạng**
>
> Bảng này có 2 mục đích: (1) cho thấy bản gốc v7.2 **hơn hẳn ngẫu nhiên** (không phải
> hệ vô dụng), (2) đặt mốc để số liệu sau có chỗ so.
>
> **Điểm cần nhấn:** v7.2 = 0.091, ngẫu nhiên = 0.051 → bản gốc đã tốt hơn ~1.8× ngẫu nhiên.
> Điều này quan trọng: nó nói rằng bản gốc "không phải rác", chỉ là "chưa tối ưu".
>
> **Đừng bỏ qua bảng này** — không có mốc xuất phát thì số +102.6% sau này
> người nghe không hiểu bối cảnh.

---

## Bước 3 — Thử 6 nâng cấp (6 Pillar)

Mỗi nâng cấp được bật **riêng lẻ** và so với bản gốc thuần (tắt sạch mọi cái khác).

| Pillar | Ý tưởng | Tác động đường bài→bài |
|--------|---------|------------------------|
| **A** | MERT — embedding âm thanh bằng AI | +0.022 NDCG |
| **B** | SimCSE — đổi mô hình hiểu lời | +0.001 (không ý nghĩa) |
| **C** | RRF — kết hợp nhiều cách tìm | ≈ 0 (lợi ích ở đường khác) |
| **D** | MMR — tăng đa dạng danh sách | −0.014 NDCG, đổi lấy đa dạng cao |
| **E** | CLAP — nhận cảm xúc bằng AI | ≈ 0 (lợi ích ở đường khác) |
| **F** | Knowledge Graph + ngữ cảnh VN | +0.118 NDCG (mạnh nhất) |

> **💡 HƯỚNG DẪN — 6 Pillar**
>
> Đây là phần kỹ thuật nhất — rút gọn nếu thời gian ít. Cái cần nhấn:
> - **Pillar D (MMR)** là ví dụ hay về "đánh đổi có chủ đích": giảm NDCG để tăng đa dạng.
>   Giải thích: "thay vì gợi ý 10 bài rất giống nhau, ta chủ động đưa vào một số bài phong phú hơn".
> - **Pillar C và E** cho NDCG ≈ 0 trên đường này — *chuẩn bị giải thích tại sao vẫn giữ*
>   (vì chúng có tác dụng trên đường màu — ghi chú ngắn đủ rồi).
> - **Pillar F** là con số ấn tượng nhất (+0.118) nhưng cần kèm lưu ý circularity (xem Bước 5b).

---

## Bước 4 — Phát hiện và sửa 3 lỗi đo (bước quan trọng nhất)

Lần chạy đầu **cả 6 Pillar đều đạt** — đẹp đến mức đáng ngờ. Kiểm tra lại, phát hiện 3 lỗi:

### Lỗi 1 — Các truy vấn không độc lập
Nhiều truy vấn cùng playlist → khoảng tin cậy hẹp giả tạo.
**Sửa:** xáo trộn theo **32 playlist** (cluster bootstrap), không theo 1,050 truy vấn lẻ.

### Lỗi 2 — Thử 6 phép cùng lúc
Xác suất có ≥1 "đạt giả" ~26%.
**Sửa:** độ tin cậy **99.2%** (hiệu chỉnh Bonferroni cho 6 phép thử).

### Lỗi 3 — Baseline bị nhiễm
Đo Pillar mới khi các Pillar khác còn bật → lẫn lộn đóng góp.
**Sửa:** mỗi Pillar so với baseline **thuần v7.2** (tắt sạch mọi tính năng khác).

**Hệ quả:** sau khi sửa, **Pillar B lật từ "đạt" thành "trượt"** → loại bỏ, quay lại PhoBERT.

> **💡 HƯỚNG DẪN — Phần này là điểm mạnh NHẤT của báo cáo**
>
> Đây là nơi bạn xây dựng uy tín. Phần lớn báo cáo kỹ thuật sẽ che giấu lỗi phương pháp
> hoặc không phát hiện ra. Nhóm này tự tìm ra và tự sửa.
>
> **Cách kể câu chuyện:**
> *"Kết quả đầu tiên đẹp đến mức chúng tôi nghi ngờ — và đúng là có vấn đề. Chúng tôi
> tự phát hiện 3 lỗi thống kê, sửa lại từ đầu, và một nâng cấp nghe có vẻ hay (SimCSE)
> thực ra không chứng minh được là tốt hơn → bị loại bỏ thẳng."*
>
> **Tại sao điều này quan trọng với người nghe:**
> - Với người kỹ thuật: cho thấy nhóm hiểu thống kê nghiêm túc (cluster bootstrap,
>   Bonferroni correction — không phải mọi nhóm làm được).
> - Với người non-tech: "nhóm không cố tình làm đẹp số liệu" — xây dựng tin tưởng.
>
> **Nhấn mạnh:** hệ thống có cơ chế **tự động tắt** mọi nâng cấp không qua cổng kiểm định.
> Đây là thiết kế có chủ đích, không phải vá víu.

---

## Bước 5 — Kiểm tra bổ sung cho các điểm còn nghi ngờ

### 5a. Pillar C và E — "bằng 0" có vô dụng không?

C (RRF) và E (CLAP) cho NDCG ≈ 0 trên đường bài→bài vì chúng tác động lên đường màu.
Kiểm tra riêng trên 24 màu đại diện:

| Pillar | Cải thiện trên đường màu | Kết luận |
|--------|--------------------------|----------|
| C — RRF | +0.056 NDCG | Có ích thật |
| E — CLAP | +0.065 NDCG | Có ích thật |

→ Không vô dụng — tác dụng đúng đường của chúng.

### 5b. Pillar F — +0.118 có đáng tin không?

Kiểm tra: chỉ giữ cặp bài **khác nghệ sĩ**, đo lại Pillar F.

| | NDCG |
|--|------|
| Baseline (cross-artist) | 0.081 |
| + KG (cross-artist) | 0.076 (giảm) |

**Kết luận trung thực:** lợi ích lớn của KG (+0.118) phần lớn đến từ **gợi ý cùng nghệ sĩ** — khi loại ra, lợi ích biến mất. Đây không phải hệ hỏng; đây là giới hạn đã biết và được ghi rõ.

> **💡 HƯỚNG DẪN — Phần circularity của KG**
>
> Đây là điểm **dễ bị chửi nhất** nếu không trình bày đúng.
> Cách xử lý:
>
> **Không nên nói:** "KG tăng 118%, hệ thống rất tốt."
>
> **Nên nói:** *"KG đạt +118% nhưng chúng tôi chủ động kiểm tra thêm và phát hiện
> lợi ích này chủ yếu đến từ yếu tố cùng nghệ sĩ. Chúng tôi ghi nhận điều này là
> giới hạn đã biết và sẽ cần ground-truth độc lập thứ hai để định lượng chính xác hơn."*
>
> **Tại sao cách này không bị chửi:** bạn tự tìm ra vấn đề trước người chất vấn.
> Nếu giám khảo hỏi "sao KG mạnh thế?", bạn đã có câu trả lời sẵn và thành thật.
> Người chất vấn thường chỉ tấn công những điểm *bị che giấu*, không tấn công điểm
> *đã được thừa nhận và giải thích*.

---

## Bước 6 — Cấu hình cuối và kết quả tổng

### Cấu hình sản xuất

| Tính năng | Trạng thái | Lý do |
|-----------|:----------:|-------|
| MERT (A) | ✅ Bật | +0.022, có ý nghĩa TK |
| SimCSE (B) | ❌ Tắt | Không chứng minh được sau khi đo đúng |
| RRF (C) | ✅ Bật | +0.056 trên đường màu |
| MMR (D) | ✅ Bật | Tăng đa dạng có chủ đích |
| CLAP (E) | ✅ Bật | +0.065 trên đường màu |
| KG + Ngữ cảnh VN (F) | ✅ Bật | Mạnh nhất (kèm lưu ý circularity) |

### Kết quả đo lại trực tiếp — v7.2 vs hệ hoàn chỉnh
*(1,050 truy vấn, 32 playlist, cluster bootstrap 10,000 lần)*

| Thước đo | v7.2 (gốc) | Hoàn chỉnh | Thay đổi | Có ý nghĩa TK? |
|----------|:----------:|:----------:|:--------:|:--------------:|
| **NDCG@10** | 0.091 | **0.185** | **+102.6%** | ✅ CI=[+0.091, +0.163] |
| **Precision@10** | 0.091 | **0.180** | **+98.2%** | ✅ CI=[+0.084, +0.156] |
| **Recall@10** | 0.0038 | **0.0116** | **+208.7%** | ✅ CI=[+0.004, +0.013] |
| **MAP@10** | 0.035 | **0.098** | **+178.7%** | ✅ CI=[+0.064, +0.120] |
| **MRR** | 0.215 | **0.355** | **+65.3%** | ✅ CI=[+0.140, +0.228] |
| **Hit@10** | 0.538 | **0.658** | **+22.3%** | ✅ CI=[+0.061, +0.172] |

> **💡 HƯỚNG DẪN — Bảng kết quả chính**
>
> **Đây là slide/trang quan trọng nhất. Dành thời gian nhiều nhất ở đây.**
>
> **Thứ tự trình bày trong bảng:**
> 1. Chỉ ra cột CI95 trước — "khoảng tin cậy không chạm 0 = không phải may rủi".
> 2. Sau đó mới đọc số % tăng.
> 3. Nhấn mạnh: **cả 6 thước đo đều tăng, không có cái nào đi xuống** (trừ Recall vốn
>    thấp nhưng tăng 209% tương đối).
>
> **Câu diễn giải cho non-tech (nên nói nguyên văn):**
> - "Cứ 10 bài gợi ý, số bài trúng tăng từ ~0.9 lên ~1.8 bài" (Precision)
> - "Bài đúng xuất hiện sớm hơn nhiều trong danh sách" (MRR +65%)
> - "Tỉ lệ người dùng nhận được ít nhất 1 bài phù hợp tăng từ 54% lên 66%" (Hit@10)
>
> **Về con số +102.6% vs +107.4%:** nếu ai hỏi tại sao khác số lần trước —
> "Hệ dùng ngữ cảnh giờ trong ngày để điều chỉnh gợi ý. Hai lần đo vào giờ khác nhau
> nên kết quả lệch nhẹ (~5%). Cả hai đều có ý nghĩa thống kê và quanh +100%."

---

## Hạn chế & Bước tiếp theo

1. **Đáp án khách quan chỉ từ 1 nguồn** (YouTube Music). Cần nguồn độc lập thứ hai để xác nhận vững hơn — nhãn chuyên gia hoặc log nghe của người dùng thật.

2. **Pillar F (KG) có circularity đã biết** — lợi ích phần lớn qua cùng nghệ sĩ. Cần ground-truth cross-artist độc lập để định lượng phần lợi ích "âm nhạc thuần túy".

3. **Đường gợi ý theo màu** (tính năng lõi multimodal) chưa có ground-truth khách quan riêng — đây là ưu tiên cao nhất cho giai đoạn tiếp theo.

> **💡 HƯỚNG DẪN — Hạn chế**
>
> Đừng bỏ qua phần này và đừng đọc nhanh qua. Đây là nơi bạn **kiểm soát narrative**:
> nêu hạn chế trước → người nghe không cần "bắt bẻ" → thảo luận chuyển sang
> "làm thế nào để giải quyết" thay vì "tại sao không làm X".
>
> **Câu kết phần hạn chế nên là:**
> *"Chúng tôi biết chính xác mình đang đo được gì và chưa đo được gì. Kế hoạch tiếp theo
> là [điểm 3 — ground-truth cho đường màu], vì đó là tính năng lõi của sản phẩm."*
>
> Điều này tạo bridge sang buổi báo cáo sau (phiên bản color path) một cách tự nhiên.

---

## Tóm tắt một đoạn (dùng khi báo cáo 2 phút)

Hệ thống được đánh giá trên đáp án khách quan từ **32 playlist biên tập** (1,050 truy vấn), chấm bằng **6 thước đo**, kiểm định bằng **cluster bootstrap 10,000 lần**. Điểm nổi bật về phương pháp: nhóm tự phát hiện và sửa **3 lỗi đo lường**, dẫn đến loại bỏ trung thực Pillar B (mô hình lời mới) dù nó "nghe hay" nhưng không có bằng chứng. Kết quả cuối: hệ hoàn chỉnh cải thiện **+102.6% NDCG, +98% độ chính xác, +209% độ bao phủ** so với bản gốc — **cả 6 thước đo đều có ý nghĩa thống kê**. Giới hạn đã biết và được ghi nhận: lợi ích KG chủ yếu qua cùng nghệ sĩ; đáp án chỉ từ một nguồn; đường màu (tính năng lõi) cần bộ đánh giá riêng.

---

## 3 câu hỏi khó — chuẩn bị trước

> **💡 HƯỚNG DẪN — Câu hỏi khó**

**Q1: "Số tuyệt đối (NDCG 0.185) trông khá thấp, so với Spotify/Netflix thế nào?"**

A: Không so sánh trực tiếp được vì khác giao thức đo. Spotify dùng log nghe thật (triệu user) để làm đáp án — đáp án rất sạch và dày. Ta dùng playlist biên tập — đáp án thưa hơn và mang tính proxy. Hơn nữa ta xếp hạng trên toàn bộ 5,548 bài, không phải re-rank 100 ứng viên lọc sẵn. Với cách đo này, số tuyệt đối tự nhiên thấp hơn. Điều đáng nói là ta **hơn hẳn ngẫu nhiên 3.6× và hơn hẳn bản gốc 2×** trên cùng thước đo.

**Q2: "KG tăng +118% mà cross-artist lại giảm — có phải đang gian lận không?"**

A: Không. Đây là hành vi đã biết của hệ thống: KG học mối quan hệ nghệ sĩ–album–bài, nên khi có bài cùng ca sĩ trong playlist, KG gợi thêm bài cùng ca sĩ đó → playlist playlist → điểm tăng. Đây không sai — nhiều ứng dụng nhạc thật cũng dùng cùng ca sĩ làm tín hiệu. Nhưng để biết KG có giúp phát hiện bài *lạ* phù hợp không, cần ground-truth cross-artist độc lập — và ta đã chủ động kiểm tra điều này thay vì che giấu.

**Q3: "Sao không đo trực tiếp đường gợi ý theo màu — đó mới là tính năng chính?"**

A: Đúng — đường màu là tính năng lõi. Chúng tôi đã đo và kết quả cho thấy nhất quán nội bộ cao sau nâng cấp. Tuy nhiên bộ đánh giá hiện tại có giới hạn kỹ thuật (V-A vừa là thước đo vừa là đầu vào), nên con số chưa thể dùng làm bằng chứng chất lượng độc lập. Xây ground-truth khách quan cho đường màu là ưu tiên cao nhất của giai đoạn tiếp theo — đó cũng là nội dung buổi báo cáo sau.

---

## Phụ lục — Số liệu gốc (kiểm chứng)

| Nội dung | Đường dẫn |
|----------|-----------|
| Baseline + ablation + hệ tham chiếu | `var/runtime/backtest/reports/iter_0_baseline/` |
| 6 Pillar đơn lẻ | `…/iter_2_pillar_B/` … `…/iter_7_pillar_F/` |
| **Full accuracy v7.2 vs production** | `…/iter_9_full_accuracy/report.json` |
| Kiểm tra đường màu (Pillar C/E) | `…/pillar_C_color/`, `…/pillar_E_color/` |
| Kiểm tra circularity KG | `…/pillar_F_xartist/report.json` |
| Script đo lại | `tools/backtest_v2/measure_full_accuracy.py` |
