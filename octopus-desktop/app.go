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

// App menyimpan state runtime Wails dan dependency yang di-inject lewat NewApp.
type App struct {
	ctx       context.Context
	mu        sync.Mutex
	cfg       settings.Settings
	configDir string
	client    *gateway.Client
}

// NewApp creates a new App application struct
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

// startup is called when the app starts. The context is saved
// so we can call the runtime methods
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
}

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

// gw membaca client di bawah mutex karena PollLogin dan SaveSettings bisa
// mengganti client saat binding lain sedang berjalan di goroutine terpisah.
func (a *App) gw() *gateway.Client {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.client
}

// runStream mengirim tiap event ke frontend saat event itu tiba (bukan
// menunggu stream selesai), lalu setelah channel ditutup baca err dari
// done-channel untuk emit stream_error bila perlu.
func (a *App) runStream(msgID string, run func(chan<- gateway.Event) error) {
	out := make(chan gateway.Event, 32)
	done := make(chan error, 1)
	go func() { done <- run(out) }()
	for ev := range out {
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
		return a.gw().SendChat(a.ctx, text, out)
	})
}

func (a *App) ApprovePlan(msgID, planID string) {
	go a.runStream(msgID, func(out chan<- gateway.Event) error {
		return a.gw().Approve(a.ctx, planID, out)
	})
}

func (a *App) RejectPlan(planID string) (bool, error) {
	return a.gw().Reject(a.ctx, planID)
}

func (a *App) StartLogin() (map[string]any, error) {
	ls, err := a.gw().StartLogin(a.ctx)
	if err != nil {
		return nil, err
	}
	runtime.BrowserOpenURL(a.ctx, ls.LoginURL)
	return map[string]any{"code": ls.Code, "login_url": ls.LoginURL}, nil
}

func (a *App) PollLogin(code string) (string, error) {
	token, pending, err := a.gw().PollLogin(a.ctx, code)
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
