# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong mã nguồn (`develop/app.py:17-18`):** Khai báo trực tiếp `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Khi push lên GitHub, bí mật bị lộ ngay lập tức và nằm vĩnh viễn trong lịch sử git.
2. **Không quản lý cấu hình theo môi trường (`develop/app.py:21-22`):** Cố định `DEBUG = True`, `MAX_TOKENS = 500` trong code thay vì đọc từ biến môi trường (vi phạm nguyên tắc *Config in Environment* của 12-Factor App).
3. **Dùng `print()` để log và làm lộ secret (`develop/app.py:33-38`):** Dùng `print(f"[DEBUG] ...")` không có timestamp/level/cấu trúc JSON để hệ thống thu thập log phân tích; đặc biệt dòng 34 còn `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm rò rỉ API key ra stdout/log.
4. **Thiếu endpoint kiểm tra sức khỏe (`/health`, `/ready`) (`develop/app.py:42-43`):** Không có liveness/readiness probe, khiến cloud platform hoặc load balancer không biết khi nào container bị treo để tự restart hay ngừng đẩy traffic vào.
5. **Bind `localhost`, cố định `port=8000` và bật `reload=True` (`develop/app.py:49-54`):**
   - `host="localhost"` chỉ lắng nghe loopback bên trong máy/container nên traffic từ ngoài container không vào được (production cần `0.0.0.0`).
   - `port=8000` cố định không đọc biến `PORT` do cloud platform (Railway/Render/Cloud Run) cấp.
   - `reload=True` bật chế độ tự nạp lại code của dev trong production gây tốn tài nguyên và không ổn định.
6. **Không xử lý Graceful Shutdown (`SIGTERM`) & thiếu kiểm tra đầu vào chặt chẽ (`develop/app.py:31`):** App không có `lifespan` hay handler dọn dẹp khi nhận `SIGTERM`, dễ cắt ngang request đang xử lý khi deploy/restart; ngoài ra endpoint nhận `question: str` qua query parameter không ràng buộc độ dài/validation rõ ràng.

---

### Exercise 1.2: Kết quả chạy thực tế (`develop` & `production`)

**1. Gọi bản `develop` (`POST /ask?question=Hello`):**
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:50:48 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

**2. Gọi bản `production` (`GET /health` và `POST /ask`):**
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:59:45 GMT
server: uvicorn
content-length: 130
content-type: application/json

{"status":"ok","uptime_seconds":29.1,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:59:46.043589+00:00"}
```
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 07:59:57 GMT
server: uvicorn
content-length: 144
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

---

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`01-localhost-vs-production/develop/`) | Production (`01-localhost-vs-production/production/`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trong `develop/app.py:17-22`. | Tách vào `production/config.py:14-47` dùng `os.getenv(...)` với `Settings().validate()` fail-fast nếu `ENVIRONMENT=production` thiếu `AGENT_API_KEY`, kèm `.env.example`. | Đổi cấu hình linh hoạt giữa dev/staging/prod mà không sửa code; không bao giờ lộ API key lên Git. |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` (`develop/app.py:49-54`). | `host=settings.host` (`0.0.0.0`), `port=settings.port` (đọc `PORT`), `reload=settings.debug` (`production/app.py:194-199`, `config.py:17-19`). | Trong Docker/cloud, `localhost` chặn kết nối từ bên ngoài container; platform tự cấp `PORT`; `reload=True` gây rò rỉ/chậm ở production. |
| **Health Check** | Không có `/health` hay `/ready` (`develop/app.py:42-43`). | Có `GET /health` trả uptime/version/env (`production/app.py:135-149`) và `GET /ready` trả 503 khi chưa sẵn sàng (`production/app.py:152-161`). | Orchestrator (Docker, Railway, Render, Kubernetes) dùng `/health` để tự restart khi treo và `/ready` để biết lúc nào được đẩy traffic. |
| **Logging** | Dùng `print()` dạng text tự do và log lộ cả `OPENAI_API_KEY` (`develop/app.py:33-38`). | Dùng `logging.basicConfig` định dạng JSON + `json.dumps(...)`, chỉ log độ dài câu hỏi/trả lời và `client_ip`, tuyệt đối không log secret (`production/app.py:28-32, 111-122`). | Structured JSON log giúp công cụ tập trung log (Loki, Datadog, CloudWatch) lọc, tìm kiếm và cảnh báo tự động mà không làm rò rỉ thông tin nhạy cảm. |
| **Graceful Shutdown** | Không xử lý vòng đời shutdown; tắt đột ngột khi dừng tiến trình. | Có `@asynccontextmanager lifespan` hạ cờ `is_ready = False` khi tắt (`production/app.py:39-68`) và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (`production/app.py:180-189`). | Khi deploy bản mới hoặc scale down, container có thời gian hoàn thành các request đang chạy dở trước khi thoát, tránh lỗi 502/504 cho người dùng. |
| **CORS & Validation** | Không cấu hình CORS, `/ask` đọc query param không validate rỗng. | Thêm `CORSMiddleware` giới hạn `allowed_origins` (`production/app.py:77-82`) và kiểm tra `question` rỗng trả `422` (`production/app.py:107-108`). | Kiểm soát domain frontend được phép gọi API và trả mã lỗi HTTP chuẩn khi client gửi sai payload. |

> **Ví dụ đối chiếu cụ thể anti-pattern đã được sửa:**  
> Trong `develop/app.py:17`, API key bị hardcode (`OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`) và in thẳng ra console ở dòng 34. Sang bản production, `config.py:27` chuyển sang `os.getenv("OPENAI_API_KEY", "")`, dòng 42–43 ép kiểm tra `AGENT_API_KEY` khi chạy production, và `production/app.py:111-122` chỉ log metadata (`question_length`, `response_length`) dưới dạng JSON.

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (`02-docker/develop/Dockerfile:8`) — đây là image Python đầy đủ (full distribution, nặng ~1 GB).
2. **Working directory:** `/app` (`02-docker/develop/Dockerfile:11`) — mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối từ `/app`.
3. **Tại sao `COPY requirements.txt` trước `COPY app.py`:** Để tận dụng **Docker layer cache**. Docker cache từng layer theo thứ tự từ trên xuống dưới; khi mã nguồn (`app.py`) thay đổi nhưng `requirements.txt` giữ nguyên, Docker sẽ dùng lại cache của bước `RUN pip install --no-cache-dir -r requirements.txt` mà không phải tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào:**
   - `CMD` cung cấp lệnh và tham số mặc định khi container khởi động, nhưng **dễ dàng bị ghi đè** nếu truyền lệnh mới ở cuối `docker run <image> <cmd>`.
   - `ENTRYPOINT` cố định tiến trình/lệnh chính của container; các tham số truyền thêm trong `docker run` hoặc `CMD` sẽ được gắn nối vào sau `ENTRYPOINT` (chỉ bị ghi đè khi dùng cờ `--entrypoint`).

---

### Exercise 2.2: Build và chạy container bản `develop`

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:05:30 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & so sánh kích thước image

**Phân tích `02-docker/production/Dockerfile`:**
- **Stage 1 (`builder` từ `python:3.11-slim`):** Cài trình biên dịch và thư viện hệ thống (`gcc`, `libpq-dev`), rồi chạy `pip install --no-cache-dir --user -r requirements.txt` để cài các gói Python vào `/root/.local`.
- **Stage 2 (`runtime` từ `python:3.11-slim`):** Tạo user non-root (`appuser`), chỉ `COPY --from=builder /root/.local /home/appuser/.local`, copy mã nguồn (`main.py`, `utils/mock_llm.py`), khai báo `HEALTHCHECK` gọi `/health` và chạy `uvicorn` dưới quyền `appuser`.
- **Tại sao image nhỏ hơn:**
  1. Dùng base `python:3.11-slim` gọn nhẹ thay vì `python:3.11` full.
  2. Toàn bộ build tools (`gcc`, `libpq-dev`, cache build) bị bỏ lại ở stage `builder`, không đi theo sang stage `runtime` cuối cùng.

**Kích thước đo được bằng `docker images | grep my-agent`:**
```text
my-agent:advanced                   bb15bad7fc5a        240MB         57.4MB
my-agent:develop                    c3ca6d2e7a3b       1.67GB          426MB
```
- **Develop (`my-agent:develop`):** `1.67 GB` (~`1,670 MB`; content size `426 MB`)
- **Production (`my-agent:advanced`):** `240 MB` (content size `57.4 MB`)
- **Chênh lệch (giảm):** giảm **`1,430 MB` (~`85.6%`)** so với bản develop (và đạt yêu cầu `< 500 MB`).

---

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc và giao tiếp các service (trên Docker bridge network `internal`):**

```text
Client (localhost:80)
       │
       ▼
  ┌─────────┐   HTTP (proxy_pass http://agent_backend -> agent:8000)   ┌───────────────┐
  │  nginx  │ ───────────────────────────────────────────────────────▶ │     agent     │
  └─────────┘                                                          │  (port 8000)  │
                                                                       └──────┬─┬──────┘
                                                REDIS_URL=redis://redis:6379/0│ │QDRANT_URL=http://qdrant:6333
                                                                              ▼ ▼
                                                                     ┌────────┐ ┌────────┐
                                                                     │ redis  │ │ qdrant │
                                                                     │ :6379  │ │ :6333  │
                                                                     └────────┘ └────────┘
```

- **Các service được khởi động:** `nginx` (reverse proxy, expose cổng `80`/`443`), `agent` (FastAPI app, chỉ mở nội bộ cổng `8000`, `depends_on` `redis` và `qdrant` ở trạng thái `service_healthy`), `redis` (`redis:7-alpine`, lưu volume `redis_data`), và `qdrant` (`qdrant/qdrant:v1.9.0`, lưu volume `qdrant_data`).
- **Cách giao tiếp:** Các container dùng Docker DNS nội bộ qua tên service (`agent`, `redis`, `qdrant`) trong mạng `internal`; client bên ngoài chỉ đi qua `nginx` ở cổng 80.

**Kết quả kiểm tra stack (`docker compose -p k5-day14-docker ps` & test qua Nginx):**
```text
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     35 seconds ago   Up 23 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     35 seconds ago   Up 23 seconds             0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    37 seconds ago   Up 34 seconds (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     37 seconds ago   Up 34 seconds (healthy)   6379/tcp
```
```http
HTTP/1.1 200 OK
Server: nginx
Date: Thu, 26 Nov 2026 08:09:36 GMT
Content-Type: application/json
Content-Length: 96
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":32.9,"version":"2.0.0","timestamp":"2026-11-26T08:09:36.409957"}
```
```http
HTTP/1.1 200 OK
Server: nginx
Date: Thu, 26 Nov 2026 08:09:55 GMT
Content-Type: application/json
Content-Length: 103
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 lên Cloud

- **Nền tảng chính:** Render (Web Service Docker từ `06-lab-complete/` + Render Key Value Redis)
- **Public URL:** https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com
- **Kiểm tra tự động:** `python3 check_production_ready.py --public-url "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com"` → `Public URL: GET .../health → 200` (`✅`), cùng 4 lệnh `curl` ở CP6 (`/health` → 200, `/ready` → 200, `/ask` không key → 401, `/ask` có key → 200).
- **Ảnh chụp:** [dashboard.png](screenshots/dashboard.png), [running.png](screenshots/running.png), [test.png](screenshots/test.png)

### So sánh `railway.toml` và `render.yaml` (`03-cloud-deployment/` & `06-lab-complete/`)

| Tiêu chí | `railway.toml` | `render.yaml` | Vì sao khác nhau? |
|---|---|---|---|
| **Định dạng & phạm vi** | File **TOML** cấu hình cho **1 service** (`[build]`, `[deploy]`). | File **YAML** dạng Blueprint (IaC) khai báo **cả stack nhiều service** (`services:` gồm web service + Redis add-on). | Railway quản lý từng service trong project riêng lẻ trên Dashboard/CLI; Render cho phép định nghĩa toàn bộ hạ tầng (app + Redis) trong một Blueprint duy nhất. |
| **Build & Runtime** | Dùng `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"` trong bản mẫu), tự nhận `CMD` của Dockerfile. | Khai báo rõ `type: web`, `runtime: docker` (hoặc `python` với `buildCommand` + `startCommand`), `region`, `plan`. | Render Blueprint yêu cầu mô tả đầy đủ thông số máy chủ (`plan`, `region`) để cấp phát tài nguyên tự động. |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`. | `healthCheckPath: /health`, `autoDeploy: true`. | Cả hai đều dùng endpoint `/health` để xác định service sống hay cần restart / giữ traffic khi zero-downtime deploy. |
| **Biến môi trường & Secret** | Không khai báo secret trong file TOML; đặt qua `railway variables set` hoặc Dashboard. | Khai báo danh sách `envVars:` trực tiếp trong YAML, với secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên Dashboard, không commit vào Git). | Render Blueprint cần biết trước schema các biến môi trường cần tạo khi khởi tạo stack từ Git repo, đồng thời tránh hardcode secret vào YAML. |

### Exercise 3.3: Pipeline CI/CD trên Google Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên nhánh `main` đi qua **4 bước tuần tự (`waitFor`)**:
1. **Test (`test`):** Dùng container `python:3.11-slim` cài `requirements.txt` + `pytest` và chạy toàn bộ test (`pytest tests/ -v --tb=short`); nếu test fail thì dừng pipeline ngay.
2. **Build (`build`):** Dùng `cloud-builders/docker` build image gắn 2 tag (`$COMMIT_SHA` và `latest`), có tận dụng `--cache-from` từ image `latest` để tăng tốc build.
3. **Push (`push`):** Đẩy cả 2 tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Dùng `gcloud run deploy` cập nhật service `ai-agent` trên Cloud Run (`asia-southeast1`, `min-instances=1`, `max-instances=10`, `512Mi` RAM, `1` CPU), cấu hình cấu trúc scaling/liveness (`/health`)/startup (`/ready`) tương ứng như trong `service.yaml`, và inject secret (`OPENAI_API_KEY`, `AGENT_API_KEY`) an toàn từ **Google Secret Manager** thay vì hardcode.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **Kiểm tra API key ở đâu:** Hàm `verify_api_key` (`develop/app.py:39-54`) đọc header `X-API-Key` thông qua `APIKeyHeader(name="X-API-Key", auto_error=False)` và được gắn làm dependency `Depends(verify_api_key)` trên `POST /ask` (`develop/app.py:67-71`), so sánh với `API_KEY = os.getenv("AGENT_API_KEY", ...)`.
- **Điều gì xảy ra nếu thiếu hoặc sai key:** Thiếu header trả `401 Unauthorized` (`Missing API key...`), sai key trả `403 Forbidden` (`Invalid API key.`).
- **Cách rotate key:** Thay đổi giá trị biến môi trường `AGENT_API_KEY` trên nền tảng/config và reload/restart service; trong hệ thống production thực tế nên hỗ trợ danh sách nhiều key hợp lệ (ví dụ active key + previous key trong khoảng chuyển tiếp) để không ngắt request của client đang dùng key cũ khi xoay vòng.

**Kết quả test thực tế (không có key → 401; có key → 200):**
```http
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:17:41 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:17:51 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT Flow (`POST /auth/token` → `POST /ask`):** Client gửi `username`/`password` (`student` / `demo123`) tới `POST /auth/token` để nhận `access_token` (JWT ký bằng HMAC-SHA256, thời hạn 60 phút, chứa thông tin `sub` và `role`). Khi gọi `POST /ask` kèm header `Authorization: Bearer <TOKEN_REDACTED>`, dependency `verify_token` giải mã và xác minh chữ ký/hạn dùng của token mà không cần tra database mỗi request.
- **Thuật toán & cấu hình Rate Limiting (`rate_limiter.py:17-87`):**
  - Thuật toán: **Sliding Window Counter** (dùng `collections.deque` lưu danh sách timestamp của từng `user_id`; mỗi lần gọi xóa các timestamp cũ hơn `now - 60s` rồi kiểm tra độ dài).
  - Giới hạn: `student` (role `user`) tối đa **10 requests / 60 giây** (`rate_limiter_user`), còn `admin` tối đa **100 requests / 60 giây** (`rate_limiter_admin`). Có thể cấu hình bypass hoặc nới hạn mức cho role `admin` dựa vào `user["role"]` đã giải mã từ JWT (`production/app.py:141`).
  - Trong môi trường multi-worker / nhiều container cần chuyển state từ RAM sang **Redis** (như Part 6 dùng Redis Sorted Set `ZREMRANGEBYSCORE` + `ZCARD` + `ZADD`).

**Kết quả test JWT (200 OK) và vòng lặp vượt ngưỡng Rate Limit (429 Too Many Requests):**
*(Token đã được che trước khi lưu)*
```bash
# Lấy token tại POST /auth/token với {"username": "student", "password": "demo123"}
# Gọi với Authorization: Bearer <REDACTED_JWT>
```
```http
=== Test 200 với JWT ===
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:22:10 GMT
server: uvicorn
content-length: 215
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```
```http
--- Request 9 (request thứ 10 trong cửa sổ 60s) ---
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:22:30 GMT
server: uvicorn
content-length: 180
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 9","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000181}}

--- Request 10 (vượt 10 req/phút -> bị chặn 429) ---
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:22:30 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795681410
retry-after: 41
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":41}}
```

---

### Exercise 4.4: Cost Guard (`04-api-gateway/production/cost_guard.py`)

- **Tại sao cần cả Rate Limit và Cost Guard:** Rate limit chỉ giới hạn **tốc độ gọi** (số request/phút), nhưng mỗi prompt dài có thể tốn gấp hàng chục lần token so với prompt ngắn. Ngược lại, một user gọi đều đặn dưới ngưỡng rate limit vẫn có thể đốt hết tiền API theo ngày/tháng. Vì vậy cần **Cost Guard** để giới hạn **tổng chi phí theo token**.
- **Cách triển khai trong `cost_guard.py:20-110`:**
  1. **Trước khi gọi LLM (`check_budget(user_id)`):** Kiểm tra tổng chi phí trong ngày ở 2 tầng: global budget (`global_daily_budget_usd = $10.0`, vượt → `503`) và per-user budget (`daily_budget_usd = $1.0`, vượt → **`402 Payment Required`**); ghi log cảnh báo khi đạt `80%` ngưỡng (`warn_at_pct`).
  2. **Sau khi gọi LLM (`record_usage(user_id, input_tokens, output_tokens)`):** Tính chi phí từ số token vào/ra (`$0.00015 / 1K input tokens`, `$0.0006 / 1K output tokens`) rồi cộng dồn vào usage theo ngày (`YYYY-MM-DD`) của user và tổng global.
  3. **Khi đưa lên production (nhiều worker/instance):** Chuyển bộ đếm `budget:{user_id}:{YYYY-MM}` hoặc `budget:daily:{YYYY-MM-DD}` sang **Redis** dùng `INCRBYFLOAT` + `EXPIRE` để mọi instance dùng chung một ngân sách chính xác.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health Checks (`/health`, `/ready`) và Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - `GET /health` (**Liveness probe**) trả lời *"Process còn sống không?"*: luôn trả `200` khi tiến trình HTTP server còn chạy (không phụ thuộc Redis/DB bên ngoài). Nếu fail, platform sẽ **restart** container.
  - `GET /ready` (**Readiness probe**) trả lời *"Instance đã sẵn sàng nhận traffic chưa?"*: kiểm tra cờ sẵn sàng (startup xong, chưa vào giai đoạn shutdown) và kết nối dependency (Redis/DB). Trả `503` khi chưa sẵn sàng để load balancer **tạm ngưng chuyển request mới** tới instance đó mà không restart container một cách vô ích.
- **Cơ chế Graceful Shutdown khi nhận `SIGTERM`:**
  1. Orchestrator gửi `SIGTERM` (signal 15) khi dừng/deploy container mới.
  2. Uvicorn bắt `SIGTERM`, kích hoạt phần shutdown của `lifespan` (`_is_ready = False`) để ngừng nhận request mới.
  3. Server chờ các request đang chạy dở (`_in_flight_requests`) hoàn thành (tối đa `timeout_graceful_shutdown=30`s) rồi mới thoát sạch với exit code 0.

**Kết quả test thực tế (`05-scaling-reliability/develop/app.py`):**
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:30:10 GMT
server: uvicorn
content-length: 186
content-type: application/json

{"status":"ok","uptime_seconds":22.0,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:30:11.111773+00:00","checks":{"memory":{"status":"ok","used_percent":13.2}}}
```
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:30:17 GMT
server: uvicorn
content-length: 37
content-type: application/json

{"ready":true,"in_flight_requests":1}
```
```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-26 08:30:30,105 INFO 🔄 Graceful shutdown initiated...
2026-11-26 08:30:30,106 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3917]
2026-11-26 08:30:30,107 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

---

### Exercise 5.3, 5.4 & 5.5: Stateless Design, Nginx Load Balancing (3 instances) & Redis

- **Vì sao state trong RAM bị hỏng khi chạy nhiều instance:** Mỗi container/worker có vùng nhớ riêng (`_memory_store`). Khi Nginx cân bằng tải theo round-robin, request 1 rơi vào `agent-1` nhưng request 2 rơi vào `agent-2` sẽ không thấy lịch sử hội thoại cũ. Lưu `session:{session_id}` vào **Redis** dùng chung giúp mọi instance đều đọc/ghi cùng một state (`Stateless`).
- **Kết quả chạy 3 agent instances (`docker compose -p k5-day14-scaling up -d --build --scale agent=3`) + `python3 test_stateless.py`:**
  - Cả 3 instance (`agent-1`, `agent-2`, `agent-3`), `nginx` và `redis` đều lên khỏe mạnh.
  - 5 request trong cùng `Session ID: 25827bb1-c1b6-45bc-a18c-cb82c23ffa80` được Nginx phân tán luân phiên tới cả 3 instance (`instance-f71022`, `instance-16cde5`, `instance-dbb091`).
  - Khi gọi `GET /chat/{session_id}/history`, Redis trả về đầy đủ **10 messages** (5 lượt hỏi/đáp), chứng minh không mất dữ liệu dù request đi qua nhiều instance khác nhau.

```text
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     25 seconds ago   Up 12 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     25 seconds ago   Up 12 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     25 seconds ago   Up 12 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     24 seconds ago   Up 11 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     25 seconds ago   Up 23 seconds (healthy)   6379/tcp
```
```text
Session ID: 25827bb1-c1b6-45bc-a18c-cb82c23ffa80
Request 1: [instance-f71022] -> What is Docker?
Request 2: [instance-16cde5] -> Why do we need containers?
Request 3: [instance-dbb091] -> What is Kubernetes?
Request 4: [instance-f71022] -> How does load balancing work?
Request 5: [instance-16cde5] -> What is Redis used for?

Total requests: 5
Instances used: {'instance-f71022', 'instance-dbb091', 'instance-16cde5'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

---

## Part 6: Final Project (`06-lab-complete/`)

Chạy `python3 check_production_ready.py` (chế độ đầy đủ trên WSL2 Ubuntu có Docker `29.5.3`, build image `69 MB`, Docker `docker stop` tắt êm `exit code 0, 0.7s`, 17 dòng log JSON hợp lệ):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

1. **Part 6 (`06-lab-complete/`):**
   - **Hỏi / Yêu cầu AI:** Hướng dẫn hoàn thiện các `TODO` trong bộ khung `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và xử lý lỗi cài `pydantic==2.9.0` trên Ubuntu Python 3.14 trong venv local.
   - **Nhận được:** Mã nguồn triển khai từng module theo 12 tiêu chí (Redis Sorted Set sliding window cho rate limit, `INCRBYFLOAT` theo ngày/tháng cho cost guard, `hmac.compare_digest` cho API key, `JsonFormatter` cho log, multi-stage `python:3.11-slim` + non-root `appuser` + `exec uvicorn`).
   - **Tự kiểm tra & xác nhận:** Đã chạy `python3 check_production_ready.py` trực tiếp trên WSL2 Ubuntu với Docker Desktop, tự kiểm chứng đủ 43/43 checks (`PASS 12/12`, image `69 MB`, `SIGTERM` exit code `0`, `docker stop` `0.7s`).
2. **Part 1–5 (`MISSION_ANSWERS.md`) & Part 7 (`BENCHMARK_REPORT.md`):**
   - **Hỏi / Yêu cầu AI:** Hướng dẫn từng bước lệnh thực hành, kiểm tra nguyên nhân lỗi Docker credential/crash container `production/Dockerfile` của Part 7 (thiếu `ENV PYTHONUSERBASE=/home/agent/.local` khiến `uvicorn` báo `ModuleNotFoundError`), bổ sung knowledge base cho 2 câu `security-02`, `scaling-03` trong `mock_llm.py`, và tổng hợp số liệu báo cáo.
   - **Tự kiểm tra & xác nhận:** Toàn bộ kết quả `curl`, dung lượng image `docker images` (`1.67 GB` vs `240 MB`), output `401/200/429`, log `SIGTERM`, `test_stateless.py`, public URL Render (`https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com`), 9 file JSON `reports/`, CSV `scale_1` & `scale_3`, `trace_id` `78da70371b27a28e68844e29feed14e7` và 7 ảnh trong `screenshots/` đều do tự chạy lệnh và chụp trực tiếp trên máy.
