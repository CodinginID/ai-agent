// Package config loads application configuration from env vars and TOML file.
package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/BurntSushi/toml"
)

// Config holds all runtime configuration for the CLI.
type Config struct {
	AppURL               string
	AdminToken           string
	EnableCodex          bool
	CodexBin             string
	CodexModel           string
	CodexSandbox         string
	EnableClaude         bool
	ClaudeBin            string
	ClaudeModel          string
	ClaudePermissionMode string
	ClaudeAllowedTools   string
	ClaudeTools          string
	EnableGLM            bool
	GLMBin               string
	GLMModel             string
	AgentTimeout         int
	AgentWorkdir         string
	DockerLogContainer   string
	Version              string
}

// agentsToml mirrors the [agent] section in ~/.config/octopus/agents.toml.
type agentsToml struct {
	AppURL               string `toml:"app_url"`
	AdminToken           string `toml:"admin_token"`
	EnableCodex          bool   `toml:"enable_codex"`
	CodexBin             string `toml:"codex_bin"`
	CodexModel           string `toml:"codex_model"`
	CodexSandbox         string `toml:"codex_sandbox"`
	EnableClaude         bool   `toml:"enable_claude"`
	ClaudeBin            string `toml:"claude_bin"`
	ClaudeModel          string `toml:"claude_model"`
	ClaudePermissionMode string `toml:"claude_permission_mode"`
	ClaudeAllowedTools   string `toml:"claude_allowed_tools"`
	ClaudeTools          string `toml:"claude_tools"`
	EnableGLM            bool   `toml:"enable_glm"`
	GLMBin               string `toml:"glm_bin"`
	GLMModel             string `toml:"glm_model"`
	AgentTimeout         int    `toml:"agent_timeout"`
	AgentWorkdir         string `toml:"agent_workdir"`
	DockerLogContainer   string `toml:"docker_log_container"`
}

// Load builds a Config applying: defaults → TOML file → local .env → env vars.
// defaultAppURL is injected at build time via ldflags.
func Load(defaultAppURL, version string) *Config {
	cfg := &Config{
		AppURL:               defaultAppURL,
		CodexBin:             "codex",
		CodexSandbox:         "docker",
		ClaudeBin:            "claude",
		ClaudePermissionMode: "default",
		GLMBin:               "glm",
		AgentTimeout:         300,
		AgentWorkdir:         ".",
		DockerLogContainer:   "aiagent_bot",
		Version:              version,
	}

	// Layer 2: TOML file.
	tomlPath := filepath.Join(configDir(), "agents.toml")
	var t agentsToml
	if _, err := toml.DecodeFile(tomlPath, &t); err == nil {
		applyTOML(cfg, &t)
	}

	// Layer 1.5: .env in current directory (dev convenience).
	loadDotEnv(".env")

	// Layer 1: environment variables (highest priority).
	applyEnv(cfg)

	return cfg
}

func configDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", "octopus")
}

func applyTOML(cfg *Config, t *agentsToml) {
	if t.AppURL != "" {
		cfg.AppURL = t.AppURL
	}
	if t.AdminToken != "" {
		cfg.AdminToken = t.AdminToken
	}
	if t.EnableCodex {
		cfg.EnableCodex = true
	}
	if t.CodexBin != "" {
		cfg.CodexBin = t.CodexBin
	}
	if t.CodexModel != "" {
		cfg.CodexModel = t.CodexModel
	}
	if t.CodexSandbox != "" {
		cfg.CodexSandbox = t.CodexSandbox
	}
	if t.EnableClaude {
		cfg.EnableClaude = true
	}
	if t.ClaudeBin != "" {
		cfg.ClaudeBin = t.ClaudeBin
	}
	if t.ClaudeModel != "" {
		cfg.ClaudeModel = t.ClaudeModel
	}
	if t.ClaudePermissionMode != "" {
		cfg.ClaudePermissionMode = t.ClaudePermissionMode
	}
	if t.ClaudeAllowedTools != "" {
		cfg.ClaudeAllowedTools = t.ClaudeAllowedTools
	}
	if t.ClaudeTools != "" {
		cfg.ClaudeTools = t.ClaudeTools
	}
	if t.EnableGLM {
		cfg.EnableGLM = true
	}
	if t.GLMBin != "" {
		cfg.GLMBin = t.GLMBin
	}
	if t.GLMModel != "" {
		cfg.GLMModel = t.GLMModel
	}
	if t.AgentTimeout > 0 {
		cfg.AgentTimeout = t.AgentTimeout
	}
	if t.AgentWorkdir != "" {
		cfg.AgentWorkdir = t.AgentWorkdir
	}
	if t.DockerLogContainer != "" {
		cfg.DockerLogContainer = t.DockerLogContainer
	}
}

func applyEnv(cfg *Config) {
	// AppURL — prefer new name, fallback to old APP_URL.
	if v := firstEnv("OCTOPUS_URL", "APP_URL"); v != "" {
		cfg.AppURL = v
	}
	// AdminToken — prefer new name, fallback to old ADMIN_TOKEN.
	if v := firstEnv("OCTOPUS_ADMIN_TOKEN", "ADMIN_TOKEN"); v != "" {
		cfg.AdminToken = v
	}
	if v := os.Getenv("ENABLE_CODEX"); v != "" {
		cfg.EnableCodex = parseBool(v)
	}
	if v := os.Getenv("CODEX_BIN"); v != "" {
		cfg.CodexBin = v
	}
	if v := os.Getenv("CODEX_MODEL"); v != "" {
		cfg.CodexModel = v
	}
	if v := os.Getenv("CODEX_SANDBOX"); v != "" {
		cfg.CodexSandbox = v
	}
	if v := os.Getenv("ENABLE_CLAUDE"); v != "" {
		cfg.EnableClaude = parseBool(v)
	}
	if v := os.Getenv("CLAUDE_BIN"); v != "" {
		cfg.ClaudeBin = v
	}
	if v := os.Getenv("CLAUDE_MODEL"); v != "" {
		cfg.ClaudeModel = v
	}
	if v := os.Getenv("CLAUDE_PERMISSION_MODE"); v != "" {
		cfg.ClaudePermissionMode = v
	}
	if v := os.Getenv("CLAUDE_ALLOWED_TOOLS"); v != "" {
		cfg.ClaudeAllowedTools = v
	}
	if v := os.Getenv("CLAUDE_TOOLS"); v != "" {
		cfg.ClaudeTools = v
	}
	if v := os.Getenv("ENABLE_GLM"); v != "" {
		cfg.EnableGLM = parseBool(v)
	}
	if v := os.Getenv("GLM_BIN"); v != "" {
		cfg.GLMBin = v
	}
	if v := os.Getenv("GLM_MODEL"); v != "" {
		cfg.GLMModel = v
	}
	if v := os.Getenv("AGENT_TIMEOUT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.AgentTimeout = n
		}
	}
	if v := os.Getenv("AGENT_WORKDIR"); v != "" {
		cfg.AgentWorkdir = v
	}
	if v := os.Getenv("DOCKER_LOG_CONTAINER"); v != "" {
		cfg.DockerLogContainer = v
	}
}

func firstEnv(keys ...string) string {
	for _, k := range keys {
		if v := os.Getenv(k); v != "" {
			return v
		}
	}
	return ""
}

func parseBool(s string) bool {
	s = strings.ToLower(strings.TrimSpace(s))
	return s == "1" || s == "true" || s == "yes" || s == "on"
}

// loadDotEnv reads key=value pairs from path and sets them as env vars
// only if the key is not already set.
func loadDotEnv(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		idx := strings.IndexByte(line, '=')
		if idx < 1 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])
		// Strip surrounding quotes.
		if len(val) >= 2 && val[0] == '"' && val[len(val)-1] == '"' {
			val = val[1 : len(val)-1]
		}
		if os.Getenv(key) == "" {
			os.Setenv(key, val) //nolint:errcheck
		}
	}
}
