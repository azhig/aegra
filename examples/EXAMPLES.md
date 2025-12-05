# Aegra API Examples

This directory contains example scripts for testing Aegra API endpoints, specifically:
1. Creating a run via `POST /threads/{thread_id}/runs`
2. Getting the `run_id` from the response
3. Connecting to streaming via `GET /threads/{thread_id}/runs/{run_id}/stream`

## Available Examples

### 1. **LangGraph SDK Example** ([example.py](example.py))

Uses the official `langgraph-sdk` client (recommended).

**Features:**
- ✅ High-level API (same as LangGraph Platform)
- ✅ Automatic retry and error handling
- ✅ Type-safe with Python types
- ✅ Supports all LangGraph features

**Usage:**
```bash
# Install SDK (if not already installed)
uv add langgraph-sdk

# Set API key
export OPENAI_API_KEY=sk-...

# Run example
python example.py
```

**Output:**
```
event: metadata, data: {'run_id': '...'}
event: values, data: {'messages': [...]}
event: messages-tuple, data: (AIMessage(...), {...})
event: end, data: None
```

---

### 2. **Pure HTTP Example** ([example_http.py](example_http.py))

Uses `httpx` for direct HTTP requests (no SDK required).

**Features:**
- ✅ Shows raw HTTP API structure
- ✅ Useful for understanding API protocol
- ✅ Works with any HTTP client (curl, fetch, etc.)
- ✅ Educational for non-Python clients

**Usage:**
```bash
# Install httpx
uv add httpx

# Set API key
export OPENAI_API_KEY=sk-...

# Run example
python example_http.py
```

**Output:**
```
📤 Creating run...
   URL: http://localhost:8000/threads/example-thread-123/runs
   Thread ID: example-thread-123
   Assistant: agent
   Message: What is the weather in San Francisco?

✅ Run created successfully!
   Run ID: 01234567-89ab-cdef-0123-456789abcdef
   Status: pending

🔌 Connecting to stream...
   URL: http://localhost:8000/threads/example-thread-123/runs/01234567.../stream
   Run ID: 01234567-89ab-cdef-0123-456789abcdef

📡 Streaming events (press Ctrl+C to stop):
--------------------------------------------------------------------------------

🔖 Event: metadata
📦 Data:
{
  "run_id": "01234567-89ab-cdef-0123-456789abcdef"
}
🆔 ID: 01234567-89ab-cdef-0123-456789abcdef_event_0
--------------------------------------------------------------------------------

🔖 Event: values
📦 Data:
{
  "messages": [
    {
      "role": "user",
      "content": "What is the weather in San Francisco?"
    }
  ]
}
...
```

---

### 3. **Curl Example** ([example_curl.sh](example_curl.sh))

Bash script using `curl` for HTTP requests.

**Features:**
- ✅ No Python required
- ✅ Works in any Unix-like environment
- ✅ Great for CI/CD pipelines
- ✅ Easy to adapt for other tools

**Usage:**
```bash
# Set API key
export OPENAI_API_KEY=sk-...

# Make executable (first time only)
chmod +x example_curl.sh

# Run example
./example_curl.sh
```

**Or with custom URL:**
```bash
AEGRA_URL=http://production-server:8000 ./example_curl.sh
```

**Output:**
```
========================================
🚀 Aegra API Example - curl
========================================

Configuration:
  URL: http://localhost:8000
  Thread ID: example-thread-1699999999
  Assistant: agent

📤 Step 1: Creating run...

✅ Run created successfully!
   Run ID: 01234567-89ab-cdef-0123-456789abcdef
   Status: pending

🔌 Step 2: Connecting to stream...
   URL: http://localhost:8000/threads/example-thread-.../runs/.../stream

📡 Streaming events (press Ctrl+C to stop):
--------------------------------------------------------------------------------
event: metadata
data: {"run_id": "..."}
id: ..._event_0

event: values
data: {"messages": [...]}
id: ..._event_1
...
```

---

## API Endpoints Used

### 1. Create Run

**Endpoint:** `POST /threads/{thread_id}/runs`

**Request:**
```json
{
  "assistant_id": "agent",
  "input": {
    "messages": [
      {"role": "user", "content": "Your message here"}
    ]
  },
  "stream_mode": ["values", "messages"]
}
```

**Response:**
```json
{
  "run_id": "01234567-89ab-cdef-0123-456789abcdef",
  "thread_id": "example-thread-123",
  "assistant_id": "agent",
  "status": "pending",
  "created_at": "2025-01-10T12:00:00Z",
  "input": {...},
  "output": null,
  "error_message": null
}
```

**Status Values:**
- `pending` - Run created, waiting to start
- `running` - Currently executing
- `completed` - Successfully finished
- `failed` - Execution failed (see `error_message`)
- `cancelled` - Cancelled by user
- `interrupted` - Human-in-the-loop interrupt

---

### 2. Stream Run Events

**Endpoint:** `GET /threads/{thread_id}/runs/{run_id}/stream`

**Protocol:** Server-Sent Events (SSE)

**Event Format:**
```
event: <event_type>
data: <json_payload>
id: <event_id>

```

**Event Types:**
- `metadata` - Run metadata (first event)
- `values` - State values after node execution
- `messages` - Message chunks (streaming LLM responses)
- `end` - Run completed

**Example:**
```
event: metadata
data: {"run_id": "..."}
id: ..._event_0

event: values
data: {"messages": [{"role": "user", "content": "..."}]}
id: ..._event_1

event: messages
data: {"content": "Hello", "type": "AIMessageChunk"}
id: ..._event_2

event: end
data: {"status": "completed"}
id: ..._event_3
```

**Reconnection:**
Send `Last-Event-ID` header to resume from specific event:
```bash
curl -H "Last-Event-ID: {run_id}_event_5" \
  http://localhost:8000/threads/{thread_id}/runs/{run_id}/stream
```

---

### 3. Get Run Status

**Endpoint:** `GET /threads/{thread_id}/runs/{run_id}`

**Response:**
```json
{
  "run_id": "01234567-89ab-cdef-0123-456789abcdef",
  "thread_id": "example-thread-123",
  "assistant_id": "agent",
  "status": "completed",
  "created_at": "2025-01-10T12:00:00Z",
  "updated_at": "2025-01-10T12:00:15Z",
  "input": {...},
  "output": {
    "messages": [...]
  },
  "error_message": null
}
```

---

## Testing with Redis Integration

### Test Distributed Streaming (Этап 1)

**Scenario:** Multiple API instances streaming same run

```bash
# Terminal 1: Start Aegra with Redis
docker compose up aegra

# Terminal 2: Create run and get run_id
python example_http.py
# Note the run_id from output

# Terminal 3: Connect to stream from different "instance" (same process)
# Simulates horizontal scaling
RUN_ID=<run_id> python -c "
import asyncio, httpx
async def stream():
    async with httpx.AsyncClient() as client:
        async with client.stream('GET', f'http://localhost:8000/threads/example-thread-123/runs/{os.environ[\"RUN_ID\"]}/stream') as r:
            async for line in r.aiter_lines():
                print(line)
asyncio.run(stream())
"
```

**Expected:** Both terminals receive events (Redis PubSub works!)

---

### Test Worker Pattern (Этап 2)

**Scenario:** Workers executing runs from task queue

```bash
# Terminal 1: Start Aegra with workers enabled
ENABLE_WORKERS=true docker compose --profile workers up

# Terminal 2: Check worker logs
docker compose logs -f aegra-worker

# Terminal 3: Create run
python example_http.py

# Expected in worker logs:
# 🚀 Worker worker-abc123 started, waiting for tasks...
# 📦 Processing task run_id=xyz789 worker_id=worker-abc123
# 💓 Heartbeat updated run_id=xyz789
# ✅ Task completed run_id=xyz789

# Terminal 4: Monitor Redis queue
watch -n 1 'docker compose exec redis redis-cli LLEN aegra:tasks'

# Expected: Queue size changes as tasks are enqueued/dequeued
```

---

## Troubleshooting

### "Connection refused"

**Problem:** Aegra not running

**Solution:**
```bash
# Start Aegra
docker compose up aegra

# Or check if running
curl http://localhost:8000/health
```

---

### "Run status: failed"

**Problem:** Agent execution error (likely missing API key)

**Solution:**
```bash
# Set OpenAI API key
export OPENAI_API_KEY=sk-...

# Restart Aegra
docker compose restart aegra

# Check logs
docker compose logs aegra
```

---

### "Stream returns empty"

**Problem:** Run already completed before stream connected

**Solution:**
Use `Last-Event-ID` to replay events:
```bash
curl -H "Last-Event-ID: {run_id}_event_0" \
  http://localhost:8000/threads/{thread_id}/runs/{run_id}/stream
```

Or check run status to see if already finished:
```bash
curl http://localhost:8000/threads/{thread_id}/runs/{run_id}
```

---

### Redis not connected

**Problem:** Redis unavailable

**Check health:**
```bash
curl http://localhost:8000/health | jq '.redis'
```

**Expected:**
- `"connected"` - Redis working
- `"unavailable (fallback to memory)"` - Using in-memory broker

**Solution:**
```bash
# Start Redis
docker compose up redis -d

# Restart Aegra
docker compose restart aegra
```

---

## Environment Variables

### Required

- `OPENAI_API_KEY` - OpenAI API key (for agent execution)

### Optional

- `AEGRA_URL` - Base URL of Aegra API (default: `http://localhost:8000`)
- `REDIS_URL` - Redis connection URL (default: `redis://localhost:6379`)
- `STREAMING_BACKEND` - Broker backend: `redis` or `memory` (default: `redis`)
- `ENABLE_WORKERS` - Use worker pattern: `true` or `false` (default: `false`)

---

## Further Examples

### Custom Stream Modes

```python
# Request specific stream modes
payload = {
    "assistant_id": "agent",
    "input": {...},
    "stream_mode": ["values", "messages", "updates", "debug"]
}
```

### Human-in-the-Loop

```python
# Interrupt before specific nodes
payload = {
    "assistant_id": "agent",
    "input": {...},
    "interrupt_before": ["human_review_node"]
}

# Resume after interrupt
resume_payload = {
    "assistant_id": "agent",
    "command": {"resume": {"approved": True}}
}
```

### Checkpoint Resume

```python
# Resume from specific checkpoint
payload = {
    "assistant_id": "agent",
    "input": {...},
    "checkpoint": {
        "thread_id": "thread-123",
        "checkpoint_ns": "",
        "checkpoint_id": "checkpoint-abc"
    }
}
```

---

## Next Steps

1. **Read API Documentation:** See [Agent Protocol Specification](https://github.com/AI-Agent-Protocol/agent-protocol)
2. **Explore LangGraph:** Learn about graph definitions in `graphs/` directory
3. **Try Custom Graphs:** Modify `aegra.json` to add your own graphs
4. **Monitor with Health Check:** `curl http://localhost:8000/health`
5. **Scale with Workers:** Enable worker pattern for production loads

---

## Resources

- **Aegra Repository:** https://github.com/ibbybuilds/aegra
- **LangGraph Documentation:** https://python.langchain.com/docs/langgraph
- **Agent Protocol:** https://github.com/AI-Agent-Protocol/agent-protocol
- **Redis Integration:** [REDIS_INTEGRATION.md](REDIS_INTEGRATION.md)
