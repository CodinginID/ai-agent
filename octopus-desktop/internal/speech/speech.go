package speech

import (
	"context"
	"errors"
)

var ErrNotConfigured = errors.New("stt belum dikonfigurasi")

type SpeechToText interface {
	Transcribe(ctx context.Context, wav []byte) (string, error)
}
