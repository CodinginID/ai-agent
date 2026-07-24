package main

import (
	"errors"
	"sync"
	"testing"

	"github.com/codinginid/octopus-desktop/internal/gateway"
	"github.com/codinginid/octopus-desktop/internal/settings"
	"github.com/zalando/go-keyring"
)

func TestRelayEventsForwardsAllThenStreamError(t *testing.T) {
	out := make(chan gateway.Event, 3)
	out <- gateway.Event{Type: "thinking", Data: map[string]any{"message": "m"}}
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)

	var got []map[string]any
	emit := func(payload map[string]any) { got = append(got, payload) }

	relayEvents("msg-1", out, errors.New("putus"), emit, func(map[string]any) {})

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

// Regression: GetSettings dan SaveSettings harus aman dipanggil bersamaan
// (jalankan dengan -race). App dibuat manual tanpa runtime Wails —
// SaveSettings hanya menyentuh settings.Save + keyring (di-mock) + mutex.
func TestConcurrentSettingsAccessNoRace(t *testing.T) {
	keyring.MockInit()
	a := &App{
		cfg:       settings.Settings{GatewayURL: "https://a.example.com", JarvisMode: true, TTSEnabled: true},
		configDir: t.TempDir(),
		client:    gateway.New("https://a.example.com", ""),
	}

	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		for range 100 {
			_ = a.GetSettings()
		}
	}()
	go func() {
		defer wg.Done()
		for range 100 {
			if err := a.SaveSettings(settings.Settings{GatewayURL: "https://b.example.com"}); err != nil {
				t.Errorf("save settings: %v", err)
				return
			}
		}
	}()
	wg.Wait()
}

func TestRelayEventsNoErrorNoStreamError(t *testing.T) {
	out := make(chan gateway.Event, 1)
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)
	var got []map[string]any
	relayEvents("m", out, nil, func(p map[string]any) { got = append(got, p) }, func(map[string]any) {})
	if len(got) != 1 {
		t.Fatalf("tidak boleh ada stream_error: %+v", got)
	}
}
