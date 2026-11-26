# Deployment Information

## Public URL
https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com

## Platform
Render (Web Service — Docker + Render Key Value Redis, Root Directory: `06-lab-complete`)

## Test Commands

### Health Check (`200 OK`)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com/health"
curl -sS "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com/health"
# Expected: {"status":"ok","environment":"production"}
```

### Readiness Check (`200 OK` when Redis connected)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com/ready"
# Expected HTTP code: 200
```

### Authentication Check (`401` without key, `200` with key)
```bash
# Missing X-API-Key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# Valid X-API-Key -> 200
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST "https://k5-l3b-day14-nguyenvanlam-2a202604115.onrender.com/ask" \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set (on Render Dashboard)
- `PORT` (injected by Render)
- `REDIS_URL` (Render Key Value internal URL)
- `AGENT_API_KEY` (secret, configured on Render)
- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
