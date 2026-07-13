package voice

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func fakePiper(t *testing.T) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake binary test butuh shell posix")
	}
	// fake piper: baca stdin, tulis "WAV:" + teks ke --output_file
	script := `#!/bin/sh
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--output_file" ]; then out="$2"; shift; fi
  shift
done
text=$(cat)
printf "WAV:%s" "$text" > "$out"
`
	p := filepath.Join(t.TempDir(), "fake-piper")
	if err := os.WriteFile(p, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestSynthesizeReturnsWavBytes(t *testing.T) {
	p := &PiperCLI{Bin: fakePiper(t), VoicePath: "voice.onnx"}
	wav, err := p.Synthesize(context.Background(), "halo dunia")
	if err != nil {
		t.Fatalf("synthesize: %v", err)
	}
	if !strings.HasPrefix(string(wav), "WAV:halo dunia") {
		t.Fatalf("isi wav salah: %q", wav)
	}
}

func TestSynthesizeUnconfigured(t *testing.T) {
	p := &PiperCLI{}
	if _, err := p.Synthesize(context.Background(), "halo"); err == nil {
		t.Fatal("bin kosong harus error")
	}
}
