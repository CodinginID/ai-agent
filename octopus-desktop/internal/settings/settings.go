package settings

import (
	"encoding/json"
	"errors"
	"fmt"
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
	return Settings{GatewayURL: "http://localhost:8080", JarvisMode: true, TTSEnabled: true}
}

func Load(dir string) (Settings, error) {
	raw, err := os.ReadFile(filepath.Join(dir, fileName))
	if errors.Is(err, os.ErrNotExist) {
		return defaults(), nil
	}
	if err != nil {
		return Settings{}, fmt.Errorf("baca config: %w", err)
	}
	s := defaults()
	if err := json.Unmarshal(raw, &s); err != nil {
		return Settings{}, fmt.Errorf("parse config: %w", err)
	}
	return s, nil
}

func Save(dir string, s Settings) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("tulis config: %w", err)
	}
	raw, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("tulis config: %w", err)
	}
	if err := os.WriteFile(filepath.Join(dir, fileName), raw, 0o600); err != nil {
		return fmt.Errorf("tulis config: %w", err)
	}
	return nil
}

func SaveToken(token string) error {
	if err := keyring.Set(keyringService, keyringAccount, token); err != nil {
		return fmt.Errorf("keyring set: %w", err)
	}
	return nil
}

func Token() (string, error) {
	token, err := keyring.Get(keyringService, keyringAccount)
	if err != nil {
		return "", fmt.Errorf("keyring get: %w", err)
	}
	return token, nil
}

func DeleteToken() error {
	if err := keyring.Delete(keyringService, keyringAccount); err != nil {
		return fmt.Errorf("keyring delete: %w", err)
	}
	return nil
}
