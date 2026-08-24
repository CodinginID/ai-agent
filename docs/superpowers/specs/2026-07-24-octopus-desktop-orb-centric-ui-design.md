# Octopus Desktop — Orb-Centric Dark UI

**Tanggal:** 2026-07-24
**Issue:** [#78](https://github.com/CodinginID/ai-agent/issues/78) (pivot Jarvis orb-centric)
**Milestone:** Shell + Design System (M2 dari pivot; voice UX sudah selesai di M1).
**Branch kerja:** `feat/octopus-desktop-app`

---

## 1. Tujuan

Ganti "cangkang" UI dari **chat-log-first (tema terang)** menjadi **orb-centric gelap futuristik**, tanpa membongkar mesinnya (reducer chat, rich cards, orb three.js, voice). Acuan visual: mockup pada komentar pivot #78.

Perubahan inti:
- Orb besar di tengah sebagai bintang utama (bukan chat-log). Orb bisa **diklik** untuk mulai mendengarkan / barge-in.
- Jawaban teks **ephemeral** (fade in/out) di bawah orb.
- Hasil kaya (metrik/tabel/aksi/approval/error) tampil di **satu panel accordion melayang** untuk giliran berjalan, bisa ditutup.
- Riwayat percakapan **tetap disimpan** dan dibuka lewat **History drawer** (bukan scrollback utama).
- Dock input bawah: teks + mic (fallback push-to-talk).
- Tema gelap: navy-hitam `#06090f`, aksen cyan `#38e1ff` + biru `#5b8cff`.

Non-goals: wake word "Hey Octopus" (Fase 2), avatar worker redesign, VAD (sudah ada di M1).

## 2. Prinsip

- **Pakai ulang mesin.** `reducer.ts`, semua `cards/*`, `orbState`/`AiOrb`, `voice/*`, `bindings.ts` dipertahankan apa adanya (kecuali penyesuaian warna orb & sedikit prop).
- **Token-driven theming.** Recolor lewat CSS custom properties di `:root`; kartu & kontrol yang sudah membaca token otomatis ikut gelap. Hindari rewrite 1660 baris CSS — ubah token + tambah section layout orb-centric.
- **Logika chat bersama.** Logika langganan event + submit + approve/reject + retry diekstrak ke hook `useChat` supaya dipakai layout baru (dan tetap teruji).

## 3. Arsitektur Komponen

```
App (chat screen, orb-centric)
├── OrbStage            orb besar (klik = listen/barge-in) + response ephemeral
│   ├── AiOrb           (reuse; warna dari state)
│   └── ResponseLayer   teks jawaban terakhir, fade in/out
├── DataPanel           panel accordion melayang (kartu giliran berjalan), tutup ✕
│   └── PartCard        (ekstrak dari ChatView.renderPart; reuse cards/*)
├── InputDock           input teks + VoiceBar (mic fallback)
├── HistoryDrawer       daftar giliran lampau (dari messages), toggle
└── SettingsModal       rail tab kiri: Umum / Suara / Provider AI / Tampilan
```

### 3.1 `chat/useChat.ts` (BARU — ekstraksi)

Hook yang memiliki `messages` + operasi, dipindah dari `ChatView`:

```ts
interface UseChat {
  messages: Message[];
  submit: (text: string) => void;
  decide: (msg: AssistantMessage, planId: string, d: "approved" | "rejected") => void;
  retryLast: () => void;
  pending: boolean;
  lastFinal: string; // teks final assistant terbaru (untuk ResponseLayer + TTS)
}
export function useChat(opts?: { onFinal?: (t: string) => void }): UseChat;
```

Isi = logika langganan `onChatEvent`/`applyEvent`, `submit` (kirim + optimistic user msg), `decide`, `retryLast`, deteksi `pending` & `lastFinal`. Teruji lewat test reducer yang sudah ada + test hook baru (opsional, ringan).

### 3.2 `chat/PartCard.tsx` (BARU — ekstraksi)

Pindahkan `renderPart` dari `ChatView` menjadi komponen `PartCard` yang me-render satu `Part` ke kartu yang sesuai (StatusLine/TextCard/MetricCard/TableCard/ActionCard/ApprovalCard/ErrorCard). Dipakai `DataPanel`.

### 3.3 `orb/OrbStage.tsx` (BARU)

- Render `AiOrb` besar di tengah + cincin HUD (CSS/SVG tipis berputar).
- `onActivate` (klik/Enter/Space pada orb) → callback ke App untuk mulai listening / barge-in.
- Berisi `ResponseLayer`.

### 3.4 `chat/ResponseLayer.tsx` (BARU)

- Menampilkan `lastFinal` (atau teks streaming berjalan) sebagai teks ephemeral di bawah orb, animasi fade. Kosong saat idle awal.

### 3.5 `chat/DataPanel.tsx` (BARU)

- Menerima `parts: Part[]` dari giliran assistant berjalan; render tiap non-text part sebagai baris **accordion** (judul ringkas + isi buka-tutup) memakai `PartCard`.
- Header dengan tombol tutup ✕. Sembunyi bila tidak ada part kaya.

### 3.6 `chat/InputDock.tsx` (BARU)

- Input teks (Enter untuk kirim) + slot `VoiceBar` (mic fallback push-to-talk sudah jadi toggle di M1) + indikator Jarvis.

### 3.7 `chat/HistoryDrawer.tsx` (BARU)

- Drawer geser dari samping berisi ringkasan tiap giliran (user text + cuplikan jawaban). Read-only. Toggle dari header.

### 3.8 Orb warna (DIUBAH)

`orb/orbState.ts` `COLORS` → palet gelap:
- idle `#38e1ff` (cyan tenang), listening `#3ddc97` (hijau), thinking `#ffb454` (amber), speaking `#ffb454` (amber, denyut amplitudo).
`orb/AiOrb.tsx` `CoreSphere` & pointLight membaca warna dari `ORB_COLORS[state]` (bukan hardcode). Uniform logic (breath/distortion) tidak berubah — test `orbState.test.ts` tetap hijau (tak menguji nilai warna).

### 3.9 Design system gelap (DIUBAH)

`style.css`:
- `:root` token → gelap: `--bg-primary:#06090f`, `--bg-secondary:#0c1119`, `--accent:#38e1ff`, `--accent-2:#5b8cff`, `--text-main:#e6f1ff`, `--text-muted:#7d8da5`, `--card-bg:rgba(18,26,40,.72)`, border cyan tipis, dsb.
- Tambah section "Orb-Centric Layout" untuk kelas baru (`.orb-app`, `.orb-stage`, `.orb-hud-ring`, `.response-layer`, `.data-panel`, `.data-accordion`, `.input-dock`, `.history-drawer`).
- Kelas layout lama (`.app-container`, `.chat-view`, `.chat-messages`) dibiarkan (tak dirender) untuk minimalkan risiko; token gelap otomatis mewarnai kartu.
- `reduce-motion` menonaktifkan rotasi cincin HUD & fade.

### 3.10 Settings tab rail (DIUBAH)

`setup/SettingsView.tsx`:
- Rail tab kiri: **Umum** (gateway, jarvis, tts, path model, unduh) / **Suara** (`vad_silence_ms` dipindah ke sini) / **Provider AI** (existing) / **Tampilan** (warna aksen orb `orb_accent`, toggle `reduce_motion`). Tab "Agents"/"Workers" existing tetap tersedia di bawah rail.
- Setting baru: `orb_accent` (string hex, default `#38e1ff`), `reduce_motion` (bool). Ditulis lewat `SaveSettings` generik + field di `settings.go`.

## 4. Alur

1. Idle: orb cyan berdenyut di tengah, ResponseLayer kosong, DataPanel & drawer tertutup.
2. Klik orb → (barge-in bila TTS jalan) mulai listening (orb hijau). VAD auto-stop (M1) → transkrip → auto-send (jarvis).
3. `thinking` (orb amber) → streaming teks muncul di ResponseLayer; kartu non-teks masuk DataPanel accordion.
4. `final` → ResponseLayer menampilkan jawaban; TTS jalan (orb denyut amber). Giliran tersimpan ke history.
5. Klik History → drawer daftar giliran lampau.

## 5. Aksesibilitas & Error

- Orb sebagai kontrol: `role="button"`, `tabIndex=0`, aktif via Enter/Space, `aria-label` sesuai state.
- `prefers-reduced-motion` + setting `reduce_motion` mematikan animasi cincin/fade.
- Error/stream_error tetap jadi ErrorCard di DataPanel dengan retry (reuse).
- Fokus keyboard: Cmd/Ctrl+K fokus input dock, Esc tutup drawer/settings.

## 6. Testing

- `orb/orbState.test.ts`: tetap hijau (tak diubah); tambah assert `ORB_COLORS.idle`/`listening`/`thinking`/`speaking` bernilai palet baru.
- `chat/useChat` (opsional): submit menambah user msg + memanggil sendChat; `final` mengeset `lastFinal` & pending=false. (Boleh diuji via reducer test existing bila hook tipis.)
- `chat/DataPanel` test: render accordion untuk parts action/metric/error; sembunyi bila hanya text.
- `chat/ResponseLayer` test: menampilkan teks terbaru; kosong saat tak ada.
- `setup/setup.test.tsx`: sesuaikan bila menguji label tab; tambah test tab "Suara" memuat kontrol jeda hening.
- `internal/settings/settings_test.go`: default `OrbAccent`/`ReduceMotion` + round-trip.
- Gate: `pnpm test` hijau, `tsc --noEmit` bersih, `go test ./...` hijau. Build produksi diverifikasi manual oleh user.

## 7. Berkas Terdampak (ringkas)

BARU: `chat/useChat.ts`, `chat/PartCard.tsx`, `chat/ResponseLayer.tsx`, `chat/DataPanel.tsx`, `chat/InputDock.tsx`, `chat/HistoryDrawer.tsx`, `orb/OrbStage.tsx` (+ test terkait).
DIUBAH: `App.tsx` (layout orb-centric), `orb/orbState.ts` (+test), `orb/AiOrb.tsx`, `style.css` (token gelap + layout), `setup/SettingsView.tsx`, `internal/settings/settings.go` (+test).
DIPERTAHANKAN utuh: `reducer.ts`, semua `cards/*`, `bindings.ts`, `voice/*`, `avatar/*`.

## 8. Risiko & Mitigasi

- **CSS 1660 baris.** Tidak di-rewrite; hanya token + section baru → risiko rendah, mudah di-review.
- **ChatView lama.** Logika diekstrak ke `useChat`/`PartCard`; `ChatView.tsx` bisa dipensiunkan (tidak dirender) tapi dibiarkan sampai review agar diff jelas. Test `ChatView.test.tsx` disesuaikan/dipertahankan bila masih relevan.
- **Ephemeral vs konteks.** History drawer menjaga akses riwayat (keputusan brainstorming), messages tetap array penuh.
