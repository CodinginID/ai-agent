package main

import (
	"errors"
	"testing"

	"github.com/codinginid/octopus-desktop/internal/gateway"
)

func TestRelayEventsForwardsAllThenStreamError(t *testing.T) {
	out := make(chan gateway.Event, 3)
	out <- gateway.Event{Type: "thinking", Data: map[string]any{"message": "m"}}
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)

	var got []map[string]any
	emit := func(payload map[string]any) { got = append(got, payload) }

	relayEvents("msg-1", out, errors.New("putus"), emit)

	if len(got) != 3 {
		t.Fatalf("harus 2 event + 1 stream_error, got %d: %+v", len(got), got)
	}
	if got[0]["msgId"] != "msg-1" || got[0]["type"] != "thinking" {
		t.Fatalf("event pertama salah: %+v", got[0])
	}
	if got[2]["type"] != "stream_error" {
		t.Fatalf("event terakhir harus stream_error: %+v", got[2])
	}
}

func TestRelayEventsNoErrorNoStreamError(t *testing.T) {
	out := make(chan gateway.Event, 1)
	out <- gateway.Event{Type: "final", Data: map[string]any{"text": "ok"}}
	close(out)
	var got []map[string]any
	relayEvents("m", out, nil, func(p map[string]any) { got = append(got, p) })
	if len(got) != 1 {
		t.Fatalf("tidak boleh ada stream_error: %+v", got)
	}
}
