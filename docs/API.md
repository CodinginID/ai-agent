# API Documentation

Base URL: `https://your-domain.com` (or `http://localhost:8000` for local dev)

---

## Authentication

The API uses two authentication methods:

### 1. Admin Token (Bearer)

Set via `ADMIN_TOKEN` environment variable. Used by TUI clients, dashboards, and server-to-server communication.

```
Authorization: Bearer <ADMIN_TOKEN>
```

### 2. Session Token (Bearer)

Obtained via the TUI login flow or Google OAuth. Used by end-user clients (browser, Telegram).

```
Authorization: Bearer <SESSION_TOKEN>
```

---

## Rate Limits

| Endpoint Group          | Limit           |
|-------------------------|-----------------|
| `/auth/*`               | 5 requests/min  |
| `/chat/send`            | 20 requests/min |
| `/admin/*`              | 30 requests/min |

When rate limited, the server returns `429 Too Many Requests`.

---

## Error Responses

All errors use a consistent format:

```json
{
  "detail": "Error description"
}
```

| Status Code | Description                          |
|-------------|--------------------------------------|
| 400         | Bad Request — invalid input/params   |
| 401         | Unauthorized — missing/invalid token |
| 403         | Forbidden                            |
| 404         | Not Found                            |
| 409         | Conflict — resource already exists   |
| 410         | Gone — resource expired/deleted      |
| 422         | Unprocessable Entity (workflow)      |
| 429         | Too Many Requests (rate limit)       |
| 500         | Internal Server Error                |
| 502         | Bad Gateway (OAuth token exchange)   |
| 503         | Service Unavailable (missing config) |

---

## SSE (Server-Sent Events) Format

Streaming endpoints (`/chat/send`, `/skills/{id}/run`, `/admin/dispatch-test`) return SSE with this format:

```
event: <event_type>
data: <JSON payload>

```

Final event:

```
event: done
data: {}

```

---

## WebSocket

The `/ws/worker` endpoint uses WebSocket for worker (TUI) connections.

```
ws://host:port/ws/worker?session=<SESSION_TOKEN>
```

Worker message types:

| Type        | Description                                |
|-------------|--------------------------------------------|
| `heartbeat` | Keep-alive ping                            |
| `capabilities` | Advertise installed CLI binaries (agents) |
| `job_chunk` | Output chunk from a running job            |
| `job_done`  | Job completed with summary                 |
| `job_error` | Job failed with error message              |

---

## Routers

---

### Auth

All auth endpoints are public (no auth required) unless noted.

#### `GET /auth/login`

Display the login landing page with a Google OAuth button.

- **Auth:** None (public)
- **Response:** HTML page

#### `GET /auth/google/login`

Redirect to Google OAuth consent screen.

- **Auth:** None (public)
- **Query Params:** `tui_code` (optional) — pair code from TUI login flow
- **Response:** 302 Redirect to Google

```bash
# Example: start the TUI login flow
curl -X POST http://localhost:8000/auth/tui/start
```

#### `GET /auth/google/callback`

Handle Google OAuth callback. Creates or updates user in the database.

- **Auth:** None (public)
- **Query Params:** `code`, `state` (required), `error` (on failure)
- **Response:** HTML page (login success/failure)

#### `POST /auth/tui/start`

Generate a new TUI pair code for terminal login.

- **Auth:** None (public)
- **Request Body:** Empty
- **Response:** JSON

```json
{
  "code": "AI-XXXXXX",
  "login_url": "https://your-domain.com/auth/tui-login?code=AI-XXXXXX",
  "expires_in_sec": 900
}
```

#### `GET /auth/tui-login`

Display the browser page where user clicks "Login with Google" to complete TUI pairing.

- **Auth:** None (public)
- **Query Params:** `code` (required)
- **Response:** HTML page

#### `POST /auth/tui/poll`

Poll for session token after Google login.

- **Auth:** None (public)
- **Request Body:**

```json
{
  "code": "AI-XXXXXX"
}
```

- **Response (200 — paired):**

```json
{
  "status": "paired",
  "session_token": "eyJhbGciOiJIUzI1NiJ9..."
}
```

- **Response (202 — pending):**

```json
{
  "status": "pending"
}
```

#### `GET /auth/me`

Validate session token and return user info.

- **Auth:** Bearer session token (required)
- **Response:** JSON

```json
{
  "user_id": "uuid-here",
  "email": "user@example.com",
  "display_name": "John Doe"
}
```

#### `POST /auth/tui/logout`

Revoke the current session.

- **Auth:** Bearer session token (required)
- **Request Body:** Empty
- **Response:** JSON

```json
{
  "revoked": true
}
```

#### `GET /auth/me/agents`

List agent configurations (Codex, Claude, GLM) for the authenticated user.

- **Auth:** Bearer session token (required)
- **Response:** JSON

```json
{
  "agents": [
    {
      "agent_id": "codex",
      "enabled": true,
      "role": "engineer",
      "model": "gpt-4o",
      "installed_on_workers": 2
    }
  ]
}
```

#### `PUT /auth/me/agents/{agent_id}`

Update agent configuration.

- **Auth:** Bearer session token (required)
- **Path Params:** `agent_id` (one of: `codex`, `claude`, `glm`)
- **Request Body:**

```json
{
  "enabled": true,
  "role": "engineer",
  "model": "gpt-4o"
}
```

- **Response:** JSON

```json
{
  "agent_id": "codex",
  "enabled": true,
  "role": "engineer",
  "model": "gpt-4o"
}
```

#### `GET /auth/me/devices`

List all devices that have connected as workers for the authenticated user.

- **Auth:** Bearer session token (required)
- **Response:** JSON

```json
{
  "devices": [
    {
      "device_id": "uuid",
      "name": "laptop-01",
      "status": "online",
      "last_seen_at": "2026-08-06T10:30:00Z",
      "created_at": "2026-07-01T08:00:00Z"
    }
  ]
}
```

#### `GET /auth/me/devices/{device_id}/agents`

List agent integrations detected on a specific device.

- **Auth:** Bearer session token (required)
- **Path Params:** `device_id`
- **Response:** JSON

```json
{
  "device_id": "uuid",
  "device_name": "laptop-01",
  "agents": [
    {
      "agent_id": "codex",
      "display_name": "OpenAI Codex",
      "provider": "openai",
      "installed": true,
      "enabled": false,
      "ready": false,
      "status": "installed",
      "version": "1.2.3",
      "executable": "/usr/local/bin/codex",
      "last_probe_at": "2026-08-06T10:30:00Z"
    }
  ]
}
```

#### `POST /auth/telegram/pair-init`

Request a Telegram pair code for linking a Telegram account.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "bot_username": "my_bot"
}
```

- **Response:** JSON

```json
{
  "code": "TG-XXXXXX",
  "deep_link": "https://t.me/my_bot?start=TG-XXXXXX",
  "bot_username": "my_bot",
  "expires_in_sec": 900
}
```

#### `POST /auth/telegram/pair-complete`

Complete Telegram pairing after user clicks deep link. Used by the Telegram adapter.

- **Auth:** Bearer admin token (required)
- **Request Body:**

```json
{
  "code": "TG-XXXXXX",
  "telegram_user_id": 123456789,
  "username": "johndoe",
  "first_name": "John"
}
```

- **Response:** JSON

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe"
}
```

#### `GET /auth/telegram/user/{telegram_user_id}`

Resolve a Telegram user ID to the core user. Used by the Telegram adapter.

- **Auth:** Bearer admin token (required)
- **Path Params:** `telegram_user_id` (integer)
- **Response:** JSON

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe"
}
```

---

### Admin

All admin endpoints require `Authorization: Bearer <ADMIN_TOKEN>`. If `ADMIN_TOKEN` is not configured, all admin endpoints return `503 Service Unavailable`.

#### `GET /admin/status`

Get server status overview.

- **Auth:** Bearer admin token (required)
- **Response:** JSON

```json
{
  "mode": "webhook",
  "user_count": 42,
  "version": "0.1.0"
}
```

#### `GET /admin/users`

List all registered users with their Telegram accounts.

- **Auth:** Bearer admin token (required)
- **Response:** JSON

```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "John Doe",
      "telegram_accounts": [
        {
          "telegram_user_id": 123456789,
          "username": "johndoe",
          "first_name": "John"
        }
      ],
      "created_at": "2026-07-01T08:00:00Z"
    }
  ]
}
```

#### `POST /admin/logout/{email}`

Remove all sessions and device links for a user (force logout).

- **Auth:** Bearer admin token (required)
- **Path Params:** `email` (string)
- **Response:** JSON

```json
{
  "email": "user@example.com",
  "removed_telegram": 1,
  "removed_devices": 2
}
```

#### `POST /admin/dispatch-test`

Test endpoint: dispatch a job to a user's worker and stream events via SSE.

- **Auth:** Bearer admin token (required)
- **Request Body:**

```json
{
  "user_id": "uuid-here",
  "agent": "echo",
  "prompt": "hello"
}
```

- **Response:** `text/event-stream`

#### `GET /admin/audit`

Get recent audit events (chat sends and agent dispatches).

- **Auth:** Bearer admin token (required)
- **Query Params:**
  - `n` (integer, default 50, max 500) — number of events
  - `user_id` (string, optional) — filter by user
- **Response:** JSON

```json
{
  "events": [
    {
      "id": "uuid",
      "event_type": "chat_send",
      "user_id": "uuid",
      "prompt": "hello",
      "status": "started",
      "created_at": "2026-08-06T10:30:00Z"
    }
  ],
  "count": 50
}
```

#### `GET /admin/jobs/{job_id}`

Inspect a persistent job's state (stored in Redis hash).

- **Auth:** Bearer admin token (required)
- **Path Params:** `job_id` (string)
- **Response:** JSON

```json
{
  "job_id": "job-uuid",
  "user_id": "uuid",
  "worker_id": "worker-uuid",
  "agent": "codex",
  "prompt": "...",
  "status": "running",
  "created_at": "2026-08-06T10:30:00Z"
}
```

---

### Chat

Chat endpoints support two auth modes:

1. **Admin token** with `as_email` in the body — admin sends messages on behalf of any user.
2. **Session token** — user sends messages as themselves.

Chat responses are streamed via Server-Sent Events (SSE).

#### `POST /chat/send`

Send a message and receive a streaming SSE response.

- **Auth:** Bearer admin token or session token (required)
- **Request Body:**

```json
{
  "text": "What is the current memory usage?",
  "as_email": "user@example.com"
}
```

- **Response:** `text/event-stream`

SSE event types:

| Event     | Description                                        |
|-----------|----------------------------------------------------|
| `thinking`| Bot is processing the message                      |
| `action_started` | An action is being executed                   |
| `text_chunk` | Streaming text chunk from AI response           |
| `action_result` | Result of an executed action                   |
| `final` | Final response from the AI                           |
| `error` | Error message                                        |
| `done` | Stream complete                                      |

```
event: thinking
data: {"message":"Thinking..."}

event: text_chunk
data: {"text":"The current memory usage is..."}

event: final
data: {"message":"Final summary here."}

event: done
data: {}
```

#### `POST /chat/approve`

Approve a pending action plan. Streams SSE events.

- **Auth:** Bearer admin token or session token (required)
- **Request Body:**

```json
{
  "plan_id": "plan-uuid",
  "as_email": "user@example.com"
}
```

- **Response:** `text/event-stream`

#### `POST /chat/reject`

Reject a pending action plan.

- **Auth:** Bearer admin token or session token (required)
- **Request Body:**

```json
{
  "plan_id": "plan-uuid",
  "as_email": "user@example.com"
}
```

- **Response:** JSON

```json
{
  "ok": true
}
```

---

### Context

All context endpoints require `Authorization: Bearer <SESSION_TOKEN>`.

#### `POST /context/remember`

Save a free-form note to the user's context memory.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "text": "We decided to use PostgreSQL for the database layer"
}
```

- **Response:** JSON (note object)

```json
{
  "id": "uuid",
  "text": "We decided to use PostgreSQL...",
  "created_at": "2026-08-06T10:30:00Z"
}
```

#### `POST /context/decision`

Record a project decision in context memory.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "text": "Use gRPC for inter-service communication"
}
```

- **Response:** JSON (decision object)

```json
{
  "id": "uuid",
  "text": "Use gRPC for inter-service communication",
  "created_at": "2026-08-06T10:30:00Z"
}
```

#### `GET /context/tasks`

List all tasks in the user's context memory.

- **Auth:** Bearer session token (required)
- **Response:** JSON array

```json
[
  {
    "id": "uuid",
    "text": "Fix the authentication bug",
    "status": "open",
    "created_at": "2026-08-06T10:30:00Z"
  }
]
```

#### `POST /context/tasks`

Add a new task to context memory.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "text": "Write unit tests for the auth module"
}
```

- **Response:** JSON (task object)

```json
{
  "id": "uuid",
  "text": "Write unit tests for the auth module",
  "status": "open",
  "created_at": "2026-08-06T10:30:00Z"
}
```

#### `POST /context/tasks/{task_id}/done`

Mark a task as completed.

- **Auth:** Bearer session token (required)
- **Path Params:** `task_id` (string)
- **Response:** JSON (task object with updated status)

```json
{
  "id": "uuid",
  "text": "Write unit tests for the auth module",
  "status": "done",
  "completed_at": "2026-08-06T11:00:00Z"
}
```

#### `GET /context`

Get full context summary including notes, decisions, and open tasks.

- **Auth:** Bearer session token (required)
- **Response:** JSON

```json
{
  "summary": "Full context summary text...",
  "open_tasks": [
    { "id": "uuid", "text": "...", "status": "open" }
  ],
  "decisions": [
    { "id": "uuid", "text": "...", "created_at": "..." }
  ],
  "notes": [
    { "id": "uuid", "text": "...", "created_at": "..." }
  ]
}
```

---

### Provider

The AI provider configuration endpoints allow per-user model selection.

All provider endpoints require `Authorization: Bearer <SESSION_TOKEN>`.

#### `GET /provider`

Get the user's current AI provider and model configuration.

- **Auth:** Bearer session token (required)
- **Response:** JSON

```json
{
  "provider": "ollama",
  "model": "qwen2.5:7b",
  "is_default": true
}
```

#### `POST /provider`

Set the user's AI provider and model.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "provider": "ollama",
  "model": "qwen2.5:14b"
}
```

- **Response:** JSON

```json
{
  "ok": true
}
```

---

### Skills

All skill endpoints require `Authorization: Bearer <SESSION_TOKEN>`. Skills are scoped by `project_id`.

#### `GET /skills`

List all skills in a project.

- **Auth:** Bearer session token (required)
- **Query Params:** `project_id` (string, required)
- **Response:** JSON

```json
{
  "skills": [
    {
      "id": "uuid",
      "project_id": "proj-uuid",
      "name": "deploy_backend",
      "description": "Deploy the backend service to production",
      "definition": {
        "steps": ["build", "test", "deploy"]
      },
      "created_at": "2026-08-06T10:30:00Z",
      "updated_at": "2026-08-06T10:30:00Z"
    }
  ]
}
```

#### `POST /skills`

Create a new skill in a project.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "project_id": "proj-uuid",
  "definition": {
    "steps": ["lint", "test", "build", "deploy"]
  }
}
```

- **Response:** JSON (created skill)
- **Status:** 201 Created

#### `GET /skills/{skill_id}`

Get a single skill by ID.

- **Auth:** Bearer session token (required)
- **Path Params:** `skill_id` (string)
- **Response:** JSON (skill object)

#### `PUT /skills/{skill_id}`

Update an existing skill's definition.

- **Auth:** Bearer session token (required)
- **Path Params:** `skill_id` (string)
- **Request Body:**

```json
{
  "definition": {
    "steps": ["lint", "test", "build"]
  }
}
```

- **Response:** JSON (updated skill)

#### `DELETE /skills/{skill_id}`

Delete a skill.

- **Auth:** Bearer session token (required)
- **Path Params:** `skill_id` (string)
- **Response:** JSON

```json
{
  "deleted": true
}
```

#### `POST /skills/validate`

Dry-run validation of a skill definition without saving.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "definition": {
    "steps": ["lint", "test", "build"]
  }
}
```

- **Response:** JSON

```json
{
  "valid": true,
  "normalized": {
    "name": "skill_name",
    "description": "Skill description",
    "steps": ["lint", "test", "build"]
  }
}
```

#### `POST /skills/{skill_id}/run`

Execute a skill. Streams events via SSE.

- **Auth:** Bearer session token (required)
- **Path Params:** `skill_id` (string)
- **Request Body:**

```json
{
  "prompt": "Deploy the backend to staging"
}
```

- **Response:** `text/event-stream`

SSE event types:

| Event | Description                                |
|-------|--------------------------------------------|
| `skill_started` | Skill execution started           |
| `step_*`      | Individual step execution        |
| `skill_completed` | Skill finished successfully   |
| `skill_failed`  | Skill execution failed         |
| `done`          | Stream complete                |

---

### Tasks

Task endpoints support both admin token and session token auth (same as chat).

#### `GET /tasks/`

Get the task board — recent task events and latest state per task.

- **Auth:** Bearer admin token or session token (required)
- **Query Params:**
  - `limit` (integer, default 100) — max events to return
- **Response:** JSON

```json
{
  "tasks": [
    {
      "id": "uuid",
      "task_id": "task-uuid",
      "role": "engineer",
      "status": "done",
      "message": "Fixed the bug",
      "issue_number": "42",
      "issue_url": "https://github.com/org/repo/issues/42"
    }
  ],
  "events": [
    {
      "id": "uuid",
      "ts": "2026-08-06T10:30:00Z",
      "task_id": "task-uuid",
      "role": "engineer",
      "status": "step_done",
      "message": "All steps completed",
      "issue_number": "42",
      "issue_url": "https://github.com/org/repo/issues/42"
    }
  ]
}
```

#### `POST /tasks/run`

Run an orchestrator task — PM decomposes the request, creates a GitHub issue, dispatches agents, and closes the issue on success.

- **Auth:** Bearer admin token or session token (required)
- **Request Body:**

```json
{
  "request": "Refactor the auth module to use JWT",
  "context": "The current auth uses session cookies and is in app/adapters/telegram_info.py",
  "as_email": "user@example.com"
}
```

- **Response:** JSON

```json
{
  "ok": true,
  "issue_number": 42,
  "issue_url": "https://github.com/org/repo/issues/42",
  "closed": true,
  "note": "Task completed successfully",
  "summary": "Auth module refactored to use JWT tokens",
  "outcomes": [
    {
      "order": 1,
      "description": "Plan: architect creates implementation plan",
      "role": "architect",
      "ok": true,
      "detail": "Plan created with 3 steps"
    },
    {
      "order": 2,
      "description": "Implement: engineer writes the code",
      "role": "engineer",
      "ok": true,
      "detail": "3 files modified"
    },
    {
      "order": 3,
      "description": "Review: reviewer validates the changes",
      "role": "reviewer",
      "ok": true,
      "detail": "All checks passed"
    }
  ]
}
```

---

### Workflow

All workflow endpoints require `Authorization: Bearer <SESSION_TOKEN>`.

#### `POST /workflow/plan`

Generate an implementation plan using the architect agent.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "goal": "Implement a rate limiter for the API"
}
```

- **Response:** JSON (plan object)

```json
{
  "plan_id": "uuid",
  "goal": "Implement a rate limiter for the API",
  "steps": [
    {
      "id": "step-1",
      "description": "Design rate limiter interface",
      "agent": "architect"
    },
    {
      "id": "step-2",
      "description": "Implement rate limiter",
      "agent": "engineer"
    },
    {
      "id": "step-3",
      "description": "Review implementation",
      "agent": "reviewer"
    }
  ],
  "created_at": "2026-08-06T10:30:00Z"
}
```

#### `POST /workflow/implement`

Execute the plan: engineer implements, reviewer reviews, loop until approved.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "plan_id": "plan-uuid"
}
```

- **Response:** JSON

```json
{
  "stage": "completed",
  "revisions": 2,
  "approved": true,
  "patch": {
    "files": [
      {
        "path": "app/adapters/rate_limiter.py",
        "action": "created"
      }
    ]
  },
  "verdict": {
    "approved": true,
    "comments": [],
    "score": 9
  }
}
```

#### `POST /workflow/review_last`

Re-run the review on the latest patch of a plan.

- **Auth:** Bearer session token (required)
- **Request Body:**

```json
{
  "plan_id": "plan-uuid"
}
```

- **Response:** JSON (verdict object)

```json
{
  "approved": true,
  "comments": [],
  "score": 9
}
```

---

### Worker WebSocket

#### `WebSocket /ws/worker`

WebSocket endpoint for workers (TUI) to connect and receive agent jobs.

- **Auth:** `?session=<SESSION_TOKEN>` query parameter
- **Connection:** `ws://host:port/ws/worker?session=<token>`

**Server-to-worker messages:**

| Type       | Description                             |
|------------|-----------------------------------------|
| `registered` | Acknowledgment with worker_id and user_id |
| `job`      | Job to execute (`job_id`, `agent`, `prompt`, `model`, `extra`) |
| `error`    | Error message                             |

**Worker-to-server messages:**

| Type           | Description                             |
|----------------|-----------------------------------------|
| `heartbeat`    | Keep-alive                              |
| `capabilities` | Advertise installed agents              |
| `job_chunk`    | Output chunk (`job_id`, `text`)         |
| `job_done`     | Job completed (`job_id`, `summary`)     |
| `job_error`    | Job failed (`job_id`, `message`)        |

```python
# Example worker connection
import websockets
import json

async with websockets.connect("ws://host:port/ws/worker?session=YOUR_TOKEN") as ws:
    msg = await ws.recv()
    data = json.loads(msg)
    print(f"Connected: worker_id={data['worker_id']}")

    # Advertise capabilities
    await ws.send(json.dumps({
        "type": "capabilities",
        "agents": {
            "codex": {"installed": True, "path": "/usr/local/bin/codex"}
        }
    }))

    # Listen for jobs
    async for raw in ws:
        event = json.loads(raw)
        if event["type"] == "job":
            # Execute the job...
            await ws.send(json.dumps({
                "type": "job_done",
                "job_id": event["job_id"],
                "summary": "Done!"
            }))
```

---

### Health

#### `GET /health`

Aggregated health check with dependency probes (Redis, Ollama, Database).

- **Auth:** None (public)
- **Response:** JSON

```json
{
  "status": "ok",
  "version": "abc1234",
  "dependencies": {
    "redis": "ok",
    "ollama": "ok",
    "database": "ok"
  },
  "details": {
    "models_loaded": 3,
    "migration_head": "0004_add_users",
    "queue_depth": 0,
    "workers_registered": 2
  }
}
```

---

### Metrics

#### `GET /metrics`

Prometheus-compatible metrics endpoint.

- **Auth:** None (public)
- **Response:** `text/plain` (Prometheus exposition format)

```
# HELP octopus_active_workers Number of currently in-flight requests.
# TYPE octopus_active_workers gauge
octopus_active_workers 2

# HELP octopus_request_total Total number of HTTP requests.
# TYPE octopus_request_total counter
octopus_request_total{method="GET",path="health"} 150
octopus_request_total{method="POST",path="chat_send"} 42
```

---

### Dashboard

#### `GET /dashboard`

Serve the self-contained read-only web dashboard (HTML).

- **Auth:** None (public) — admin token entered in-browser via localStorage
- **Response:** `text/html`

The dashboard displays:
- Health status and version
- Dependency status (Redis, Ollama, Database)
- Active tasks with issue links
- Event timeline

---

## CORS

The API supports Cross-Origin Resource Sharing. Allowed origins are configured via the `CORS_ALLOWED_ORIGINS` environment variable.

```
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
```

---

## OpenAPI / Swagger

Interactive API documentation is available at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`
