package voice

import (
	"context"
	"errors"
)

var ErrNotConfigured = errors.New("tts belum dikonfigurasi")

type TextToSpeech interface {
	Synthesize(ctx context.Context, text string) ([]byte, error)
}
