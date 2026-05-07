package tui

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/codinginid/octopus/internal/config"
	"github.com/codinginid/octopus/internal/session"
)

// ── Message types ────────────────────────────────────────────────────────────

type tickMsg time.Time

type statusUpdateMsg struct {
	online bool
	mode   string
	users  int
}

type outputMsg struct{ line OutputLine }

type chatChunkMsg struct{ text string }

type chatDoneMsg struct{}

type loginPairCodeMsg struct {
	code     string
	loginURL string
}

type loginSuccessMsg struct{ sess *session.Session }

type loginFailedMsg struct{ reason string }

type sessionRestoredMsg struct{ sess *session.Session }

type emailsLoadedMsg struct{ emails []string }

type workerStatusMsg struct {
	connected bool
	workerID  string
}

type upgradeResultMsg struct {
	newVersion string
	err        error
}

type storeCancelMsg struct{ cancel func() }

type logoutDoneMsg struct{}

// ── Output ────────────────────────────────────────────────────────────────────

// OutputPart is one styled segment within a line.
type OutputPart struct {
	Class string
	Text  string
}

// OutputLine is a collection of styled parts that form one logical output line.
type OutputLine struct {
	Parts []OutputPart
}

// Render returns the rendered string of the line, word-wrapping at width.
func (l OutputLine) Render(width int) string {
	var sb strings.Builder
	for _, p := range l.Parts {
		style := StyleFor(p.Class)
		sb.WriteString(style.Render(p.Text))
	}
	result := sb.String()
	if width > 0 {
		result = lipgloss.NewStyle().MaxWidth(width).Render(result)
	}
	return result
}

// simpleLine is a convenience constructor for a single-part line.
func simpleLine(class, text string) OutputLine {
	return OutputLine{Parts: []OutputPart{{Class: class, Text: text}}}
}

// ── StatusInfo ────────────────────────────────────────────────────────────────

// StatusInfo holds the most recent status from the backend.
type StatusInfo struct {
	Online bool
	Mode   string
	Users  int
}

// ── Model ─────────────────────────────────────────────────────────────────────

// Model is the Bubble Tea model for the Octopus TUI.
type Model struct {
	// Layout dimensions.
	width  int
	height int

	// Bubble Tea components.
	viewport viewport.Model
	input    textinput.Model

	// Application state.
	cfg     *config.Config
	session *session.Session
	status  StatusInfo
	running bool

	// Output buffer.
	lines     []OutputLine
	streamBuf string // accumulates SSE text_chunk data

	// Input history.
	history     []string
	histIdx     int    // -1 = not navigating history
	historyPath string // path to history file

	// Tab completion state.
	emails      []string
	completions []string
	compIdx     int

	// Login state.
	loginActive bool
	loginCancel func() // cancels the active login polling goroutine

	// Reference to the running program (set via SetProgram).
	program *tea.Program
}

// New creates a new Model with defaults applied.
func New(cfg *config.Config) *Model {
	ti := textinput.New()
	ti.Placeholder = "type a message or /command…"
	ti.Focus()
	ti.CharLimit = 2000

	vp := viewport.New(0, 0)
	vp.SetContent("")

	return &Model{
		cfg:     cfg,
		input:   ti,
		viewport: vp,
		histIdx: -1,
		running: true,
	}
}

// SetProgram stores the program reference so goroutines can send messages.
func (m *Model) SetProgram(p *tea.Program) {
	m.program = p
}

// GetSession returns the current session (safe for concurrent read from worker).
func (m *Model) GetSession() *session.Session {
	return m.session
}

// IsRunning returns whether the TUI is still active.
func (m *Model) IsRunning() bool {
	return m.running
}

// LoadHistory reads the history file and populates m.history.
func (m *Model) LoadHistory(path string) {
	m.historyPath = path
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		if t := strings.TrimSpace(scanner.Text()); t != "" {
			m.history = append(m.history, t)
		}
	}
}

// appendHistoryFile appends a single entry to the history file.
func (m *Model) appendHistoryFile(text string) {
	if m.historyPath == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(m.historyPath), 0o700)
	f, err := os.OpenFile(m.historyPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.WriteString(text + "\n")
}

// rebuildViewport regenerates the viewport content from m.lines.
func (m *Model) rebuildViewport() {
	var sb strings.Builder
	for _, line := range m.lines {
		sb.WriteString(line.Render(m.width))
		sb.WriteRune('\n')
	}
	// Append the active streaming buffer as the latest line.
	if m.streamBuf != "" {
		sb.WriteString(StyleAI.Render(m.streamBuf))
	}
	m.viewport.SetContent(sb.String())
}

// viewportHeight calculates the available viewport height:
//
//	total - header(9) - separator(1) - statusbar(1) - inputframe(3)
func (m *Model) viewportHeight() int {
	h := m.height - 9 - 1 - 1 - 3
	if h < 1 {
		h = 1
	}
	return h
}

// appendLine adds a line to output and refreshes the viewport.
func (m *Model) appendLine(line OutputLine) {
	m.lines = append(m.lines, line)
	m.rebuildViewport()
	m.viewport.GotoBottom()
}
