package tui

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/codinginid/octopus/internal/api"
	"github.com/codinginid/octopus/internal/qr"
	"github.com/codinginid/octopus/internal/session"
)

// dispatchCommand routes a /command string to its handler.
func (m *Model) dispatchCommand(raw string) tea.Cmd {
	parts := strings.Fields(raw)
	if len(parts) == 0 {
		return nil
	}
	cmd := strings.ToLower(parts[0])
	args := parts[1:]

	switch cmd {
	case "/help":
		return m.cmdHelp()
	case "/login":
		return m.cmdLogin()
	case "/logout":
		return m.cmdLogout()
	case "/me":
		return m.cmdMe()
	case "/pair-telegram":
		return m.cmdPairTelegram(args)
	case "/status":
		return m.cmdStatus()
	case "/users":
		return m.cmdUsers()
	case "/admin-logout":
		if len(args) == 0 {
			m.appendLine(simpleLine("warn", "  usage: /admin-logout <email>"))
			return nil
		}
		return m.cmdAdminLogout(args[0])
	case "/logs":
		return m.cmdLogs(args)
	case "/shell", "/zsh":
		return m.cmdShell()
	case "/clear":
		return m.cmdClear()
	case "/quit", "/exit", "/q":
		m.running = false
		return tea.Quit
	case "/agents":
		return m.cmdAgents(args)
	case "/audit":
		n := 50
		if len(args) > 0 {
			if v, err := strconv.Atoi(args[0]); err == nil {
				n = v
			}
		}
		return m.cmdAudit(n)
	default:
		m.appendLine(simpleLine("warn", "  unknown command: "+cmd+". Type /help for commands."))
		return nil
	}
}

// ── /help ─────────────────────────────────────────────────────────────────────

func (m *Model) cmdHelp() tea.Cmd {
	lines := []OutputLine{
		simpleLine("section", "Commands"),
		simpleLine("rule", strings.Repeat("─", 56)),
	}

	type entry struct{ name, desc string }
	entries := []entry{
		{"/help", "tampilkan daftar command ini"},
		{"/login", "login Google via QR — wajib pertama kali"},
		{"/logout", "logout session TUI saat ini"},
		{"/me", "info user yang sedang login"},
		{"/pair-telegram <token>", "link bot Telegram ke akun ini (token dari @BotFather)"},
		{"/status", "mode bot, jumlah user, versi backend"},
		{"/users", "daftar user terdaftar (admin)"},
		{"/admin-logout <email>", "putus link Telegram user (admin)"},
		{"/logs [n]", "tail n baris log Docker (default 50)"},
		{"/logs -f", "follow log live  (Ctrl+C untuk stop)"},
		{"/shell", "drop ke shell  —  exit untuk kembali"},
		{"/clear", "bersihkan output TUI"},
		{"/quit", "keluar dari TUI"},
		{"", ""},
		{"(teks bebas)", "kirim chat ke bot  —  perlu /login dulu"},
	}
	for _, e := range entries {
		if e.name == "" {
			lines = append(lines, simpleLine("", ""))
			continue
		}
		lines = append(lines, OutputLine{Parts: []OutputPart{
			{Class: "cmd.name", Text: fmt.Sprintf("  %-26s", e.name)},
			{Class: "cmd.desc", Text: e.desc},
		}})
	}

	for _, l := range lines {
		m.appendLine(l)
	}
	return nil
}

// ── /login ────────────────────────────────────────────────────────────────────

func (m *Model) cmdLogin() tea.Cmd {
	if m.session != nil {
		m.appendLine(simpleLine("warn", "  already logged in as "+m.session.Email+". /logout first."))
		return nil
	}
	if m.loginActive {
		m.appendLine(simpleLine("warn", "  login already in progress…"))
		return nil
	}
	m.loginActive = true

	// Cancel any previous polling goroutine.
	if m.loginCancel != nil {
		m.loginCancel()
		m.loginCancel = nil
	}

	program := m.program
	cfg := m.cfg

	return func() tea.Msg {
		code, loginURL, err := api.TUIStart(cfg.AppURL)
		if err != nil {
			return loginFailedMsg{reason: "cannot reach backend: " + err.Error()}
		}

		// Render QR code.
		qrStr, qrErr := qr.Render(loginURL)
		if qrErr != nil {
			qrStr = "(QR unavailable: " + qrErr.Error() + ")"
		}

		program.Send(outputMsg{simpleLine("section", "\n  Scan to login:")})
		for _, line := range strings.Split(strings.TrimRight(qrStr, "\n"), "\n") {
			program.Send(outputMsg{simpleLine("ai", line)})
		}
		program.Send(outputMsg{simpleLine("dim", "  Pair code: "+code)})
		program.Send(outputMsg{OutputLine{Parts: []OutputPart{
			{Class: "dim", Text: "  URL: "},
			{Class: "link", Text: loginURL},
		}}})

		if strings.Contains(loginURL, "localhost") || strings.Contains(loginURL, "127.0.0.1") {
			openBrowser(loginURL)
		}

		ctx, cancel := context.WithTimeout(context.Background(), 600*time.Second)
		// Send cancel func back to the model so it can be cancelled later.
		program.Send(storeCancelMsg{cancel: cancel})

		go func() {
			defer cancel()
			ticker := time.NewTicker(2 * time.Second)
			defer ticker.Stop()
			for {
				select {
				case <-ctx.Done():
					program.Send(loginFailedMsg{reason: "timeout or cancelled"})
					return
				case <-ticker.C:
					token, pending, pollErr := api.TUIPoll(cfg.AppURL, code)
					if pollErr != nil {
						program.Send(loginFailedMsg{reason: pollErr.Error()})
						return
					}
					if pending {
						continue
					}
					if token == "" {
						program.Send(loginFailedMsg{reason: "empty token"})
						return
					}
					me, meErr := api.Me(cfg.AppURL, token)
					if meErr != nil {
						program.Send(loginFailedMsg{reason: "session validate: " + meErr.Error()})
						return
					}
					sess := &session.Session{
						Token:       token,
						UserID:      mapStrVal(me, "user_id"),
						Email:       mapStrVal(me, "email"),
						DisplayName: mapStrVal(me, "display_name"),
						BackendURL:  cfg.AppURL,
					}
					program.Send(loginSuccessMsg{sess: sess})
					return
				}
			}
		}()

		return nil
	}
}

// ── /logout ───────────────────────────────────────────────────────────────────

func (m *Model) cmdLogout() tea.Cmd {
	if m.session == nil {
		m.appendLine(simpleLine("warn", "  not logged in"))
		return nil
	}
	sess := m.session
	cfg := m.cfg
	program := m.program
	return func() tea.Msg {
		if err := api.TUILogout(cfg.AppURL, sess.Token); err != nil {
			program.Send(outputMsg{simpleLine("warn", "  backend logout error: "+err.Error())})
		}
		session.Clear()
		program.Send(outputMsg{simpleLine("ok", "  ✓ logged out")})
		program.Send(logoutDoneMsg{})
		return nil
	}
}

// ── /me ───────────────────────────────────────────────────────────────────────

func (m *Model) cmdMe() tea.Cmd {
	if m.session == nil {
		m.appendLine(simpleLine("warn", "  not logged in"))
		return nil
	}
	sess := m.session
	m.appendLine(OutputLine{Parts: []OutputPart{
		{Class: "table.hdr", Text: "  email:       "},
		{Class: "user.email", Text: sess.Email},
	}})
	m.appendLine(OutputLine{Parts: []OutputPart{
		{Class: "table.hdr", Text: "  display:     "},
		{Class: "ai", Text: sess.DisplayName},
	}})
	m.appendLine(OutputLine{Parts: []OutputPart{
		{Class: "table.hdr", Text: "  user_id:     "},
		{Class: "dim", Text: sess.UserID},
	}})
	m.appendLine(OutputLine{Parts: []OutputPart{
		{Class: "table.hdr", Text: "  backend:     "},
		{Class: "link", Text: sess.BackendURL},
	}})
	return nil
}

// ── /pair-telegram ────────────────────────────────────────────────────────────

func (m *Model) cmdPairTelegram(args []string) tea.Cmd {
	if m.session == nil {
		m.appendLine(simpleLine("warn", "  not logged in. /login first."))
		return nil
	}

	// Usage: /pair-telegram <bot_token>
	if len(args) == 0 {
		m.appendLine(simpleLine("section", "\n  Link Telegram Bot ke akun kamu:"))
		m.appendLine(simpleLine("dim",     "  1. Buat bot baru via @BotFather di Telegram"))
		m.appendLine(simpleLine("dim",     "  2. Copy token yang diberikan BotFather"))
		m.appendLine(simpleLine("dim",     "  3. Jalankan: /pair-telegram <token>"))
		m.appendLine(simpleLine("dim",     ""))
		m.appendLine(simpleLine("dim",     "  Contoh:"))
		m.appendLine(simpleLine("code",    "  /pair-telegram 1234567890:ABCDEFabcdefGHIJKL..."))
		return nil
	}

	botToken := strings.TrimSpace(args[0])
	sess := m.session
	cfg := m.cfg
	program := m.program

	return func() tea.Msg {
		// Validasi token + ambil username bot dari Telegram API
		program.Send(outputMsg{simpleLine("dim", "  Validating bot token...")})
		botUsername, err := api.TelegramGetMe(botToken)
		if err != nil {
			return outputMsg{simpleLine("err", "  Token tidak valid: "+err.Error())}
		}
		program.Send(outputMsg{simpleLine("ok", fmt.Sprintf("  Bot: @%s ✓", botUsername))})

		// Minta pair code dari Core, sertakan bot username untuk deep link
		program.Send(outputMsg{simpleLine("dim", "  Generating pair code...")})
		code, deepLink, expires, err := api.TelegramPairInit(cfg.AppURL, sess.Token, botUsername)
		if err != nil {
			return outputMsg{simpleLine("err", "  pair-init failed: "+err.Error())}
		}

		program.Send(outputMsg{simpleLine("section", "\n  Buka bot dan kirim perintah /start:")})
		program.Send(outputMsg{simpleLine("dim", fmt.Sprintf("  expires: %ds", expires))})

		if deepLink != "" {
			program.Send(outputMsg{OutputLine{Parts: []OutputPart{
				{Class: "dim", Text: "  link: "},
				{Class: "link", Text: deepLink},
			}}})
			program.Send(outputMsg{simpleLine("dim", "")})
			qrStr, qrErr := qr.Render(deepLink)
			if qrErr == nil {
				for _, line := range strings.Split(strings.TrimRight(qrStr, "\n"), "\n") {
					program.Send(outputMsg{simpleLine("ai", line)})
				}
			}
		} else {
			// Tidak ada deep link (bot_username tidak dikenal) — tampilkan code saja
			program.Send(outputMsg{simpleLine("dim", fmt.Sprintf("  Buka @%s dan kirim:", botUsername))})
			program.Send(outputMsg{simpleLine("code", fmt.Sprintf("  /start %s", code))})
		}
		return nil
	}
}

// ── /status ───────────────────────────────────────────────────────────────────

func (m *Model) cmdStatus() tea.Cmd {
	cfg := m.cfg
	program := m.program
	return func() tea.Msg {
		online, mode, err := api.Health(cfg.AppURL)
		if err != nil {
			return outputMsg{simpleLine("err", "  health check failed: "+err.Error())}
		}
		if !online {
			return outputMsg{simpleLine("err", "  backend offline")}
		}
		program.Send(outputMsg{simpleLine("ok", "  ● online")})
		if mode != "" {
			program.Send(outputMsg{simpleLine("dim", "  mode: "+mode)})
		}

		if cfg.AdminToken != "" {
			status, statusErr := api.AdminStatus(cfg.AppURL, cfg.AdminToken)
			if statusErr == nil {
				for k, v := range status {
					program.Send(outputMsg{simpleLine("dim", fmt.Sprintf("  %s: %v", k, v))})
				}
			}
		}
		return nil
	}
}

// ── /users ────────────────────────────────────────────────────────────────────

func (m *Model) cmdUsers() tea.Cmd {
	if m.cfg.AdminToken == "" {
		m.appendLine(simpleLine("warn", "  OCTOPUS_ADMIN_TOKEN not set"))
		return nil
	}
	cfg := m.cfg
	program := m.program
	return func() tea.Msg {
		users, err := api.AdminUsers(cfg.AppURL, cfg.AdminToken)
		if err != nil {
			return outputMsg{simpleLine("err", "  /users failed: "+err.Error())}
		}
		program.Send(outputMsg{OutputLine{Parts: []OutputPart{
			{Class: "table.hdr", Text: fmt.Sprintf("  %-32s %-24s %-14s %s", "email", "name", "telegram", "created")},
		}}})
		program.Send(outputMsg{simpleLine("rule", "  "+strings.Repeat("─", 80))})
		for _, u := range users {
			email := mapStrVal(u, "email")
			name := mapStrVal(u, "display_name")
			tg := mapStrVal(u, "telegram_username")
			created := mapStrVal(u, "created_at")
			if len(created) > 10 {
				created = created[:10]
			}
			program.Send(outputMsg{OutputLine{Parts: []OutputPart{
				{Class: "user.email", Text: fmt.Sprintf("  %-32s", email)},
				{Class: "ai", Text: fmt.Sprintf("%-24s", name)},
				{Class: "dim", Text: fmt.Sprintf("%-14s", tg)},
				{Class: "dim", Text: created},
			}}})
		}
		return nil
	}
}

// ── /admin-logout ─────────────────────────────────────────────────────────────

func (m *Model) cmdAdminLogout(email string) tea.Cmd {
	if m.cfg.AdminToken == "" {
		m.appendLine(simpleLine("warn", "  OCTOPUS_ADMIN_TOKEN not set"))
		return nil
	}
	cfg := m.cfg
	return func() tea.Msg {
		result, err := api.AdminLogout(cfg.AppURL, cfg.AdminToken, email)
		if err != nil {
			return outputMsg{simpleLine("err", "  admin-logout failed: "+err.Error())}
		}
		msg := mapStrVal(result, "message")
		if msg == "" {
			msg = "done"
		}
		return outputMsg{simpleLine("ok", "  ✓ "+msg)}
	}
}

// ── /logs ─────────────────────────────────────────────────────────────────────

func (m *Model) cmdLogs(args []string) tea.Cmd {
	container := m.cfg.DockerLogContainer

	if len(args) > 0 && args[0] == "-f" {
		return tea.ExecProcess(exec.Command("docker", "logs", "-f", container), func(err error) tea.Msg {
			if err != nil {
				return outputMsg{simpleLine("warn", "  docker logs exited: "+err.Error())}
			}
			return outputMsg{simpleLine("dim", "  (follow mode ended)")}
		})
	}

	n := "50"
	if len(args) > 0 {
		if _, err := strconv.Atoi(args[0]); err == nil {
			n = args[0]
		}
	}

	program := m.program
	return func() tea.Msg {
		cmd := exec.Command("docker", "logs", "--tail", n, container)
		out, err := cmd.CombinedOutput()
		if err != nil {
			return outputMsg{simpleLine("err", "  docker logs error: "+err.Error())}
		}
		scanner := bufio.NewScanner(strings.NewReader(string(out)))
		for scanner.Scan() {
			program.Send(outputMsg{simpleLine("dim", scanner.Text())})
		}
		return nil
	}
}

// ── /shell ────────────────────────────────────────────────────────────────────

func (m *Model) cmdShell() tea.Cmd {
	shell := os.Getenv("SHELL")
	if shell == "" {
		shell = "/bin/sh"
	}
	return tea.ExecProcess(exec.Command(shell), func(err error) tea.Msg {
		if err != nil {
			return outputMsg{simpleLine("warn", "  shell exited: "+err.Error())}
		}
		return outputMsg{simpleLine("dim", "  (returned from shell)")}
	})
}

// ── /clear ────────────────────────────────────────────────────────────────────

func (m *Model) cmdClear() tea.Cmd {
	m.lines = nil
	m.streamBuf = ""
	m.rebuildViewport()
	return nil
}

// ── /agents ───────────────────────────────────────────────────────────────────

func (m *Model) cmdAgents(args []string) tea.Cmd {
	if m.session == nil {
		m.appendLine(simpleLine("warn", "  not logged in. /login first."))
		return nil
	}
	sess := m.session
	cfg := m.cfg
	program := m.program

	if len(args) == 0 {
		return func() tea.Msg {
			agents, err := api.GetAgents(cfg.AppURL, sess.Token)
			if err != nil {
				return outputMsg{simpleLine("err", "  /agents failed: "+err.Error())}
			}
			program.Send(outputMsg{OutputLine{Parts: []OutputPart{
				{Class: "table.hdr", Text: fmt.Sprintf("  %-16s %-8s %-16s %-8s %s", "agent", "enabled", "role", "workers", "model")},
			}}})
			program.Send(outputMsg{simpleLine("rule", "  "+strings.Repeat("─", 64))})
			for _, a := range agents {
				name := mapStrVal(a, "name")
				enabled := fmt.Sprintf("%v", a["enabled"])
				role := mapStrVal(a, "role")
				workers := fmt.Sprintf("%v", a["workers"])
				model := mapStrVal(a, "model")
				program.Send(outputMsg{OutputLine{Parts: []OutputPart{
					{Class: "cmd.name", Text: fmt.Sprintf("  %-16s", name)},
					{Class: "dim", Text: fmt.Sprintf("%-8s %-16s %-8s %s", enabled, role, workers, model)},
				}}})
			}
			return nil
		}
	}

	agentName := args[0]
	if len(args) < 2 {
		m.appendLine(simpleLine("warn", "  usage: /agents <name> on|off|role <role>|model <model>"))
		return nil
	}

	action := strings.ToLower(args[1])
	payload := map[string]any{}

	switch action {
	case "on":
		payload["enabled"] = true
	case "off":
		payload["enabled"] = false
	case "role":
		if len(args) < 3 {
			m.appendLine(simpleLine("warn", "  usage: /agents <name> role <role>"))
			return nil
		}
		payload["role"] = args[2]
	case "model":
		if len(args) < 3 {
			m.appendLine(simpleLine("warn", "  usage: /agents <name> model <model>"))
			return nil
		}
		payload["model"] = args[2]
	default:
		m.appendLine(simpleLine("warn", "  unknown action: "+action))
		return nil
	}

	return func() tea.Msg {
		result, err := api.UpdateAgent(cfg.AppURL, sess.Token, agentName, payload)
		if err != nil {
			return outputMsg{simpleLine("err", "  update agent failed: "+err.Error())}
		}
		msg := mapStrVal(result, "message")
		if msg == "" {
			msg = "updated"
		}
		return outputMsg{simpleLine("ok", "  ✓ "+msg)}
	}
}

// ── /audit ────────────────────────────────────────────────────────────────────

func (m *Model) cmdAudit(n int) tea.Cmd {
	if m.cfg.AdminToken == "" {
		m.appendLine(simpleLine("warn", "  OCTOPUS_ADMIN_TOKEN not set"))
		return nil
	}
	cfg := m.cfg
	program := m.program
	return func() tea.Msg {
		entries, err := api.AdminAudit(cfg.AppURL, cfg.AdminToken, n)
		if err != nil {
			return outputMsg{simpleLine("err", "  /audit failed: "+err.Error())}
		}
		program.Send(outputMsg{OutputLine{Parts: []OutputPart{
			{Class: "table.hdr", Text: fmt.Sprintf("  %-22s %-18s %-12s %-8s %s", "ts", "event", "agent", "status", "preview")},
		}}})
		program.Send(outputMsg{simpleLine("rule", "  "+strings.Repeat("─", 80))})
		for _, e := range entries {
			ts := mapStrVal(e, "ts")
			if len(ts) > 22 {
				ts = ts[:22]
			}
			event := mapStrVal(e, "event")
			agent := mapStrVal(e, "agent")
			status := mapStrVal(e, "status")
			preview := mapStrVal(e, "preview")
			if len(preview) > 40 {
				preview = preview[:40] + "…"
			}
			program.Send(outputMsg{OutputLine{Parts: []OutputPart{
				{Class: "dim", Text: fmt.Sprintf("  %-22s %-18s %-12s %-8s %s", ts, event, agent, status, preview)},
			}}})
		}
		return nil
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// mapStrVal safely extracts a string value from a map[string]any.
func mapStrVal(m map[string]any, key string) string {
	if m == nil {
		return ""
	}
	if v, ok := m[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
		return fmt.Sprintf("%v", v)
	}
	return ""
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "linux":
		cmd = exec.Command("xdg-open", url)
	default:
		return
	}
	_ = cmd.Start()
}
