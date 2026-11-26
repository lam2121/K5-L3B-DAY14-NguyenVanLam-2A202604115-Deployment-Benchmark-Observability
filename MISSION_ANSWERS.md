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

*(Đang chờ kết quả chạy Bước 2)*

---

## Part 3: Cloud Deployment

*(Đang chờ kết quả chạy Bước 6)*

---

## Part 4: API Security

*(Đang chờ kết quả chạy Bước 3)*

---

## Part 5: Scaling & Reliability

*(Đang chờ kết quả chạy Bước 4)*

---

## Part 6: Final Project (`06-lab-complete/`)

*(Đang chờ kết quả chạy `check_production_ready.py` ở Bước 5)*

---

## AI Log

*(Sẽ cập nhật đầy đủ các phần có sử dụng AI hỗ trợ khi hoàn thiện lab)*
