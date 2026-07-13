// octopus-desktop/internal/gateway/sse.go
package gateway

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

type Event struct {
	Type string
	Data map[string]any
}

// parseSSE membaca stream SSE dan mengirim tiap event ke out.
// Return nil hanya jika event terminator "done" diterima; stream putus
// sebelum "done" dianggap error supaya UI bisa menandai pesan terputus.
func parseSSE(r io.Reader, out chan<- Event) error {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	var evType, data string
	flush := func() (done bool, err error) {
		if evType == "" {
			return false, nil
		}
		if evType == "done" {
			return true, nil
		}
		payload := map[string]any{}
		if data != "" {
			if err := json.Unmarshal([]byte(data), &payload); err != nil {
				return false, fmt.Errorf("payload sse bukan json valid: %w", err)
			}
		}
		out <- Event{Type: evType, Data: payload}
		return false, nil
	}
	for sc.Scan() {
		line := sc.Text()
		switch {
		case line == "":
			done, err := flush()
			if done || err != nil {
				return err
			}
			evType, data = "", ""
		case strings.HasPrefix(line, "event: "):
			evType = strings.TrimPrefix(line, "event: ")
		case strings.HasPrefix(line, "data: "):
			data = strings.TrimPrefix(line, "data: ")
		}
	}
	if err := sc.Err(); err != nil {
		return fmt.Errorf("stream sse putus: %w", err)
	}
	return fmt.Errorf("stream sse berakhir tanpa event done")
}
