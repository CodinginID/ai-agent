// octopus-desktop/internal/gateway/client.go
package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/codinginid/octopus-desktop/internal/settings"
	"github.com/codinginid/octopus-desktop/internal/storage"
)

var ErrUnauthorized = errors.New("unauthorized")

type Client struct {
	baseURL string
	token   string
	http    *http.Client
	// localDB opsional — nil kalau tidak di-set, berarti tidak ada cache offline.
	localDB *storage.LocalDB
}

func New(baseURL, token string) *Client {
	return &Client{
		baseURL: baseURL,
		token:   token,
		// Tanpa timeout global: batas waktu diserahkan ke context caller
		// (stream bisa berjalan lama); hanya Reject yang pakai timeout eksplisit.
		http: &http.Client{},
	}
}

type LoginStart struct {
	Code         string `json:"code"`
	LoginURL     string `json:"login_url"`
	ExpiresInSec int    `json:"expires_in_sec"`
}

func (c *Client) requestJSON(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var bodyReader *bytes.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("siapkan request %s: %w", path, err)
		}
		bodyReader = bytes.NewReader(raw)
	}

	var req *http.Request
	var err error
	if bodyReader != nil {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, bodyReader)
	} else {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, nil)
	}
	if err != nil {
		return nil, fmt.Errorf("siapkan request %s: %w", path, err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}
	if key, err := settings.PersonalKey(); err == nil && key != "" {
		req.Header.Set("X-Personal-Anthropic-Key", key)
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

func (c *Client) postJSON(ctx context.Context, path string, body any) (*http.Response, error) {
	return c.requestJSON(ctx, http.MethodPost, path, body)
}

func (c *Client) getJSON(ctx context.Context, path string) (*http.Response, error) {
	return c.requestJSON(ctx, http.MethodGet, path, nil)
}

func (c *Client) putJSON(ctx context.Context, path string, body any) (*http.Response, error) {
	return c.requestJSON(ctx, http.MethodPut, path, body)
}

func (c *Client) StartLogin(ctx context.Context) (LoginStart, error) {
	resp, err := c.postJSON(ctx, "/auth/tui/start", map[string]string{})
	if err != nil {
		return LoginStart{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return LoginStart{}, fmt.Errorf("/auth/tui/start gagal: HTTP %d", resp.StatusCode)
	}
	var ls LoginStart
	if err := json.NewDecoder(resp.Body).Decode(&ls); err != nil {
		return LoginStart{}, fmt.Errorf("decode respons /auth/tui/start: %w", err)
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
		return "", false, fmt.Errorf("decode respons /auth/tui/poll: %w", err)
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
	// Jika gateway tidak terjangkau, antri pesan ke lokal DB supaya bisa
	// disinkronkan nanti saat reconnect.
	if err := c.http.Do(c.makeTestReq(ctx)); err != nil && c.localDB != nil {
		if saveErr := c.localDB.QueueMessage(text); saveErr != nil {
			slog.Warn("gagal antri pesan offline", "error", saveErr)
		}
		out <- Event{Type: "stream_error", Data: map[string]any{"message": "gateway tidak terjangkau, pesan diantri"}}
		close(out)
		return nil
	}
	return c.stream(ctx, "/chat/send", map[string]string{"text": text}, out)
}

// makeTestReq buatkan request dummy hanya untuk tes koneksi HTTP tanpa
// mengirim payload ke server. Jika request berhasil, berarti gateway reachable.
func (c *Client) makeTestReq(ctx context.Context) *http.Request {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/auth/me", nil)
	return req
}

// SetLocalDB pasang cache lokal untuk offline mode.
func (c *Client) SetLocalDB(db *storage.LocalDB) {
	c.localDB = db
}

// SyncPendingMessages kirim semua pesan yang masih pending ke gateway.
func (c *Client) SyncPendingMessages(ctx context.Context) {
	if c.localDB == nil {
		return
	}
	pending, err := c.localDB.GetPendingMessages()
	if err != nil {
		slog.Warn("gagal ambil pesan pending untuk sinkronisasi", "error", err)
		return
	}
	if len(pending) == 0 {
		return
	}
	slog.Info("sinkronisasi pesan offline", "count", len(pending))

	for _, msg := range pending {
		if err := c.stream(ctx, "/chat/send", map[string]string{"text": msg.Text}, nil); err != nil {
			slog.Warn("sinkronisasi pesan gagal", "id", msg.ID, "error", err)
			continue
		}
		if err := c.localDB.MarkSent(msg.ID); err != nil {
			slog.Warn("tandai pesan terkirim gagal", "id", msg.ID, "error", err)
		}
	}
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
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("/chat/reject gagal: HTTP %d", resp.StatusCode)
	}
	var out struct {
		OK bool `json:"ok"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return false, fmt.Errorf("decode respons /chat/reject: %w", err)
	}
	return out.OK, nil
}

func (c *Client) GetProvider(ctx context.Context) (map[string]any, error) {
	resp, err := c.getJSON(ctx, "/provider")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET /provider gagal: HTTP %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("decode /provider: %w", err)
	}
	return out, nil
}

func (c *Client) SetProvider(ctx context.Context, provider, model string) error {
	body := map[string]any{"provider": provider}
	if model != "" {
		body["model"] = model
	}
	resp, err := c.postJSON(ctx, "/provider", body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("POST /provider gagal: HTTP %d", resp.StatusCode)
	}
	return nil
}

func (c *Client) GetAgents(ctx context.Context) (map[string]any, error) {
	resp, err := c.getJSON(ctx, "/me/agents")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET /me/agents gagal: HTTP %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("decode /me/agents: %w", err)
	}
	return out, nil
}

func (c *Client) ToggleAgent(ctx context.Context, agentID string, enabled bool) error {
	resp, err := c.putJSON(ctx, "/me/agents/"+agentID, map[string]any{"enabled": enabled})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("PUT /me/agents/%s gagal: HTTP %d", agentID, resp.StatusCode)
	}
	return nil
}

// UpdateInfo berisi detail update dari GitHub release terakhir.
// Empty strings pada field berarti data belum tersedia (mis. saat parsing gagal).
type UpdateInfo struct {
	CurrentVersion string `json:"current_version"`
	LatestVersion  string `json:"latest_version"`
	DownloadURL    string `json:"download_url"`
	ReleaseNotes   string `json:"release_notes"`
}

// CheckForUpdates mengecek versi terbaru di GitHub releases dan mengembalikan
// string terbaru bila versi berbeda, atau string kosong bila sudah terbaru.
// Caller tetap butuh UpdateInfo lengkap (judul, URL download) untuk dialog;
// metode ini hanya memberi sinyal cepat apakah ada update yang perlu ditawarkan.
func (c *Client) CheckForUpdates(ctx context.Context, currentVersion string) (UpdateInfo, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		"https://api.github.com/repos/codinginid/ai-agent/releases/latest", nil)
	if err != nil {
		return UpdateInfo{}, fmt.Errorf("siapkan request github releases: %w", err)
	}
	req.Header.Set("Accept", "application/vnd.github.v3+json")
	req.Header.Set("User-Agent", "octopus-desktop")

	resp, err := c.http.Do(req)
	if err != nil {
		return UpdateInfo{}, fmt.Errorf("fetch github releases: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return UpdateInfo{}, fmt.Errorf("github releases HTTP %d", resp.StatusCode)
	}

	var raw struct {
		TagName    string `json:"tag_name"`
		Name       string `json:"name"`
		HTMLURL    string `json:"html_url"`
		Body       string `json:"body"`
		Assets     []struct {
			Name               string `json:"name"`
			BrowserDownloadURL string `json:"browser_download_url"`
		} `json:"assets"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return UpdateInfo{}, fmt.Errorf("decode github releases: %w", err)
	}

	latest := strings.TrimPrefix(raw.TagName, "v")
	current := strings.TrimPrefix(currentVersion, "v")

	downloadURL := ""
	for _, a := range raw.Assets {
		if strings.Contains(a.Name, "octopus-desktop") {
			downloadURL = a.BrowserDownloadURL
			break
		}
	}

	return UpdateInfo{
		CurrentVersion: currentVersion,
		LatestVersion:  raw.TagName,
		DownloadURL:    downloadURL,
		ReleaseNotes:   raw.Name + "\n" + raw.Body,
	}, latest != current
}
