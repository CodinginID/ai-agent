# Octopus Desktop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplikasi desktop chat-first & voice-first (Wails: Go + React/TS) sebagai klien SSE ke gateway Octopus Core, dengan STT Whisper lokal dan TTS Piper lokal ("mode Jarvis").

**Architecture:** Frontend React di webview memetakan event SSE (`thinking`, `approval_required`, `action_result`, …) menjadi kartu visual; backend Go menangani HTTP/SSE ke gateway, keyring, subprocess whisper-cli/piper, dan downloader model. Backend FastAPI hanya ditambah dua endpoint additive: `POST /chat/approve` dan `POST /chat/reject` (satu-satunya jalur approve non-Telegram).

**Tech Stack:** Wails v2, Go 1.24, React 18 + TypeScript + Vite, Vitest + React Testing Library, `github.com/zalando/go-keyring`, whisper.cpp CLI (subprocess), Piper (subprocess), pytest (backend).

**Spec:** `docs/superpowers/specs/2026-07-12-octopus-desktop-design.md`

## Global Constraints

- Branch kerja: `feat/octopus-desktop-app`; commit conventional commits bahasa Indonesia, huruf kecil, tanpa titik akhir, maks 72 char.
- Direktori baru: `octopus-desktop/` (module `github.com/codinginid/octopus-desktop`), didaftarkan di `go.work`.
- Backend Python: HANYA menambah endpoint approve/reject di `app/interfaces/chat.py` + test; tidak mengubah perilaku endpoint lain.
- Semua fungsi Go/TS dengan type lengkap; error dari subprocess/HTTP di-wrap per adapter; TIDAK pakai `shell=True`-style (`exec.Command` dengan args list).
- Prinsip: kegagalan voice/visual tidak boleh mematikan chat teks.
- Default UX: mode Jarvis AKTIF (transkrip auto-send, jawaban final dibacakan).
- Token session di keyring OS (service `octopus-desktop`), bukan file.
- Jalankan `pytest tests/ -v` untuk Python, `go test ./...` untuk Go, `npm test` (Vitest) untuk frontend. Sebelum commit backend Python: `make check` bila tersedia.

---

### Task 1: Endpoint gateway `POST /chat/approve` + `POST /chat/reject`

Konteks: approve saat ini hanya ada sebagai command bot Telegram (`app/handlers/approval.py`) yang meng-consume singleton `pending_plans` (dipakai juga oleh `build_use_case()` via `app/composition.py:_build_pending_plans`). Klien HTTP (TUI/desktop) belum bisa approve. Endpoint baru berjalan di proses gateway yang sama, jadi singleton-nya shared.

**Files:**
- Modify: `app/interfaces/chat.py` (tambah di bawah `chat_send`)
- Test: `tests/interfaces/test_chat_approval.py` (baru)

**Interfaces:**
- Consumes: `app.handlers.approval.pending_plans` (`PendingPlanStore.consume/cancel`), `app.handlers.registry.action_registry`, `app.domain.use_cases._conv_id_to_int`, `_format_sse`, `_resolve_caller`
- Produces: `POST /chat/approve` body `{"plan_id": str, "as_email": str|null}` → SSE stream (`action_started`, `action_result`, `final` | `error`), diakhiri `event: done`. `POST /chat/reject` body sama → JSON `{"ok": bool}`. Dipakai Task 4 (klien Go).

- [ ] **Step 1: Tulis failing test**

```python
# tests/interfaces/test_chat_approval.py
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.interfaces.gateway import app as gateway_app
import app.interfaces.chat as chat_mod


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        chat_mod, "_resolve_caller", lambda auth: ("user@example.com", "session")
    )
    return TestClient(gateway_app)


def _pending(intent: str = "docker_compose_restart") -> SimpleNamespace:
    return SimpleNamespace(
        plan=SimpleNamespace(plan_id="abc123", intent=intent),
        chat_id=0,
        user_text="restart service",
        action_context={"service": "web"},
        expires_at=datetime.now() + timedelta(minutes=5),
    )


def test_approve_unknown_plan_streams_error(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "consume", lambda plan_id, chat_id: None
    )
    resp = client.post(
        "/chat/approve",
        json={"plan_id": "nope"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert "event: error" in resp.text


def test_approve_executes_action_and_streams_result(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "consume", lambda plan_id, chat_id: _pending()
    )
    monkeypatch.setattr(
        chat_mod.action_registry, "execute", lambda name, ctx: "service restarted"
    )
    resp = client.post(
        "/chat/approve",
        json={"plan_id": "abc123"},
        headers={"Authorization": "Bearer x"},
    )
    body = resp.text
    assert "event: action_started" in body
    assert "event: action_result" in body
    assert "service restarted" in body
    assert "event: final" in body
    assert "event: done" in body


def test_reject_cancels_plan(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "cancel", lambda plan_id, chat_id: True
    )
    resp = client.post(
        "/chat/reject",
        json={"plan_id": "abc123"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_reject_unknown_plan_returns_ok_false(client, monkeypatch):
    monkeypatch.setattr(
        chat_mod.pending_plans, "cancel", lambda plan_id, chat_id: False
    )
    resp = client.post(
        "/chat/reject",
        json={"plan_id": "zzz"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.json() == {"ok": False}
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `pytest tests/interfaces/test_chat_approval.py -v`
Expected: FAIL — `AttributeError: module 'app.interfaces.chat' has no attribute 'pending_plans'` (atau 404).

- [ ] **Step 3: Implementasi endpoint di `app/interfaces/chat.py`**

Tambahkan import di bagian atas (dekat import lain):

```python
from app.domain.use_cases import _conv_id_to_int
from app.handlers.approval import pending_plans
from app.handlers.registry import action_registry
```

Tambahkan di bawah `chat_send`:

```python
class PlanDecisionRequest(BaseModel):
    plan_id: str
    # sama seperti ChatSendRequest: hanya untuk admin token
    as_email: str | None = None


def _decision_conv_id(authorization: str | None, as_email: str | None) -> str:
    caller_user_id, mode = _resolve_caller(authorization)
    if mode == "admin":
        if not as_email:
            raise HTTPException(
                status_code=400, detail="admin token requires 'as_email' field"
            )
        return as_email
    return caller_user_id


async def _stream_approval(plan_id: str, conv_id: str) -> AsyncIterator[str]:
    from app.domain.messaging import ChatEvent

    pending = pending_plans.consume(plan_id, _conv_id_to_int(conv_id))
    if pending is None:
        yield _format_sse(
            ChatEvent.error(
                f"Plan '{plan_id}' tidak ditemukan atau sudah kedaluwarsa."
            )
        )
        yield "event: done\ndata: {}\n\n"
        return

    action_name = pending.plan.intent
    yield _format_sse(ChatEvent.action_started(action_name))
    try:
        result = await asyncio.to_thread(
            action_registry.execute, action_name, pending.action_context
        )
    except Exception as exc:  # noqa: BLE001 — batas proses eksternal, relay ke klien
        yield _format_sse(ChatEvent.error(f"Action {action_name} gagal: {exc}"))
        yield "event: done\ndata: {}\n\n"
        return

    yield _format_sse(ChatEvent.action_result(action_name, result))
    yield _format_sse(ChatEvent.final(f"Approved & executed: {action_name}"))
    yield "event: done\ndata: {}\n\n"


@router.post("/approve")
async def chat_approve(
    req: Annotated[PlanDecisionRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    conv_id = _decision_conv_id(authorization, req.as_email)
    return StreamingResponse(
        _stream_approval(req.plan_id, conv_id),
        media_type="text/event-stream",
    )


@router.post("/reject")
async def chat_reject(
    req: Annotated[PlanDecisionRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    conv_id = _decision_conv_id(authorization, req.as_email)
    ok = pending_plans.cancel(req.plan_id, _conv_id_to_int(conv_id))
    return {"ok": ok}
```

Catatan: `_conv_id_to_int` valid karena `chat_send` menyimpan plan dengan `chat_id=_conv_id_to_int(ctx.conversation_id)` dan `conversation_id == caller_user_id` untuk session user — proses yang sama, hash yang sama.

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `pytest tests/interfaces/test_chat_approval.py -v`
Expected: 4 PASS. Lalu `pytest tests/ -v` — tidak ada regresi.

- [ ] **Step 5: Commit**

```bash
git add app/interfaces/chat.py tests/interfaces/test_chat_approval.py
git commit -m "feat(gateway): endpoint chat approve dan reject untuk klien http"
```

---

### Task 2: Scaffold aplikasi Wails `octopus-desktop/`

**Files:**
- Create: `octopus-desktop/` (hasil `wails init`, template react-ts)
- Modify: `go.work` (tambah `use ./octopus-desktop`)

**Interfaces:**
- Produces: kerangka app Wails; module Go `github.com/codinginid/octopus-desktop`; frontend Vite React-TS di `octopus-desktop/frontend/`. Semua task berikutnya bekerja di dalam direktori ini.

- [ ] **Step 1: Install Wails CLI**

```bash
go install github.com/wailsapp/wails/v2/cmd/wails@latest
export PATH="$PATH:$(go env GOPATH)/bin"
wails version
```
Expected: versi v2.x tercetak.

- [ ] **Step 2: Init proyek**

```bash
cd /Users/anonymous/Documents/office/codinginid/ai-agent
wails init -n octopus-desktop -t react-ts
```

- [ ] **Step 3: Rename module & daftarkan ke go.work**

Edit `octopus-desktop/go.mod` baris 1 menjadi:

```
module github.com/codinginid/octopus-desktop
```

Ganti semua import internal template yang memakai nama module lama (cek `main.go`, `app.go`) agar konsisten. Lalu edit `go.work`:

```
go 1.23.0

toolchain go1.24.6

use (
	./octopus-cli
	./octopus-desktop
)
```

- [ ] **Step 4: Verifikasi build**

```bash
cd octopus-desktop && go mod tidy && go build ./... && cd frontend && npm install && npm run build
```
Expected: sukses tanpa error. (Opsional: `wails doctor` untuk cek dependency platform.)

- [ ] **Step 5: Commit**

```bash
git add go.work octopus-desktop
git commit -m "feat(desktop): scaffold aplikasi wails react-ts octopus desktop"
```

---

### Task 3: Package Go `internal/settings` (config + keyring)

**Files:**
- Create: `octopus-desktop/internal/settings/settings.go`
- Test: `octopus-desktop/internal/settings/settings_test.go`

**Interfaces:**
- Produces (dipakai Task 5):
  - `type Settings struct { GatewayURL string; JarvisMode bool; TTSEnabled bool; WhisperBin string; PiperBin string; WhisperModelPath string; PiperVoicePath string }`
  - `func Load(dir string) (Settings, error)` — file tidak ada → default (`JarvisMode: true, TTSEnabled: true`)
  - `func Save(dir string, s Settings) error`
  - `func SaveToken(token string) error` / `func Token() (string, error)` / `func DeleteToken() error` (keyring service `octopus-desktop`, account `session_token`)

- [ ] **Step 1: Tulis failing test**

```go
// octopus-desktop/internal/settings/settings_test.go
package settings

import (
	"testing"

	"github.com/zalando/go-keyring"
)

func TestLoadMissingFileReturnsDefaults(t *testing.T) {
	s, err := Load(t.TempDir())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !s.JarvisMode || !s.TTSEnabled {
		t.Fatalf("default JarvisMode/TTSEnabled harus true, got %+v", s)
	}
}

func TestSaveThenLoadRoundtrip(t *testing.T) {
	dir := t.TempDir()
	in := Settings{GatewayURL: "https://octo.example.com", JarvisMode: false, TTSEnabled: true}
	if err := Save(dir, in); err != nil {
		t.Fatalf("save: %v", err)
	}
	out, err := Load(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if out.GatewayURL != in.GatewayURL || out.JarvisMode != in.JarvisMode {
		t.Fatalf("roundtrip mismatch: %+v", out)
	}
}

func TestTokenRoundtripViaKeyring(t *testing.T) {
	keyring.MockInit()
	if err := SaveToken("tok-123"); err != nil {
		t.Fatalf("save token: %v", err)
	}
	got, err := Token()
	if err != nil || got != "tok-123" {
		t.Fatalf("token roundtrip: %q %v", got, err)
	}
	if err := DeleteToken(); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if _, err := Token(); err == nil {
		t.Fatal("token harus error setelah delete")
	}
}
```

- [ ] **Step 2: Run, pastikan gagal compile**

Run: `cd octopus-desktop && go get github.com/zalando/go-keyring && go test ./internal/settings/`
Expected: FAIL (undefined: Load, dst).

- [ ] **Step 3: Implementasi**

```go
// octopus-desktop/internal/settings/settings.go
package settings

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"github.com/zalando/go-keyring"
)

const (
	keyringService = "octopus-desktop"
	keyringAccount = "session_token"
	fileName       = "config.json"
)

type Settings struct {
	GatewayURL       string `json:"gateway_url"`
	JarvisMode       bool   `json:"jarvis_mode"`
	TTSEnabled       bool   `json:"tts_enabled"`
	WhisperBin       string `json:"whisper_bin"`
	PiperBin         string `json:"piper_bin"`
	WhisperModelPath string `json:"whisper_model_path"`
	PiperVoicePath   string `json:"piper_voice_path"`
}

func defaults() Settings {
	return Settings{JarvisMode: true, TTSEnabled: true}
}

func Load(dir string) (Settings, error) {
	raw, err := os.ReadFile(filepath.Join(dir, fileName))
	if errors.Is(err, os.ErrNotExist) {
		return defaults(), nil
	}
	if err != nil {
		return Settings{}, err
	}
	s := defaults()
	if err := json.Unmarshal(raw, &s); err != nil {
		return Settings{}, err
	}
	return s, nil
}

func Save(dir string, s Settings) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, fileName), raw, 0o600)
}

func SaveToken(token string) error { return keyring.Set(keyringService, keyringAccount, token) }
func Token() (string, error)       { return keyring.Get(keyringService, keyringAccount) }
func DeleteToken() error           { return keyring.Delete(keyringService, keyringAccount) }
```

- [ ] **Step 4: Run test, pastikan lulus**

Run: `go test ./internal/settings/ -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add octopus-desktop/internal/settings octopus-desktop/go.mod octopus-desktop/go.sum
git commit -m "feat(desktop): package settings dengan config json dan keyring"
```

---

### Task 4: Package Go `internal/gateway` (auth pairing + SSE client)

Kontrak API nyata (dari `app/interfaces/auth.py` dan `chat.py`):
- `POST /auth/tui/start` → `{"code","login_url","expires_in_sec"}`
- `POST /auth/tui/poll` body `{"code"}` → 202 `{"status":"pending"}` | 200 `{"status":"paired","session_token"}` | 410
- `POST /chat/send` Bearer token, body `{"text"}` → SSE `event: <type>\ndata: <json>\n\n`, diakhiri `event: done`
- `POST /chat/approve` body `{"plan_id"}` → SSE (Task 1); `POST /chat/reject` → `{"ok":bool}`

**Files:**
- Create: `octopus-desktop/internal/gateway/client.go`, `octopus-desktop/internal/gateway/sse.go`
- Test: `octopus-desktop/internal/gateway/client_test.go`

**Interfaces:**
- Produces (dipakai Task 5):
  - `type Event struct { Type string; Data map[string]any }`
  - `type LoginStart struct { Code string; LoginURL string; ExpiresInSec int }`
  - `func New(baseURL, token string) *Client`
  - `(*Client) StartLogin(ctx) (LoginStart, error)`
  - `(*Client) PollLogin(ctx, code string) (token string, pending bool, err error)`
  - `(*Client) SendChat(ctx, text string, out chan<- Event) error` — menutup out saat selesai; error ⇒ event terakhir bertipe `error` sudah dikirim ATAU err != nil untuk putus koneksi
  - `(*Client) Approve(ctx, planID string, out chan<- Event) error`
  - `(*Client) Reject(ctx, planID string) (bool, error)`
  - `var ErrUnauthorized = errors.New("unauthorized")` — dikembalikan saat HTTP 401

- [ ] **Step 1: Tulis failing test**

```go
// octopus-desktop/internal/gateway/client_test.go
package gateway

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func collect(t *testing.T, run func(out chan<- Event) error) ([]Event, error) {
	t.Helper()
	out := make(chan Event, 32)
	errc := make(chan error, 1)
	go func() { errc <- run(out) }()
	var evs []Event
	for ev := range out {
		evs = append(evs, ev)
	}
	return evs, <-errc
}

func TestSendChatParsesSSEEvents(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer tok" {
			t.Errorf("missing bearer, got %q", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "event: thinking\ndata: {\"message\":\"mikir\"}\n\n")
		fmt.Fprint(w, "event: final\ndata: {\"text\":\"halo\"}\n\n")
		fmt.Fprint(w, "event: done\ndata: {}\n\n")
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	evs, err := collect(t, func(out chan<- Event) error {
		return c.SendChat(context.Background(), "hai", out)
	})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(evs) != 2 || evs[0].Type != "thinking" || evs[1].Type != "final" {
		t.Fatalf("events salah: %+v", evs)
	}
	if evs[1].Data["text"] != "halo" {
		t.Fatalf("payload final salah: %+v", evs[1].Data)
	}
}

func TestSendChatUnauthorized(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := New(srv.URL, "expired")
	_, err := collect(t, func(out chan<- Event) error {
		return c.SendChat(context.Background(), "hai", out)
	})
	if !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("harus ErrUnauthorized, got %v", err)
	}
}

func TestSendChatBrokenStreamReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "event: thinking\ndata: {\"message\":\"mikir\"}\n\n")
		// putus tanpa event done
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	evs, err := collect(t, func(out chan<- Event) error {
		return c.SendChat(context.Background(), "hai", out)
	})
	if err == nil {
		t.Fatal("stream putus tanpa 'done' harus error")
	}
	if len(evs) != 1 {
		t.Fatalf("event sebelum putus tetap terkirim: %+v", evs)
	}
}

func TestLoginStartAndPoll(t *testing.T) {
	step := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/auth/tui/start":
			fmt.Fprint(w, `{"code":"ABCD","login_url":"https://x/login?code=ABCD","expires_in_sec":300}`)
		case "/auth/tui/poll":
			if step == 0 {
				step++
				w.WriteHeader(202)
				fmt.Fprint(w, `{"status":"pending"}`)
				return
			}
			fmt.Fprint(w, `{"status":"paired","session_token":"tok-999"}`)
		}
	}))
	defer srv.Close()

	c := New(srv.URL, "")
	ls, err := c.StartLogin(context.Background())
	if err != nil || ls.Code != "ABCD" {
		t.Fatalf("start: %+v %v", ls, err)
	}
	_, pending, err := c.PollLogin(context.Background(), "ABCD")
	if err != nil || !pending {
		t.Fatalf("poll 1 harus pending: %v", err)
	}
	tok, pending, err := c.PollLogin(context.Background(), "ABCD")
	if err != nil || pending || tok != "tok-999" {
		t.Fatalf("poll 2: tok=%q pending=%v err=%v", tok, pending, err)
	}
}

func TestReject(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"ok":true}`)
	}))
	defer srv.Close()
	ok, err := New(srv.URL, "tok").Reject(context.Background(), "plan-1")
	if err != nil || !ok {
		t.Fatalf("reject: %v %v", ok, err)
	}
}
```

- [ ] **Step 2: Run, pastikan gagal compile**

Run: `go test ./internal/gateway/`
Expected: FAIL (undefined New, Event, ErrUnauthorized).

- [ ] **Step 3: Implementasi SSE parser**

```go
// octopus-desktop/internal/gateway/sse.go
package gateway

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

type Event struct {
	Type string
	Data map[string]any
}

// parseSSE membaca stream SSE dan mengirim tiap event ke out.
// Return nil hanya jika event terminator "done" diterima; stream putus
// sebelum "done" dianggap error supaya UI bisa menandai pesan terputus.
func parseSSE(r io.Reader, out chan<- Event) error {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	var evType, data string
	flush := func() (done bool, err error) {
		if evType == "" {
			return false, nil
		}
		if evType == "done" {
			return true, nil
		}
		payload := map[string]any{}
		if data != "" {
			if err := json.Unmarshal([]byte(data), &payload); err != nil {
				return false, fmt.Errorf("payload sse bukan json valid: %w", err)
			}
		}
		out <- Event{Type: evType, Data: payload}
		return false, nil
	}
	for sc.Scan() {
		line := sc.Text()
		switch {
		case line == "":
			done, err := flush()
			if done || err != nil {
				return err
			}
			evType, data = "", ""
		case strings.HasPrefix(line, "event: "):
			evType = strings.TrimPrefix(line, "event: ")
		case strings.HasPrefix(line, "data: "):
			data = strings.TrimPrefix(line, "data: ")
		}
	}
	if err := sc.Err(); err != nil {
		return fmt.Errorf("stream sse putus: %w", err)
	}
	return fmt.Errorf("stream sse berakhir tanpa event done")
}
```

- [ ] **Step 4: Implementasi client**

```go
// octopus-desktop/internal/gateway/client.go
package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"
)

var ErrUnauthorized = errors.New("unauthorized")

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

func New(baseURL, token string) *Client {
	return &Client{
		baseURL: baseURL,
		token:   token,
		// Timeout hanya untuk request non-stream; stream pakai context caller.
		http: &http.Client{},
	}
}

type LoginStart struct {
	Code         string `json:"code"`
	LoginURL     string `json:"login_url"`
	ExpiresInSec int    `json:"expires_in_sec"`
}

func (c *Client) postJSON(ctx context.Context, path string, body any) (*http.Response, error) {
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("gateway tidak terjangkau: %w", err)
	}
	if resp.StatusCode == http.StatusUnauthorized {
		resp.Body.Close()
		return nil, ErrUnauthorized
	}
	return resp, nil
}

func (c *Client) StartLogin(ctx context.Context) (LoginStart, error) {
	resp, err := c.postJSON(ctx, "/auth/tui/start", map[string]string{})
	if err != nil {
		return LoginStart{}, err
	}
	defer resp.Body.Close()
	var ls LoginStart
	if err := json.NewDecoder(resp.Body).Decode(&ls); err != nil {
		return LoginStart{}, err
	}
	return ls, nil
}

func (c *Client) PollLogin(ctx context.Context, code string) (string, bool, error) {
	resp, err := c.postJSON(ctx, "/auth/tui/poll", map[string]string{"code": code})
	if err != nil {
		return "", false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusAccepted {
		return "", true, nil
	}
	if resp.StatusCode != http.StatusOK {
		return "", false, fmt.Errorf("poll gagal: HTTP %d", resp.StatusCode)
	}
	var out struct {
		SessionToken string `json:"session_token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", false, err
	}
	return out.SessionToken, false, nil
}

func (c *Client) stream(ctx context.Context, path string, body any, out chan<- Event) error {
	defer close(out)
	resp, err := c.postJSON(ctx, path, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s gagal: HTTP %d", path, resp.StatusCode)
	}
	return parseSSE(resp.Body, out)
}

func (c *Client) SendChat(ctx context.Context, text string, out chan<- Event) error {
	return c.stream(ctx, "/chat/send", map[string]string{"text": text}, out)
}

func (c *Client) Approve(ctx context.Context, planID string, out chan<- Event) error {
	return c.stream(ctx, "/chat/approve", map[string]string{"plan_id": planID}, out)
}

func (c *Client) Reject(ctx context.Context, planID string) (bool, error) {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	resp, err := c.postJSON(ctx, "/chat/reject", map[string]string{"plan_id": planID})
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	var out struct {
		OK bool `json:"ok"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return false, err
	}
	return out.OK, nil
}
```

- [ ] **Step 5: Run test, pastikan lulus**

Run: `go test ./internal/gateway/ -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add octopus-desktop/internal/gateway
git commit -m "feat(desktop): klien gateway dengan sse parser dan login pairing"
```

---

### Task 5: Wails App bindings (`app.go`)

**Files:**
- Modify: `octopus-desktop/app.go` (ganti isi template), `octopus-desktop/main.go` (wiring)
- Test: `octopus-desktop/app_test.go`

**Interfaces:**
- Consumes: `internal/settings`, `internal/gateway`; Task 9/10 nanti mengisi field `stt`/`tts` (interface didefinisikan di task masing-masing, di sini disimpan sebagai field yang boleh nil).
- Produces (dipanggil frontend via binding `window.go.main.App.*`):
  - `StartLogin() (map[string]any, error)` — `{code, login_url}`; juga buka browser
  - `PollLogin(code string) (string, error)` — `"pending"` | `"paired"` (token disimpan keyring, client di-refresh)
  - `IsLoggedIn() bool`, `Logout() error`
  - `SendChat(msgID, text string)` — async; emit event runtime `chat:event` payload `{msgId, type, data}`; saat stream error emit `{msgId, type:"stream_error", data:{message}}`
  - `ApprovePlan(msgID, planID string)` — sama seperti SendChat
  - `RejectPlan(planID string) (bool, error)`
  - `GetSettings() settings.Settings`, `SaveSettings(s settings.Settings) error`

- [ ] **Step 1: Tulis failing test untuk logika non-UI**

Bagian yang bisa dites tanpa runtime Wails: relay channel → emitter. Ekstrak fungsi `relayEvents`.

```go
// octopus-desktop/app_test.go
package main

import (
	"errors"
	"testing"

	"github.com/codinginid/octopus-desktop/internal/gateway"
)

func TestRelayEventsForwardsAllThenStreamError(t *testing.T) {
	out := make(chan gateway.Event, 3)
	out <- gateway.Event{Type: "thinking", Data: map[string]any{"message": "m"}}
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)

	var got []map[string]any
	emit := func(payload map[string]any) { got = append(got, payload) }

	relayEvents("msg-1", out, errors.New("putus"), emit)

	if len(got) != 3 {
		t.Fatalf("harus 2 event + 1 stream_error, got %d: %+v", len(got), got)
	}
	if got[0]["msgId"] != "msg-1" || got[0]["type"] != "thinking" {
		t.Fatalf("event pertama salah: %+v", got[0])
	}
	if got[2]["type"] != "stream_error" {
		t.Fatalf("event terakhir harus stream_error: %+v", got[2])
	}
}

func TestRelayEventsNoErrorNoStreamError(t *testing.T) {
	out := make(chan gateway.Event, 1)
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)
	var got []map[string]any
	relayEvents("m", out, nil, func(p map[string]any) { got = append(got, p) })
	if len(got) != 1 {
		t.Fatalf("tidak boleh ada stream_error: %+v", got)
	}
}
```

Catatan: channel sudah ditutup oleh `Client.stream`; di test kita tutup manual dan pass err terpisah — `relayEvents` menerima err setelah drain (lihat implementasi: pemanggil mengirim err hasil SendChat).

- [ ] **Step 2: Run, pastikan gagal**

Run: `go test . -run TestRelay -v`
Expected: FAIL (undefined relayEvents).

- [ ] **Step 3: Implementasi `app.go`**

```go
// octopus-desktop/app.go
package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/codinginid/octopus-desktop/internal/gateway"
	"github.com/codinginid/octopus-desktop/internal/settings"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

type App struct {
	ctx       context.Context
	mu        sync.Mutex
	cfg       settings.Settings
	configDir string
	client    *gateway.Client
}

func NewApp() *App {
	base, err := os.UserConfigDir()
	if err != nil {
		base = "."
	}
	dir := filepath.Join(base, "octopus-desktop")
	cfg, err := settings.Load(dir)
	if err != nil {
		cfg = settings.Settings{JarvisMode: true, TTSEnabled: true}
	}
	a := &App{cfg: cfg, configDir: dir}
	token, _ := settings.Token()
	a.client = gateway.New(cfg.GatewayURL, token)
	return a
}

func (a *App) startup(ctx context.Context) { a.ctx = ctx }

// relayEvents meneruskan event stream ke emitter dengan msgId, lalu
// menutup dengan stream_error bila stream berakhir tidak normal.
func relayEvents(msgID string, out <-chan gateway.Event, streamErr error, emit func(map[string]any)) {
	for ev := range out {
		emit(map[string]any{"msgId": msgID, "type": ev.Type, "data": ev.Data})
	}
	if streamErr != nil {
		emit(map[string]any{
			"msgId": msgID,
			"type":  "stream_error",
			"data":  map[string]any{"message": streamErr.Error()},
		})
	}
}

func (a *App) emit(payload map[string]any) {
	runtime.EventsEmit(a.ctx, "chat:event", payload)
}

func (a *App) runStream(msgID string, run func(chan<- gateway.Event) error) {
	out := make(chan gateway.Event, 32)
	done := make(chan error, 1)
	go func() { done <- run(out) }()
	// Drain dulu; err baru tersedia setelah channel ditutup oleh client.
	buffered := []gateway.Event{}
	for ev := range out {
		buffered = append(buffered, ev)
		a.emit(map[string]any{"msgId": msgID, "type": ev.Type, "data": ev.Data})
	}
	if err := <-done; err != nil {
		a.emit(map[string]any{
			"msgId": msgID, "type": "stream_error",
			"data": map[string]any{"message": err.Error()},
		})
	}
}

func (a *App) SendChat(msgID, text string) {
	go a.runStream(msgID, func(out chan<- gateway.Event) error {
		return a.client.SendChat(a.ctx, text, out)
	})
}

func (a *App) ApprovePlan(msgID, planID string) {
	go a.runStream(msgID, func(out chan<- gateway.Event) error {
		return a.client.Approve(a.ctx, planID, out)
	})
}

func (a *App) RejectPlan(planID string) (bool, error) {
	return a.client.Reject(a.ctx, planID)
}

func (a *App) StartLogin() (map[string]any, error) {
	ls, err := a.client.StartLogin(a.ctx)
	if err != nil {
		return nil, err
	}
	runtime.BrowserOpenURL(a.ctx, ls.LoginURL)
	return map[string]any{"code": ls.Code, "login_url": ls.LoginURL}, nil
}

func (a *App) PollLogin(code string) (string, error) {
	token, pending, err := a.client.PollLogin(a.ctx, code)
	if err != nil {
		return "", err
	}
	if pending {
		return "pending", nil
	}
	if err := settings.SaveToken(token); err != nil {
		return "", fmt.Errorf("gagal simpan token ke keyring: %w", err)
	}
	a.mu.Lock()
	a.client = gateway.New(a.cfg.GatewayURL, token)
	a.mu.Unlock()
	return "paired", nil
}

func (a *App) IsLoggedIn() bool {
	tok, err := settings.Token()
	return err == nil && tok != ""
}

func (a *App) Logout() error { return settings.DeleteToken() }

func (a *App) GetSettings() settings.Settings { return a.cfg }

func (a *App) SaveSettings(s settings.Settings) error {
	if err := settings.Save(a.configDir, s); err != nil {
		return err
	}
	a.mu.Lock()
	a.cfg = s
	token, _ := settings.Token()
	a.client = gateway.New(s.GatewayURL, token)
	a.mu.Unlock()
	return nil
}
```

Sesuaikan `main.go` template: pastikan `NewApp()` dipakai dan `OnStartup: app.startup` terpasang (template react-ts sudah begitu; cukup pastikan nama method cocok).

Catatan implementasi: `relayEvents` dipakai oleh test sebagai unit murni; `runStream` adalah versi runtime yang emit langsung — keduanya harus konsisten. Jika saat implementasi terasa duplikatif, refactor `runStream` memakai `relayEvents` dengan mengumpulkan err lebih dulu.

- [ ] **Step 4: Run test & build**

Run: `go test . -v && go build ./...`
Expected: PASS + build sukses.

- [ ] **Step 5: Commit**

```bash
git add octopus-desktop/app.go octopus-desktop/main.go octopus-desktop/app_test.go
git commit -m "feat(desktop): wails bindings chat login approve dan settings"
```

---

### Task 6: Frontend — tipe event + chat reducer

**Files:**
- Create: `octopus-desktop/frontend/src/chat/types.ts`, `octopus-desktop/frontend/src/chat/reducer.ts`
- Test: `octopus-desktop/frontend/src/chat/reducer.test.ts`
- Modify: `octopus-desktop/frontend/package.json` (tambah vitest, @testing-library/react, jsdom)

**Interfaces:**
- Produces (dipakai Task 7 & 11):

```ts
// types.ts (kontrak penuh — salin apa adanya)
export type ChatEventPayload = Record<string, unknown>;

export interface IncomingEvent {
  msgId: string;
  type: string; // thinking|intent_classified|approval_required|action_started|action_result|text_chunk|final|error|observing|reflecting|retrying|stream_error
  data: ChatEventPayload;
}

export type Part =
  | { kind: "status"; text: string }
  | { kind: "text"; text: string; streaming: boolean }
  | { kind: "action"; action: string; running: boolean; output: string }
  | { kind: "approval"; planId: string; summary: string; decided: "" | "approved" | "rejected" }
  | { kind: "error"; message: string; retryable: boolean };

export interface AssistantMessage {
  msgId: string;
  role: "assistant";
  parts: Part[];
  done: boolean;
  finalText: string; // untuk TTS
}

export interface UserMessage {
  msgId: string;
  role: "user";
  text: string;
}

export type Message = UserMessage | AssistantMessage;
```

- `applyEvent(messages: Message[], ev: IncomingEvent): Message[]` — pure function; buat AssistantMessage baru jika msgId belum ada.

Aturan mapping (uji semuanya):
| Event | Efek |
|---|---|
| `thinking`/`observing`/`reflecting`/`retrying` | ganti part `status` terakhir (atau tambah) dengan `data.message` |
| `intent_classified` | part `status`: `intent: <intent> (<confidence>)` |
| `text_chunk` | append `data.text` ke part `text` streaming terakhir (buat jika belum ada) |
| `action_started` | tambah part `action` running=true |
| `action_result` | set part action (action sama) running=false + output |
| `approval_required` | tambah part `approval` (planId, summary) |
| `final` | hapus part `status`, set `done=true`, `finalText=data.text`; jika tidak ada part text/action, tambah part text berisi finalText |
| `error` | tambah part `error` retryable=false, `done=true` |
| `stream_error` | tambah part `error` retryable=true, `done=true` |

- [ ] **Step 1: Setup Vitest**

```bash
cd octopus-desktop/frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Tambah di `package.json` scripts: `"test": "vitest run"`. Buat `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true },
});
```

- [ ] **Step 2: Tulis failing test**

```ts
// octopus-desktop/frontend/src/chat/reducer.test.ts
import { describe, expect, it } from "vitest";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message } from "./types";

const ev = (type: string, data: Record<string, unknown> = {}, msgId = "m1") => ({
  msgId,
  type,
  data,
});

const last = (msgs: Message[]) => msgs[msgs.length - 1] as AssistantMessage;

describe("applyEvent", () => {
  it("membuat assistant message baru untuk msgId baru", () => {
    const out = applyEvent([], ev("thinking", { message: "mikir" }));
    expect(out).toHaveLength(1);
    expect(last(out).parts).toEqual([{ kind: "status", text: "mikir" }]);
  });

  it("mengganti status, bukan menumpuk", () => {
    let msgs = applyEvent([], ev("thinking", { message: "a" }));
    msgs = applyEvent(msgs, ev("observing", { message: "b" }));
    const statuses = last(msgs).parts.filter((p) => p.kind === "status");
    expect(statuses).toEqual([{ kind: "status", text: "b" }]);
  });

  it("menggabungkan text_chunk menjadi satu part streaming", () => {
    let msgs = applyEvent([], ev("text_chunk", { text: "Ha" }));
    msgs = applyEvent(msgs, ev("text_chunk", { text: "lo" }));
    expect(last(msgs).parts).toContainEqual({ kind: "text", text: "Halo", streaming: true });
  });

  it("action_started lalu action_result mengisi output", () => {
    let msgs = applyEvent([], ev("action_started", { action: "memory" }));
    msgs = applyEvent(msgs, ev("action_result", { action: "memory", output: "RAM 60%" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "action",
      action: "memory",
      running: false,
      output: "RAM 60%",
    });
  });

  it("approval_required menghasilkan part approval", () => {
    const msgs = applyEvent([], ev("approval_required", { plan_id: "p1", summary: "restart web" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "approval",
      planId: "p1",
      summary: "restart web",
      decided: "",
    });
  });

  it("final menutup pesan dan menyimpan finalText", () => {
    let msgs = applyEvent([], ev("thinking", { message: "mikir" }));
    msgs = applyEvent(msgs, ev("final", { text: "beres" }));
    const m = last(msgs);
    expect(m.done).toBe(true);
    expect(m.finalText).toBe("beres");
    expect(m.parts.some((p) => p.kind === "status")).toBe(false);
  });

  it("stream_error menghasilkan error retryable", () => {
    const msgs = applyEvent([], ev("stream_error", { message: "putus" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "error",
      message: "putus",
      retryable: true,
    });
    expect(last(msgs).done).toBe(true);
  });
});
```

- [ ] **Step 3: Run, pastikan gagal**

Run: `npm test`
Expected: FAIL (cannot resolve ./reducer).

- [ ] **Step 4: Implementasi `reducer.ts`**

```ts
// octopus-desktop/frontend/src/chat/reducer.ts
import type { AssistantMessage, IncomingEvent, Message, Part } from "./types";

const STATUS_TYPES = new Set(["thinking", "observing", "reflecting", "retrying"]);

function withoutStatus(parts: Part[]): Part[] {
  return parts.filter((p) => p.kind !== "status");
}

function updateAssistant(msg: AssistantMessage, ev: IncomingEvent): AssistantMessage {
  const d = ev.data;
  if (STATUS_TYPES.has(ev.type)) {
    return { ...msg, parts: [...withoutStatus(msg.parts), { kind: "status", text: String(d.message ?? "") }] };
  }
  switch (ev.type) {
    case "intent_classified":
      return {
        ...msg,
        parts: [
          ...withoutStatus(msg.parts),
          { kind: "status", text: `intent: ${d.intent} (${d.confidence})` },
        ],
      };
    case "text_chunk": {
      const parts = [...msg.parts];
      const lastPart = parts[parts.length - 1];
      if (lastPart?.kind === "text" && lastPart.streaming) {
        parts[parts.length - 1] = { ...lastPart, text: lastPart.text + String(d.text ?? "") };
      } else {
        parts.push({ kind: "text", text: String(d.text ?? ""), streaming: true });
      }
      return { ...msg, parts };
    }
    case "action_started":
      return {
        ...msg,
        parts: [...msg.parts, { kind: "action", action: String(d.action ?? ""), running: true, output: "" }],
      };
    case "action_result":
      return {
        ...msg,
        parts: msg.parts.map((p) =>
          p.kind === "action" && p.action === d.action && p.running
            ? { ...p, running: false, output: String(d.output ?? "") }
            : p,
        ),
      };
    case "approval_required":
      return {
        ...msg,
        parts: [
          ...msg.parts,
          { kind: "approval", planId: String(d.plan_id ?? ""), summary: String(d.summary ?? ""), decided: "" },
        ],
      };
    case "final": {
      const finalText = String(d.text ?? "");
      let parts = withoutStatus(msg.parts).map((p) =>
        p.kind === "text" ? { ...p, streaming: false } : p,
      );
      if (!parts.some((p) => p.kind === "text" || p.kind === "action")) {
        parts = [...parts, { kind: "text", text: finalText, streaming: false }];
      }
      return { ...msg, parts, done: true, finalText };
    }
    case "error":
      return {
        ...msg,
        parts: [...withoutStatus(msg.parts), { kind: "error", message: String(d.message ?? ""), retryable: false }],
        done: true,
      };
    case "stream_error":
      return {
        ...msg,
        parts: [...withoutStatus(msg.parts), { kind: "error", message: String(d.message ?? ""), retryable: true }],
        done: true,
      };
    default:
      return msg;
  }
}

export function applyEvent(messages: Message[], ev: IncomingEvent): Message[] {
  const idx = messages.findIndex((m) => m.msgId === ev.msgId && m.role === "assistant");
  if (idx === -1) {
    const fresh: AssistantMessage = { msgId: ev.msgId, role: "assistant", parts: [], done: false, finalText: "" };
    return [...messages, updateAssistant(fresh, ev)];
  }
  const next = [...messages];
  next[idx] = updateAssistant(next[idx] as AssistantMessage, ev);
  return next;
}
```

- [ ] **Step 5: Run test, pastikan lulus**

Run: `npm test`
Expected: 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add octopus-desktop/frontend
git commit -m "feat(desktop): chat reducer pemetaan event sse ke message parts"
```

---

### Task 7: Frontend — kartu visual + ChatView

**Files:**
- Create: `octopus-desktop/frontend/src/chat/cards/TextCard.tsx`, `ActionCard.tsx`, `MetricCard.tsx`, `TableCard.tsx`, `ApprovalCard.tsx`, `StatusLine.tsx`, `ErrorCard.tsx`
- Create: `octopus-desktop/frontend/src/chat/ChatView.tsx`, `octopus-desktop/frontend/src/chat/bindings.ts`
- Test: `octopus-desktop/frontend/src/chat/cards/cards.test.tsx`
- Modify: `octopus-desktop/frontend/src/App.tsx` (render ChatView)

**Interfaces:**
- Consumes: `Part`, `Message`, `applyEvent` (Task 6); binding Wails `window.go.main.App` (Task 5) via wrapper `bindings.ts`.
- Produces: `bindings.ts` mengekspor `sendChat(msgId, text)`, `approvePlan(msgId, planId)`, `rejectPlan(planId)`, `onChatEvent(cb)` — dipakai Task 11/12.

Keputusan render per part:
- `action` dengan action ∈ {`memory`, `disk`, `server_status`, `docker_stats`} → `MetricCard` (ekstrak persentase via regex, tampilkan bar; fallback `<pre>` output).
- `action` dengan action ∈ {`docker_ps`, `docker_images`, `docker_compose_ps`, `processes`} → `TableCard`: parse output kolumnar (header + baris, split `2+ spasi`) menjadi `<table>`; bila parsing gagal (kurang dari 2 kolom terdeteksi) fallback `<pre>`.
- Action lain → `ActionCard` (`<pre>` monospace scrollable + label action + spinner saat running).
- **Catatan deviasi spec:** `DeployCard` stepper live TIDAK dibuat di v1 — backend hanya emit `action_started` → `action_result` (satu blok), tidak ada event per-step deploy. Deploy dirender sebagai `ActionCard` (spinner saat running). Stepper live butuh perubahan backend yang oleh spec dinyatakan di luar scope.
- `approval` → `ApprovalCard` dengan tombol Approve/Reject; setelah klik, tombol disabled (decided).
- `text` → `TextCard` (render markdown sederhana: paragraf + `**bold**` + code fence; TANPA library markdown dulu — cukup pre-wrap).
- `status` → `StatusLine` italic redup; `error` → `ErrorCard` merah + tombol "Coba lagi" bila retryable.

- [ ] **Step 1: Buat `bindings.ts`**

```ts
// octopus-desktop/frontend/src/chat/bindings.ts
import type { IncomingEvent } from "./types";

type GoApp = {
  SendChat(msgId: string, text: string): Promise<void>;
  ApprovePlan(msgId: string, planId: string): Promise<void>;
  RejectPlan(planId: string): Promise<boolean>;
};

declare global {
  interface Window {
    go: { main: { App: GoApp } };
    runtime: {
      EventsOn(name: string, cb: (payload: unknown) => void): () => void;
    };
  }
}

export const sendChat = (msgId: string, text: string) => window.go.main.App.SendChat(msgId, text);
export const approvePlan = (msgId: string, planId: string) => window.go.main.App.ApprovePlan(msgId, planId);
export const rejectPlan = (planId: string) => window.go.main.App.RejectPlan(planId);

export function onChatEvent(cb: (ev: IncomingEvent) => void): () => void {
  return window.runtime.EventsOn("chat:event", (payload) => cb(payload as IncomingEvent));
}
```

- [ ] **Step 2: Tulis failing test kartu**

```tsx
// octopus-desktop/frontend/src/chat/cards/cards.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "./ApprovalCard";
import { MetricCard } from "./MetricCard";
import { TableCard, parseColumns } from "./TableCard";

describe("MetricCard", () => {
  it("mengekstrak persentase dari output", () => {
    render(<MetricCard action="memory" output={"Memory usage: 62.5%\nSwap: 10%"} />);
    expect(screen.getByText(/62.5%/)).toBeTruthy();
  });

  it("fallback pre saat tidak ada persentase", () => {
    render(<MetricCard action="memory" output="tidak ada angka" />);
    expect(screen.getByText("tidak ada angka")).toBeTruthy();
  });
});

describe("TableCard", () => {
  const psOutput = [
    "CONTAINER ID   IMAGE          STATUS         NAMES",
    "abc123def456   nginx:latest   Up 2 hours     web",
    "789ghi012jkl   redis:7        Up 5 minutes   cache",
  ].join("\n");

  it("parseColumns memecah header dan baris berdasarkan 2+ spasi", () => {
    const t = parseColumns(psOutput);
    expect(t?.header).toEqual(["CONTAINER ID", "IMAGE", "STATUS", "NAMES"]);
    expect(t?.rows).toHaveLength(2);
    expect(t?.rows[0][3]).toBe("web");
  });

  it("render table dengan sel dari output", () => {
    render(<TableCard action="docker_ps" output={psOutput} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("nginx:latest")).toBeTruthy();
  });

  it("fallback pre bila bukan kolumnar", () => {
    render(<TableCard action="docker_ps" output="cuma satu kolom" />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("cuma satu kolom")).toBeTruthy();
  });
});

describe("ApprovalCard", () => {
  it("memanggil onApprove dengan planId", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalCard planId="p1" summary="restart web" decided="" onApprove={onApprove} onReject={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onApprove).toHaveBeenCalledWith("p1");
  });

  it("tombol disabled setelah decided", () => {
    render(
      <ApprovalCard planId="p1" summary="s" decided="approved" onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    const btn = screen.getByRole("button", { name: /approve/i }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
```

- [ ] **Step 3: Run, pastikan gagal**

Run: `npm test`
Expected: FAIL (cannot resolve ./ApprovalCard, ./MetricCard).

- [ ] **Step 4: Implementasi kartu**

```tsx
// octopus-desktop/frontend/src/chat/cards/MetricCard.tsx
const PCT_RE = /([A-Za-z /]+)?:?\s*(\d+(?:\.\d+)?)\s*%/g;

export function MetricCard({ action, output }: { action: string; output: string }) {
  const metrics = [...output.matchAll(PCT_RE)].map((m) => ({
    label: (m[1] ?? action).trim(),
    value: parseFloat(m[2]),
  }));
  if (metrics.length === 0) {
    return <pre className="card card-pre">{output}</pre>;
  }
  return (
    <div className="card card-metric">
      <div className="card-title">{action}</div>
      {metrics.map((m, i) => (
        <div key={i} className="metric-row">
          <span className="metric-label">{m.label}</span>
          <div className="metric-bar">
            <div
              className={`metric-fill ${m.value > 85 ? "danger" : m.value > 65 ? "warn" : ""}`}
              style={{ width: `${Math.min(m.value, 100)}%` }}
            />
          </div>
          <span className="metric-value">{m.value}%</span>
        </div>
      ))}
      <details>
        <summary>output mentah</summary>
        <pre>{output}</pre>
      </details>
    </div>
  );
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/TableCard.tsx
export interface ParsedTable {
  header: string[];
  rows: string[][];
}

export function parseColumns(output: string): ParsedTable | null {
  const lines = output.split("\n").filter((l) => l.trim() !== "");
  if (lines.length < 2) return null;
  const header = lines[0].trim().split(/\s{2,}/);
  if (header.length < 2) return null;
  const rows = lines.slice(1).map((l) => l.trim().split(/\s{2,}/));
  return { header, rows };
}

export function TableCard({ action, output }: { action: string; output: string }) {
  const table = parseColumns(output);
  if (!table) return <pre className="card card-pre">{output}</pre>;
  return (
    <div className="card card-table">
      <div className="card-title">{action}</div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {table.header.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/ApprovalCard.tsx
export function ApprovalCard({
  planId,
  summary,
  decided,
  onApprove,
  onReject,
}: {
  planId: string;
  summary: string;
  decided: "" | "approved" | "rejected";
  onApprove: (planId: string) => void;
  onReject: (planId: string) => void;
}) {
  const disabled = decided !== "";
  return (
    <div className="card card-approval">
      <div className="card-title">Butuh persetujuan</div>
      <pre className="approval-summary">{summary}</pre>
      <div className="approval-buttons">
        <button disabled={disabled} onClick={() => onApprove(planId)}>
          Approve
        </button>
        <button disabled={disabled} className="danger" onClick={() => onReject(planId)}>
          Reject
        </button>
      </div>
      {decided !== "" && <div className="approval-decided">{decided}</div>}
    </div>
  );
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/ActionCard.tsx
export function ActionCard({ action, running, output }: { action: string; running: boolean; output: string }) {
  return (
    <div className="card card-action">
      <div className="card-title">
        {action} {running && <span className="spinner">⏳</span>}
      </div>
      {output && <pre className="card-pre">{output}</pre>}
    </div>
  );
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/TextCard.tsx
export function TextCard({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div className="card card-text">
      <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
      {streaming && <span className="cursor">▌</span>}
    </div>
  );
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/StatusLine.tsx
export function StatusLine({ text }: { text: string }) {
  return <div className="status-line">{text}</div>;
}
```

```tsx
// octopus-desktop/frontend/src/chat/cards/ErrorCard.tsx
export function ErrorCard({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  return (
    <div className="card card-error">
      <span>{message}</span>
      {retryable && onRetry && <button onClick={onRetry}>Coba lagi</button>}
    </div>
  );
}
```

- [ ] **Step 5: Implementasi `ChatView.tsx`**

```tsx
// octopus-desktop/frontend/src/chat/ChatView.tsx
import { useEffect, useRef, useState } from "react";
import { approvePlan, onChatEvent, rejectPlan, sendChat } from "./bindings";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message, Part } from "./types";
import { ActionCard } from "./cards/ActionCard";
import { ApprovalCard } from "./cards/ApprovalCard";
import { ErrorCard } from "./cards/ErrorCard";
import { MetricCard } from "./cards/MetricCard";
import { StatusLine } from "./cards/StatusLine";
import { TableCard } from "./cards/TableCard";
import { TextCard } from "./cards/TextCard";

const METRIC_ACTIONS = new Set(["memory", "disk", "server_status", "docker_stats"]);
const TABLE_ACTIONS = new Set(["docker_ps", "docker_images", "docker_compose_ps", "processes"]);

let counter = 0;
const newMsgId = () => `m-${Date.now()}-${counter++}`;

export function ChatView({
  onFinal,
  inputExtra,
}: {
  onFinal?: (text: string) => void;
  inputExtra?: React.ReactNode; // slot untuk tombol mic (Task 11)
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const lastFinal = useRef("");

  useEffect(() => {
    return onChatEvent((ev) => setMessages((prev) => applyEvent(prev, ev)));
  }, []);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.done && lastMsg.finalText && lastMsg.finalText !== lastFinal.current) {
      lastFinal.current = lastMsg.finalText;
      onFinal?.(lastMsg.finalText);
    }
  }, [messages, onFinal]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const msgId = newMsgId();
    setMessages((prev) => [...prev, { msgId: `u-${msgId}`, role: "user", text: trimmed }]);
    void sendChat(msgId, trimmed);
    setDraft("");
  };

  const decide = (msg: AssistantMessage, planId: string, decision: "approved" | "rejected") => {
    setMessages((prev) =>
      prev.map((m) =>
        m.msgId === msg.msgId && m.role === "assistant"
          ? {
              ...m,
              parts: m.parts.map((p) =>
                p.kind === "approval" && p.planId === planId ? { ...p, decided: decision } : p,
              ),
            }
          : m,
      ),
    );
    if (decision === "approved") void approvePlan(newMsgId(), planId);
    else void rejectPlan(planId);
  };

  const renderPart = (msg: AssistantMessage, p: Part, i: number) => {
    switch (p.kind) {
      case "status":
        return <StatusLine key={i} text={p.text} />;
      case "text":
        return <TextCard key={i} text={p.text} streaming={p.streaming} />;
      case "action":
        if (!p.running && METRIC_ACTIONS.has(p.action))
          return <MetricCard key={i} action={p.action} output={p.output} />;
        if (!p.running && TABLE_ACTIONS.has(p.action))
          return <TableCard key={i} action={p.action} output={p.output} />;
        return <ActionCard key={i} action={p.action} running={p.running} output={p.output} />;
      case "approval":
        return (
          <ApprovalCard
            key={i}
            planId={p.planId}
            summary={p.summary}
            decided={p.decided}
            onApprove={(id) => decide(msg, id, "approved")}
            onReject={(id) => decide(msg, id, "rejected")}
          />
        );
      case "error":
        return <ErrorCard key={i} message={p.message} retryable={p.retryable} />;
    }
  };

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.msgId} className="msg-user">{m.text}</div>
          ) : (
            <div key={m.msgId} className="msg-assistant">
              {m.parts.map((p, i) => renderPart(m, p, i))}
            </div>
          ),
        )}
      </div>
      <div className="chat-input">
        {inputExtra}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(draft)}
          placeholder="Ketik perintah… (atau tahan tombol mic)"
        />
        <button onClick={() => submit(draft)}>Kirim</button>
      </div>
    </div>
  );
}
```

Ekspor helper `submitText` tidak perlu — Task 11 memakai prop `inputExtra` + callback. Tambahkan juga fungsi `submitFromVoice` bila dibutuhkan Task 11: ubah `ChatView` menerima prop opsional `registerSubmit?: (fn: (text: string) => void) => void` dan panggil `registerSubmit?.(submit)` dalam `useEffect` sekali — sudah cukup untuk auto-send transkrip.

Update `App.tsx` template menjadi render `<ChatView />` + CSS dasar di `style.css` (class yang dipakai kartu; styling bebas, dark theme sederhana).

- [ ] **Step 6: Run test + build**

Run: `npm test && npm run build`
Expected: PASS + build sukses.

- [ ] **Step 7: Commit**

```bash
git add octopus-desktop/frontend
git commit -m "feat(desktop): chatview dengan kartu metrik action approval dan error"
```

---

### Task 8: Package Go `internal/assets` (downloader model)

**Files:**
- Create: `octopus-desktop/internal/assets/download.go`
- Test: `octopus-desktop/internal/assets/download_test.go`

**Interfaces:**
- Produces (dipakai Task 12 via binding baru di app.go):
  - `type Item struct { Name, URL, SHA256, DestName string }`
  - `func Download(ctx context.Context, it Item, destDir string, progress func(done, total int64)) (string, error)` — return path file; verifikasi sha256 bila `it.SHA256 != ""`; download ke file `.part` lalu rename (atomic).
  - `func DefaultItems() []Item` — model default: whisper `ggml-base.bin` (URL huggingface resmi ggerganov/whisper.cpp) dan voice piper `id_ID` bila tersedia (kalau tidak ada suara id_ID resmi, pakai `en_US-amy-medium`). **Saat eksekusi**: isi kolom `SHA256` dengan hasil `shasum -a 256` dari file yang diunduh dari sumber resmi — jangan tebak nilainya; kosongkan bila tidak sempat (verifikasi di-skip dengan log warning).

- [ ] **Step 1: Tulis failing test**

```go
// octopus-desktop/internal/assets/download_test.go
package assets

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestDownloadVerifiesChecksumAndRenames(t *testing.T) {
	content := []byte("model-bytes")
	sum := sha256.Sum256(content)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(content)
	}))
	defer srv.Close()

	dir := t.TempDir()
	var lastDone int64
	path, err := Download(context.Background(), Item{
		Name: "test", URL: srv.URL, SHA256: hex.EncodeToString(sum[:]), DestName: "model.bin",
	}, dir, func(done, total int64) { lastDone = done })
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if filepath.Base(path) != "model.bin" {
		t.Fatalf("path salah: %s", path)
	}
	if lastDone != int64(len(content)) {
		t.Fatalf("progress terakhir %d != %d", lastDone, len(content))
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("file tidak ada: %v", err)
	}
}

func TestDownloadBadChecksumFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("corrupt"))
	}))
	defer srv.Close()

	_, err := Download(context.Background(), Item{
		Name: "test", URL: srv.URL, SHA256: "deadbeef", DestName: "model.bin",
	}, t.TempDir(), nil)
	if err == nil {
		t.Fatal("checksum salah harus error")
	}
}
```

- [ ] **Step 2: Run, pastikan gagal**

Run: `go test ./internal/assets/`
Expected: FAIL (undefined Download, Item).

- [ ] **Step 3: Implementasi**

```go
// octopus-desktop/internal/assets/download.go
package assets

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

type Item struct {
	Name     string
	URL      string
	SHA256   string
	DestName string
}

func DefaultItems() []Item {
	return []Item{
		{
			Name:     "whisper-base",
			URL:      "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
			SHA256:   "", // diisi saat eksekusi dari unduhan resmi; kosong = skip verify
			DestName: "ggml-base.bin",
		},
		{
			Name:     "piper-voice",
			URL:      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
			SHA256:   "",
			DestName: "piper-voice.onnx",
		},
		{
			Name:     "piper-voice-config",
			URL:      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
			SHA256:   "",
			DestName: "piper-voice.onnx.json",
		},
	}
}

type progressWriter struct {
	w        io.Writer
	done     int64
	total    int64
	callback func(done, total int64)
}

func (p *progressWriter) Write(b []byte) (int, error) {
	n, err := p.w.Write(b)
	p.done += int64(n)
	if p.callback != nil {
		p.callback(p.done, p.total)
	}
	return n, err
}

func Download(ctx context.Context, it Item, destDir string, progress func(done, total int64)) (string, error) {
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, it.URL, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("unduh %s gagal: %w", it.Name, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unduh %s gagal: HTTP %d", it.Name, resp.StatusCode)
	}

	dest := filepath.Join(destDir, it.DestName)
	part := dest + ".part"
	f, err := os.Create(part)
	if err != nil {
		return "", err
	}
	hasher := sha256.New()
	pw := &progressWriter{w: io.MultiWriter(f, hasher), total: resp.ContentLength, callback: progress}
	_, copyErr := io.Copy(pw, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		os.Remove(part)
		return "", fmt.Errorf("unduh %s terputus: %w", it.Name, copyErr)
	}
	if closeErr != nil {
		return "", closeErr
	}
	if it.SHA256 != "" {
		got := hex.EncodeToString(hasher.Sum(nil))
		if got != it.SHA256 {
			os.Remove(part)
			return "", fmt.Errorf("checksum %s tidak cocok: got %s", it.Name, got)
		}
	}
	if err := os.Rename(part, dest); err != nil {
		return "", err
	}
	return dest, nil
}
```

- [ ] **Step 4: Run test, pastikan lulus**

Run: `go test ./internal/assets/ -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add octopus-desktop/internal/assets
git commit -m "feat(desktop): downloader model dengan checksum dan progress"
```

---

### Task 9: Package Go `internal/speech` (STT port + WhisperCLIAdapter)

**Files:**
- Create: `octopus-desktop/internal/speech/speech.go`, `octopus-desktop/internal/speech/whisper.go`
- Test: `octopus-desktop/internal/speech/whisper_test.go`

**Interfaces:**
- Produces (dipakai Task 11 via binding `Transcribe`):
  - `type SpeechToText interface { Transcribe(ctx context.Context, wav []byte) (string, error) }`
  - `type WhisperCLI struct { Bin string; ModelPath string }` — implement SpeechToText via subprocess `whisper-cli -m <model> -f <wav> -nt -np` (stdout = transkrip)
  - `var ErrNotConfigured = errors.New("stt belum dikonfigurasi")`

- [ ] **Step 1: Tulis failing test (fake binary)**

```go
// octopus-desktop/internal/speech/whisper_test.go
package speech

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func fakeBin(t *testing.T, script string) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake binary test butuh shell posix")
	}
	p := filepath.Join(t.TempDir(), "fake-whisper")
	if err := os.WriteFile(p, []byte("#!/bin/sh\n"+script), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestTranscribeReturnsStdout(t *testing.T) {
	bin := fakeBin(t, `echo " restart service web "`)
	w := &WhisperCLI{Bin: bin, ModelPath: "model.bin"}
	got, err := w.Transcribe(context.Background(), []byte("RIFFfake"))
	if err != nil {
		t.Fatalf("transcribe: %v", err)
	}
	if got != "restart service web" {
		t.Fatalf("harus di-trim, got %q", got)
	}
}

func TestTranscribeBinaryFailureWrapped(t *testing.T) {
	bin := fakeBin(t, `echo "boom" >&2; exit 1`)
	w := &WhisperCLI{Bin: bin, ModelPath: "model.bin"}
	if _, err := w.Transcribe(context.Background(), []byte("RIFFfake")); err == nil {
		t.Fatal("exit 1 harus error")
	}
}

func TestTranscribeUnconfigured(t *testing.T) {
	w := &WhisperCLI{}
	if _, err := w.Transcribe(context.Background(), nil); err == nil {
		t.Fatal("bin kosong harus error ErrNotConfigured")
	}
}
```

- [ ] **Step 2: Run, pastikan gagal**

Run: `go test ./internal/speech/`
Expected: FAIL (undefined WhisperCLI).

- [ ] **Step 3: Implementasi**

```go
// octopus-desktop/internal/speech/speech.go
package speech

import (
	"context"
	"errors"
)

var ErrNotConfigured = errors.New("stt belum dikonfigurasi")

type SpeechToText interface {
	Transcribe(ctx context.Context, wav []byte) (string, error)
}
```

```go
// octopus-desktop/internal/speech/whisper.go
package speech

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// WhisperCLI menjalankan binary whisper.cpp (whisper-cli) sebagai subprocess.
// Input wav 16kHz mono PCM16 (disiapkan frontend).
type WhisperCLI struct {
	Bin       string
	ModelPath string
}

func (w *WhisperCLI) Transcribe(ctx context.Context, wav []byte) (string, error) {
	if w.Bin == "" || w.ModelPath == "" {
		return "", ErrNotConfigured
	}
	tmp, err := os.CreateTemp("", "octo-stt-*.wav")
	if err != nil {
		return "", err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(wav); err != nil {
		tmp.Close()
		return "", err
	}
	tmp.Close()

	cmd := exec.CommandContext(ctx, w.Bin,
		"-m", w.ModelPath,
		"-f", filepath.Clean(tmp.Name()),
		"-nt", // tanpa timestamp
		"-np", // tanpa banner/progress di stderr
	)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("whisper gagal: %w — %s", err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(stdout.String()), nil
}
```

- [ ] **Step 4: Run test, pastikan lulus**

Run: `go test ./internal/speech/ -v`
Expected: 3 PASS (atau SKIP di Windows).

- [ ] **Step 5: Commit**

```bash
git add octopus-desktop/internal/speech
git commit -m "feat(desktop): port stt dengan adapter whisper cli"
```

---

### Task 10: Package Go `internal/voice` (TTS port + PiperAdapter)

**Files:**
- Create: `octopus-desktop/internal/voice/voice.go`, `octopus-desktop/internal/voice/piper.go`
- Test: `octopus-desktop/internal/voice/piper_test.go`

**Interfaces:**
- Produces (dipakai Task 11 via binding `Speak`):
  - `type TextToSpeech interface { Synthesize(ctx context.Context, text string) ([]byte, error) }` — return WAV bytes
  - `type PiperCLI struct { Bin string; VoicePath string }` — subprocess: `piper --model <voice.onnx> --output_file <tmp.wav>`, teks via stdin
  - `var ErrNotConfigured = errors.New("tts belum dikonfigurasi")`

- [ ] **Step 1: Tulis failing test**

```go
// octopus-desktop/internal/voice/piper_test.go
package voice

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func fakePiper(t *testing.T) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake binary test butuh shell posix")
	}
	// fake piper: baca stdin, tulis "WAV:" + teks ke --output_file
	script := `#!/bin/sh
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--output_file" ]; then out="$2"; shift; fi
  shift
done
text=$(cat)
printf "WAV:%s" "$text" > "$out"
`
	p := filepath.Join(t.TempDir(), "fake-piper")
	if err := os.WriteFile(p, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestSynthesizeReturnsWavBytes(t *testing.T) {
	p := &PiperCLI{Bin: fakePiper(t), VoicePath: "voice.onnx"}
	wav, err := p.Synthesize(context.Background(), "halo dunia")
	if err != nil {
		t.Fatalf("synthesize: %v", err)
	}
	if !strings.HasPrefix(string(wav), "WAV:halo dunia") {
		t.Fatalf("isi wav salah: %q", wav)
	}
}

func TestSynthesizeUnconfigured(t *testing.T) {
	p := &PiperCLI{}
	if _, err := p.Synthesize(context.Background(), "halo"); err == nil {
		t.Fatal("bin kosong harus error")
	}
}
```

- [ ] **Step 2: Run, pastikan gagal**

Run: `go test ./internal/voice/`
Expected: FAIL (undefined PiperCLI).

- [ ] **Step 3: Implementasi**

```go
// octopus-desktop/internal/voice/voice.go
package voice

import (
	"context"
	"errors"
)

var ErrNotConfigured = errors.New("tts belum dikonfigurasi")

type TextToSpeech interface {
	Synthesize(ctx context.Context, text string) ([]byte, error)
}
```

```go
// octopus-desktop/internal/voice/piper.go
package voice

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

type PiperCLI struct {
	Bin       string
	VoicePath string
}

func (p *PiperCLI) Synthesize(ctx context.Context, text string) ([]byte, error) {
	if p.Bin == "" || p.VoicePath == "" {
		return nil, ErrNotConfigured
	}
	tmp, err := os.CreateTemp("", "octo-tts-*.wav")
	if err != nil {
		return nil, err
	}
	tmpName := tmp.Name()
	tmp.Close()
	defer os.Remove(tmpName)

	cmd := exec.CommandContext(ctx, p.Bin,
		"--model", p.VoicePath,
		"--output_file", tmpName,
	)
	cmd.Stdin = strings.NewReader(text)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("piper gagal: %w — %s", err, strings.TrimSpace(stderr.String()))
	}
	return os.ReadFile(tmpName)
}
```

- [ ] **Step 4: Run test, pastikan lulus**

Run: `go test ./internal/voice/ -v`
Expected: 2 PASS.

- [ ] **Step 5: Tambah bindings STT/TTS/assets di `app.go`**

Tambahkan field & method di `App` (modify `octopus-desktop/app.go`):

```go
// tambahan import: encoding/base64,
//   "github.com/codinginid/octopus-desktop/internal/assets"
//   "github.com/codinginid/octopus-desktop/internal/speech"
//   "github.com/codinginid/octopus-desktop/internal/voice"

func (a *App) stt() speech.SpeechToText {
	return &speech.WhisperCLI{Bin: a.cfg.WhisperBin, ModelPath: a.cfg.WhisperModelPath}
}

func (a *App) tts() voice.TextToSpeech {
	return &voice.PiperCLI{Bin: a.cfg.PiperBin, VoicePath: a.cfg.PiperVoicePath}
}

// Transcribe menerima WAV base64 dari frontend, return transkrip.
func (a *App) Transcribe(wavB64 string) (string, error) {
	wav, err := base64.StdEncoding.DecodeString(wavB64)
	if err != nil {
		return "", fmt.Errorf("wav base64 tidak valid: %w", err)
	}
	return a.stt().Transcribe(a.ctx, wav)
}

// Speak sintesis teks → WAV base64 untuk diputar frontend.
func (a *App) Speak(text string) (string, error) {
	wav, err := a.tts().Synthesize(a.ctx, text)
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(wav), nil
}

// DownloadAssets unduh model default; progress via event "assets:progress".
func (a *App) DownloadAssets() error {
	dir := filepath.Join(a.configDir, "models")
	for _, it := range assets.DefaultItems() {
		item := it
		path, err := assets.Download(a.ctx, item, dir, func(done, total int64) {
			runtime.EventsEmit(a.ctx, "assets:progress", map[string]any{
				"name": item.Name, "done": done, "total": total,
			})
		})
		if err != nil {
			return err
		}
		a.mu.Lock()
		switch item.Name {
		case "whisper-base":
			a.cfg.WhisperModelPath = path
		case "piper-voice":
			a.cfg.PiperVoicePath = path
		}
		a.mu.Unlock()
	}
	return settings.Save(a.configDir, a.cfg)
}

// BinaryStatus cek ketersediaan whisper-cli & piper di PATH/settings.
func (a *App) BinaryStatus() map[string]bool {
	find := func(configured, name string) bool {
		if configured != "" {
			_, err := os.Stat(configured)
			return err == nil
		}
		_, err := exec.LookPath(name)
		return err == nil
	}
	return map[string]bool{
		"whisper": find(a.cfg.WhisperBin, "whisper-cli"),
		"piper":   find(a.cfg.PiperBin, "piper"),
	}
}
```

Jika `WhisperBin`/`PiperBin` kosong tapi ada di PATH, resolve saat `stt()`/`tts()` dipanggil: tambahkan helper kecil `resolveBin(configured, name string) string` yang memakai `exec.LookPath`. (Implementasikan langsung, jangan tunda.)

Run: `go build ./... && go test ./...`
Expected: sukses.

- [ ] **Step 6: Commit**

```bash
git add octopus-desktop/internal/voice octopus-desktop/app.go
git commit -m "feat(desktop): port tts piper dan bindings transcribe speak download"
```

---

### Task 11: Frontend — perekam mic, VoiceBar, mode Jarvis

**Files:**
- Create: `octopus-desktop/frontend/src/voice/recorder.ts`, `octopus-desktop/frontend/src/voice/VoiceBar.tsx`, `octopus-desktop/frontend/src/voice/tts.ts`
- Test: `octopus-desktop/frontend/src/voice/recorder.test.ts`
- Modify: `octopus-desktop/frontend/src/App.tsx` (wiring VoiceBar + Jarvis)

**Interfaces:**
- Consumes: binding `window.go.main.App.Transcribe(wavB64)`, `.Speak(text)`, `.GetSettings()`; `ChatView` prop `inputExtra`, `registerSubmit`, `onFinal` (Task 7).
- Produces:
  - `encodeWAV(samples: Float32Array, sampleRate: number): ArrayBuffer` — PCM16 mono WAV (pure, unit-tested)
  - `class MicRecorder { start(): Promise<void>; stop(): Promise<string> }` — return WAV base64 16kHz mono
  - `speak(text: string): Promise<void>` — panggil binding Speak, decode base64, play via `Audio`
  - `<VoiceBar onTranscript={(text) => void} jarvis={bool} onToggleJarvis={fn} />`

- [ ] **Step 1: Tulis failing test encodeWAV**

```ts
// octopus-desktop/frontend/src/voice/recorder.test.ts
import { describe, expect, it } from "vitest";
import { encodeWAV } from "./recorder";

describe("encodeWAV", () => {
  it("menghasilkan header RIFF/WAVE dengan ukuran benar", () => {
    const samples = new Float32Array(16000); // 1 detik silence @16kHz
    const buf = encodeWAV(samples, 16000);
    const view = new DataView(buf);
    const tag = (off: number) =>
      String.fromCharCode(view.getUint8(off), view.getUint8(off + 1), view.getUint8(off + 2), view.getUint8(off + 3));
    expect(tag(0)).toBe("RIFF");
    expect(tag(8)).toBe("WAVE");
    expect(view.getUint32(24, true)).toBe(16000); // sample rate
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(buf.byteLength).toBe(44 + samples.length * 2);
  });

  it("meng-clamp sample di luar [-1,1]", () => {
    const buf = encodeWAV(new Float32Array([2.0, -2.0]), 16000);
    const view = new DataView(buf);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});
```

- [ ] **Step 2: Run, pastikan gagal**

Run: `npm test`
Expected: FAIL (encodeWAV undefined).

- [ ] **Step 3: Implementasi `recorder.ts`**

```ts
// octopus-desktop/frontend/src/voice/recorder.ts
export function encodeWAV(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buf);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

const TARGET_RATE = 16000;

function downsample(input: Float32Array, fromRate: number): Float32Array {
  if (fromRate === TARGET_RATE) return input;
  const ratio = fromRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) out[i] = input[Math.floor(i * ratio)];
  return out;
}

export class MicRecorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private chunks: Float32Array[] = [];
  private node: ScriptProcessorNode | null = null;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.node.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    src.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  async stop(): Promise<string> {
    const rate = this.ctx?.sampleRate ?? TARGET_RATE;
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close();
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const all = new Float32Array(total);
    let off = 0;
    for (const c of this.chunks) {
      all.set(c, off);
      off += c.length;
    }
    const wav = encodeWAV(downsample(all, rate), TARGET_RATE);
    const bytes = new Uint8Array(wav);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return btoa(bin);
  }
}
```

- [ ] **Step 4: Implementasi `tts.ts` dan `VoiceBar.tsx`**

```ts
// octopus-desktop/frontend/src/voice/tts.ts
export async function speak(text: string): Promise<void> {
  const b64 = await window.go.main.App.Speak(text);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = new Audio(url);
  await audio.play().finally(() => URL.revokeObjectURL(url));
}
```

Tambahkan `Transcribe(wavB64: string): Promise<string>` dan `Speak(text: string): Promise<string>` ke deklarasi `GoApp` di `bindings.ts`.

```tsx
// octopus-desktop/frontend/src/voice/VoiceBar.tsx
import { useRef, useState } from "react";
import { MicRecorder } from "./recorder";

export function VoiceBar({
  onTranscript,
  jarvis,
  onToggleJarvis,
}: {
  onTranscript: (text: string) => void;
  jarvis: boolean;
  onToggleJarvis: () => void;
}) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing" | "unavailable">("idle");
  const [error, setError] = useState("");
  const rec = useRef<MicRecorder | null>(null);

  const start = async () => {
    try {
      rec.current = new MicRecorder();
      await rec.current.start();
      setState("recording");
      setError("");
    } catch {
      setState("unavailable");
      setError("Mic tidak tersedia atau izin ditolak — pakai input teks.");
    }
  };

  const stop = async () => {
    if (!rec.current) return;
    setState("transcribing");
    try {
      const wavB64 = await rec.current.stop();
      const text = await window.go.main.App.Transcribe(wavB64);
      if (text) onTranscript(text);
      setState("idle");
    } catch (e) {
      setState("idle");
      setError(`Transkripsi gagal: ${String(e)}`);
    }
  };

  return (
    <div className="voice-bar">
      <button
        className={`mic-button ${state}`}
        disabled={state === "transcribing" || state === "unavailable"}
        onMouseDown={start}
        onMouseUp={stop}
        title="Tahan untuk bicara"
      >
        {state === "recording" ? "🔴" : state === "transcribing" ? "…" : "🎤"}
      </button>
      <label className="jarvis-toggle">
        <input type="checkbox" checked={jarvis} onChange={onToggleJarvis} /> Jarvis
      </label>
      {error && <span className="voice-error">{error}</span>}
    </div>
  );
}
```

- [ ] **Step 5: Wiring di `App.tsx`**

```tsx
// octopus-desktop/frontend/src/App.tsx
import { useEffect, useRef, useState } from "react";
import { ChatView } from "./chat/ChatView";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import "./style.css";

export default function App() {
  const [jarvis, setJarvis] = useState(true);
  const submitRef = useRef<((text: string) => void) | null>(null);

  useEffect(() => {
    window.go.main.App.GetSettings().then((s) => setJarvis(Boolean(s.jarvis_mode)));
  }, []);

  const handleTranscript = (text: string) => {
    if (jarvis) {
      submitRef.current?.(text); // auto-send
    } else {
      window.dispatchEvent(new CustomEvent("voice:draft", { detail: text }));
    }
  };

  const handleFinal = (text: string) => {
    if (jarvis) void speak(text).catch(() => {}); // TTS gagal tidak boleh ganggu chat
  };

  return (
    <ChatView
      onFinal={handleFinal}
      registerSubmit={(fn) => (submitRef.current = fn)}
      inputExtra={
        <VoiceBar onTranscript={handleTranscript} jarvis={jarvis} onToggleJarvis={() => setJarvis(!jarvis)} />
      }
    />
  );
}
```

Di `ChatView`: tambah prop `registerSubmit?: (fn: (text: string) => void) => void` (panggil sekali dalam `useEffect`), dan listener `voice:draft` yang mengisi `setDraft(detail)` — transkrip non-Jarvis masuk input box.

`GetSettings` di `bindings.ts`: tambah `GetSettings(): Promise<Record<string, unknown>>` dan `SaveSettings(s): Promise<void>`.

Catatan platform: untuk macOS tambahkan `NSMicrophoneUsageDescription` di `octopus-desktop/build/darwin/Info.plist` ("Octopus merekam suara untuk perintah voice").

- [ ] **Step 6: Run test + build, coba manual**

```bash
npm test && npm run build && cd .. && go build ./...
wails dev   # smoke test manual: ketik pesan; tahan mic (butuh whisper-cli terinstal)
```
Expected: test PASS; `wails dev` tampil ChatView dengan mic.

- [ ] **Step 7: Commit**

```bash
git add octopus-desktop
git commit -m "feat(desktop): voice bar mode jarvis dengan mic recorder dan tts"
```

---

### Task 12: Login screen + Settings + first-run onboarding

**Files:**
- Create: `octopus-desktop/frontend/src/setup/LoginView.tsx`, `octopus-desktop/frontend/src/setup/SettingsView.tsx`
- Test: `octopus-desktop/frontend/src/setup/setup.test.tsx`
- Modify: `octopus-desktop/frontend/src/App.tsx` (routing sederhana: login → chat; tombol ⚙ buka settings)

**Interfaces:**
- Consumes: bindings `StartLogin`, `PollLogin`, `IsLoggedIn`, `Logout`, `GetSettings`, `SaveSettings`, `DownloadAssets`, `BinaryStatus`; event `assets:progress`.
- Produces: alur first-run lengkap.

Perilaku:
- Saat mount `App`: `IsLoggedIn()` → false ⇒ render `LoginView`.
- `LoginView`: tombol "Login dengan Google" → `StartLogin()` (browser terbuka otomatis) → tampilkan kode → poll `PollLogin(code)` tiap 2 detik hingga `"paired"` → pindah ke chat.
- `SettingsView`: form GatewayURL, toggle Jarvis/TTS, path binary whisper/piper (+ hasil `BinaryStatus`), tombol "Unduh model" dengan progress bar dari event `assets:progress`, tombol Logout.
- Banner koneksi: bila event `stream_error` berisi `unauthorized` ⇒ kembali ke `LoginView`.

- [ ] **Step 1: Tulis failing test**

```tsx
// octopus-desktop/frontend/src/setup/setup.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginView } from "./LoginView";

beforeEach(() => {
  (window as any).go = {
    main: {
      App: {
        StartLogin: vi.fn().mockResolvedValue({ code: "ABCD", login_url: "https://x" }),
        PollLogin: vi.fn().mockResolvedValueOnce("pending").mockResolvedValueOnce("paired"),
      },
    },
  };
});

describe("LoginView", () => {
  it("menampilkan kode setelah start dan memanggil onPaired saat paired", async () => {
    const onPaired = vi.fn();
    render(<LoginView onPaired={onPaired} pollIntervalMs={1} />);
    fireEvent.click(screen.getByRole("button", { name: /login/i }));
    await waitFor(() => expect(screen.getByText("ABCD")).toBeTruthy());
    await waitFor(() => expect(onPaired).toHaveBeenCalled(), { timeout: 2000 });
  });
});
```

- [ ] **Step 2: Run, pastikan gagal**

Run: `npm test`
Expected: FAIL (LoginView belum ada).

- [ ] **Step 3: Implementasi `LoginView.tsx`**

```tsx
// octopus-desktop/frontend/src/setup/LoginView.tsx
import { useEffect, useRef, useState } from "react";

export function LoginView({
  onPaired,
  pollIntervalMs = 2000,
}: {
  onPaired: () => void;
  pollIntervalMs?: number;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);

  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  const start = async () => {
    try {
      const res = await window.go.main.App.StartLogin();
      setCode(String(res.code));
      timer.current = window.setInterval(async () => {
        try {
          const status = await window.go.main.App.PollLogin(String(res.code));
          if (status === "paired") {
            if (timer.current) window.clearInterval(timer.current);
            onPaired();
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          setError(String(e));
        }
      }, pollIntervalMs);
    } catch (e) {
      setError(`Gateway tidak terjangkau: ${String(e)}`);
    }
  };

  return (
    <div className="login-view">
      <h1>Octopus</h1>
      <p>Login untuk terhubung ke gateway Octopus kamu.</p>
      <button onClick={start}>Login dengan Google</button>
      {code && (
        <p>
          Browser terbuka — pastikan kodenya sama: <strong>{code}</strong>
        </p>
      )}
      {error && <p className="voice-error">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Implementasi `SettingsView.tsx`**

```tsx
// octopus-desktop/frontend/src/setup/SettingsView.tsx
import { useEffect, useState } from "react";

type Cfg = Record<string, unknown>;

export function SettingsView({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  const [cfg, setCfg] = useState<Cfg>({});
  const [bins, setBins] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<{ name: string; done: number; total: number } | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    window.go.main.App.GetSettings().then(setCfg);
    window.go.main.App.BinaryStatus().then(setBins);
    return window.runtime.EventsOn("assets:progress", (p) =>
      setProgress(p as { name: string; done: number; total: number }),
    );
  }, []);

  const set = (k: string, v: unknown) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    await window.go.main.App.SaveSettings(cfg);
    onClose();
  };

  const download = async () => {
    setDownloading(true);
    try {
      await window.go.main.App.DownloadAssets();
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="settings-view">
      <h2>Pengaturan</h2>
      <label>
        Gateway URL
        <input value={String(cfg.gateway_url ?? "")} onChange={(e) => set("gateway_url", e.target.value)} />
      </label>
      <label>
        <input type="checkbox" checked={Boolean(cfg.jarvis_mode)} onChange={(e) => set("jarvis_mode", e.target.checked)} />
        Mode Jarvis (auto-send + bacakan jawaban)
      </label>
      <label>
        <input type="checkbox" checked={Boolean(cfg.tts_enabled)} onChange={(e) => set("tts_enabled", e.target.checked)} />
        Suara balasan (TTS)
      </label>
      <div className="bin-status">
        whisper-cli: {bins.whisper ? "✅" : "❌ (install whisper.cpp / isi path di bawah)"} · piper: {bins.piper ? "✅" : "❌"}
      </div>
      <label>
        Path whisper-cli
        <input value={String(cfg.whisper_bin ?? "")} onChange={(e) => set("whisper_bin", e.target.value)} />
      </label>
      <label>
        Path piper
        <input value={String(cfg.piper_bin ?? "")} onChange={(e) => set("piper_bin", e.target.value)} />
      </label>
      <button onClick={download} disabled={downloading}>
        {downloading ? "Mengunduh…" : "Unduh model (Whisper + suara Piper)"}
      </button>
      {progress && (
        <progress value={progress.done} max={Math.max(progress.total, 1)}>
          {progress.name}
        </progress>
      )}
      <div className="settings-actions">
        <button onClick={save}>Simpan</button>
        <button onClick={onClose}>Batal</button>
        <button className="danger" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}
```

Update `bindings.ts` GoApp: tambah `StartLogin(): Promise<Record<string, unknown>>`, `PollLogin(code: string): Promise<string>`, `IsLoggedIn(): Promise<boolean>`, `Logout(): Promise<void>`, `DownloadAssets(): Promise<void>`, `BinaryStatus(): Promise<Record<string, boolean>>`.

Update `App.tsx`: state `screen: "loading" | "login" | "chat"`, cek `IsLoggedIn()` saat mount; tombol ⚙ toggle `SettingsView` overlay; handler `stream_error` dengan pesan mengandung `unauthorized` ⇒ `setScreen("login")` (pasang di `onChatEvent` level App atau lewat callback dari ChatView — pilih yang paling sederhana saat implementasi).

- [ ] **Step 5: Run test + build**

Run: `npm test && npm run build && cd .. && go build ./...`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add octopus-desktop/frontend
git commit -m "feat(desktop): login pairing settings dan onboarding unduh model"
```

---

### Task 13: CI untuk octopus-desktop

**Files:**
- Create: `.github/workflows/octopus-desktop.yml`

**Interfaces:**
- Consumes: struktur test Task 3-12.

- [ ] **Step 1: Tulis workflow**

```yaml
# .github/workflows/octopus-desktop.yml
name: octopus-desktop

on:
  pull_request:
    paths:
      - "octopus-desktop/**"
      - ".github/workflows/octopus-desktop.yml"
  push:
    branches: [main]
    paths:
      - "octopus-desktop/**"

jobs:
  go:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: octopus-desktop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.24"
      - run: go vet ./internal/... .
      - run: go test ./... -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: octopus-desktop/frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - run: npx tsc --noEmit
      - run: npm test
```

Catatan: job Go menjalankan `go test ./...` termasuk `app_test.go`; package `main` Wails perlu asset frontend embed (`frontend/dist`) — bila `go vet`/`go test .` gagal karena embed kosong, tambahkan step `mkdir -p frontend/dist && touch frontend/dist/.keep` sebelum test (template Wails meng-embed `frontend/dist`).

- [ ] **Step 2: Validasi lokal**

```bash
cd octopus-desktop && go vet ./internal/... . && go test ./... && cd frontend && npx tsc --noEmit && npm test
```
Expected: semua hijau.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/octopus-desktop.yml
git commit -m "chore(ci): workflow test go dan frontend octopus desktop"
```

---

### Task 14: Verifikasi end-to-end manual + dokumentasi singkat

- [ ] **Step 1: Jalankan gateway lokal + wails dev**

```bash
# terminal 1 — gateway (ikuti cara existing repo, mis. dev.sh / uvicorn)
./dev.sh   # atau: uvicorn app.interfaces.gateway:app --port 8000
# terminal 2
cd octopus-desktop && wails dev
```

Checklist manual (catat hasil di PR description):
1. Login pairing via browser → masuk chat.
2. Ketik "cek memory" → MetricCard muncul.
3. Perintah medium-risk ("restart service web") → ApprovalCard → Approve → hasil eksekusi masuk.
4. Reject sebuah plan → status rejected.
5. Tahan mic, ucapkan perintah → transkrip → auto-send (mode Jarvis).
6. Jawaban final dibacakan (TTS) saat Jarvis aktif.
7. Matikan gateway di tengah stream → pesan ditandai error retryable, app tidak crash.

- [ ] **Step 2: Update README singkat**

Tambahkan seksi "Desktop app" di `README.md` (5-8 baris: apa itu, cara build `wails build`, dependency whisper-cli/piper). Jangan buat file docs baru.

- [ ] **Step 3: Commit + push + PR**

```bash
git add README.md
git commit -m "docs: seksi octopus desktop di readme"
git push origin feat/octopus-desktop-app
# Buat PR: "feat: aplikasi desktop octopus (wails) dengan voice mode jarvis"
```
