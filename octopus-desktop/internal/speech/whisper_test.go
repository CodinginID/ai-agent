package speech

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func fakeBin(t *testing.T, script string) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake binary test butuh shell posix")
	}
	p := filepath.Join(t.TempDir(), "fake-whisper")
	if err := os.WriteFile(p, []byte("#!/bin/sh\n"+script), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestTranscribeReturnsStdout(t *testing.T) {
	bin := fakeBin(t, `echo " restart service web "`)
	w := &WhisperCLI{Bin: bin, ModelPath: "model.bin"}
	got, err := w.Transcribe(context.Background(), []byte("RIFFfake"))
	if err != nil {
		t.Fatalf("transcribe: %v", err)
	}
	if got != "restart service web" {
		t.Fatalf("harus di-trim, got %q", got)
	}
}

func TestTranscribeBinaryFailureWrapped(t *testing.T) {
	bin := fakeBin(t, `echo "boom" >&2; exit 1`)
	w := &WhisperCLI{Bin: bin, ModelPath: "model.bin"}
	if _, err := w.Transcribe(context.Background(), []byte("RIFFfake")); err == nil {
		t.Fatal("exit 1 harus error")
	}
}

func TestTranscribeUnconfigured(t *testing.T) {
	w := &WhisperCLI{}
	if _, err := w.Transcribe(context.Background(), nil); err == nil {
		t.Fatal("bin kosong harus error ErrNotConfigured")
	}
}
