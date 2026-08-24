package assets

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestDownloadVerifiesChecksumAndRenames(t *testing.T) {
	content := []byte("model-bytes")
	sum := sha256.Sum256(content)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(content)
	}))
	defer srv.Close()

	dir := t.TempDir()
	var lastDone int64
	path, err := Download(context.Background(), Item{
		Name: "test", URL: srv.URL, SHA256: hex.EncodeToString(sum[:]), DestName: "model.bin",
	}, dir, func(done, total int64) { lastDone = done })
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if filepath.Base(path) != "model.bin" {
		t.Fatalf("path salah: %s", path)
	}
	if lastDone != int64(len(content)) {
		t.Fatalf("progress terakhir %d != %d", lastDone, len(content))
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("file tidak ada: %v", err)
	}
}

func TestDownloadBadChecksumFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("corrupt"))
	}))
	defer srv.Close()

	_, err := Download(context.Background(), Item{
		Name: "test", URL: srv.URL, SHA256: "deadbeef", DestName: "model.bin",
	}, t.TempDir(), nil)
	if err == nil {
		t.Fatal("checksum salah harus error")
	}
}
