package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	modelassets "github.com/codinginid/octopus-desktop/internal/assets"
	"github.com/codinginid/octopus-desktop/internal/gateway"
	"github.com/codinginid/octopus-desktop/internal/speech"
	"github.com/codinginid/octopus-desktop/internal/settings"
	"github.com/codinginid/octopus-desktop/internal/storage"
	"github.com/codinginid/octopus-desktop/internal/voice"
	"github.com/wailsapp/wails/v2/pkg/menu"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/menu"
	"github.com/wailsapp/wails/v2/pkg/menu/keys"
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
	localDB   *storage.LocalDB

	// currentVersion diisi saat build lewat -ldflags; kosong = dev build.
	currentVersion string
	// updateChecked menandai apakah sudah pernah cek update supaya tidak
	// spam log saat startup.
	updateChecked bool
	// updateCheckNext dijadwalkan untuk cek berikutnya (24 jam dari startup).
	updateCheckNext time.Time
	// updateInfo menyimpan info update terakhir untuk dialog.
	updateInfo *gateway.UpdateInfo
}

// version saat ini dari wails.json (dev). Production build diisi lewat -ldflags.
const currentVersion = "0.1.0"

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

	// Inisialisasi cache offline — error diabaikan karena opsional
	dbPath := filepath.Join(dir, "cache.db")
	localDB, err := storage.NewLocalDB(dbPath)
	if err != nil {
		slog.Warn("gagal buka cache database, mode offline nonaktif", "error", err)
		localDB = nil
	} else if err := localDB.Open(); err != nil {
		slog.Warn("gagal buka tabel cache, mode offline nonaktif", "error", err)
		_ = localDB.Close()
		localDB = nil
	}

	a := &App{cfg: cfg, configDir: dir, localDB: localDB}
	token, _ := settings.Token()
	a.client = gateway.New(cfg.GatewayURL, token)
	if localDB != nil {
		a.client.SetLocalDB(localDB)
	}
	return a
}

// startup is called when the app starts. The context is saved
// so we can call the runtime methods
func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.currentVersion = currentVersion
	// Jalankan cek update pertama, lalu jadwalkan ulang tiap 24 jam.
	go a.checkForUpdates()
	a.updateCheckNext = time.Now().Add(24 * time.Hour)
	go a.periodicUpdateCheck()
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

// resolveBin mencari executable: path dari settings (bila ada & valid),
// lalu PATH, lalu extraDirs. Aplikasi GUI macOS tidak mewarisi PATH shell,
// jadi lokasi Homebrew dkk. wajib dicek eksplisit lewat extraDirs.
func resolveBin(configured, name string, extraDirs ...string) string {
	if configured != "" {
		if info, err := os.Stat(configured); err == nil && !info.IsDir() {
			return configured
		}
	}
	if p, err := exec.LookPath(name); err == nil {
		return p
	}
	for _, dir := range extraDirs {
		p := filepath.Join(dir, name)
		if info, err := os.Stat(p); err == nil && !info.IsDir() {
			return p
		}
	}
	return ""
}

// binSearchDirs: bin/piper hasil DownloadAssets, lalu prefix Homebrew (arm64
// & intel) dan /usr/local/bin untuk instalasi manual.
func (a *App) binSearchDirs() []string {
	return []string{
		filepath.Join(a.configDir, "bin", "piper"),
		"/opt/homebrew/bin",
		"/usr/local/bin",
	}
}

func (a *App) stt() speech.SpeechToText {
	a.mu.Lock()
	defer a.mu.Unlock()
	bin := resolveBin(a.cfg.WhisperBin, "whisper-cli", a.binSearchDirs()...)
	return &speech.WhisperCLI{Bin: bin, ModelPath: a.cfg.WhisperModelPath}
}

// tts memilih engine: piper bila ada (kualitas lebih baik), kalau tidak
// fallback ke `say` bawaan macOS supaya TTS tetap jalan tanpa instalasi.
func (a *App) tts() voice.TextToSpeech {
	a.mu.Lock()
	defer a.mu.Unlock()
	bin := resolveBin(a.cfg.PiperBin, "piper", a.binSearchDirs()...)
	if bin != "" && a.cfg.PiperVoicePath != "" {
		return &voice.PiperCLI{Bin: bin, VoicePath: a.cfg.PiperVoicePath}
	}
	if say := resolveBin("", "say", "/usr/bin"); say != "" {
		v := ""
		if a.cfg.Language == "" || a.cfg.Language == "id" {
			v = "Damayanti" // suara id_ID; SayCLI fallback ke default bila belum terpasang
		}
		return &voice.SayCLI{Bin: say, Voice: v}
	}
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
	if err := a.installPiperBinary(); err != nil {
		return err
	}

	a.mu.Lock()
	cfgCopy := a.cfg
	a.mu.Unlock()
	return settings.Save(a.configDir, cfgCopy)
}

// installPiperBinary unduh & ekstrak prebuilt piper resmi ke configDir/bin
// bila belum ada piper yang bisa dipakai. No-op bila sudah ada atau platform
// tidak punya prebuilt (whisper-cli tetap harus dari brew — tidak ada rilis
// binary macOS resmi dari whisper.cpp).
func (a *App) installPiperBinary() error {
	a.mu.Lock()
	configured := a.cfg.PiperBin
	a.mu.Unlock()
	if resolveBin(configured, "piper", a.binSearchDirs()...) != "" {
		return nil
	}
	item, ok := modelassets.PiperBinaryItem()
	if !ok {
		return nil
	}
	binDir := filepath.Join(a.configDir, "bin")
	archive, err := modelassets.Download(a.ctx, item, binDir, func(done, total int64) {
		runtime.EventsEmit(a.ctx, "assets:progress", map[string]any{
			"name":  item.Name,
			"done":  done,
			"total": total,
		})
	})
	if err != nil {
		return err
	}
	defer os.Remove(archive)
	if err := modelassets.ExtractTarGz(archive, binDir); err != nil {
		return err
	}
	a.mu.Lock()
	a.cfg.PiperBin = filepath.Join(binDir, "piper", "piper")
	a.mu.Unlock()
	return nil
}

// BinaryStatus mengembalikan path whisper-cli & piper yang ter-resolve
// (string kosong = tidak ditemukan) supaya UI bisa menampilkan lokasi.
func (a *App) BinaryStatus() map[string]string {
	a.mu.Lock()
	cfg := a.cfg
	a.mu.Unlock()
	dirs := a.binSearchDirs()
	return map[string]string{
		"whisper": resolveBin(cfg.WhisperBin, "whisper-cli", dirs...),
		"piper":   resolveBin(cfg.PiperBin, "piper", dirs...),
		"say":     resolveBin("", "say", "/usr/bin"),
	}
}

// checkForUpdates jalankan sekali pada startup: fetch GitHub releases,
// bandingkan versi, tampilkan dialog bila ada update. Error di-log saja —
// tidak boleh memblokir startup aplikasi.
func (a *App) checkForUpdates() {
	a.mu.Lock()
	if a.updateChecked {
		a.mu.Unlock()
		return
	}
	a.updateChecked = true
	a.mu.Unlock()

	ctx, cancel := context.WithTimeout(a.ctx, 15*time.Second)
	defer cancel()

	ver := currentVersion
	c := a.gw()
	info, err := c.CheckForUpdates(ctx, ver)
	if err != nil {
		slog.Warn("cek update gagal", "error", err)
		return
	}
	a.mu.Lock()
	a.updateInfo = &info
	a.mu.Unlock()

	hasUpdate := info.LatestVersion != "" && info.LatestVersion != ver
	if !hasUpdate {
		return
	}
	a.showUpdateDialog(info)
}

// periodicUpdateCheck sleep 24 jam, lalu jalankan checkForUpdates ulang.
// Loop berjalan sepanjang app hidup.
func (a *App) periodicUpdateCheck() {
	ticker := time.NewTicker(24 * time.Hour)
	defer ticker.Stop()
	for range ticker.C {
		a.checkForUpdates()
	}
}

// showUpdateDialog tampilkan dialog Wails yang menawarkan download update.
// Dialog ini hanya bisa dipanggil dari goroutine UI utama; karena cek update
// berjalan di goroutine background, panggil runtime.WindowShow dulu supaya
// dialog muncul di foreground window.
func (a *App) showUpdateDialog(info gateway.UpdateInfo) {
	runtime.WindowShow(a.ctx)

	title := "Update tersedia"
	message := fmt.Sprintf(
		"Versi %s tersedia (saat ini %s).\n\n%s",
		info.LatestVersion, info.CurrentVersion, info.ReleaseNotes,
	)

	dialogOptions := runtime.DialogOptions{
		Type:       runtime.DialogTypeInformation,
		Title:      title,
		Message:    message,
		Buttons:    []string{"Update", "Skip"},
		Cancelable: true,
		Default:    "Skip",
	}

	chosen, err := runtime.Dialog(a.ctx, dialogOptions)
	if err != nil {
		slog.Warn("dialog update gagal", "error", err)
		return
	}

	if chosen == "Update" && info.DownloadURL != "" {
		go a.downloadUpdate(info.DownloadURL)
	}
}

// downloadUpdate unduh binary update ke configDir lalu buka folder hasil download.
// Download dilakukan di goroutine background supaya UI tidak frozen.
func (a *App) downloadUpdate(downloadURL string) {
	slog.Info("unduh update", "url", downloadURL)

	// Parse URL untuk dapat nama file.
	u, err := url.Parse(downloadURL)
	if err != nil {
		slog.Warn("parse URL download gagal", "error", err)
		runtime.WindowMessage(a.ctx, "Gagal", "URL download tidak valid")
		return
	}
	filename := filepath.Base(u.Path)
	if filename == "" || filename == "." {
		filename = "octopus-desktop-update.zip"
	}

	destDir := filepath.Join(a.configDir, "downloads")
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		slog.Warn("buat folder downloads gagal", "error", err)
		return
	}

	destFile := filepath.Join(destDir, filename)
	req, err := http.NewRequestWithContext(a.ctx, http.MethodGet, downloadURL, nil)
	if err != nil {
		slog.Warn("siapkan request download gagal", "error", err)
		return
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		slog.Warn("download gagal", "error", err)
		runtime.WindowMessage(a.ctx, "Gagal", fmt.Sprintf("Download update gagal: %v", err))
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Warn("download HTTP gagal", "status", resp.StatusCode)
		runtime.WindowMessage(a.ctx, "Gagal", fmt.Sprintf("Download gagal: HTTP %d", resp.StatusCode))
		return
	}

	f, err := os.Create(destFile)
	if err != nil {
		slog.Warn("buat file download gagal", "error", err)
		return
	}
	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(destFile)
		slog.Warn("tulis file download gagal", "error", err)
		runtime.WindowMessage(a.ctx, "Gagal", fmt.Sprintf("Simpan update gagal: %v", err))
		return
	}
	if err := f.Close(); err != nil {
		os.Remove(destFile)
		slog.Warn("tutup file download gagal", "error", err)
		return
	}

	slog.Info("update berhasil didownload", "path", destFile)
	// Buka folder downloads untuk user install manual.
	_ = exec.Command("open", destDir).Start()
}
