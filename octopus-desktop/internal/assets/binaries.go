package assets

import (
	"archive/tar"
	"compress/gzip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const piperReleaseBase = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"

// piperArchives memetakan GOOS/GOARCH ke nama arsip prebuilt resmi rhasspy/piper.
// macOS sengaja TIDAK ada: arsip macos_* rilis 2023.11.14-2 rusak (isinya
// binary x86_64 bahkan untuk aarch64, dan libespeak-ng/libonnxruntime hilang) —
// di macOS TTS fallback ke `say` bawaan (lihat voice.SayCLI).
// Windows belum didukung karena arsipnya .zip.
var piperArchives = map[string]string{
	"linux/amd64": "piper_linux_x86_64.tar.gz",
	"linux/arm64": "piper_linux_aarch64.tar.gz",
}

// piperChecksums berisi sha256 arsip yang sudah diverifikasi manual.
// Kosong = skip verify (konsisten dengan model items).
var piperChecksums = map[string]string{}

// PiperBinary mengembalikan item unduhan binary piper untuk platform yang diminta.
// ok=false bila tidak ada prebuilt resmi untuk platform tersebut.
func PiperBinary(goos, goarch string) (Item, bool) {
	name, ok := piperArchives[goos+"/"+goarch]
	if !ok {
		return Item{}, false
	}
	return Item{
		Name:     "piper-bin",
		URL:      piperReleaseBase + name,
		SHA256:   piperChecksums[name],
		DestName: name,
	}, true
}

// PiperBinaryItem sama seperti PiperBinary untuk platform saat runtime.
func PiperBinaryItem() (Item, bool) {
	return PiperBinary(runtime.GOOS, runtime.GOARCH)
}

// ExtractTarGz mengekstrak arsip .tar.gz ke destDir sambil mempertahankan
// permission (bit eksekusi binary harus selamat) dan menolak path traversal.
func ExtractTarGz(archivePath, destDir string) error {
	f, err := os.Open(archivePath)
	if err != nil {
		return err
	}
	defer f.Close()

	gz, err := gzip.NewReader(f)
	if err != nil {
		return fmt.Errorf("ekstrak %s: %w", filepath.Base(archivePath), err)
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return fmt.Errorf("ekstrak %s: %w", filepath.Base(archivePath), err)
		}
		dest, err := safeJoin(destDir, hdr.Name)
		if err != nil {
			return err
		}
		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(dest, 0o755); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
				return err
			}
			if err := writeFile(dest, tr, hdr.FileInfo().Mode().Perm()); err != nil {
				return err
			}
		case tar.TypeSymlink:
			// Dylib piper memakai symlink relatif (mis. libonnxruntime.dylib → versi).
			if _, err := safeJoin(filepath.Dir(dest), hdr.Linkname); err != nil {
				return err
			}
			os.Remove(dest)
			if err := os.Symlink(hdr.Linkname, dest); err != nil {
				return err
			}
		}
	}
}

func safeJoin(destDir, name string) (string, error) {
	dest := filepath.Join(destDir, filepath.Clean(name))
	if dest != destDir && !strings.HasPrefix(dest, filepath.Clean(destDir)+string(os.PathSeparator)) {
		return "", fmt.Errorf("arsip berisi path di luar tujuan: %s", name)
	}
	return dest, nil
}

func writeFile(dest string, r io.Reader, perm os.FileMode) error {
	out, err := os.OpenFile(dest, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, perm)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, r); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}
