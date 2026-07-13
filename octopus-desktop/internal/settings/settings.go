// octopus-desktop/internal/settings/settings.go
package settings

import (
	"encoding/json"
	"errors"
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
	return Settings{JarvisMode: true, TTSEnabled: true}
}

func Load(dir string) (Settings, error) {
	raw, err := os.ReadFile(filepath.Join(dir, fileName))
	if errors.Is(err, os.ErrNotExist) {
		return defaults(), nil
	}
	if err != nil {
		return Settings{}, err
	}
	s := defaults()
	if err := json.Unmarshal(raw, &s); err != nil {
		return Settings{}, err
	}
	return s, nil
}

func Save(dir string, s Settings) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, fileName), raw, 0o600)
}

func SaveToken(token string) error { return keyring.Set(keyringService, keyringAccount, token) }
func Token() (string, error)       { return keyring.Get(keyringService, keyringAccount) }
func DeleteToken() error           { return keyring.Delete(keyringService, keyringAccount) }
