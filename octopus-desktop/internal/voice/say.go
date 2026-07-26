package voice

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// SayCLI memakai TTS bawaan macOS (/usr/bin/say) sebagai fallback saat piper
// tidak tersedia — piper tidak punya rilis binary macOS yang utuh, sedangkan
// say selalu ada di setiap Mac tanpa instalasi apa pun.
type SayCLI struct {
	Bin   string
	Voice string // opsional, mis. "Damayanti"; kosong = suara default sistem
}

func (s *SayCLI) Synthesize(ctx context.Context, text string) ([]byte, error) {
	if s.Bin == "" {
		return nil, ErrNotConfigured
	}
	wav, err := s.run(ctx, text, s.Voice)
	if err != nil && s.Voice != "" {
		// Suara yang diminta bisa saja belum terpasang — coba suara default.
		return s.run(ctx, text, "")
	}
	return wav, err
}

func (s *SayCLI) run(ctx context.Context, text, voiceName string) ([]byte, error) {
	tmp, err := os.CreateTemp("", "octo-tts-*.wav")
	if err != nil {
		return nil, err
	}
	tmpName := tmp.Name()
	tmp.Close()
	defer os.Remove(tmpName)

	args := []string{"-o", tmpName, "--data-format=LEI16@22050"}
	if voiceName != "" {
		args = append(args, "-v", voiceName)
	}
	cmd := exec.CommandContext(ctx, s.Bin, args...)
	cmd.Stdin = strings.NewReader(text)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("say gagal: %w — %s", err, strings.TrimSpace(stderr.String()))
	}
	return os.ReadFile(tmpName)
}
