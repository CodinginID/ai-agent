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

	"github.com/codinginid/octopus-desktop/internal/settings"
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
