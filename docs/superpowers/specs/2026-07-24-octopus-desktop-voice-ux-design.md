# Octopus Desktop — Voice UX (VAD Hands-Free + Barge-In)

**Tanggal:** 2026-07-24
**Issue:** [#78](https://github.com/CodinginID/ai-agent/issues/78) (pivot Jarvis orb-centric)
**Milestone:** Voice UX (M1 dari pivot) — didahulukan sebelum refactor layout orb-centric penuh.
**Branch kerja:** `feat/octopus-desktop-app`

---

## 1. Tujuan

Mengubah interaksi suara dari **push-to-talk (tahan tombol)** menjadi **hands-free ala Jarvis**:

- **Klik sekali** tombol mic → mulai mendengarkan; berhenti **otomatis** saat pengguna diam (VAD auto-stop).
- **Barge-in**: saat AI sedang bicara (TTS), memicu listen langsung **menghentikan TTS** dan mulai mendengarkan.
- Durasi hening (silence timeout) **dapat diatur** di Settings.

Non-goals milestone ini (ditunda ke milestone berikutnya):
- Layout orb-centric penuh (OrbStage/ResponseLayer/DataPanel/InputDock).
- Design system gelap + cleanup `style.css`.
- History drawer.
- "Klik orb" sebagai pemicu (pemicu tetap tombol mic VoiceBar untuk sekarang).
- Wake word "Hey Octopus" (Fase 2 terpisah, butuh engine on-device).
- Tuning warna orb per state (bagian design-system milestone).

## 2. Prinsip

- **Pakai ulang mesin, tambah perilaku.** Orb (`orbState.ts`), reducer chat, `Transcribe`/`Speak` bindings, dan `MicRecorder` dipertahankan; VAD & barge-in ditambahkan tanpa membongkar engine.
- **Logika inti murni & teruji.** Keputusan VAD dan perhitungan energi diisolasi jadi fungsi murni (tanpa Web Audio) supaya bisa di-unit-test tanpa mock audio.
- **Semua lokal.** Tidak ada dependensi baru ke cloud; VAD berbasis energi (RMS) di frontend, tanpa library eksternal berat.

## 3. Arsitektur

Tiga unit dengan tanggung jawab tunggal:

```
┌──────────────┐   rms per frame   ┌──────────────┐  "speech-end"  ┌──────────────┐
│  MicRecorder │ ────────────────► │  VadDetector │ ─────────────► │   VoiceBar   │
│ (Web Audio)  │                   │   (murni)    │                │  (UI/state)  │
└──────────────┘                   └──────────────┘                └──────┬───────┘
       ▲                                                                   │ transcript
       │ start(opts.onSpeechEnd)                                           ▼
       └───────────────────────────────────────────────────────  Transcribe → onTranscript
```

### 3.1 `voice/vad.ts` — VadDetector (BARU, murni)

Detektor aktivitas suara berbasis energi, **tanpa** dependensi Web Audio. Waktu di-inject sebagai argumen agar deterministik & teruji.

```ts
export interface VadParams {
  threshold: number;   // RMS di atas ini dianggap "ada suara" (default 0.02)
  silenceMs: number;   // lama hening yang mengakhiri ujaran (default 1200)
  minSpeechMs: number; // minimal durasi bicara sebelum silence bisa mengakhiri (default 300)
}

export const DEFAULT_VAD: VadParams;

export class VadDetector {
  constructor(params: VadParams);
  /** Umpankan energi RMS satu frame beserta timestamp (ms).
   *  Return true TEPAT SEKALI saat ujaran dianggap selesai. */
  feed(rms: number, nowMs: number): boolean;
  reset(): void;
}
```

Aturan:
- Sebelum ada frame di atas `threshold`, tidak pernah return `speech-end` (menunggu pengguna mulai bicara).
- Setelah terdeteksi bicara ≥ `minSpeechMs`, jika hening berlanjut ≥ `silenceMs`, `feed` return `true` sekali lalu detektor jadi "selesai" (feed berikutnya return `false` sampai `reset`).

### 3.2 `voice/recorder.ts` — MicRecorder (DIUBAH)

- Tambah helper murni `computeFrameRms(frame: Float32Array): number` (di-export, teruji).
- `start(opts?: { onSpeechEnd?: () => void; vad?: VadParams })`:
  - Jika `vad` diberikan, di dalam `onaudioprocess` hitung RMS frame, umpankan ke `VadDetector` dengan `performance.now()`, dan panggil `onSpeechEnd` saat detektor mengakhiri ujaran.
  - Pengumpulan chunk & `stop()`→WAV tetap seperti sekarang.
- Tanpa `opts`, perilaku lama tidak berubah (kompatibel mundur).

### 3.3 `voice/tts.ts` — speak (DIUBAH, interruptible)

- Simpan referensi playback aktif di level modul.
- Export `cancelSpeech(): void` yang menghentikan `Audio` + menutup `AudioContext` playback yang sedang jalan (idempotent, aman dipanggil saat tidak ada playback).
- `speak()` mendaftarkan playback saat mulai dan membersihkannya saat selesai/dibatalkan. Saat dibatalkan, promise `speak()` resolve normal (bukan reject) supaya barge-in tidak memunculkan error di chat.

### 3.4 `voice/VoiceBar.tsx` — hands-free + barge-in (DIUBAH)

- Tombol mic jadi **toggle klik**, bukan tahan (`onMouseDown/onMouseUp` → `onClick`):
  - Klik saat idle → `cancelSpeech()` (barge-in, aman jika tak ada TTS) lalu mulai `MicRecorder.start({ vad, onSpeechEnd: stop })`.
  - Klik saat merekam → stop manual (paksa berhenti) — fallback jika VAD tak memicu.
- VAD `onSpeechEnd` memanggil jalur `stop()` yang sama (transcribe → `onTranscript`).
- `silenceMs` dibaca dari settings (prop `vadSilenceMs`), sisanya pakai `DEFAULT_VAD`.
- State & label existing (`listening`/`recording`/`transcribing`) dipertahankan; hint diperbarui ("Klik untuk bicara" / "Mendengarkan… (otomatis berhenti saat diam)").

### 3.5 Settings (DIUBAH)

- `internal/settings/settings.go`: tambah `VadSilenceMs int` (`json:"vad_silence_ms"`), default `1200` di `defaults()`.
- `setup/SettingsView.tsx`: kontrol angka/slider "Jeda hening sebelum berhenti (ms)" (rentang 500–3000). Tersimpan lewat `SaveSettings` yang sudah generik.
- `App.tsx`: baca `vad_silence_ms` dari settings, teruskan ke `VoiceBar` sebagai `vadSilenceMs`.

## 4. Alur Data (jarvis mode)

1. Pengguna klik mic → (jika TTS jalan) `cancelSpeech()` → `MicRecorder.start({ vad, onSpeechEnd })`. Orb → `listening`.
2. Pengguna bicara; diam ~`silenceMs` → `VadDetector.feed` return true → `onSpeechEnd` → `MicRecorder.stop()` → WAV.
3. `Transcribe(wav)` → teks → `onTranscript` → (jarvis) auto-send ke chat. Orb → `thinking`.
4. Jawaban final → `speak()` (orb `speaking`, amplitudo → distorsi orb seperti sekarang).
5. Pengguna klik mic saat langkah 4 → barge-in: `cancelSpeech()` menghentikan langkah 4, kembali ke langkah 1.

Non-jarvis: langkah 3 mengarah ke `voice:draft` (tidak auto-send), seperti perilaku sekarang.

## 5. Penanganan Error

- Izin mikrofon ditolak / tak tersedia → pesan existing di VoiceBar (tidak berubah).
- VAD tak pernah memicu (pengguna diam total) → tombol tetap bisa diklik untuk stop manual. (Tidak menambah max-timeout di milestone ini; klik-stop sudah cukup.)
- TTS dibatalkan (barge-in) → `speak()` resolve normal, tak ada ErrorCard.
- Transkripsi kosong → langsung idle, tak ada pesan.

## 6. Testing

Semua kode baru wajib bertes (aturan proyek).

- `voice/vad.test.ts` (murni, tanpa mock audio):
  - Diam terus → tak pernah speech-end.
  - Bicara lalu diam ≥ silenceMs → speech-end tepat sekali.
  - Bicara < minSpeechMs lalu diam → belum speech-end (guard minSpeech).
  - Hening sebentar (< silenceMs) di tengah bicara → tidak memicu.
  - Setelah speech-end, `feed` berikutnya false sampai `reset()`.
- `voice/recorder.test.ts`: `computeFrameRms` untuk frame senyap ≈ 0, frame keras > threshold.
- `voice/tts.test.ts`: `cancelSpeech()` idempotent saat tak ada playback; `computeRmsAmplitude` existing tetap hijau.
- `voice/VoiceBar` (test existing di setup/ChatView jika ada): toggle klik memulai & menghentikan; barge-in memanggil `cancelSpeech`.
- `internal/settings/settings_test.go`: default `VadSilenceMs == 1200`; round-trip Save/Load mempertahankan nilai.

Gate sebelum selesai: `go test ./...` (octopus-desktop) hijau, `pnpm test` (frontend) hijau, typecheck bersih, build Wails sukses.

## 7. Berkas Terdampak

| Berkas | Perubahan |
|---|---|
| `frontend/src/voice/vad.ts` | BARU — VadDetector + DEFAULT_VAD |
| `frontend/src/voice/vad.test.ts` | BARU — unit test VAD |
| `frontend/src/voice/recorder.ts` | `computeFrameRms` + opsi VAD di `start()` |
| `frontend/src/voice/recorder.test.ts` | test `computeFrameRms` |
| `frontend/src/voice/tts.ts` | `cancelSpeech()` + playback interruptible |
| `frontend/src/voice/tts.test.ts` | test `cancelSpeech` idempotent |
| `frontend/src/voice/VoiceBar.tsx` | toggle klik, VAD, barge-in, prop `vadSilenceMs` |
| `frontend/src/App.tsx` | teruskan `vad_silence_ms` ke VoiceBar |
| `frontend/src/setup/SettingsView.tsx` | kontrol jeda hening |
| `internal/settings/settings.go` | field `VadSilenceMs` default 1200 |
| `internal/settings/settings_test.go` | test default + round-trip |

## 8. Risiko & Mitigasi

- **ScriptProcessorNode deprecated.** Sudah dipakai di recorder existing; tetap dipakai untuk konsistensi. Migrasi ke AudioWorklet di luar scope.
- **Threshold RMS statis** bisa terlalu sensitif di lingkungan berisik. Milestone ini pakai default tetap + silence configurable; sensitivitas adaptif ditunda (YAGNI) sampai ada bukti perlu.
- **Perubahan signature `MicRecorder.start`** opsional/ backward-compatible sehingga pemanggil lain tak rusak.
