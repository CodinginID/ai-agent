package settings

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/zalando/go-keyring"
)

func TestLoadMissingFileReturnsDefaults(t *testing.T) {
	s, err := Load(t.TempDir())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !s.JarvisMode || !s.TTSEnabled {
		t.Fatalf("default JarvisMode/TTSEnabled harus true, got %+v", s)
	}
	if s.VadSilenceMs != 1200 {
		t.Fatalf("default VadSilenceMs harus 1200, got %d", s.VadSilenceMs)
	}
	if s.OrbAccent != "#38e1ff" {
		t.Fatalf("default OrbAccent harus #38e1ff, got %q", s.OrbAccent)
	}
}

func TestSaveThenLoadPreservesAppearance(t *testing.T) {
	dir := t.TempDir()
	if err := Save(dir, Settings{OrbAccent: "#5b8cff", ReduceMotion: true}); err != nil {
		t.Fatalf("save: %v", err)
	}
	out, err := Load(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if out.OrbAccent != "#5b8cff" || !out.ReduceMotion {
		t.Fatalf("appearance roundtrip: %+v", out)
	}
}

func TestSaveThenLoadPreservesVadSilenceMs(t *testing.T) {
	dir := t.TempDir()
	if err := Save(dir, Settings{GatewayURL: "http://x", VadSilenceMs: 900}); err != nil {
		t.Fatalf("save: %v", err)
	}
	out, err := Load(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if out.VadSilenceMs != 900 {
		t.Fatalf("VadSilenceMs roundtrip: got %d", out.VadSilenceMs)
	}
}

func TestSaveThenLoadRoundtrip(t *testing.T) {
	dir := t.TempDir()
	in := Settings{GatewayURL: "https://octo.example.com", JarvisMode: false, TTSEnabled: true}
	if err := Save(dir, in); err != nil {
		t.Fatalf("save: %v", err)
	}
	out, err := Load(dir)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if out.GatewayURL != in.GatewayURL || out.JarvisMode != in.JarvisMode {
		t.Fatalf("roundtrip mismatch: %+v", out)
	}
}

func TestLoadCorruptJSONReturnsError(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "config.json"), []byte("{invalid"), 0o600); err != nil {
		t.Fatalf("setup: %v", err)
	}
	if _, err := Load(dir); err == nil {
		t.Fatal("Load harus error untuk JSON korup")
	}
}

func TestTokenRoundtripViaKeyring(t *testing.T) {
	keyring.MockInit()
	if err := SaveToken("tok-123"); err != nil {
		t.Fatalf("save token: %v", err)
	}
	got, err := Token()
	if err != nil || got != "tok-123" {
		t.Fatalf("token roundtrip: %q %v", got, err)
	}
	if err := DeleteToken(); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if _, err := Token(); err == nil {
		t.Fatal("token harus error setelah delete")
	}
}
