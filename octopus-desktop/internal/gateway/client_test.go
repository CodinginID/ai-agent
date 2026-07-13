// octopus-desktop/internal/gateway/client_test.go
package gateway

import (
	"context"
	"encoding/json"
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

func TestApproveParsesSSEEvents(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/approve" {
			t.Errorf("path salah: %s", r.URL.Path)
		}
		var body struct {
			PlanID string `json:"plan_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.PlanID != "plan-1" {
			t.Errorf("body plan_id salah: %+v err=%v", body, err)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "event: action_started\ndata: {\"action\":\"restart\"}\n\n")
		fmt.Fprint(w, "event: final\ndata: {\"text\":\"beres\"}\n\n")
		fmt.Fprint(w, "event: done\ndata: {}\n\n")
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	evs, err := collect(t, func(out chan<- Event) error {
		return c.Approve(context.Background(), "plan-1", out)
	})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(evs) != 2 || evs[0].Type != "action_started" || evs[1].Type != "final" {
		t.Fatalf("events salah: %+v", evs)
	}
}

func TestStartLoginServerErrorReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprint(w, `{"detail":"boom"}`)
	}))
	defer srv.Close()

	_, err := New(srv.URL, "").StartLogin(context.Background())
	if err == nil {
		t.Fatal("HTTP 500 harus menghasilkan error, bukan zero value")
	}
}

func TestRejectServerErrorReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprint(w, `{"detail":"boom"}`)
	}))
	defer srv.Close()

	ok, err := New(srv.URL, "tok").Reject(context.Background(), "plan-1")
	if err == nil {
		t.Fatal("HTTP 500 harus menghasilkan error")
	}
	if ok {
		t.Fatal("ok harus false saat server error")
	}
}
