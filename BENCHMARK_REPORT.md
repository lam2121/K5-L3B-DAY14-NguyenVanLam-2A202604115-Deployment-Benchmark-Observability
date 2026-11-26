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

### 4.1 Screenshot & Quan sát Grafana (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`) — [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** — [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Đọc số liệu từ Dashboard Grafana (`screenshots/grafana-dashboard.png`) & Trả lời Exercise 7.4:**
- **Các chỉ số Golden Signals quan sát được:** Traffic `18.0 req/s` (đỉnh trước đó `~60 req/s`), Error rate `0.71%`, Latency `p95 = 295.20 ms` (trên đồ thị lúc tải cao `p95` lên `~700–1000 ms`, `p99` nhảy lên `~1.8–1.9 s` trong khi `p50` và `avg` giữ quanh `~200–300 ms`), In-flight `6`, Instances `2`, LLM cost (1h) `$0.5254`.
- **Khoảng cách giữa `avg` và `p95`/`p99`:** Cho thấy hiện tượng **tail latency** — phần lớn request chạy rất nhanh (~200ms) nên kéo `avg` xuống thấp, nhưng ~3% request chậm (~1.7s) làm `p99` (và `p95` khi tải dồn) tăng vọt gấp nhiều lần `avg`.
- **Phân tải giữa 2 instance:** Nginx cân bằng tải theo round-robin (`resolve` DNS mỗi 10s), chia traffic cho 2 container agent (`agent-2`, `agent-3`) chạy song song.
- **Vì sao `input tokens/s` > `output tokens/s`:** Ở `v2` (RAG), prompt gửi vào LLM ghép thêm `SYSTEM_PROMPT` + context tài liệu truy xuất từ knowledge base + câu hỏi, nên độ dài đầu vào lớn hơn nhiều so với câu trả lời ngắn gọn ở đầu ra (ví dụ trong trace `78da703`: `74` input tokens vs `37` output tokens).
- **Vì sao `curl http://localhost:8080/metrics` bị chặn (404):** Trong `nginx/nginx.conf`, Nginx chủ động chặn endpoint `/metrics` từ bên ngoài để tránh lộ số liệu vận hành ra public; chỉ Prometheus trong mạng Docker nội bộ `obs_net` mới scrape trực tiếp `/metrics` từ các container `agent:8000`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (xác nhận `FIRING` trong [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)) | ~1 phút | **Error rate** (`Golden Signals`) & **Requests/s theo status code** (`503` tăng mạnh) |
| B | `MOCK_SLOW_RATE=0.3` | *(Chưa chạy riêng; đã chạy đủ A, C, D, E)* | — | **Latency `/ask` — p50 / p95 / p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (xác nhận `FIRING` trong [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)) | ~2 phút | **LLM cost (1h)** & **cost USD/giờ** |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~1 phút | **Instances** (giảm số instance `up`) |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** (kiểm tra `/api/v1/alerts` trả về `[]`) | Không firing | **Retrieval hit ratio** mất / **Tokens/s** giảm / bảng **agent_info** chuyển sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng (Prometheus) chỉ đo được máy có sống, lỗi HTTP `5xx`, latency hay chi phí — **không biết câu trả lời có đúng hay không**. Khi agent bị tụt từ `v2` (RAG) về `v1` (mất retrieval), latency thậm chí nhanh hơn và cost giảm xuống, nên mọi panel Golden Signals vẫn xanh. Để phát hiện sớm sự cố chất lượng trong production, cần:
1. Chạy **Eval tự động trên golden dataset (`run_eval.py`) như Quality Gate trong CI/CD** trước mỗi lần deploy (chặn merge bằng exit code `1` nếu accuracy tụt hoặc có regression).
2. Theo dõi các **metric chất lượng/domain riêng** (như `retrieval_hit_ratio`, tỉ lệ câu trả lời fallback, điểm LLM-as-judge trên mẫu traffic thật và feedback 👍/👎 của người dùng).
3. Nếu xảy ra lỗi 504 ở Nginx do agent bị treo/pause, metric trên chính agent sẽ không đếm được vì request timeout ở tầng proxy — cần giám sát thêm **access log/metrics từ Nginx hoặc synthetic probe từ bên ngoài**.

### 4.3 Debug bằng trace

- **Trace chậm (`screenshots/jaeger-slow-trace.png`):**
  - `trace_id`: `78da70371b27a28e68844e29feed14e7` (Jaeger hiển thị `78da703`)
  - Tổng thời gian: `1716.7 ms` (`1.7s` trên Jaeger)
  - Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1692.0 ms`, `98.6%` tổng thời gian; bước `agent.retrieve_context` chỉ mất `20.4 ms`, `retrieval.documents = 1`, Input `74` tokens / Output `37` tokens)
  - Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:44:45.537926+00:00", "level": "INFO", "service": "observable-agent", "instance": "3d3d1a43d912", "event": "llm_call", "trace_id": "78da70371b27a28e68844e29feed14e7", "span_id": "3715af8a61a1b495", "request_id": "bc1835e1ab94", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1692.0}
{"ts": "2026-11-26T09:44:45.539563+00:00", "level": "INFO", "service": "observable-agent", "instance": "3d3d1a43d912", "event": "http_request", "trace_id": "78da70371b27a28e68844e29feed14e7", "span_id": "3715af8a61a1b495", "request_id": "bc1835e1ab94", "method": "POST", "route": "/ask", "status": 200, "ms": 1716.7}
```

- **Trace lỗi (`screenshots/jaeger-error-trace.png`):**
  - Trace `57f3604` (`POST /ask`, status `503`, tổng thời gian `123 ms`), span `agent.run` (`120 ms`) ghi nhận event `exception`: `exception.type = utils.mock_llm.LLMError`, `exception.message = Upstream LLM error: 503 Service Unavailable (mock)`.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 (`scale_1`) | 64.98 (Aggregated) / 59.04 (`/ask`) | 200 | 680 (Aggregated) / 780 (`/ask`) | 1700 | 796 / 7737 (10.29%) |
| 3 (`scale_3`) | 64.31 (Aggregated) / 58.46 (`/ask`) | 200 | 680 (Aggregated) / 800 (`/ask`) | 1700 | 62 / 7659 (0.81%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **p95 và RPS gần như không đổi** khi scale từ 1 lên 3 instance (`p50 = 200 ms`, `p95 = 680 ms` aggregated / `780–800 ms` trên `/ask`, RPS `~64–65 req/s`). Nguyên nhân là nút thắt không nằm ở CPU của agent mà nằm ở **thời gian chờ upstream LLM** (`MOCK_LATENCY_MS=120ms` + jitter + `MOCK_SLOW_RATE=0.03` gây tail latency ~`1.7s`) kết hợp với `wait_time` cố định phía Locust client (100 user). Vì FastAPI chạy bất đồng bộ (`async/await`), 1 instance vẫn xử lý song song tốt các chờ đợi I/O ở mức tải này.
- **Lợi ích rõ nhất khi scale lên 3 instance là độ ổn định (Failures):** Ở `scale_1` (`scale_1_failures.csv`), có `727` lỗi `502 Bad Gateway` ở 13 giây đầu khi 1 container mới khởi động/Nginx làm mới DNS và `69` lỗi `503` từ mock LLM (`10.29%` tổng cộng); khi scale lên `3` instance (`scale_3_failures.csv`), lỗi `502` biến mất hoàn toàn (`0` lỗi `/health`), tổng failure giảm xuống chỉ còn `62 / 7659` (`0.81%`, khớp đúng tỉ lệ lỗi giả lập `MOCK_ERROR_RATE=0.01`).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Không đánh giá hiệu năng bằng `average`:** 3%–10% request chậm làm `p95`/`p99` tăng vọt lên `~1.7s` trong khi `avg` chỉ nhích nhẹ; đặt SLO theo `p95`/`p99` mới phản ánh đúng trải nghiệm người dùng.
  2. **Chất lượng phải đo bằng Eval + Quality Gate (`cost / câu đúng`):** Observability hạ tầng (Grafana/Prometheus) luôn xanh khi tụt về `v1`, chỉ có benchmark trên golden dataset mới bắt được regression và chứng minh hiệu quả chi phí thực (`v2` rẻ hơn ~11 lần trên mỗi câu đúng).
  3. **Liên kết 3 trụ cột Metrics → Traces → Logs:** Grafana/Prometheus báo có spike hoặc lỗi → Jaeger chỉ ra chính xác span gây chậm (`chat mock-llm-small` chiếm `98.6%`) hoặc exception → `trace_id` giúp grep thẳng tới dòng log JSON chi tiết.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert sau:**
  - **Metrics/Alerts ở tầng Nginx & Synthetic probe:** theo dõi lỗi `502`/`504` ở load balancer (vì agent bị treo không tự ghi nhận được lỗi timeout ở Nginx) và synthetic health check từ bên ngoài.
  - **Metrics/Alerts về chất lượng RAG & Redis:** `retrieval_hit_ratio` thấp bất thường, tỉ lệ fallback response, độ trễ truy vấn Redis (`redis_command_duration_seconds`), và tỉ lệ request bị chặn bởi Rate Limit (`429`) / Cost Guard (`402`).
  - **Alert về chi phí theo ngày (`DAILY_BUDGET_USD`) và chất lượng định kỳ (LLM-as-judge / user feedback).**
