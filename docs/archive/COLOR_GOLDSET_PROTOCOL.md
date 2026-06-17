# Vietnamese V-A Gold-set — Annotation Protocol (audit V17, P0 #2)

Mục đích: tạo bộ nhãn Valence-Arousal do **người Việt** chấm để **validate/calibrate** các nhãn
máy (v4: arousal từ MERT/DEAM, valence từ LLM) — vốn chưa từng đo trên nhạc Việt. Đây là tiền đề
để đánh giá đúng mọi nâng cấp (kể cả encoder swap, vốn đã đo thấy KHÔNG cải thiện trên GT cũ).

## Quy trình
1. Tạo template: `python -m tools.build_color_goldset` → `var/goldset/color_va_goldset_template.csv`
   (208 bài, phân tầng đều theo cảm xúc, đã xáo trộn, KHÔNG kèm nhãn — chấm mù).
2. **≥3 (lý tưởng 5) người Việt** mỗi người copy template thành `var/goldset/ratings/<tên>.csv`
   và điền 2 cột (nghe bài hoặc đọc lời + nghe), **độc lập, không bàn với nhau**.
3. Tổng hợp + validate: `python -m tools.eval_color_goldset`.

## Hai trục (thang 0.0–1.0)
- **rater_valence** — mức độ DỄ CHỊU/tích cực của cảm xúc bài hát:
  `0.0` = rất tiêu cực/buồn/u tối · `0.5` = trung tính · `1.0` = rất tích cực/vui/hân hoan.
- **rater_arousal** — mức độ NĂNG LƯỢNG/kích thích:
  `0.0` = rất nhẹ/tĩnh lặng/ru ngủ · `0.5` = vừa · `1.0` = rất mạnh/sôi động/dồn dập.

> Hai trục ĐỘC LẬP. Ví dụ: ballad buồn = valence thấp + arousal thấp; rock giận dữ = valence thấp +
> arousal cao; pop vui = valence cao + arousal cao; hát ru êm = valence cao + arousal thấp.

## Nguyên tắc chấm
- Chấm **cảm xúc bài hát biểu đạt** (perceived), không phải tâm trạng riêng của bạn lúc nghe.
- Ưu tiên **nghe** bản nhạc; lời (`lyric_preview`) chỉ hỗ trợ.
- Dùng cả dải 0–1, đừng dồn về giữa. Có thể dùng 1 chữ số thập phân (0.0, 0.1, …, 1.0).
- Không tra Google/không bàn với người khác trong lúc chấm.

## Tiêu chí đạt (eval tự tính)
- **Inter-rater ICC(2,k) ≥ 0.75** mỗi trục → nhãn người đáng tin (nếu < 0.5: cần thêm rater /
  làm rõ hướng dẫn). Arousal thường cao hơn valence (valence khó đồng thuận hơn — đúng literature).
- Sau đó: **Pearson r + RMSE** của v4 vs trung bình người = số validation thật cho MERT-arousal &
  LLM-valence. So sánh arousal r ở đây với DEAM CV R²=0.58.

## Dùng kết quả
- Nếu r thấp / RMSE cao → calibrate (isotonic) nhãn máy về thang người, hoặc fine-tune probe.
- Bộ này cũng là **GT bổ sung** để A/B các thay đổi ranking (encoder, σ, query…) trên nhạc Việt thật,
  thay cho GT L2-LLM n=12 (yếu, thiên V-A) hiện tại.
