package tui

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// sendChatCmd sends a chat message to the backend via SSE and streams the
// response back to the TUI via program.Send.
func sendChatCmd(baseURL, token, text string, program *tea.Program) tea.Cmd {
	return func() tea.Msg {
		client := &http.Client{Timeout: 120 * time.Second}

		reqBody := fmt.Sprintf(`{"text":%q}`, text)
		req, err := http.NewRequest(http.MethodPost, baseURL+"/chat/send", strings.NewReader(reqBody))
		if err != nil {
			return outputMsg{simpleLine("err", "  chat request error: "+err.Error())}
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Accept", "text/event-stream")
		req.Header.Set("User-Agent", "octopus-tui/0.2.0")

		resp, err := client.Do(req)
		if err != nil {
			return outputMsg{simpleLine("err", "  chat request failed: "+err.Error())}
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusUnauthorized {
			return outputMsg{simpleLine("err", "  session expired. Ketik /login lagi.")}
		}
		if resp.StatusCode != http.StatusOK {
			return outputMsg{simpleLine("err", fmt.Sprintf("  HTTP %d from /chat/send", resp.StatusCode))}
		}

		parseSSE(resp, program)
		return nil
	}
}

// parseSSE reads the SSE stream from resp.Body and dispatches messages to
// the program.
func parseSSE(resp *http.Response, program *tea.Program) {
	scanner := bufio.NewScanner(resp.Body)

	var eventName string
	var dataLines []string
	chatStarted := false

	flush := func() {
		if eventName == "" {
			return
		}
		dataStr := strings.Join(dataLines, "\n")
		var payload map[string]any
		if dataStr != "" {
			_ = json.Unmarshal([]byte(dataStr), &payload)
		}
		if payload == nil {
			payload = map[string]any{}
		}

		switch eventName {
		case "intent_classified":
			intent := sseStrVal(payload, "intent")
			conf := sseFloatVal(payload, "confidence")
			program.Send(outputMsg{simpleLine("dim", fmt.Sprintf("  > intent: %s (%.0f%%)", intent, conf*100))})

		case "thinking":
			program.Send(outputMsg{simpleLine("dim", "  > "+sseStrVal(payload, "message"))})

		case "approval_required":
			planID := sseStrVal(payload, "plan_id")
			summary := sseStrVal(payload, "summary")
			program.Send(outputMsg{simpleLine("warn", fmt.Sprintf("  butuh approval — plan_id=%s", planID))})
			if summary != "" {
				program.Send(outputMsg{simpleLine("", summary)})
			}

		case "action_started":
			program.Send(outputMsg{simpleLine("dim", "  > running "+sseStrVal(payload, "action")+"...")})

		case "action_result":
			output := sseStrVal(payload, "output")
			program.Send(outputMsg{simpleLine("", output)})

		case "text_chunk":
			chunk := sseStrVal(payload, "text")
			chatStarted = true
			program.Send(chatChunkMsg{text: chunk})

		case "final":
			if chatStarted {
				program.Send(chatDoneMsg{})
				chatStarted = false
			} else {
				finalText := sseStrVal(payload, "text")
				if finalText != "" {
					program.Send(outputMsg{simpleLine("ai", "  "+finalText)})
				}
			}

		case "error":
			if chatStarted {
				program.Send(chatDoneMsg{})
				chatStarted = false
			}
			program.Send(outputMsg{simpleLine("err", "  error: "+sseStrVal(payload, "message"))})
		}
	}

	for scanner.Scan() {
		line := scanner.Text()

		if line == "" {
			flush()
			eventName = ""
			dataLines = nil
			continue
		}
		if strings.HasPrefix(line, "event: ") {
			eventName = strings.TrimPrefix(line, "event: ")
		} else if strings.HasPrefix(line, "data: ") {
			dataLines = append(dataLines, strings.TrimPrefix(line, "data: "))
		}
	}
	// Flush any remaining event.
	flush()

	// Ensure streaming is finalised.
	if chatStarted {
		program.Send(chatDoneMsg{})
	}
}

// sseStrVal safely extracts a string value from a parsed SSE payload map.
func sseStrVal(m map[string]any, key string) string {
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

// sseFloatVal safely extracts a float64 value from a parsed SSE payload map.
func sseFloatVal(m map[string]any, key string) float64 {
	if m == nil {
		return 0
	}
	if v, ok := m[key]; ok {
		if f, ok := v.(float64); ok {
			return f
		}
	}
	return 0
}
