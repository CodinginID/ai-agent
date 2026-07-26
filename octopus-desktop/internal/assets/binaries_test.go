package assets

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"
)

func buildTarGz(t *testing.T, entries []tar.Header, contents map[string][]byte) string {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for _, hdr := range entries {
		h := hdr
		if body, ok := contents[h.Name]; ok {
			h.Size = int64(len(body))
		}
		if err := tw.WriteHeader(&h); err != nil {
			t.Fatalf("write header %s: %v", h.Name, err)
		}
		if body, ok := contents[h.Name]; ok {
			if _, err := tw.Write(body); err != nil {
				t.Fatalf("write body %s: %v", h.Name, err)
			}
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := gz.Close(); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "archive.tar.gz")
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestExtractTarGzPreservesExecBitAndContent(t *testing.T) {
	archive := buildTarGz(t, []tar.Header{
		{Name: "piper/", Typeflag: tar.TypeDir, Mode: 0o755},
		{Name: "piper/piper", Typeflag: tar.TypeReg, Mode: 0o755},
		{Name: "piper/espeak-ng-data/phondata", Typeflag: tar.TypeReg, Mode: 0o644},
	}, map[string][]byte{
		"piper/piper":                    []byte("#!/bin/true"),
		"piper/espeak-ng-data/phondata":  []byte("data"),
	})

	dest := t.TempDir()
	if err := ExtractTarGz(archive, dest); err != nil {
		t.Fatalf("extract: %v", err)
	}

	bin := filepath.Join(dest, "piper", "piper")
	info, err := os.Stat(bin)
	if err != nil {
		t.Fatalf("binary tidak ada: %v", err)
	}
	if info.Mode().Perm()&0o100 == 0 {
		t.Fatalf("bit eksekusi hilang: %v", info.Mode())
	}
	got, err := os.ReadFile(filepath.Join(dest, "piper", "espeak-ng-data", "phondata"))
	if err != nil || string(got) != "data" {
		t.Fatalf("isi file nested salah: %q err=%v", got, err)
	}
}

func TestExtractTarGzHandlesRelativeSymlink(t *testing.T) {
	archive := buildTarGz(t, []tar.Header{
		{Name: "piper/libonnxruntime.1.14.1.dylib", Typeflag: tar.TypeReg, Mode: 0o644},
		{Name: "piper/libonnxruntime.dylib", Typeflag: tar.TypeSymlink, Mode: 0o777, Linkname: "libonnxruntime.1.14.1.dylib"},
	}, map[string][]byte{
		"piper/libonnxruntime.1.14.1.dylib": []byte("lib"),
	})

	dest := t.TempDir()
	if err := ExtractTarGz(archive, dest); err != nil {
		t.Fatalf("extract: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(dest, "piper", "libonnxruntime.dylib"))
	if err != nil || string(got) != "lib" {
		t.Fatalf("symlink tidak resolve ke isi lib: %q err=%v", got, err)
	}
}

func TestExtractTarGzRejectsPathTraversal(t *testing.T) {
	archive := buildTarGz(t, []tar.Header{
		{Name: "../evil", Typeflag: tar.TypeReg, Mode: 0o644},
	}, map[string][]byte{
		"../evil": []byte("x"),
	})

	if err := ExtractTarGz(archive, t.TempDir()); err == nil {
		t.Fatal("path traversal harus ditolak")
	}
}

func TestExtractTarGzRejectsSymlinkEscape(t *testing.T) {
	archive := buildTarGz(t, []tar.Header{
		{Name: "piper/escape", Typeflag: tar.TypeSymlink, Mode: 0o777, Linkname: "../../outside"},
	}, nil)

	if err := ExtractTarGz(archive, t.TempDir()); err == nil {
		t.Fatal("symlink keluar destDir harus ditolak")
	}
}

func TestPiperBinaryKnownAndUnknownPlatform(t *testing.T) {
	it, ok := PiperBinary("linux", "amd64")
	if !ok || it.URL == "" {
		t.Fatalf("linux/amd64 harus tersedia: %+v ok=%v", it, ok)
	}
	// Arsip macOS upstream rusak (binary x86_64 + dylib hilang) — wajib false
	// supaya installPiperBinary tidak memasang binary yang tidak bisa jalan.
	if _, ok := PiperBinary("darwin", "arm64"); ok {
		t.Fatal("darwin harus ok=false — fallback ke say")
	}
	if _, ok := PiperBinary("windows", "amd64"); ok {
		t.Fatal("windows belum didukung — harus ok=false")
	}
}
