// Package api provides HTTP functions for communicating with the Octopus backend.
package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ErrLoginAborted is returned when the backend signals that the pair code
// has expired or is unknown (HTTP 410).
var ErrLoginAborted = errors.New("login aborted: code expired or unknown")

// clientWithTimeout returns a new HTTP client with the given timeout.
func clientWithTimeout(d time.Duration) *http.Client {
	return &http.Client{Timeout: d}
}

func doJSON(c *http.Client, method, url string, body any, headers map[string]string) ([]byte, int, error) {
	var bodyReader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, 0, fmt.Errorf("marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		return nil, 0, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := c.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, resp.StatusCode, err
	}
	return data, resp.StatusCode, nil
}

func bearerHeader(token string) map[string]string {
	return map[string]string{"Authorization": "Bearer " + token}
}

// Health checks the backend liveness endpoint.
// Returns (reachable, mode, error).
func Health(baseURL string) (bool, string, error) {
	c := clientWithTimeout(5 * time.Second)
	data, status, err := doJSON(c, http.MethodGet, baseURL+"/health", nil, nil)
	if err != nil {
		return false, "", err
	}
	if status != http.StatusOK {
		return false, "", fmt.Errorf("HTTP %d", status)
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return true, "", nil
	}
	mode, _ := payload["mode"].(string)
	return true, mode, nil
}

// AdminStatus fetches /admin/status with an admin bearer token.
func AdminStatus(baseURL, adminToken string) (map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	data, status, err := doJSON(c, http.MethodGet, baseURL+"/admin/status", nil, bearerHeader(adminToken))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// AdminUsers fetches the list of registered users.
func AdminUsers(baseURL, adminToken string) ([]map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	data, status, err := doJSON(c, http.MethodGet, baseURL+"/admin/users", nil, bearerHeader(adminToken))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return nil, err
	}
	users, _ := payload["users"].([]any)
	result := make([]map[string]any, 0, len(users))
	for _, u := range users {
		if m, ok := u.(map[string]any); ok {
			result = append(result, m)
		}
	}
	return result, nil
}

// AdminLogout forces a logout for a specific user email via admin endpoint.
func AdminLogout(baseURL, adminToken, email string) (map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	url := fmt.Sprintf("%s/admin/logout/%s", baseURL, email)
	data, status, err := doJSON(c, http.MethodPost, url, nil, bearerHeader(adminToken))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// AdminAudit fetches the last n audit log entries.
func AdminAudit(baseURL, adminToken string, n int) ([]map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	url := fmt.Sprintf("%s/admin/audit?n=%d", baseURL, n)
	data, status, err := doJSON(c, http.MethodGet, url, nil, bearerHeader(adminToken))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result []map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		// Some backends wrap in an object.
		var wrapper map[string]any
		if err2 := json.Unmarshal(data, &wrapper); err2 == nil {
			if entries, ok := wrapper["entries"].([]any); ok {
				for _, e := range entries {
					if m, ok := e.(map[string]any); ok {
						result = append(result, m)
					}
				}
				return result, nil
			}
		}
		return nil, err
	}
	return result, nil
}

// Me fetches the authenticated user's profile.
func Me(baseURL, token string) (map[string]any, error) {
	c := clientWithTimeout(15 * time.Second)
	data, status, err := doJSON(c, http.MethodGet, baseURL+"/auth/me", nil, bearerHeader(token))
	if err != nil {
		return nil, err
	}
	if status == http.StatusUnauthorized {
		return nil, fmt.Errorf("session expired (HTTP 401)")
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// TUIStart initiates a new QR login session.
// Returns (code, loginURL, error).
func TUIStart(baseURL string) (string, string, error) {
	c := clientWithTimeout(5 * time.Second)
	data, status, err := doJSON(c, http.MethodPost, baseURL+"/auth/tui/start", nil, nil)
	if err != nil {
		return "", "", err
	}
	if status != http.StatusOK {
		return "", "", fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return "", "", err
	}
	code, _ := payload["code"].(string)
	loginURL, _ := payload["login_url"].(string)
	return code, loginURL, nil
}

// TUIPoll checks whether the QR code has been scanned and paired.
// Returns (token, pending, error).
// pending=true means the user hasn't scanned yet.
// ErrLoginAborted is returned when the backend signals 410.
func TUIPoll(baseURL, code string) (string, bool, error) {
	c := clientWithTimeout(5 * time.Second)
	body := map[string]string{"code": code}
	data, status, err := doJSON(c, http.MethodPost, baseURL+"/auth/tui/poll", body, nil)
	if err != nil {
		// Network error — treat as pending to allow retry.
		return "", true, nil
	}
	if status == 410 {
		return "", false, ErrLoginAborted
	}
	if status == http.StatusAccepted || status == 202 {
		return "", true, nil
	}
	if status == http.StatusOK {
		var payload map[string]any
		if err := json.Unmarshal(data, &payload); err != nil {
			return "", false, ErrLoginAborted
		}
		pairedStatus, _ := payload["status"].(string)
		token, _ := payload["session_token"].(string)
		if pairedStatus == "paired" && token != "" {
			return token, false, nil
		}
		return "", false, ErrLoginAborted
	}
	// Any other unexpected status → keep polling.
	return "", true, nil
}

// TUILogout revokes the current TUI session on the backend.
func TUILogout(baseURL, token string) error {
	c := clientWithTimeout(5 * time.Second)
	_, status, err := doJSON(c, http.MethodPost, baseURL+"/auth/tui/logout", nil, bearerHeader(token))
	if err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("HTTP %d", status)
	}
	return nil
}

// TelegramGetMe validates a Telegram bot token and returns the bot's username.
// Calls the official Telegram Bot API getMe endpoint.
func TelegramGetMe(botToken string) (string, error) {
	c := clientWithTimeout(8 * time.Second)
	url := "https://api.telegram.org/bot" + botToken + "/getMe"
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	resp, err := c.Do(req)
	if err != nil {
		return "", fmt.Errorf("cannot reach Telegram API: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	var result struct {
		OK     bool `json:"ok"`
		Result struct {
			Username string `json:"username"`
			FirstName string `json:"first_name"`
		} `json:"result"`
		Description string `json:"description"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return "", fmt.Errorf("invalid response from Telegram: %w", err)
	}
	if !result.OK {
		return "", fmt.Errorf("invalid token: %s", result.Description)
	}
	return result.Result.Username, nil
}

// TelegramPairInit starts the Telegram pairing flow.
// botUsername is fetched beforehand via TelegramGetMe — Core uses it for the deep link.
// Returns (code, deepLink, botUsername, expiresInSec, error).
func TelegramPairInit(baseURL, sessionToken, botUsername string) (string, string, int, error) {
	c := clientWithTimeout(15 * time.Second)
	body := map[string]any{}
	if botUsername != "" {
		body["bot_username"] = botUsername
	}
	data, status, err := doJSON(c, http.MethodPost, baseURL+"/auth/telegram/pair-init", body, bearerHeader(sessionToken))
	if err != nil {
		return "", "", 0, err
	}
	if status != http.StatusOK {
		return "", "", 0, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return "", "", 0, err
	}
	code, _ := payload["code"].(string)
	deepLink, _ := payload["deep_link"].(string)
	expires := 0
	if v, ok := payload["expires_in_sec"].(float64); ok {
		expires = int(v)
	}
	return code, deepLink, expires, nil
}

// GetAgents fetches the current user's registered agent configurations.
func GetAgents(baseURL, token string) ([]map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	data, status, err := doJSON(c, http.MethodGet, baseURL+"/auth/me/agents", nil, bearerHeader(token))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result []map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		var wrapper map[string]any
		if err2 := json.Unmarshal(data, &wrapper); err2 == nil {
			if agents, ok := wrapper["agents"].([]any); ok {
				for _, a := range agents {
					if m, ok := a.(map[string]any); ok {
						result = append(result, m)
					}
				}
				return result, nil
			}
		}
		return nil, err
	}
	return result, nil
}

// UpdateAgent updates a specific agent configuration.
func UpdateAgent(baseURL, token, agentID string, payload map[string]any) (map[string]any, error) {
	c := clientWithTimeout(5 * time.Second)
	url := fmt.Sprintf("%s/auth/me/agents/%s", baseURL, agentID)
	data, status, err := doJSON(c, http.MethodPut, url, payload, bearerHeader(token))
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", status, truncate(data, 200))
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// FetchEmails returns the list of user emails (admin only).
func FetchEmails(baseURL, adminToken string) ([]string, error) {
	users, err := AdminUsers(baseURL, adminToken)
	if err != nil {
		return nil, err
	}
	emails := make([]string, 0, len(users))
	for _, u := range users {
		if email, ok := u["email"].(string); ok && email != "" {
			emails = append(emails, email)
		}
	}
	return emails, nil
}

func truncate(data []byte, n int) string {
	s := string(data)
	if len(s) > n {
		return s[:n]
	}
	return s
}
