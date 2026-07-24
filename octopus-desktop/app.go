package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"

	modelassets "github.com/codinginid/octopus-desktop/internal/assets"
	"github.com/codinginid/octopus-desktop/internal/gateway"
	"github.com/codinginid/octopus-desktop/internal/speech"
	"github.com/codinginid/octopus-desktop/internal/settings"
	"github.com/codinginid/octopus-desktop/internal/voice"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// relayEvents iterate channel event, emit tiap event ke channel utama,
// emit avatar event ke channel terpisah bila event menandakan worker lifecycle,
// lalu emit stream_error bila err != nil.
func relayEvents(msgID string, out <-chan gateway.Event, err error,
	emit func(map[string]any), emitAvatar func(map[string]any)) {
	for ev := range out {
		emit(map[string]any{"msgId": msgID, "type": ev.Type, "data": ev.Data})

		if avatarEventTypes[ev.Type] {
			emitAvatar(map[string]any{"msgId": msgID, "type": ev.Type, "data": ev.Data})
		}
	}
	if err != nil {
		emit(map[string]any{
			"msgId": msgID, "type": "stream_error",
			"data": map[string]any{"message": err.Error()},
		})
	}
}

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
		cfg = settings.Settings{GatewayURL: "http://localhost:8080", JarvisMode: true, TTSEnabled: true}
	}
	if cfg.GatewayURL == "" {
		cfg.GatewayURL = "http://localhost:8080"
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

// avatarEventTypes adalah set event type dari backend yang menandakan worker lifecycle.
// Saat terima event ini, backend juga emit "avatar:event" supaya AvatarSystem bisa update state.
var avatarEventTypes = map[string]bool{
	"worker:started": true,
	"worker:progress": true,
	"worker:completed": true,
	"worker:error": true,
}

func (a *App) emit(payload map[string]any) {
	runtime.EventsEmit(a.ctx, "chat:event", payload)
}

// emitAvatar emit ke channel "avatar:event" untuk AvatarSystem (frontend).
func (a *App) emitAvatar(payload map[string]any) {
	runtime.EventsEmit(a.ctx, "avatar:event", payload)
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
// Emit juga avatar events untuk worker lifecycle.
func (a *App) runStream(msgID string, run func(chan<- gateway.Event) error) {
	out := make(chan gateway.Event, 32)
	done := make(chan error, 1)
	go func() { done <- run(out) }()
	relayEvents(msgID, out, <-done, a.emit, a.emitAvatar)
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

func (a *App) GetSettings() settings.Settings {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.cfg
}

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

func (a *App) GetProvider() (map[string]any, error) {
	return a.gw().GetProvider(context.Background())
}

func (a *App) SetProvider(provider, model string) error {
	return a.gw().SetProvider(context.Background(), provider, model)
}

func (a *App) GetAgents() (map[string]any, error) {
	return a.gw().GetAgents(context.Background())
}

func (a *App) ToggleAgent(agentID string, enabled bool) error {
	return a.gw().ToggleAgent(context.Background(), agentID, enabled)
}

func (a *App) GetPersonalKey() (string, error) {
	k, err := settings.PersonalKey()
	if err != nil {
		return "", nil // Return empty if not found/error
	}
	return k, nil
}

func (a *App) SavePersonalKey(key string) error {
	return settings.SavePersonalKey(key)
}

func (a *App) DeletePersonalKey() error {
	return settings.DeletePersonalKey()
}

func resolveBin(configured, name string) string {
	if configured != "" {
		return configured
	}
	p, err := exec.LookPath(name)
	if err == nil {
		return p
	}
	return ""
}

func (a *App) stt() speech.SpeechToText {
	a.mu.Lock()
	defer a.mu.Unlock()
	bin := resolveBin(a.cfg.WhisperBin, "whisper-cli")
	return &speech.WhisperCLI{Bin: bin, ModelPath: a.cfg.WhisperModelPath}
}

func (a *App) tts() voice.TextToSpeech {
	a.mu.Lock()
	defer a.mu.Unlock()
	bin := resolveBin(a.cfg.PiperBin, "piper")
	return &voice.PiperCLI{Bin: bin, VoicePath: a.cfg.PiperVoicePath}
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
	for _, it := range modelassets.DefaultItems() {
		item := it
		path, err := modelassets.Download(a.ctx, item, dir, func(done, total int64) {
			runtime.EventsEmit(a.ctx, "assets:progress", map[string]any{
				"name":  item.Name,
				"done":  done,
				"total": total,
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
	a.mu.Lock()
	cfgCopy := a.cfg
	a.mu.Unlock()
	return settings.Save(a.configDir, cfgCopy)
}

// BinaryStatus cek ketersediaan whisper-cli & piper di PATH/settings.
func (a *App) BinaryStatus() map[string]bool {
	a.mu.Lock()
	cfg := a.cfg
	a.mu.Unlock()
	find := func(configured, name string) bool {
		if configured != "" {
			_, err := os.Stat(configured)
			return err == nil
		}
		_, err := exec.LookPath(name)
		return err == nil
	}
	return map[string]bool{
		"whisper": find(cfg.WhisperBin, "whisper-cli"),
		"piper":   find(cfg.PiperBin, "piper"),
	}
}
