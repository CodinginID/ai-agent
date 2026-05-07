package tui

import (
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"

	"github.com/codinginid/octopus/internal/api"
	"github.com/codinginid/octopus/internal/config"
	"github.com/codinginid/octopus/internal/session"
)

// Init returns the initial batch of commands on startup.
// Implements tea.Model on *Model.
func (m *Model) Init() tea.Cmd {
	return tea.Batch(
		textinput.Blink,
		checkStatusCmd(m.cfg),
		restoreSessionCmd(m.cfg),
		tickCmd(),
	)
}

// Update is the central Bubble Tea update function.
// Implements tea.Model on *Model.
func (m *Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.viewport = viewport.New(m.width, m.viewportHeight())
		m.input.Width = m.width - 4
		m.rebuildViewport()
		m.viewport.GotoBottom()

	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "ctrl+d":
			m.running = false
			if m.loginCancel != nil {
				m.loginCancel()
			}
			return m, tea.Quit

		case "enter":
			cmd := m.handleSubmit()
			return m, cmd

		case "up":
			if len(m.history) > 0 {
				if m.histIdx < 0 {
					m.histIdx = len(m.history) - 1
				} else if m.histIdx > 0 {
					m.histIdx--
				}
				m.input.SetValue(m.history[m.histIdx])
				m.input.CursorEnd()
			}

		case "down":
			if m.histIdx >= 0 {
				m.histIdx++
				if m.histIdx >= len(m.history) {
					m.histIdx = -1
					m.input.SetValue("")
				} else {
					m.input.SetValue(m.history[m.histIdx])
					m.input.CursorEnd()
				}
			}

		case "tab":
			cmd := m.handleTab()
			return m, cmd

		default:
			m.completions = nil
			m.compIdx = 0
			var inputCmd tea.Cmd
			m.input, inputCmd = m.input.Update(msg)
			cmds = append(cmds, inputCmd)
		}

	case tickMsg:
		cmds = append(cmds, checkStatusCmd(m.cfg), tickCmd())

	case statusUpdateMsg:
		m.status = StatusInfo{
			Online: msg.online,
			Mode:   msg.mode,
			Users:  msg.users,
		}

	case outputMsg:
		m.appendLine(msg.line)

	case chatChunkMsg:
		m.streamBuf += msg.text
		m.rebuildViewport()
		m.viewport.GotoBottom()

	case chatDoneMsg:
		if m.streamBuf != "" {
			m.appendLine(simpleLine("ai", m.streamBuf))
			m.streamBuf = ""
		}
		m.rebuildViewport()
		m.viewport.GotoBottom()

	case loginSuccessMsg:
		m.session = msg.sess
		if err := session.Save(msg.sess); err != nil {
			m.appendLine(simpleLine("warn", "  could not save session: "+err.Error()))
		}
		m.loginActive = false
		m.appendLine(simpleLine("ok", "  ✓ logged in as "+msg.sess.Email))
		if m.cfg.AdminToken != "" {
			cmds = append(cmds, loadEmailsCmd(m.cfg))
		}

	case loginFailedMsg:
		m.loginActive = false
		m.appendLine(simpleLine("err", "  ✗ login failed: "+msg.reason))

	case sessionRestoredMsg:
		m.session = msg.sess
		m.appendLine(simpleLine("dim", "  ✓ session restored: "+msg.sess.Email))
		if m.cfg.AdminToken != "" {
			cmds = append(cmds, loadEmailsCmd(m.cfg))
		}

	case emailsLoadedMsg:
		m.emails = msg.emails

	case workerStatusMsg:
		if msg.connected {
			m.appendLine(simpleLine("dim", "  ✓ worker terhubung ke backend (id="+msg.workerID+")"))
		} else {
			m.appendLine(simpleLine("dim", "  worker disconnected, reconnecting…"))
		}

	case storeCancelMsg:
		m.loginCancel = msg.cancel

	case logoutDoneMsg:
		m.session = nil

	case upgradeResultMsg:
		if msg.err != nil {
			m.appendLine(simpleLine("err", "  upgrade failed: "+msg.err.Error()))
		} else {
			m.appendLine(simpleLine("ok", "  ✓ upgraded to "+msg.newVersion+" — restart to apply"))
		}

	default:
		var vpCmd tea.Cmd
		m.viewport, vpCmd = m.viewport.Update(msg)
		cmds = append(cmds, vpCmd)
	}

	return m, tea.Batch(cmds...)
}

// handleSubmit processes the Enter key press.
func (m *Model) handleSubmit() tea.Cmd {
	text := strings.TrimSpace(m.input.Value())
	m.input.SetValue("")
	m.histIdx = -1
	m.completions = nil
	m.compIdx = 0

	if text == "" {
		return nil
	}

	m.history = append(m.history, text)
	m.appendHistoryFile(text)

	m.appendLine(OutputLine{Parts: []OutputPart{
		{Class: "echo.prompt", Text: "> "},
		{Class: "echo.text", Text: text},
	}})

	if strings.HasPrefix(text, "/") {
		return m.dispatchCommand(text)
	}

	if m.session == nil {
		m.appendLine(simpleLine("warn", "  belum login. Ketik /login dulu."))
		return nil
	}
	return sendChatCmd(m.cfg.AppURL, m.session.Token, text, m.program)
}

// handleTab cycles through completions.
func (m *Model) handleTab() tea.Cmd {
	val := m.input.Value()

	if len(m.completions) == 0 {
		m.completions = buildCompletions(val, m.emails)
		m.compIdx = 0
	}

	if len(m.completions) == 0 {
		return nil
	}

	m.input.SetValue(m.completions[m.compIdx])
	m.input.CursorEnd()
	m.compIdx = (m.compIdx + 1) % len(m.completions)
	return nil
}

// buildCompletions generates completions for the current input value.
func buildCompletions(val string, emails []string) []string {
	commands := []string{
		"/help", "/login", "/logout", "/me", "/pair-telegram",
		"/status", "/users", "/admin-logout ", "/logs", "/logs -f",
		"/shell", "/clear", "/quit", "/agents", "/audit",
	}

	prefix := strings.ToLower(val)
	var matches []string

	if strings.HasPrefix(prefix, "/admin-logout ") {
		partial := val[len("/admin-logout "):]
		for _, email := range emails {
			if strings.HasPrefix(email, partial) {
				matches = append(matches, "/admin-logout "+email)
			}
		}
		return matches
	}

	for _, cmd := range commands {
		if strings.HasPrefix(strings.ToLower(cmd), prefix) {
			matches = append(matches, cmd)
		}
	}
	return matches
}

// ── Background commands ───────────────────────────────────────────────────────

func tickCmd() tea.Cmd {
	return tea.Tick(30*time.Second, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

func checkStatusCmd(cfg *config.Config) tea.Cmd {
	appURL := cfg.AppURL
	return func() tea.Msg {
		online, mode, err := api.Health(appURL)
		if err != nil {
			return statusUpdateMsg{online: false}
		}
		return statusUpdateMsg{online: online, mode: mode}
	}
}

func restoreSessionCmd(cfg *config.Config) tea.Cmd {
	appURL := cfg.AppURL
	return func() tea.Msg {
		sess := session.Load(appURL)
		if sess == nil {
			return nil
		}
		_, err := api.Me(appURL, sess.Token)
		if err != nil {
			return nil
		}
		return sessionRestoredMsg{sess: sess}
	}
}

func loadEmailsCmd(cfg *config.Config) tea.Cmd {
	appURL := cfg.AppURL
	adminToken := cfg.AdminToken
	return func() tea.Msg {
		emails, err := api.FetchEmails(appURL, adminToken)
		if err != nil {
			return nil
		}
		return emailsLoadedMsg{emails: emails}
	}
}
