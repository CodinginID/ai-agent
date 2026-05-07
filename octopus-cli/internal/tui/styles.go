// Package tui implements the Bubble Tea TUI for the Octopus CLI.
package tui

import (
	"github.com/charmbracelet/lipgloss"
)

//nolint:gochecknoglobals
var (
	// Logo gradient — each line styled with a slightly different hue.
	LogoL1 = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#06b6d4"))
	LogoL2 = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#0ea5e9"))
	LogoL3 = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#3b82f6"))
	LogoL4 = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#6366f1"))
	LogoL5 = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#8b5cf6"))
	LogoL6 = lipgloss.NewStyle().Foreground(lipgloss.Color("#6d28d9"))
	LogoSub = lipgloss.NewStyle().Foreground(lipgloss.Color("#475569"))
	LogoVer = lipgloss.NewStyle().Foreground(lipgloss.Color("#0891b2"))
	LogoHintKey = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#3d5473"))
	LogoHint    = lipgloss.NewStyle().Foreground(lipgloss.Color("#2d3f55"))

	StyleOK       = lipgloss.NewStyle().Foreground(lipgloss.Color("#34d399"))
	StyleErr      = lipgloss.NewStyle().Foreground(lipgloss.Color("#f87171"))
	StyleWarn     = lipgloss.NewStyle().Foreground(lipgloss.Color("#fbbf24"))
	StyleDim      = lipgloss.NewStyle().Foreground(lipgloss.Color("#4a6080"))
	StyleAI       = lipgloss.NewStyle().Foreground(lipgloss.Color("#e2e8f0"))
	StyleCmdName  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#38bdf8"))
	StyleCmdDesc  = lipgloss.NewStyle().Foreground(lipgloss.Color("#64748b"))
	StyleLink     = lipgloss.NewStyle().Foreground(lipgloss.Color("#60a5fa")).Underline(true)
	StyleSection  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#e2e8f0"))
	StyleRule     = lipgloss.NewStyle().Foreground(lipgloss.Color("#1e3350"))
	StyleTableHdr = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#4a6080"))
	StyleUserEmail  = lipgloss.NewStyle().Foreground(lipgloss.Color("#60a5fa"))
	StyleEchoPrompt = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#06b6d4"))
	StyleEchoText   = lipgloss.NewStyle().Foreground(lipgloss.Color("#94a3b8"))

	// Status bar.
	StatusBarStyle = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30"))
	StatusOK       = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Foreground(lipgloss.Color("#34d399"))
	StatusErr      = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Foreground(lipgloss.Color("#f87171"))
	StatusWarn     = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Foreground(lipgloss.Color("#fbbf24"))
	StatusDim      = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Foreground(lipgloss.Color("#4a6080"))
	StatusUser     = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Bold(true).Foreground(lipgloss.Color("#60a5fa"))
	StatusSep      = lipgloss.NewStyle().Background(lipgloss.Color("#0f1c30")).Foreground(lipgloss.Color("#1e3350"))

	// Input area.
	InputStyle  = lipgloss.NewStyle().BorderStyle(lipgloss.NormalBorder()).BorderForeground(lipgloss.Color("#1e3350"))
	InputPrefix = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#06b6d4"))
)

// StyleFor returns the lipgloss style for a given class name string.
// Class names come from OutputPart.Class and SSE event rendering.
func StyleFor(class string) lipgloss.Style {
	switch class {
	case "ok":
		return StyleOK
	case "err":
		return StyleErr
	case "warn":
		return StyleWarn
	case "dim":
		return StyleDim
	case "ai":
		return StyleAI
	case "cmd.name":
		return StyleCmdName
	case "cmd.desc":
		return StyleCmdDesc
	case "link":
		return StyleLink
	case "section":
		return StyleSection
	case "rule":
		return StyleRule
	case "table.hdr":
		return StyleTableHdr
	case "user.email":
		return StyleUserEmail
	case "echo.prompt":
		return StyleEchoPrompt
	case "echo.text":
		return StyleEchoText
	default:
		return lipgloss.NewStyle()
	}
}
