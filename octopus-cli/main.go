package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"

	"github.com/codinginid/octopus/internal/config"
	"github.com/codinginid/octopus/internal/session"
	"github.com/codinginid/octopus/internal/tui"
)

// defaultAppURL is overridden at build time via:
//
//	go build -ldflags="-X main.defaultAppURL=https://prod.example.com"
var defaultAppURL = "http://localhost:8080"

// Version is the current CLI version, also overridable via ldflags.
const Version = "0.2.0"

func main() {
	root := &cobra.Command{
		Use:   "octopus",
		Short: "Octopus — server monitor & AI chat TUI",
		Long:  "Octopus CLI: connect to your Octopus backend, chat with AI, and manage your server from the terminal.",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runTUI()
		},
		SilenceUsage: true,
	}

	root.AddCommand(upgradeCmd())
	root.Version = Version

	if err := root.Execute(); err != nil {
		os.Exit(1)
	}
}

// runTUI starts the Bubble Tea TUI.
func runTUI() error {
	cfg := config.Load(defaultAppURL, Version)

	model := tui.New(cfg)

	p := tea.NewProgram(
		model,
		tea.WithAltScreen(),
		tea.WithMouseCellMotion(),
	)

	// Give the model a reference to the program so background goroutines
	// can send messages.
	model.SetProgram(p)

	// Ensure history directory exists.
	ensureHistoryDir()

	// Load history from disk.
	model.LoadHistory(historyFilePath())

	// Start the worker loop in a background goroutine.
	go tui.RunWorkerLoop(cfg, func() *session.Session {
		return model.GetSession()
	}, func() bool {
		return model.IsRunning()
	}, p)

	if _, err := p.Run(); err != nil {
		return fmt.Errorf("TUI error: %w", err)
	}
	return nil
}

// ── upgrade command ───────────────────────────────────────────────────────────

func upgradeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "upgrade",
		Short: "Check for a newer release and replace the binary",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runUpgrade()
		},
		SilenceUsage: true,
	}
}

const githubAPI = "https://api.github.com/repos/CodinginID/ai-agent/releases/latest"

func runUpgrade() error {
	fmt.Printf("Current version: v%s\n", Version)
	fmt.Println("Checking for updates…")

	latest, err := fetchLatestVersion()
	if err != nil {
		return fmt.Errorf("check failed: %w", err)
	}

	if !isNewer(latest, Version) {
		fmt.Printf("Already up to date (v%s).\n", Version)
		return nil
	}

	fmt.Printf("New version available: %s\n", latest)
	fmt.Println("Downloading…")

	binaryName := buildBinaryName(latest)
	downloadURL := fmt.Sprintf("https://github.com/CodinginID/ai-agent/releases/download/%s/%s", latest, binaryName)

	if err := downloadAndReplace(downloadURL); err != nil {
		return fmt.Errorf("upgrade failed: %w", err)
	}

	fmt.Printf("✓ Upgraded to %s. Restart to apply.\n", latest)
	return nil
}

func fetchLatestVersion() (string, error) {
	resp, err := http.Get(githubAPI) //nolint:gosec,noctx
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("GitHub API returned HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	// Simple extraction — avoid importing encoding/json just for one field.
	tag := extractJSONString(string(body), "tag_name")
	if tag == "" {
		return "", fmt.Errorf("could not parse tag_name from GitHub response")
	}
	return tag, nil
}

// extractJSONString extracts a string value for a key from a JSON object
// without a full JSON parser (avoids import cycle risk, keeps it tiny).
func extractJSONString(body, key string) string {
	needle := `"` + key + `":"`
	idx := strings.Index(body, needle)
	if idx < 0 {
		return ""
	}
	start := idx + len(needle)
	end := strings.IndexByte(body[start:], '"')
	if end < 0 {
		return ""
	}
	return body[start : start+end]
}

func isNewer(remote, current string) bool {
	// Strip leading 'v'.
	r := strings.TrimPrefix(remote, "v")
	c := strings.TrimPrefix(current, "v")
	// Simple string comparison — semver without pre-release should work.
	return r > c
}

func buildBinaryName(version string) string {
	os := runtime.GOOS
	arch := runtime.GOARCH
	name := fmt.Sprintf("octopus-%s-%s", os, arch)
	if os == "windows" {
		name += ".exe"
	}
	return name
}

func downloadAndReplace(downloadURL string) error {
	resp, err := http.Get(downloadURL) //nolint:gosec,noctx
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download returned HTTP %d", resp.StatusCode)
	}

	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("locate current binary: %w", err)
	}
	execPath, err = filepath.EvalSymlinks(execPath)
	if err != nil {
		return fmt.Errorf("resolve symlinks: %w", err)
	}

	// Write to a temp file next to the binary.
	tmpPath := execPath + ".new"
	f, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(tmpPath) //nolint:errcheck
		return fmt.Errorf("write download: %w", err)
	}
	f.Close()

	// Atomically replace the binary.
	if err := os.Rename(tmpPath, execPath); err != nil {
		os.Remove(tmpPath) //nolint:errcheck
		return fmt.Errorf("replace binary: %w", err)
	}
	return nil
}

// ── History helpers ───────────────────────────────────────────────────────────

func historyFilePath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "share", "octopus", "history")
}

func ensureHistoryDir() {
	dir := filepath.Dir(historyFilePath())
	_ = os.MkdirAll(dir, 0o700)
}
