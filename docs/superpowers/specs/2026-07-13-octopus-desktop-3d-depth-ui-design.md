# Octopus Desktop — 3D Orb & Depth UI Design

**Date:** 2026-07-13
**Status:** Approved
**Scope:** `octopus-desktop/frontend`

## Problem

The current UI (`App.css`, `style.css`) uses a flat cyberpunk theme — glow, blur,
gradients — but has no sense of depth or motion. Cards, buttons, and modals sit on
one visual plane; the only "lift" effect is a 1px `translateY` on button press. The
app feels rigid ("kaku"). There is no real 3D element anywhere.

## Goals

1. Add a real 3D centerpiece (an "AI orb") that visually represents app state
   (idle / thinking / speaking), reacting to actual TTS audio amplitude — not a
   canned animation.
2. Give every major surface (chat bubbles, answer cards, buttons, modals) a sense
   of depth via pointer-driven tilt and layered elevation shadows.
3. Keep the addition scoped to the frontend only — no backend/Go changes beyond
   what's needed to support real playback-end signaling in `voice/tts.ts`.

## Non-goals

- No full-screen WebGL background/visualizer (rejected in favor of a header orb —
  less distracting from chat content).
- No redesign of the color palette, typography, or card content layout.
- No accessibility work bundled into this change (tracked separately — see prior
  code review notes on VoiceBar/icon-only buttons).

## Design

### 1. AI Orb (`frontend/src/orb/`)

- `AiOrb.tsx` — a small (`64–80px`) `@react-three/fiber` `<Canvas>` containing one
  sphere mesh with a custom shader material (fresnel rim glow + noise-based surface
  distortion). Colors interpolate along the existing accent gradient
  (`#3b82f6` → `#10b981`), shifting toward `--warning` (`#f59e0b`) in the `thinking`
  state.
- Accepts `state: "idle" | "thinking" | "speaking"` and `amplitude: number` (0–1,
  only meaningful in `speaking` state) as props. Purely presentational — no
  app-level state or Wails bindings inside this component.
- Animation behavior:
  - `idle`: slow constant rotation + subtle sinusoidal "breathing" scale.
  - `thinking`: faster rotation, higher noise-distortion amplitude, color shifts
    toward amber.
  - `speaking`: surface pulse driven directly by the `amplitude` prop (updated via
    `requestAnimationFrame`, not React state, to avoid re-render churn).
- Dependencies added to `frontend/package.json`: `three`, `@react-three/fiber`,
  `@react-three/drei`.

### 2. Audio-reactive speaking state (`frontend/src/voice/tts.ts`)

Current `speak()`:
```ts
export async function speak(text: string): Promise<void> {
  const b64 = await window.go.main.App.Speak(text);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = new Audio(url);
  await audio.play().finally(() => URL.revokeObjectURL(url));
}
```
`audio.play()` resolves when playback **starts**, not ends, so the URL is revoked
almost immediately and callers have no way to know when speech actually finishes.

New signature:
```ts
export async function speak(
  text: string,
  onAmplitude?: (level: number) => void,
): Promise<void>
```
- Resolves on the audio element's `ended` event (so "speaking" state lasts as long
  as audio actually plays).
- If `onAmplitude` is provided, wires up an `AudioContext` + `AnalyserNode` +
  `MediaElementAudioSourceNode` on the same audio element, sampling RMS amplitude
  once per animation frame until playback ends, then tears down the audio graph
  (disconnect nodes, close the `AudioContext`).
- Object URL revocation moves to the `ended`/`finally` path so it still runs
  exactly once per call.

### 3. Header layout (`App.tsx` / `style.css`)

`.app-header` changes from a 2-item `justify-content: space-between` flex row to a
3-column grid (`title | orb | settings-button`), so the orb sits horizontally
centered regardless of title/button width. Title font-size reduced slightly to
balance the new centerpiece.

### 4. State wiring (`App.tsx`, `chat/ChatView.tsx`)

- `ChatView` gains an optional prop `onPendingChange?: (pending: boolean) => void`:
  - called with `true` synchronously inside `submit()`.
  - called with `false` in the existing "last message done" `useEffect` (the same
    one that already fires `onFinal`).
- `App.tsx` derives `aiState`:
  - `speaking` while a `speak()` call is in flight (tracked via local state set
    before/after the call).
  - else `thinking` while `pending` is true.
  - else `idle`.
- `amplitude` state in `App.tsx` updated via the `onAmplitude` callback passed to
  `speak()`, passed through to `<AiOrb>`.

### 5. Depth/tilt CSS system (`frontend/src/hooks/usePointerTilt.ts`, `style.css`)

- New hook `usePointerTilt<T extends HTMLElement>()`: returns a ref; attaches
  `pointermove`/`pointerleave` listeners that set `--tilt-x`/`--tilt-y` CSS custom
  properties on the element (clamped to a small max angle, e.g. ±6deg). No React
  state — writes directly to `style.setProperty` to avoid re-render cost on every
  mouse move.
- New utility class `.tilt-surface` in `style.css`:
  ```css
  .tilt-surface {
    transform: perspective(600px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg));
    transition: transform 0.15s ease-out;
  }
  ```
- Applied (hook attached + class added) to: `.futuristic-card` (all AI answer
  cards), `.msg-user` chat bubbles, buttons (`chat-input button`,
  `approval-buttons button`, `.cyber-btn`), and modal panels (`.login-view`,
  `.settings-view`).
- New elevation token scale (4 levels, color-tinted box-shadows) replacing the
  single flat `box-shadow` currently on `.futuristic-card`; hover raises one
  elevation level.
- Background grid (`body::before`) gets a subtle parallax: translate by a few px
  based on pointer position relative to viewport center, applied via the same
  `usePointerTilt`-style approach but reading translate instead of rotate (small
  dedicated inline listener in `App.tsx`, since it's a single global background
  element, not a reusable component).

## Testing

- `AiOrb`: smoke-render test only (mock/stub WebGL context as needed for jsdom;
  assert it mounts and unmounts without throwing). No visual/pixel assertions —
  consistent with this project's existing test style (behavior/logic, not
  rendering pixels).
- `usePointerTilt`: unit test dispatching simulated `pointermove`/`pointerleave`
  events on a test element, asserting the CSS custom properties update and reset.
- `voice/tts.ts`: extend existing test coverage to assert `speak()` resolves on
  `ended` (not on `play()`), and that `onAmplitude` is invoked when provided.
- No new Go-side tests required (no backend changes).

## Files touched/added

**Added:**
- `frontend/src/orb/AiOrb.tsx`
- `frontend/src/orb/orbMaterial.ts`
- `frontend/src/hooks/usePointerTilt.ts`
- `frontend/src/hooks/usePointerTilt.test.ts`
- `frontend/src/orb/AiOrb.test.tsx`

**Modified:**
- `frontend/package.json` (add three/r3f/drei)
- `frontend/src/App.tsx` (header layout, aiState wiring, background parallax)
- `frontend/src/chat/ChatView.tsx` (`onPendingChange` prop)
- `frontend/src/voice/tts.ts` (amplitude callback, resolve on `ended`)
- `frontend/src/style.css` (elevation tokens, `.tilt-surface`, header grid layout)

**Added (tests):**
- `frontend/src/voice/tts.test.ts` (no existing test file for `tts.ts` today)
