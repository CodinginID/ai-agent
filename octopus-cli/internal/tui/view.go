package tui

import (
	"fmt"
	"strings"
)

// View renders the full TUI screen.
// Implements tea.Model on *Model.
func (m *Model) View() string {
	if m.width == 0 {
		return "loading…"
	}

	var sb strings.Builder
	sb.WriteString(m.renderHeader())
	sb.WriteString(m.renderSeparator())
	sb.WriteString(m.viewport.View())
	sb.WriteString("\n")
	sb.WriteString(m.renderStatusBar())
	sb.WriteString("\n")
	sb.WriteString(m.renderInput())
	return sb.String()
}

// renderHeader renders the 9-line ASCII logo.
func (m *Model) renderHeader() string {
	const (
		l1 = `   ██████╗   ██████╗ ████████╗  ██████╗  ██████╗  ██╗   ██╗ ███████╗`
		l2 = `  ██╔═══██╗ ██╔════╝ ╚══██╔══╝ ██╔═══██╗ ██╔══██╗ ██║   ██║ ██╔════╝`
		l3 = `  ██║   ██║ ██║         ██║    ██║   ██║ ██████╔╝ ██║   ██║ ███████╗`
		l4 = `  ██║   ██║ ██║         ██║    ██║   ██║ ██╔═══╝  ██║   ██║ ╚════██║`
		l5 = `  ╚██████╔╝ ╚██████╗    ██║    ╚██████╔╝ ██║      ╚██████╔╝ ███████║`
		l6 = `   ╚═════╝   ╚═════╝    ╚═╝     ╚═════╝  ╚═╝       ╚═════╝  ╚══════╝`
	)

	sub := "  OCTOPUS  ·  Server Monitoring  ·  Control  ·  AI Chat"
	ver := fmt.Sprintf("  ─────  v%s", m.cfg.Version)
	hints := "  " +
		LogoHintKey.Render("Tab") + LogoHint.Render(" complete   ") +
		LogoHintKey.Render("↑↓") + LogoHint.Render(" history   ") +
		LogoHintKey.Render("/help") + LogoHint.Render(" commands   ") +
		LogoHintKey.Render("Ctrl-C") + LogoHint.Render(" quit")

	return strings.Join([]string{
		LogoL1.Render(l1),
		LogoL2.Render(l2),
		LogoL3.Render(l3),
		LogoL4.Render(l4),
		LogoL5.Render(l5),
		LogoL6.Render(l6),
		LogoSub.Render(sub),
		LogoVer.Render(ver),
		hints,
	}, "\n") + "\n"
}

// renderSeparator renders a full-width horizontal rule.
func (m *Model) renderSeparator() string {
	rule := strings.Repeat("─", m.width)
	return StyleRule.Render(rule) + "\n"
}

// renderStatusBar renders the one-line status bar with background.
func (m *Model) renderStatusBar() string {
	sep := StatusSep.Render("  │  ")

	var indicator string
	if m.status.Online {
		indicator = StatusOK.Render("● online")
	} else if m.running {
		indicator = StatusWarn.Render("◌ connecting…")
	} else {
		indicator = StatusErr.Render("● offline")
	}

	parts := []string{" " + indicator}

	if m.status.Mode != "" {
		parts = append(parts, StatusDim.Render("mode: ")+StatusBarStyle.Render(m.status.Mode))
	}
	if m.status.Users > 0 {
		parts = append(parts, StatusDim.Render(fmt.Sprintf("users: %d", m.status.Users)))
	}
	if m.session != nil {
		parts = append(parts, StatusDim.Render("as: ")+StatusUser.Render(m.session.Email))
	}

	parts = append(parts, StatusDim.Render(m.cfg.AppURL)+" ")

	bar := strings.Join(parts, sep)
	// Pad to full width.
	barLen := lipglossLen(bar)
	if m.width > barLen {
		bar += StatusBarStyle.Render(strings.Repeat(" ", m.width-barLen))
	}
	return bar
}

// renderInput renders the 3-line input frame.
func (m *Model) renderInput() string {
	prefix := InputPrefix.Render("> ")
	content := prefix + m.input.View()
	return InputStyle.Width(m.width - 2).Render(content)
}

// lipglossLen approximates the visible width of a rendered string
// by stripping ANSI escape codes.
func lipglossLen(s string) int {
	// Very simple: count non-escape bytes.
	inEscape := false
	count := 0
	for _, r := range s {
		if r == '\x1b' {
			inEscape = true
			continue
		}
		if inEscape {
			if r == 'm' {
				inEscape = false
			}
			continue
		}
		count++
	}
	return count
}
