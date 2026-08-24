package speech

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// WhisperCLI menjalankan binary whisper.cpp (whisper-cli) sebagai subprocess.
// Input wav 16kHz mono PCM16 (disiapkan frontend).
type WhisperCLI struct {
	Bin       string
	ModelPath string
}

func (w *WhisperCLI) Transcribe(ctx context.Context, wav []byte) (string, error) {
	if w.Bin == "" || w.ModelPath == "" {
		return "", ErrNotConfigured
	}
	tmp, err := os.CreateTemp("", "octo-stt-*.wav")
	if err != nil {
		return "", err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(wav); err != nil {
		tmp.Close()
		return "", err
	}
	tmp.Close()

	cmd := exec.CommandContext(ctx, w.Bin,
		"-m", w.ModelPath,
		"-f", filepath.Clean(tmp.Name()),
		"-nt", // tanpa timestamp
		"-np", // tanpa banner/progress di stderr
	)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("whisper gagal: %w — %s", err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(stdout.String()), nil
}
