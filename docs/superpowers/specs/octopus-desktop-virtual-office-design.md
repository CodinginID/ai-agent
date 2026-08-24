# Octopus Desktop App — Virtual Office Design

**Date:** 2026-07-17
**Status:** Approved by user
**Scope:** Desktop app (Wails + React + Three.js) sebagai rich UI replacement dari Telegram bot

---

## 1. Context & Problem

Telegram bot adalah always-on interface untuk AI agent. User bisa remote-nyala dari mana saja, tapi Telegram terbatas:
- Tidak ada visual richness (hanya text/markdown)
- Tidak ada voice interaction native
- Tidak bisa menampilkan data terstruktur yang bagus (charts, tables, maps)
- Tidak ada "personality" — bot terasa dingin

Desktop app hadir untuk mengisi gap tersebut: ketika user berada di depan komputer, mereka dapat interaksi yang lebih kaya dengan "karakter" AI yang hidup.

## 2. Three-Interface Architecture

```
                    ┌──────────────┐
                    │   TELEGRAM   │
                    │    Bot       │
                    │  (always-on) │
                    └──────┬───────┘
                           │ gateway (sama)
                           │
                    ┌──────▼───────┐
                    │   GATEWAY    │
                    │    VPS       │
                    │  (AI engine) │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
    ┌─────────▼───┐ ┌──────▼─────┐ ┌───▼──────────┐
    │  DESKTOP    │ │   TUI CLI  │ │              │
    │  APP        │ │            │ │              │
    │ (rich GUI)  │ │ (power UI) │ │              │
    └─────────────┘ └────────────┘ └──────────────┘
```

**Ketiga interface berbagi backend yang sama** (Gateway VPS + AI engine). Yang berbeda hanya presentation layer:

| Interface | Kapan | Role | Style |
|-----------|-------|------|-------|
| Desktop App | User di depan komputer | Rich interaction, voice, avatar | Light, friendly, animated |
| TUI CLI | Admin/VPS context | Server management, fast ops | Dark terminal, keyboard-driven |
| Telegram Bot | User AFK / remote | Lightweight, always-on | Markdown, text-only |

## 3. Core Design: Virtual Office

### 3.1 Konsep

Desktop app adalah "virtual office" — sebuah workspace digital di mana AI worker hadir sebagai avatar yang hidup. Bukan sekadar chat bot, tapi sebuah tempat kerja dengan karakter.

### 3.2 Avatar System (Dynamic)

**Prinsip:** Avatar muncul hanya saat bertugas. Tidak ada avatar yang "selalu di layar" kecuali AI orchestrator (main orb).

```
Worker Lifecycle:
  IDLE           → (tidak ada avatar)
  AWAITING_TASK  → avatar fade-in (opacity 0 → 1, ~500ms)
  WORKING        → avatar aktif, animasi sesuai tugas
  COMPLETE       → avatar fade-out (opacity 1 → 0, ~500ms)
  ERROR          → avatar error state (shake/distorted), muncul lagi jika retry
```

**Avatar Properties (per worker):**
- **Shape** — berbeda per worker type:
  - Engineer: gear/cog yang berputar
  - Reviewer: magnifying glass yang pulse
  - Architect: blueprint/draft yang unfold
  - Server: server rack yang blink
  - Docker: container box yang stack
- **Color** — sesuai role (blue=engineer, green=reviewer, purple=architect, orange=server, cyan=docker)
- **Animation states:**
  - `idle`: gentle float/breathe
  - `working`: active animation (rotate, pulse, bounce)
  - `error`: shake/distort
- **Position:** bottom-center area, di atas chat area

### 3.3 Main Orb (AI Orchestrator)

Main orb adalah "face" dari AI — selalu ada, mewakili kesadaran utama.

**Current state:** Sudah ada di `src/orb/AiOrb.tsx` sebagai particle orbit system (dark cyber).
**Changes needed:**
- Ganti dark cyber theme → light/office theme (particle warna `#4a90d9` → `#5b9bd5`, background orbit transparan)
- Tambahkan expression states sesuai context:
  - `thinking`: orbit cepat + warm glow (`#f6ad55`)
  - `speaking`: pulse sesuai TTS amplitude
  - `idle`: gentle breathing (`#4a90d9`)
  - `listening`: (saat voice input aktif) — orbit melambat + warna `#6bc99a`
- Posisi: fixed di area header, tidak bergerak
- Warna orbit berubah dinamis sesuai state, bukan static

### 3.4 Chat View

Chat sebagai interface utama — semua interaksi melalui percakapan.

**Input methods:**
- Text input (existing)
- Voice input (existing, Whisper STT)
- Jarvis mode (auto-send + auto-TTS)

**Output rendering (rich inline cards):**

| Card Type | Data Source | Visual |
|-----------|-------------|--------|
| `TextCard` | AI text response | Clean text block |
| `ActionCard` | docker, git, custom actions | Status + result summary |
| `MetricCard` | server_status, disk, memory | Bar chart + values |
| `TableCard` | docker_ps, processes | Table layout |
| `ApprovalCard` | plan approvals | Buttons (approve/reject) |
| `ErrorCard` | errors | Red banner with retry |
| `StatusLine` | status events | Subtle status indicator |

**Data flow:**
```
User input → Gateway → AI response stream → Events (chat:event) → Reducer → Render cards
                                                        ↓
                                            Worker task events → Avatar system
```

## 4. Component Architecture

```
octopus-desktop/frontend/src/
├── app/
│   └── App.tsx                 # Root: screen routing (loading → login → chat)
├── orb/
│   ├── AiOrb.tsx              # Main AI orchestrator (particle orbit)
│   ├── orbState.ts            # State computation (idle/thinking/speaking)
│   └── orbMaterial.ts         # Three.js shader
├── chat/
│   ├── ChatView.tsx           # Main chat interface
│   ├── bindings.ts            # Go→TS bindings
│   ├── reducer.ts             # Event→message reducer
│   ├── types.ts               # Message/Part type definitions
│   └── cards/
│       ├── ActionCard.tsx
│       ├── ApprovalCard.tsx
│       ├── ErrorCard.tsx
│       ├── MetricCard.tsx
│       ├── StatusLine.tsx
│       ├── TableCard.tsx
│       └── TextCard.tsx
├── voice/
│   ├── VoiceBar.tsx           # Mic button + Jarvis toggle
│   ├── recorder.ts            # MediaRecorder + WAV encoder
│   └── tts.ts                 # TTS playback + amplitude analysis
├── setup/
│   ├── LoginView.tsx          # OAuth login flow
│   └── SettingsView.tsx       # System/Provider/Agent settings
├── hooks/
│   └── usePointerTilt.ts      # 3D tilt effect for cards
└── style.css                  # Light/office theme styles
```

## 5. Data Model

### Worker (per agent)

```typescript
interface Worker {
  id: string;
  name: string;
  type: 'engineer' | 'reviewer' | 'architect' | 'server' | 'docker' | 'git' | 'custom';
  color: string;              // hex color for avatar
  shape: AvatarShape;         // shape type
  state: 'idle' | 'working' | 'error';
  currentTask?: string;       // what it's doing
}
```

### Avatar Event (from backend)

```typescript
interface AvatarEvent {
  type: 'worker:started' | 'worker:progress' | 'worker:completed' | 'worker:error';
  workerId: string;
  workerName: string;
  workerType: string;
  taskId?: string;
  progress?: number;          // 0-1
  error?: string;
}
```

Backend perlu emit event `avatar:event` dengan payload di atas setiap kali worker state berubah.

## 6. Visual Theme: Light Office

**Palet warna:**
- Background: `#f8f9fa` (warm white)
- Surface: `#ffffff` (pure white cards)
- Primary: `#4a90d9` (soft blue)
- Secondary: `#6bc99a` (soft green)
- Text: `#2d3748` (dark gray, bukan pure black)
- Muted: `#718096` (medium gray)
- Accent warm: `#f6ad55` (soft orange)
- Error: `#fc8181` (soft red)

**Typography:**
- Headers: `'Inter'` atau `'SF Pro Display'` (clean, modern)
- Body: `'Inter'` atau `'system-ui'`
- Code/mono: `'JetBrains Mono'` (tetap untuk code blocks)

**Card design:**
- Border-radius: `12px` (lebi round, friendly)
- Shadow: `0 2px 8px rgba(0,0,0,0.06)` (soft, subtle)
- No corner brackets, no scanlines
- No glow effects (or very minimal)

## 7. Interaction Design

### Voice Input Flow

```
User tap mic → recording state → voice waveform → transcribe (Whisper)
                                              ↓
                                    Draft di text input (non-Jarvis)
                                    OR auto-send (Jarvis mode)
                                              ↓
                                    TTS reply → amplitude → orb animation
```

**Mic permission handling:**
- Jika `getUserMedia` reject → show gentle banner: "Mic tidak tersedia. Gunakan text input."
- Bukan error, hanya info
- Option: "Setujui mic di System Preferences" link

### Navigation

Tidak ada tab/panel switching. Semua navigasi melalui percakapan:
- "Liat status server" → MetricCard muncul di chat
- "Jalanin docker ps" → TableCard muncul di chat
- "Bantu code ini" → Worker avatar muncul, ActionCard muncul

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl+K` | Focus chat input |
| `Esc` | Close modal (settings) |
| `Space` | Toggle Jarvis mode (when focused on voice bar) |

## 8. Settings Tab: Worker/Avatar Config

New settings tab: **"Workers"**

```
Workers Tab:
┌─────────────────────────────────────┐
│ Worker: Engineer                    │
│ Status: ● Aktif                      │
│ Avatar: [gear icon] [color picker]  │
│ Voice: [male/female/none]           │
│ Auto-respond: [on/off]              │
└─────────────────────────────────────┘
```

Fitur:
- Toggle avatar visibility per worker
- Customize avatar color
- TTS voice selection per worker (optional)
- Auto-respond setting (apakah worker langsung jawab atau perlu approval)

## 9. Error Handling

| Error | User-visible | Action |
|-------|-------------|--------|
| Gateway unreachable | Red banner: "Gateway tidak terjangkau" | Retry button, show last cached state |
| AI model error | ErrorCard dengan retry button | Retry → kirim ulang ke AI |
| TTS failed | Silent fail (log only) | Tidak ganggu UX |
| STT failed | ErrorCard: "Gagal mendeteksi suara" | User bisa retry atau ketik manual |
| Mic permission denied | Banner: "Mic tidak tersedia" | Fallback ke text input |
| Asset download fail | Settings: show failed assets, retry button | Retry download |
| OAuth token expired | Redirect to login view | Auto-redirect |

## 10. Testing Strategy

| Test Type | What to test |
|-----------|-------------|
| Unit: Avatar state machine | Idle→Working→Complete flow |
| Unit: Chat reducer | Event→Message transformation |
| Unit: TTS amplitude | computeRmsAmplitude correctness |
| Integration: Voice end-to-end | Record → Transcribe → Send → Reply |
| Integration: Worker lifecycle | Start login → Send chat → Worker avatar → Complete |
| E2E: Full flow | Login → Chat → Voice → Settings → Avatar interaction |

## 11. Implementation Phases

**Phase 1: Theme Migration**
- Replace dark cyber theme → light office theme (CSS)
- Update fonts, colors, card designs
- Test all existing components render correctly in light theme

**Phase 2: Worker Avatar System**
- Define Worker interface & avatar event types
- Implement Avatar component (Three.js or SVG sprite)
- Wire backend events → avatar state changes
- Fade-in/fade-out animation system

**Phase 3: Avatar Customization**
- Settings tab for workers
- Color picker per worker
- Shape selection per worker type
- Persist settings to gateway

**Phase 4: Enhanced Voice Flow**
- Better mic permission handling (graceful fallback)
- Voice draft UX refinement
- TTS amplitude → avatar expression binding

**Phase 5: Polish**
- Keyboard shortcuts
- Smooth animations
- Accessibility (screen reader support)
- Performance optimization (avatar rendering)

---

## References

- Hexagonal Architecture: ports & adapters pattern (existing)
- Wails v2: Go backend + web frontend bridge
- Three.js: 3D rendering for orb and avatars
- React Three Fiber: declarative Three.js in React
- Whisper.cpp: local STT
- Piper TTS: local TTS
