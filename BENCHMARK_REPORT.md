# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ report JSON / CSV / log / screenshot thực tế khi chạy bài lab.

**Họ tên:** Nguyễn Văn Lâm (MSSV: 2A202604115)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows + WSL2 Ubuntu (Docker Desktop 29.5.3)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Với mock LLM (~120–180ms + retrieval ~20ms), 95% request bình thường hoàn thành dưới 500ms; chỉ 3% tail latency (~1.7s) rơi vào p99. |
| Error rate `/ask` | < 2 % | Mock LLM có tỉ lệ lỗi upstream mặc định ~1%, nên ngưỡng < 2% đảm bảo vận hành bình thường đạt SLO và chỉ báo động khi lỗi bất thường. |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu 100% sau sửa KB) | Đảm bảo agent v2 (RAG) trả lời đúng phần lớn kiến thức chuẩn; chặn regression trước khi merge. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.22 | 190.4 | 224.3 | 1710.7 | 0.00% (0/300) | PASS |
| 10 | 37.81 | 190.1 | 220.6 | 1689.3 | 0.00% (0/300) | PASS |
| 50 | 102.99 | 200.8 | 264.4 | 1707.6 | 0.33% (1/300) | PASS |
| 100 | 58.30 | 355.8 | 3037.0 | 3310.4 | 0.67% (2/300) | FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS **không tăng tuyến tính** mãi theo concurrency:
- Từ concurrency `1 → 10 → 50`, RPS tăng mạnh (`4.22 → 37.81 → 102.99 req/s`) nhờ FastAPI bất đồng bộ xử lý song song các thao tác chờ I/O mà p50/p95 hầu như chưa đổi (`~190–264ms`).
- Đến concurrency `100`, một tiến trình agent (1 worker) chạm ngưỡng bão hòa hàng đợi/event loop và kết nối đồng thời, khiến các request phải xếp hàng chờ nhau: **RPS giảm ngược xuống `58.30 req/s`**, p50 tăng lên `355.8 ms` và **p95 vọt lên `3037.0 ms` (vi phạm SLO `< 500 ms`)**.

---

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.6 | 217.6 | 238.6 |
| 0.03 (mặc định) | 249.2 | 230.5 | 1685.7 |
| 0.1 | 322.1 | 1683.5 | 1713.4 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất:** `p99` (và tiếp theo là `p95` khi tỉ lệ request chậm vượt 5%). Khi `MOCK_SLOW_RATE` tăng từ `0 → 0.03`, `avg` chỉ nhích nhẹ từ `191.6 ms` lên `249.2 ms` (`+57.6 ms`), nhưng `p99` nhảy vọt gấp ~7 lần lên **`1685.7 ms`**. Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm), `avg` mới là `322.1 ms` (vẫn dưới ngưỡng 500 ms), nhưng cả **`p95` đã vọt lên `1683.5 ms`** (vi phạm SLO).
- **Lý do không đặt SLO theo average:** Giá trị trung bình bị 90–97% request nhanh kéo xuống nên che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng gặp tail latency. Đặt SLO theo `p95`/`p99` mới bảo vệ được trải nghiệm thực tế của đa số người dùng.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.1 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000404 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040395 | $0.00003627 | $0.00003436 |
| Quality gate | FAIL (exit code 1) | PASS (exit code 0) | PASS (exit code 0) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` giải thích sự khác biệt giữa API key và JWT (token có chữ ký số, thời điểm hết hạn) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` mô tả Kubernetes HPA scale theo CPU, memory hoặc custom metrics vào `KNOWLEDGE_BASE`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v1 không có retrieval nên chỉ đúng `1/23` (`4.3%`), còn v2 (RAG) nhảy vọt lên `21/23` (`91.3%`) trước khi sửa KB và `23/23` (`100%`) sau khi bổ sung tài liệu.
- **Chi phí & Token:** v2 chèn context tìm được vào prompt nên `avg_tokens` tăng gần gấp đôi (`57.1 → 109.1`), làm tổng chi phí tăng từ `$0.000404` lên `$0.000762`; tuy nhiên xét trên **cost / câu trả lời đúng**, v2 (`$0.00003627`) **rẻ hơn ~11.1 lần** so với v1 (`$0.00040395`).
- **Latency:** v2 chậm hơn chút (~`20 ms` cho bước retrieval, `p95 = 221.7 ms` so với `188.4 ms` của v1), hoàn toàn chấp nhận được để đổi lấy độ chính xác tăng vượt bậc.
- **Quality gate trong CI ([.github/workflows/eval.yml](.github/workflows/eval.yml)):** `run_eval.py` kiểm tra `accuracy >= --min-accuracy` và `regressions == 0` so với `--baseline`. Nếu không đạt (ví dụ chạy v1 với `--baseline reports/eval_v2.json`), script thoát với **exit code `1`**, khiến job CI trên Pull Request bị đánh dấu fail và chặn merge tự động.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [ ] Một trace lỗi trong Jaeger (có event `exception`) — [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [ ] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** — [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

*(Chờ kết quả Bước 8)*

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

*(Chờ số liệu từ `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`)*

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
