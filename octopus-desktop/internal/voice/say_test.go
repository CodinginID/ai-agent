package voice

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// fakeSay meniru /usr/bin/say: tulis "SAY:<voice>:<teks stdin>" ke file -o.
// Bila voice mengandung "invalid", exit 1 (suara tidak terpasang).
func fakeSay(t *testing.T) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake binary test butuh shell posix")
	}
	script := `#!/bin/sh
out=""
voice=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift ;;
    -v) voice="$2"; shift ;;
  esac
  shift
done
case "$voice" in *invalid*) echo "Voice not found" >&2; exit 1 ;; esac
text=$(cat)
printf "SAY:%s:%s" "$voice" "$text" > "$out"
`
	p := filepath.Join(t.TempDir(), "fake-say")
	if err := os.WriteFile(p, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestSaySynthesizeReturnsWavBytes(t *testing.T) {
	s := &SayCLI{Bin: fakeSay(t), Voice: "Damayanti"}
	wav, err := s.Synthesize(context.Background(), "halo dunia")
	if err != nil {
		t.Fatalf("synthesize: %v", err)
	}
	if string(wav) != "SAY:Damayanti:halo dunia" {
		t.Fatalf("isi wav salah: %q", wav)
	}
}

func TestSayMissingVoiceFallsBackToDefault(t *testing.T) {
	s := &SayCLI{Bin: fakeSay(t), Voice: "invalid-voice"}
	wav, err := s.Synthesize(context.Background(), "halo")
	if err != nil {
		t.Fatalf("harus fallback ke suara default: %v", err)
	}
	if !strings.HasPrefix(string(wav), "SAY::") {
		t.Fatalf("harus tanpa voice: %q", wav)
	}
}

func TestSayUnconfigured(t *testing.T) {
	s := &SayCLI{}
	if _, err := s.Synthesize(context.Background(), "halo"); err == nil {
		t.Fatal("bin kosong harus error")
	}
}
