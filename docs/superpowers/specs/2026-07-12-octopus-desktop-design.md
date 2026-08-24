# Octopus Desktop — Design Spec

**Tanggal:** 2026-07-12
**Status:** Disetujui user (brainstorming selesai)

## Ringkasan

Aplikasi desktop chat-first untuk Octopus — pengalaman "smart assistant seperti Jarvis": user mengetik atau berbicara dalam bahasa natural, asisten menjawab dengan kartu visual (metrik server, tabel Docker/Git, approval, progress deploy) dan bisa membacakan jawabannya. Aplikasi ini adalah klien baru ke gateway Octopus Core yang sudah ada, sejajar dengan Telegram dan TUI.

## Keputusan Produk

| Aspek | Keputusan |
|---|---|
| Pengalaman utama | Chat-first (seperti Claude/ChatGPT desktop), jawaban berupa kartu visual |
| Input default | **Voice-first (mode Jarvis)** — aplikasi siap mendengarkan; transkrip auto-send; TTS balik aktif default. Input teks tetap tersedia sebagai alternatif |
| Platform | macOS + Windows + Linux |
| Hubungan dengan backend | Klien gateway saja — backend FastAPI tidak berubah; worker tetap via `octopus-cli` |
| Voice input (STT) | **Wajib v1.** Whisper lokal (whisper.cpp), di balik interface swappable |
| Voice output (TTS) | **Wajib v1.** Piper lokal, di balik interface swappable ("mode Jarvis") |
| Privasi | Semua pemrosesan suara lokal di device — konsisten dengan prinsip proyek (tidak ada data ke cloud) |
| Framework | **Wails** (Go + web UI React/TypeScript) — selaras dengan stack Go yang sudah ada (`octopus-cli`, `telegram-adapter`), binary kecil |

## Arsitektur

Direktori baru `octopus-desktop/` di repo ini, terdaftar di `go.work`.

```
┌──────────────────────── Octopus Desktop (Wails) ────────────────────────┐
│  Frontend (webview: React + TypeScript)                                 │
│    ChatView · kartu visual (metrik/tabel/approval/deploy) · mic button  │
│                    │  Wails bindings + events                           │
│  Backend Go                                                             │
│    ┌─────────────┐ ┌──────────────┐ ┌─────────────┐ ┌───────────────┐   │
│    │ GatewayClient│ │  STT (port)  │ │  TTS (port) │ │ Settings/Auth │   │
│    │ SSE consumer │ │ whisper.cpp  │ │   Piper     │ │  keyring OS   │   │
│    └──────┬──────┘ └──────────────┘ └─────────────┘ └───────────────┘   │
└───────────┼──────────────────────────────────────────────────────────────┘
            │ HTTPS + Bearer token (sama seperti TUI)
            ▼
     Octopus Core (FastAPI) — TIDAK BERUBAH
     POST /chat/send → SSE: thinking, approval_required, action_result, …
```

Prinsip:

1. **Ports & adapters di Go** — `SpeechToText` dan `TextToSpeech` adalah interface; `WhisperAdapter` dan `PiperAdapter` implementasinya. Ganti engine = tulis adapter baru.
2. **Backend tidak berubah** — desktop hanya konsumen `POST /chat/send` (SSE) dan endpoint auth/approval yang ada. Perubahan opsional di masa depan: payload terstruktur (JSON) pada `ACTION_RESULT` untuk kartu lebih kaya; v1 jalan tanpa itu.
3. **Model tidak dibundel** — model Whisper & suara Piper diunduh saat first-run ke direktori data aplikasi (installer tetap ~15MB).
4. **Token di keyring OS** (Keychain / Credential Manager / libsecret), bukan file plaintext.

## Komponen

### Frontend (React + TypeScript)

- **ChatView** — daftar pesan; pesan asisten dirender live dari stream SSE. Area input **voice-first**: tombol mic besar (push-to-talk atau hotkey) sebagai interaksi utama, input teks tersedia sebagai alternatif di bawahnya.
- **Kartu visual** per tipe event/hasil:
  - `MetricCard` — gauge/angka CPU, memory, disk
  - `TableCard` — docker ps/images, git log/status sebagai tabel
  - `ApprovalCard` — rencana eksekusi + tombol Approve/Reject
  - `DeployCard` — stepper pull → build → up → health check, update live
  - `TextCard` — fallback markdown
- **VoiceBar** — indikator rekam, level meter mic, toggle mode Jarvis (default **aktif**: transkrip auto-send + jawaban dibacakan; dimatikan = teks masuk input box dulu untuk dikoreksi).
- **SettingsView** — URL gateway, login, pilihan model Whisper & suara Piper, on/off TTS.

### Backend Go (`octopus-desktop/internal/`)

| Package | Tanggung jawab |
|---|---|
| `gateway` | Klien HTTP + konsumen SSE ke Octopus Core; meneruskan event ke frontend via Wails events |
| `speech` | Interface `SpeechToText` + `WhisperAdapter` (whisper.cpp binding); rekam mic → teks |
| `voice` | Interface `TextToSpeech` + `PiperAdapter` (subprocess); teks → audio |
| `assets` | First-run downloader model (checksum + progress) |
| `settings` | Config + token di keyring OS |

## Alur Data

### Perintah suara

1. User tekan/tahan tombol mic (atau hotkey) → Go merekam audio mic.
2. Selesai bicara → `WhisperAdapter` transkrip lokal → **auto-send** (default, mode Jarvis). Jika mode Jarvis dimatikan, teks masuk input box dulu agar bisa dikoreksi.
3. `gateway` POST `/chat/send` → SSE mengalir: `thinking` → `intent_classified` → `action_started` → `action_result` → `final`.
4. Frontend memetakan tiap event ke kartu; `approval_required` memunculkan `ApprovalCard`.
5. Saat `final` tiba dan TTS aktif → `PiperAdapter` membacakan ringkasan jawaban (teks final, bukan isi tabel mentah).

### Approve

`ApprovalCard` → Approve → Go memanggil endpoint approval gateway (yang sama dengan perintah `/approve`) → event kelanjutan eksekusi masuk ke pesan yang sama.

## Error Handling

| Situasi | Perilaku |
|---|---|
| Gateway tidak terjangkau / token expired | Banner status koneksi; tombol reconnect; redirect ke login jika 401; pesan gagal bisa di-retry |
| SSE terputus di tengah stream | Pesan ditandai "terputus" + tombol retry — tidak ada silent hang |
| Mic tidak ada / izin ditolak | Tombol mic disabled + tooltip alasan; aplikasi otomatis jatuh ke mode teks (voice-first butuh mic, tapi tanpa mic chat tetap berfungsi penuh) |
| Download model gagal | Retry/resume; aplikasi tetap bisa teks-only sebelum model siap |
| Whisper/Piper crash | Error di-wrap per adapter; tampil sebagai toast; sesi chat tidak mati |

Prinsip: **voice dan visual adalah lapisan tambahan — kegagalannya tidak boleh mematikan chat teks dasar.**

## Testing

- **Go**: unit test per package — `gateway` dengan `httptest` (mock SSE, termasuk stream terputus); `speech`/`voice` lewat interface dengan fake adapter (tanpa binary nyata); `assets` dengan mock HTTP + checksum.
- **Frontend**: Vitest + React Testing Library — pemetaan tiap `ChatEventType` → komponen kartu yang benar; state `ApprovalCard`; reducer stream chat.
- **E2E smoke** (opsional, belakangan): Wails build + Playwright terhadap gateway lokal.
- **CI**: job GitHub Actions baru `octopus-desktop` (lint + test Go & frontend), terpisah dari pipeline Python.

## Di Luar Scope v1

- Perubahan backend (payload terstruktur `ACTION_RESULT`)
- Worker terbundel di aplikasi desktop
- TTS/STT cloud atau OS-native (cukup lewat adapter baru nanti)
- Dashboard mode (chat-first dulu)
- Auto-update aplikasi
