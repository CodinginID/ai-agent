// Package session manages the local TUI session persisted to disk.
package session

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// Session holds authenticated user information.
type Session struct {
	Token       string `json:"token"`
	UserID      string `json:"user_id"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name,omitempty"`
	BackendURL  string `json:"backend_url"`
}

func sessionFile() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", "octopus", "session.json")
}

// Load reads the session from disk.
// Returns nil if no session exists, it is invalid, or it belongs to a
// different backend URL.
func Load(currentBackendURL string) *Session {
	data, err := os.ReadFile(sessionFile())
	if err != nil {
		return nil
	}
	var s Session
	if err := json.Unmarshal(data, &s); err != nil {
		return nil
	}
	if s.Token == "" {
		return nil
	}
	// Session is bound to a specific backend.
	if s.BackendURL != currentBackendURL {
		return nil
	}
	return &s
}

// Save persists the session to disk with permission 0600.
func Save(s *Session) error {
	path := sessionFile()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		return err
	}
	return nil
}

// Clear removes the session file from disk.
func Clear() {
	_ = os.Remove(sessionFile())
}
