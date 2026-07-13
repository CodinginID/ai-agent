// octopus-desktop/internal/settings/settings_test.go
package settings

import (
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
