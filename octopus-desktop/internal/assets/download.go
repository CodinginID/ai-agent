package assets

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

type Item struct {
	Name     string
	URL      string
	SHA256   string
	DestName string
}

func DefaultItems() []Item {
	return []Item{
		{
			Name:     "whisper-base",
			URL:      "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
			SHA256:   "", // diisi saat eksekusi dari unduhan resmi; kosong = skip verify
			DestName: "ggml-base.bin",
		},
		{
			Name:     "piper-voice",
			URL:      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
			SHA256:   "",
			DestName: "piper-voice.onnx",
		},
		{
			Name:     "piper-voice-config",
			URL:      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
			SHA256:   "",
			DestName: "piper-voice.onnx.json",
		},
	}
}

type progressWriter struct {
	w        io.Writer
	done     int64
	total    int64
	callback func(done, total int64)
}

func (p *progressWriter) Write(b []byte) (int, error) {
	n, err := p.w.Write(b)
	p.done += int64(n)
	if p.callback != nil {
		p.callback(p.done, p.total)
	}
	return n, err
}

func Download(ctx context.Context, it Item, destDir string, progress func(done, total int64)) (string, error) {
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, it.URL, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("unduh %s gagal: %w", it.Name, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unduh %s gagal: HTTP %d", it.Name, resp.StatusCode)
	}

	dest := filepath.Join(destDir, it.DestName)
	part := dest + ".part"
	f, err := os.Create(part)
	if err != nil {
		return "", err
	}
	hasher := sha256.New()
	pw := &progressWriter{w: io.MultiWriter(f, hasher), total: resp.ContentLength, callback: progress}
	_, copyErr := io.Copy(pw, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		os.Remove(part)
		return "", fmt.Errorf("unduh %s terputus: %w", it.Name, copyErr)
	}
	if closeErr != nil {
		return "", closeErr
	}
	if it.SHA256 != "" {
		got := hex.EncodeToString(hasher.Sum(nil))
		if got != it.SHA256 {
			os.Remove(part)
			return "", fmt.Errorf("checksum %s tidak cocok: got %s", it.Name, got)
		}
	}
	if err := os.Rename(part, dest); err != nil {
		return "", err
	}
	return dest, nil
}
