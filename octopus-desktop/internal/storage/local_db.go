// octopus-desktop/internal/storage/local_db.go
// Package storage menyediakan cache offline berbasis SQLite untuk menyimpan
// pesan chat dan antrian pesan saat aplikasi tidak terhubung ke gateway.
package storage

import (
	"database/sql"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// Message merepresentasikan satu pesan chat yang disimpan di cache lokal.
type Message struct {
	ID        string
	UserID    string
	Text      string
	CreatedAt time.Time
	Sent      bool
}

// LocalDB adalah cache offline berbasis SQLite.
type LocalDB struct {
	db   *sql.DB
	path string
	mu   sync.Mutex
}

// NewLocalDB membuat atau membuka database SQLite di path yang diberikan.
func NewLocalDB(path string) (*LocalDB, error) {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("buat folder database gagal: %w", err)
	}
	drv, err := sql.Open("sqlite3", path+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("buka database gagal: %w", err)
	}
	drv.SetMaxOpenConns(1)
	drv.SetMaxIdleConns(1)
	return &LocalDB{db: drv, path: path}, nil
}

// Open memastikan semua tabel sudah ada di database.
func (l *LocalDB) Open() error {
	schema := `
	CREATE TABLE IF NOT EXISTS messages (
		id TEXT PRIMARY KEY,
		user_id TEXT NOT NULL,
		text TEXT NOT NULL,
		created_at TEXT NOT NULL
	);
	CREATE TABLE IF NOT EXISTS pending_messages (
		id TEXT PRIMARY KEY,
		text TEXT NOT NULL,
		created_at TEXT NOT NULL,
		sent INTEGER NOT NULL DEFAULT 0
	);
	CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
	CREATE INDEX IF NOT EXISTS idx_pending_messages_created ON pending_messages(created_at);
	`
	if _, err := l.db.Exec(schema); err != nil {
		return fmt.Errorf("buat tabel gagal: %w", err)
	}
	return nil
}

// Close tutup koneksi database.
func (l *LocalDB) Close() error {
	if l.db != nil {
		return l.db.Close()
	}
	return nil
}

// SaveMessage simpan pesan ke tabel messages.
func (l *LocalDB) SaveMessage(msg Message) error {
	_, err := l.db.Exec(
		`INSERT OR REPLACE INTO messages (id, user_id, text, created_at) VALUES (?, ?, ?, ?)`,
		msg.ID, msg.UserID, msg.Text, msg.CreatedAt.Format(time.RFC3339),
	)
	if err != nil {
		return fmt.Errorf("simpan pesan gagal: %w", err)
	}
	return nil
}

// GetMessages ambil pesan berdasarkan user_id, diurutkan terbaru dulu.
func (l *LocalDB) GetMessages(userID string, limit int) ([]Message, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := l.db.Query(
		`SELECT id, user_id, text, created_at FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?`,
		userID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("query pesan gagal: %w", err)
	}
	defer rows.Close()

	var msgs []Message
	for rows.Next() {
		var msg Message
		var createdAt string
		if err := rows.Scan(&msg.ID, &msg.UserID, &msg.Text, &createdAt); err != nil {
			return nil, fmt.Errorf("scan pesan gagal: %w", err)
		}
		msg.CreatedAt, err = time.Parse(time.RFC3339, createdAt)
		if err != nil {
			slog.Warn("parse created_at gagal", "id", msg.ID, "error", err)
			msg.CreatedAt = time.Time{}
		}
		msgs = append(msgs, msg)
	}
	return msgs, rows.Err()
}

// QueueMessage tambahkan pesan ke antrian pending.
func (l *LocalDB) QueueMessage(text string) error {
	id := fmt.Sprintf("pending-%d", time.Now().UnixNano())
	now := time.Now()
	_, err := l.db.Exec(
		`INSERT OR REPLACE INTO pending_messages (id, text, created_at, sent) VALUES (?, ?, ?, 0)`,
		id, text, now.Format(time.RFC3339),
	)
	if err != nil {
		return fmt.Errorf("antri pesan gagal: %w", err)
	}
	slog.Debug("pesan diantri", "id", id, "text", text)
	return nil
}

// MarkSent tandai pesan sudah dikirim ke gateway.
func (l *LocalDB) MarkSent(id string) error {
	res, err := l.db.Exec(`UPDATE pending_messages SET sent = 1 WHERE id = ?`, id)
	if err != nil {
		return fmt.Errorf("tandai pesan terkirim gagal: %w", err)
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		slog.Warn("tandai pesan tidak ditemukan", "id", id)
	}
	return nil
}

// GetPendingMessages ambil semua pesan yang belum dikirim.
func (l *LocalDB) GetPendingMessages() ([]Message, error) {
	rows, err := l.db.Query(
		`SELECT id, text, created_at FROM pending_messages WHERE sent = 0 ORDER BY created_at ASC`,
	)
	if err != nil {
		return nil, fmt.Errorf("query pesan pending gagal: %w", err)
	}
	defer rows.Close()

	var msgs []Message
	for rows.Next() {
		var msg Message
		var createdAt string
		if err := rows.Scan(&msg.ID, &msg.Text, &createdAt); err != nil {
			return nil, fmt.Errorf("scan pesan pending gagal: %w", err)
		}
		msg.CreatedAt, err = time.Parse(time.RFC3339, createdAt)
		if err != nil {
			slog.Warn("parse created_at pending gagal", "id", msg.ID, "error", err)
			msg.CreatedAt = time.Time{}
		}
		msg.Sent = false
		msgs = append(msgs, msg)
	}
	return msgs, rows.Err()
}

// SyncMessages sinkronkan daftar pesan ke tabel messages.
func (l *LocalDB) SyncMessages(messages []Message) error {
	tx, err := l.db.Begin()
	if err != nil {
		return fmt.Errorf("mulai transaksi gagal: %w", err)
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`INSERT OR REPLACE INTO messages (id, user_id, text, created_at) VALUES (?, ?, ?, ?)`)
	if err != nil {
		return fmt.Errorf("prepare stmt gagal: %w", err)
	}
	defer stmt.Close()

	for _, msg := range messages {
		if _, err := stmt.Exec(msg.ID, msg.UserID, msg.Text, msg.CreatedAt.Format(time.RFC3339)); err != nil {
			return fmt.Errorf("simpan pesan batch gagal: %w", err)
		}
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("komit transaksi gagal: %w", err)
	}
	return nil
}
