package voice

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

type PiperCLI struct {
	Bin       string
	VoicePath string
}

func (p *PiperCLI) Synthesize(ctx context.Context, text string) ([]byte, error) {
	if p.Bin == "" || p.VoicePath == "" {
		return nil, ErrNotConfigured
	}
	tmp, err := os.CreateTemp("", "octo-tts-*.wav")
	if err != nil {
		return nil, err
	}
	tmpName := tmp.Name()
	tmp.Close()
	defer os.Remove(tmpName)

	cmd := exec.CommandContext(ctx, p.Bin,
		"--model", p.VoicePath,
		"--output_file", tmpName,
	)
	cmd.Stdin = strings.NewReader(text)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("piper gagal: %w — %s", err, strings.TrimSpace(stderr.String()))
	}
	return os.ReadFile(tmpName)
}
