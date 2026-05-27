# IMPLEMENTATION CHECKLIST — Backtest + Cải thiện hệ thống

**Phạm vi đã chọn:** **C — Đầy đủ (đo + cải thiện)** — toàn bộ 7 phase của
`PLAN_BACKTEST_METRICS.md` + `PLAN_SYSTEM_UPGRADE.md`.

**Cách dùng file này:**
1. Mỗi phiên Claude Code chỉ làm **1 phase**. Làm xong → verify → commit → `/clear` → phase sau.
2. Copy nguyên block prompt của phase đang làm, dán vào Claude Code (đã nhúng guardrails sẵn).
3. Tick `[x]` khi phase **đạt tiêu chí** (không phải khi "code xong").
4. Phần bị chặn (thiếu data/budget): **skip + ghi vào báo cáo Hạn chế**, không chế số.

---

## GUARDRAILS — đã nhúng trong từng prompt, nhắc lại để bạn hiểu vì sao

| Ràng buộc | Chống lỗi |
|---|---|
| "Đọc ĐẦY ĐỦ section plan trước khi code, không code từ trí nhớ" | Sau `/clear` Claude quên chi tiết → code sai spec |
| "Chạy THẬT, dán output thật, KHÔNG số placeholder" | Claude bịa kết quả |
| "Chỉ làm Phase N, không làm quá phạm vi" | Làm lố, dở dang |
| "Bị chặn thì DỪNG + báo, không chế" | Né bằng số giả |
| "Gắn nhãn validity (external/semi/engine-derived) mọi metric" | Mất tính khoa học |

---

## TIẾN ĐỘ TỔNG

- [ ] **Phase 0** — Prerequisites (dọn legacy, refactor weights, skeleton)
- [ ] **Phase 1** — Đo baseline v7.2 (property metrics) → `iter_0_baseline`
- [ ] **Phase 2** — Ground truth ngoài (crawl) + accuracy metrics
- [ ] **Phase 3** — Ablation → xác định thứ tự pillar
- [ ] **Phase 4** — Weight optimization → `iter_1_weight_opt`
- [ ] **Phase 5** — Pillar upgrades (mỗi pillar 1 phiên, thứ tự do Phase 3)
- [ ] **Phase 6** — Final Report

**Chuẩn bị trước (việc của bạn, Claude không tự làm):**
- [ ] Bật Docker DB: `make dev` (Phase 1+ cần DB)
- [ ] Mạng ổn định cho Phase 2 (crawl) + Phase 5 (tải MERT/ViDeBERTa)
- [ ] Xác nhận query DB reality §2 vẫn đúng (5548 songs) trước Phase 1

---

## PHASE 0 — Prerequisites

**Tiêu chí đạt:** `tools/backtest.py` đã xóa; app vẫn import/khởi động OK; `pytest` pass;
`recommend_by_song` đọc weight từ `config.RECO_SONG_WEIGHTS`; skeleton `tools/backtest_v2/` tồn tại.

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §5 (Decommission), §10.1 (refactor weights),
§7.3 (mood_tags check), §13 Phase 0. Code TỪ PLAN, không từ trí nhớ.

Thực hiện ĐÚNG Phase 0, không làm quá:
1. Xóa tools/backtest.py; gỡ BacktestRequest, WeightTestRequest + 3 route backtest
   trong api/system.py (giữ /api/backtest/dataset-stats, sẽ rewire sau).
2. Refactor weight hardcode trong recommend_by_song (core/recommendation_engine.py)
   → config.RECO_SONG_WEIGHTS (cả nhánh has_lyrics và audio-only fallback).
3. Chạy mood_tags discriminativeness check (§7.3), báo kết quả: dùng được hay loại.
4. Tạo skeleton tools/backtest_v2/ (core.py, catalog.py, metrics/, ground_truth/,
   improve/, baselines/, stats.py, reporters/, cli.py) — file rỗng/stub + CLI chạy được.

Verify THẬT và dán output: `python -m pytest test/` + `python -c "import app"`.
Bị chặn thì DỪNG và báo. Xong commit với message rõ ràng.
```

---

## PHASE 1 — Đo baseline (property metrics)

**Tiêu chí đạt:** chạy `python -m tools.backtest_v2 run` ra report THẬT cho 5 system ×
~11 property metric, mỗi số kèm CI 95%; lưu `var/runtime/backtest/reports/iter_0_baseline/`.

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §6 (kiến trúc), §8 (công thức từng metric),
§9 (baselines), §12 (stats), §13 Phase 1. Code TỪ PLAN.
Yêu cầu Docker DB đang chạy (make dev).

Implement ĐÚNG Phase 1, không làm Phase 2:
- catalog.py: wrap MusicRecommender đang chạy, map original_index.
- stats.py: stratified sampler theo mood_quadrant (seed=42, 500 query) + paired
  bootstrap + CI 95%.
- metrics/property.py: ILD_lyrics/audio/va/color, Coverage, Artist Gini,
  MoodCoherence, TempoCoherence, ColorCoherence, Calibration error, symmetry,
  serendipity-proxy — đúng công thức §8.
- metrics/operational.py: Latency p50/p95/p99 (N=200).
- baselines: random, audio_only, lyrics_only, va_only, brightify_v7.2 (locked).
- reporters/: markdown + json, gắn nhãn validity="property" cho nhóm này.

Chạy THẬT: python -m tools.backtest_v2 run --config configs/backtest_v0.yaml
Dán report.md SỐ THẬT. TUYỆT ĐỐI không số placeholder. Bị chặn → DỪNG + báo.
Commit.
```

---

## PHASE 2 — Ground truth ngoài + accuracy

**Tiêu chí đạt:** có `editorial_playlists_v1.json` (báo rõ số playlist qua filter + số track
match); chạy được NDCG@10/Precision/Recall THẬT với nhãn validity="external".

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §7.1 (crawl), §8 Group B (accuracy),
§13 Phase 2. Code TỪ PLAN. Cần mạng + Docker DB.

Implement ĐÚNG Phase 2:
- ground_truth/editorial.py: crawl playlist VN qua ytmusicapi (search filter=playlists
  + get_playlist), fuzzy-match track_name+artist (normalize diacritics) vào catalog 5548.
  Filter: bỏ playlist <10 hit và >70% coverage. Chỉ lưu mapping, không lưu audio.
- metrics/accuracy.py: NDCG@K, Precision@K, Recall@K, MAP@K, MRR, Hit@K (K=5,10,20).

Chạy crawl THẬT, báo: số playlist qua filter + tổng track match. Rồi chạy:
python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1
Dán NDCG@10 THẬT, gắn validity="external". Nếu crawl fail/ít data → DỪNG + báo,
KHÔNG dùng quadrant làm relevance thay thế (tautology). Commit.
```

---

## PHASE 3 — Ablation → thứ tự pillar

**Tiêu chí đạt:** có `signal_importance.json` với ΔNDCG khi drop từng signal; kết luận
thứ tự pillar ưu tiên (mapping §11.2).

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §11.2 (ablation→pillar), §13 Phase 3.
Code TỪ PLAN. Cần editorial GT từ Phase 2.

Implement ĐÚNG Phase 3:
- improve/ablation.py: với mỗi signal trong RECO_SONG_WEIGHTS, set weight=0,
  normalize phần còn lại, chạy backtest, ghi ΔNDCG@10 + ΔILD_lyrics + ΔMoodCoherence.
- Lưu reports/iter_0_baseline/ablation/signal_importance.json.
- va_sanity.py: engine-derived sanity floor, gắn validity="engine-derived".

Chạy THẬT toàn bộ ablation, dán bảng kết quả. Kết luận: signal nào yếu nhất →
đề xuất thứ tự pillar theo bảng mapping §11.2 (lyrics→B, audio→A, va/emotion→E,
diversity→D, retrieval→C). Đây là INPUT quyết định Phase 5. Commit.
```

---

## PHASE 4 — Weight optimization

**Tiêu chí đạt:** chạy optimizer; CHỈ update `config.RECO_SONG_WEIGHTS` nếu CI của delta
NDCG không chứa 0 và dương; lưu `iter_1_weight_opt/` + compare vs iter_0.

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §11.1 (weight opt), §11.3 (iteration
protocol), §13 Phase 4. Code TỪ PLAN.

Implement ĐÚNG Phase 4:
- improve/weight_opt.py: scipy SLSQP, objective = maximize NDCG@10 (external),
  constraint ILD_lyrics >= baseline*0.95, ràng buộc Σw=1. Split editorial GT
  80% optimize / 20% validate (chống overfit).
- Chạy optimizer → weight_search/optimal_weights.yaml.

Compare iter_0 vs iter_1 bằng paired bootstrap. CHỈ cập nhật config.RECO_SONG_WEIGHTS
nếu CI delta NDCG không chứa 0 VÀ dương. Nếu không cải thiện → giữ nguyên weights gốc,
ghi rõ "đã gần optimal". Dán số THẬT cả 2 trường hợp. Lưu iter_1_weight_opt/. Commit.
```

---

## PHASE 5 — Pillar upgrades (mỗi pillar = 1 phiên riêng)

> **Thứ tự pillar do Phase 3 quyết định**, không làm theo bảng chữ cái. Pillar E (cần
> annotation $500-1000) và Backlog data → **skip + ghi Hạn chế**. Pillar G (backend) độc lập,
> làm lúc nào cũng được.

**Tiêu chí đạt mỗi pillar:** code + flag enable trong config.py; chạy backtest; pass gate
(NDCG ext không giảm, ILD không giảm >5%, latency p95 không tăng >30%); lưu `iter_N_pillar_X/`.

**Bảng tra section plan cho từng pillar:**
| Pillar | Section | Tải model? |
|---|---|---|
| A — MERT/CLAP audio | PLAN_SYSTEM_UPGRADE §3 | MERT-95M, CLAP (~1GB) |
| B — ViDeBERTa/ViSoBERT | §4 | ViDeBERTa/ViSoBERT |
| C — RRF + rerank | §5 | cross-encoder |
| D — MMR/DPP diversity | §6 | không |
| E — MLP emotion combiner | §7 | **BỊ CHẶN: cần annotation** |
| F — Cold-start KG/weather | §8 | không |
| G — Backend async/Redis | §9 | không |

```
Phase 3 ablation cho thấy [SIGNAL] yếu nhất → làm [PILLAR X].
Đọc ĐẦY ĐỦ docs/PLAN_SYSTEM_UPGRADE.md §[N] (Pillar X). Code TỪ PLAN.

Implement ĐÚNG các bước của Pillar X, thêm flag enable trong config.py (mặc định
giữ behavior cũ để rollback được). Nếu cần tải model → tải vào var/volumes/hf_cache.
Nếu cần migration → tạo trong alembic/versions/ kèm downgrade().

Chạy backtest: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1
Compare iter trước vs iter này (paired bootstrap). GATE: NDCG@10 ext không giảm,
ILD_lyrics không giảm >5%, latency p95 không tăng >30%.
- Pass → giữ, commit, lưu iter_N_pillar_X/.
- Fail → revert flag, ghi lý do vào report, commit phần revert.
Dán số THẬT. Bị chặn (thiếu data/model tải lỗi) → DỪNG + báo.
```

*Lặp prompt trên cho từng pillar theo thứ tự ablation. Tick mỗi pillar:*
- [ ] Pillar ___ (iter_2)
- [ ] Pillar ___ (iter_3)
- [ ] Pillar ___ (iter_4)
- [ ] ... (thêm nếu cần)

---

## PHASE 6 — Final Report

**Tiêu chí đạt:** `var/runtime/backtest/reports/final/REPORT.md` đầy đủ theo template §14,
số lấy từ các `report.json` THẬT, không bịa.

```
Đọc ĐẦY ĐỦ docs/PLAN_BACKTEST_METRICS.md §14 (template báo cáo). Code/viết TỪ PLAN.

Tổng hợp tất cả iter_*/report.json đã có thành reports/final/REPORT.md theo ĐÚNG
template §14, gồm: Executive Summary (v7.2→vX.Y + CI), Phương pháp (metric chọn/loại
+ lý do), Baseline, Ablation, từng Iteration (vấn đề→hành động→kết quả→lý do),
Tổng kết delta + significance, Hạn chế (offline-only, popularity=0, no user...),
Khuyến nghị.

LẤY SỐ THẬT từ report.json, KHÔNG bịa. Mỗi metric gắn nhãn validity. Phần đã skip
(Pillar E, Backlog) ghi vào mục Hạn chế. Cuối cùng: wire lại /api/backtest/* vào
framework mới. Commit.
```

---

## GHI CHÚ KHI BÁO CÁO THẦY

- File nộp chính: `reports/final/REPORT.md` (in PDF).
- Kèm: git log (chứng minh quá trình từng iteration), 2 plan docs (phương pháp luận).
- Điểm mạnh nhấn mạnh: validity labeling (chống tautology), reproducible (seed=42),
  thứ tự pillar có căn cứ ablation (không đoán).
- Thành thật về Hạn chế (offline-only, chưa có user) = điểm cộng, không phải trừ.
