// Package qr renders a QR code as unicode block characters for terminal display.
package qr

import (
	"strings"

	qrcode "github.com/skip2/go-qrcode"
)

// Render encodes text as a QR code and returns a multi-line string using
// unicode block characters. Two QR rows are packed into one terminal line
// using ▀ (upper half), ▄ (lower half), █ (full), and space.
func Render(text string) (string, error) {
	qr, err := qrcode.New(text, qrcode.Low)
	if err != nil {
		return "", err
	}
	qr.DisableBorder = false

	bitmap := qr.Bitmap()

	var sb strings.Builder
	for y := 0; y < len(bitmap); y += 2 {
		row := bitmap[y]
		var nextRow []bool
		if y+1 < len(bitmap) {
			nextRow = bitmap[y+1]
		}
		for x := 0; x < len(row); x++ {
			top := row[x]
			bot := false
			if nextRow != nil && x < len(nextRow) {
				bot = nextRow[x]
			}
			switch {
			case top && bot:
				sb.WriteRune('█')
			case top && !bot:
				sb.WriteRune('▀')
			case !top && bot:
				sb.WriteRune('▄')
			default:
				sb.WriteRune(' ')
			}
		}
		sb.WriteRune('\n')
	}
	return sb.String(), nil
}
