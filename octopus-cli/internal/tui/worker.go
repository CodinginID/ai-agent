package tui

import (
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gorilla/websocket"

	"github.com/codinginid/octopus/internal/config"
	"github.com/codinginid/octopus/internal/session"
)

const (
	workerReconnectInitial = 2 * time.Second
	workerReconnectMax     = 60 * time.Second
	workerHeartbeatPeriod  = 30 * time.Second
	workerChunkSize        = 1024
)

// RunWorkerLoop connects to the backend WebSocket worker endpoint, advertises
// capabilities, and handles incoming job messages. It runs in a goroutine and
// reconnects with exponential backoff.
func RunWorkerLoop(cfg *config.Config, getSession func() *session.Session, isRunning func() bool, program *tea.Program) {
	delay := workerReconnectInitial

	for isRunning() {
		sess := getSession()
		if sess == nil {
			time.Sleep(2 * time.Second)
			continue
		}

		err := runWorkerSession(cfg, sess.Token, program)
		if err == nil {
			// Clean disconnect — reset backoff.
			delay = workerReconnectInitial
		} else {
			program.Send(outputMsg{simpleLine("dim", fmt.Sprintf("  worker disconnected (%s), reconnecting in %.0fs…", err.Error(), delay.Seconds()))})
		}

		if !isRunning() {
			break
		}
		time.Sleep(delay)
		delay = minDuration(delay*2, workerReconnectMax)
	}
}

// runWorkerSession handles one WebSocket connection lifecycle.
func runWorkerSession(cfg *config.Config, token string, program *tea.Program) error {
	wsURL := buildWSURL(cfg.AppURL, token)

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}
	conn, _, err := dialer.Dial(wsURL, nil)
	if err != nil {
		return err
	}
	defer conn.Close()

	// Advertise capabilities.
	caps := detectCapabilities(cfg)
	capsMsg, _ := json.Marshal(map[string]any{
		"type":   "capabilities",
		"agents": caps,
	})
	if err := conn.WriteMessage(websocket.TextMessage, capsMsg); err != nil {
		return err
	}

	// Reset backoff on successful connection.
	delay := workerReconnectInitial

	// Start heartbeat goroutine.
	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(workerHeartbeatPeriod)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				hb, _ := json.Marshal(map[string]string{"type": "heartbeat"})
				if err := conn.WriteMessage(websocket.TextMessage, hb); err != nil {
					return
				}
			}
		}
	}()
	defer close(done)

	_ = delay // backoff reset only used at caller level

	for {
		_, msgBytes, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var msg map[string]any
		if err := json.Unmarshal(msgBytes, &msg); err != nil {
			continue
		}
		handleWorkerMessage(conn, cfg, msg, program)
	}
}

// handleWorkerMessage dispatches a single inbound WebSocket message.
func handleWorkerMessage(conn *websocket.Conn, cfg *config.Config, msg map[string]any, program *tea.Program) {
	kind, _ := msg["type"].(string)
	switch kind {
	case "registered":
		workerID, _ := msg["worker_id"].(string)
		program.Send(workerStatusMsg{connected: true, workerID: workerID})

	case "heartbeat_ack":
		// no-op

	case "job":
		jobID, _ := msg["job_id"].(string)
		agent, _ := msg["agent"].(string)
		prompt, _ := msg["prompt"].(string)
		if jobID != "" && agent != "" {
			go executeAgent(conn, cfg, jobID, agent, prompt)
		}

	default:
		// Unknown message — ignore.
	}
}

// executeAgent runs the specified agent binary and streams output via WebSocket.
func executeAgent(conn *websocket.Conn, cfg *config.Config, jobID, agent, prompt string) {
	args, err := buildAgentArgs(cfg, agent, prompt)
	if err != nil {
		sendWS(conn, map[string]any{
			"type":    "job_error",
			"job_id":  jobID,
			"message": err.Error(),
		})
		return
	}

	// Echo agent: fake response without spawning a subprocess.
	if agent == "echo" {
		sendWS(conn, map[string]any{
			"type":   "job_chunk",
			"job_id": jobID,
			"text":   fmt.Sprintf("[echo] received: %s\n", prompt),
		})
		sendWS(conn, map[string]any{
			"type":     "job_done",
			"job_id":   jobID,
			"exit_code": 0,
			"summary":  fmt.Sprintf("echoed %d chars", len(prompt)),
		})
		return
	}

	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stderr = cmd.Stdout
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		sendWS(conn, map[string]any{
			"type":    "job_error",
			"job_id":  jobID,
			"message": "pipe error: " + err.Error(),
		})
		return
	}

	if err := cmd.Start(); err != nil {
		sendWS(conn, map[string]any{
			"type":    "job_error",
			"job_id":  jobID,
			"message": "start error: " + err.Error(),
		})
		return
	}

	buf := make([]byte, workerChunkSize)
	for {
		n, err := stdout.Read(buf)
		if n > 0 {
			sendWS(conn, map[string]any{
				"type":   "job_chunk",
				"job_id": jobID,
				"text":   string(buf[:n]),
			})
		}
		if err != nil {
			if err != io.EOF {
				_ = cmd.Process.Kill()
				sendWS(conn, map[string]any{
					"type":    "job_error",
					"job_id":  jobID,
					"message": "read error: " + err.Error(),
				})
				return
			}
			break
		}
	}

	exitCode := 0
	summary := "exit 0"
	if err := cmd.Wait(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
			summary = fmt.Sprintf("failed with exit %d", exitCode)
		} else {
			summary = err.Error()
		}
	}

	sendWS(conn, map[string]any{
		"type":      "job_done",
		"job_id":    jobID,
		"exit_code": exitCode,
		"summary":   summary,
	})
}

// buildAgentArgs constructs the command-line argument list for an agent.
func buildAgentArgs(cfg *config.Config, agent, prompt string) ([]string, error) {
	switch agent {
	case "echo":
		return nil, nil // handled inline

	case "codex":
		if !cfg.EnableCodex {
			return nil, fmt.Errorf("codex belum aktif. Set ENABLE_CODEX=true")
		}
		bin, err := exec.LookPath(cfg.CodexBin)
		if err != nil {
			return nil, fmt.Errorf("codex CLI tidak ditemukan: %s", cfg.CodexBin)
		}
		args := []string{
			bin, "exec",
			"--cd", cfg.AgentWorkdir,
			"--sandbox", cfg.CodexSandbox,
			"--ask-for-approval", "never",
			"--skip-git-repo-check",
			"--ephemeral",
			"--color", "never",
		}
		if cfg.CodexModel != "" {
			args = append(args, "--model", cfg.CodexModel)
		}
		args = append(args, prompt)
		return args, nil

	case "claude":
		if !cfg.EnableClaude {
			return nil, fmt.Errorf("claude belum aktif. Set ENABLE_CLAUDE=true")
		}
		bin, err := exec.LookPath(cfg.ClaudeBin)
		if err != nil {
			return nil, fmt.Errorf("claude CLI tidak ditemukan: %s", cfg.ClaudeBin)
		}
		args := []string{
			bin,
			"--print",
			"--no-session-persistence",
			"--permission-mode", cfg.ClaudePermissionMode,
			"--output-format", "text",
		}
		if cfg.ClaudeTools != "" {
			args = append(args, "--tools", cfg.ClaudeTools)
		}
		if cfg.ClaudeAllowedTools != "" && cfg.ClaudeAllowedTools != "default" {
			args = append(args, "--allowedTools", cfg.ClaudeAllowedTools)
		}
		if cfg.ClaudeModel != "" {
			args = append(args, "--model", cfg.ClaudeModel)
		}
		args = append(args, prompt)
		return args, nil

	case "glm":
		if !cfg.EnableGLM {
			return nil, fmt.Errorf("glm belum aktif. Set ENABLE_GLM=true")
		}
		bin, err := exec.LookPath(cfg.GLMBin)
		if err != nil {
			return nil, fmt.Errorf("glm CLI tidak ditemukan: %s", cfg.GLMBin)
		}
		args := []string{bin}
		if cfg.GLMModel != "" {
			args = append(args, "--model", cfg.GLMModel)
		}
		args = append(args, prompt)
		return args, nil

	default:
		available := "echo"
		if cfg.EnableCodex {
			available += ", codex"
		}
		if cfg.EnableClaude {
			available += ", claude"
		}
		if cfg.EnableGLM {
			available += ", glm"
		}
		return nil, fmt.Errorf("agent '%s' belum didukung. Available: %s", agent, available)
	}
}

// detectCapabilities checks which agent binaries are installed.
func detectCapabilities(cfg *config.Config) map[string]any {
	caps := map[string]any{}
	for agentID, binName := range map[string]string{
		"codex":  cfg.CodexBin,
		"claude": cfg.ClaudeBin,
		"glm":    cfg.GLMBin,
	} {
		path, err := exec.LookPath(binName)
		caps[agentID] = map[string]any{
			"installed": err == nil,
			"path":      path,
			"bin":       binName,
		}
	}
	return caps
}

// buildWSURL converts an HTTP URL to a WebSocket URL with the session token.
func buildWSURL(appURL, token string) string {
	u, err := url.Parse(appURL)
	if err != nil {
		return ""
	}
	switch u.Scheme {
	case "https":
		u.Scheme = "wss"
	default:
		u.Scheme = "ws"
	}
	u.Path = "/ws/worker"
	u.RawQuery = "session=" + url.QueryEscape(token)
	return u.String()
}

// sendWS marshals and sends a message over the WebSocket connection.
func sendWS(conn *websocket.Conn, msg map[string]any) {
	data, err := json.Marshal(msg)
	if err != nil {
		return
	}
	_ = conn.WriteMessage(websocket.TextMessage, data)
}

// minDuration returns the smaller of two durations.
func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}

// historyPath returns the path to the command history file.
func historyPath() string {
	home, _ := os.UserHomeDir()
	return fmt.Sprintf("%s/.local/share/octopus/history", home)
}
