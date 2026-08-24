# Octopus Desktop 3D Orb & Depth UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Octopus Desktop's frontend a real 3D centerpiece (a state-reactive AI orb) and a pointer-driven depth/tilt system across chat bubbles, answer cards, buttons, and modals, replacing the current flat cyberpunk look.

**Architecture:** A `@react-three/fiber` canvas (`AiOrb`) renders a single shader-driven sphere whose animation parameters come from a pure, unit-tested function (`orbState.ts`) driven by an `aiState` (`idle`/`thinking`/`speaking`) computed in `App.tsx`. Separately, a reusable `usePointerTilt` hook + `Tilt` wrapper component add perspective-tilt and layered elevation shadows to existing card/modal/bubble surfaces via a shared `.tilt-surface` CSS utility class — no visual redesign, additive depth only.

**Tech Stack:** React 19, TypeScript (strict), Vite, vitest + @testing-library/react (jsdom), `three`, `@react-three/fiber`, `@react-three/drei`.

## Global Constraints

- TypeScript strict mode is on (`tsconfig.json`) — `npm run build` (`tsc && vite build`) must pass with zero errors after every task.
- Tests run via `npm test` (`vitest run`), jsdom environment, globals enabled (`vitest.config.ts`).
- Follow existing test conventions: `describe`/`it` blocks with Indonesian description strings (see `reducer.test.ts`, `recorder.test.ts`, `setup.test.tsx`).
- Commit messages follow this repo's established convention: `type(scope): description`, lowercase, no trailing period, scope `desktop` (see `git log` — e.g. `feat(desktop): tingkatkan tampilan ui dengan tema futuristik cyberpunk`).
- No Go/backend changes in this plan — frontend-only (`octopus-desktop/frontend`).
- Spec: `docs/superpowers/specs/2026-07-13-octopus-desktop-3d-depth-ui-design.md`.

---

### Task 1: Orb state logic + 3D dependencies

**Files:**
- Create: `octopus-desktop/frontend/src/orb/orbState.ts`
- Test: `octopus-desktop/frontend/src/orb/orbState.test.ts`
- Modify: `octopus-desktop/frontend/package.json` (via `npm install`)

**Interfaces:**
- Produces: `export type OrbState = "idle" | "thinking" | "speaking"`, `export interface OrbUniformParams { rotationSpeed: number; breathScale: number; distortion: number; colorMix: number }`, `export function computeOrbUniforms(state: OrbState, amplitude: number, elapsedSeconds: number): OrbUniformParams`, `export function deriveAiState(pending: boolean, speaking: boolean): OrbState`. These are consumed by Task 6 (`AiOrb.tsx`) and Task 8 (`App.tsx`).

- [ ] **Step 1: Install 3D dependencies**

Run: `cd octopus-desktop/frontend && npm install three @react-three/fiber @react-three/drei`
Expected: `three`, `@react-three/fiber`, `@react-three/drei` added under `"dependencies"` in `package.json`, no `ERESOLVE` errors.

- [ ] **Step 2: Write the failing test**

Create `octopus-desktop/frontend/src/orb/orbState.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { computeOrbUniforms, deriveAiState } from "./orbState";

describe("computeOrbUniforms", () => {
  it("idle: breathing berosilasi, distortion tetap kecil", () => {
    const u0 = computeOrbUniforms("idle", 0, 0);
    expect(u0.breathScale).toBeCloseTo(0, 5);
    expect(u0.distortion).toBeCloseTo(0.08, 5);
    expect(u0.colorMix).toBe(0);

    const uQuarter = computeOrbUniforms("idle", 0, Math.PI / 2 / 1.2);
    expect(uQuarter.breathScale).toBeCloseTo(0.04, 5);
  });

  it("thinking: distortion tinggi dan colorMix penuh ke amber", () => {
    const u = computeOrbUniforms("thinking", 0, 5);
    expect(u.distortion).toBeCloseTo(0.35, 5);
    expect(u.colorMix).toBe(1);
    expect(u.breathScale).toBe(0);
  });

  it("speaking: distortion mengikuti amplitude, di-clamp ke [0,1]", () => {
    expect(computeOrbUniforms("speaking", 0, 1).distortion).toBe(0);
    expect(computeOrbUniforms("speaking", 0.5, 1).distortion).toBeCloseTo(0.3, 5);
    expect(computeOrbUniforms("speaking", 5, 1).distortion).toBeCloseTo(0.6, 5);
    expect(computeOrbUniforms("speaking", -5, 1).distortion).toBe(0);
  });
});

describe("deriveAiState", () => {
  it("speaking menang atas pending", () => {
    expect(deriveAiState(true, true)).toBe("speaking");
  });
  it("pending tanpa speaking -> thinking", () => {
    expect(deriveAiState(true, false)).toBe("thinking");
  });
  it("tidak pending & tidak speaking -> idle", () => {
    expect(deriveAiState(false, false)).toBe("idle");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd octopus-desktop/frontend && npx vitest run src/orb/orbState.test.ts`
Expected: FAIL with "Cannot find module './orbState'" (file doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `octopus-desktop/frontend/src/orb/orbState.ts`:

```ts
export type OrbState = "idle" | "thinking" | "speaking";

export interface OrbUniformParams {
  rotationSpeed: number;
  breathScale: number;
  distortion: number;
  colorMix: number;
}

const BASE: Record<OrbState, { rotationSpeed: number; distortion: number; colorMix: number }> = {
  idle: { rotationSpeed: 0.15, distortion: 0.08, colorMix: 0 },
  thinking: { rotationSpeed: 0.6, distortion: 0.35, colorMix: 1 },
  speaking: { rotationSpeed: 0.3, distortion: 0, colorMix: 0.15 },
};

export function computeOrbUniforms(
  state: OrbState,
  amplitude: number,
  elapsedSeconds: number,
): OrbUniformParams {
  const base = BASE[state];
  const breathScale = state === "idle" ? 0.04 * Math.sin(elapsedSeconds * 1.2) : 0;
  const distortion = state === "speaking" ? Math.min(1, Math.max(0, amplitude)) * 0.6 : base.distortion;
  return {
    rotationSpeed: base.rotationSpeed,
    breathScale,
    distortion,
    colorMix: base.colorMix,
  };
}

export function deriveAiState(pending: boolean, speaking: boolean): OrbState {
  if (speaking) return "speaking";
  if (pending) return "thinking";
  return "idle";
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd octopus-desktop/frontend && npx vitest run src/orb/orbState.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
cd octopus-desktop/frontend && git add package.json package-lock.json src/orb/orbState.ts src/orb/orbState.test.ts
git commit -m "feat(desktop): tambah logic state orb ai dan dependency three.js"
```

---

### Task 2: `usePointerTilt` hook

**Files:**
- Create: `octopus-desktop/frontend/src/hooks/usePointerTilt.ts`
- Test: `octopus-desktop/frontend/src/hooks/usePointerTilt.test.tsx`

**Interfaces:**
- Produces: `export function usePointerTilt<T extends HTMLElement>(): RefObject<T | null>` — attaches the returned ref to any element to make it tilt on pointer movement via `--tilt-x`/`--tilt-y` CSS custom properties. Consumed by Task 3 (`Tilt.tsx`), Task 4 (`UserBubble.tsx`, `LoginView.tsx`, `SettingsView.tsx`), Task 5 (`ChatView.tsx` send button).

- [ ] **Step 1: Write the failing test**

Create `octopus-desktop/frontend/src/hooks/usePointerTilt.test.tsx`:

```tsx
import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePointerTilt } from "./usePointerTilt";

function TestBox() {
  const ref = usePointerTilt<HTMLDivElement>();
  return <div ref={ref} data-testid="box" />;
}

describe("usePointerTilt", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mengatur --tilt-x/--tilt-y berdasarkan posisi pointer, reset saat pointer keluar", () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      right: 100,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => {},
    } as DOMRect);

    const { getByTestId } = render(<TestBox />);
    const box = getByTestId("box");

    fireEvent.pointerMove(box, { clientX: 100, clientY: 0 });
    expect(box.style.getPropertyValue("--tilt-y")).toBe("6.00deg");
    expect(box.style.getPropertyValue("--tilt-x")).toBe("6.00deg");

    fireEvent.pointerLeave(box);
    expect(box.style.getPropertyValue("--tilt-x")).toBe("0deg");
    expect(box.style.getPropertyValue("--tilt-y")).toBe("0deg");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd octopus-desktop/frontend && npx vitest run src/hooks/usePointerTilt.test.tsx`
Expected: FAIL with "Cannot find module './usePointerTilt'".

- [ ] **Step 3: Write the implementation**

Create `octopus-desktop/frontend/src/hooks/usePointerTilt.ts`:

```ts
import { useEffect, useRef } from "react";

const MAX_TILT_DEG = 6;

export function usePointerTilt<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const handleMove = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width;
      const py = (e.clientY - rect.top) / rect.height;
      const tiltY = (px - 0.5) * 2 * MAX_TILT_DEG;
      const tiltX = (0.5 - py) * 2 * MAX_TILT_DEG;
      el.style.setProperty("--tilt-x", `${tiltX.toFixed(2)}deg`);
      el.style.setProperty("--tilt-y", `${tiltY.toFixed(2)}deg`);
    };

    const handleLeave = () => {
      el.style.setProperty("--tilt-x", "0deg");
      el.style.setProperty("--tilt-y", "0deg");
    };

    el.addEventListener("pointermove", handleMove);
    el.addEventListener("pointerleave", handleLeave);
    return () => {
      el.removeEventListener("pointermove", handleMove);
      el.removeEventListener("pointerleave", handleLeave);
    };
  }, []);

  return ref;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd octopus-desktop/frontend && npx vitest run src/hooks/usePointerTilt.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
cd octopus-desktop/frontend && git add src/hooks/usePointerTilt.ts src/hooks/usePointerTilt.test.tsx
git commit -m "feat(desktop): tambah hook usePointerTilt untuk efek depth"
```

---

### Task 3: `Tilt` wrapper component

**Files:**
- Create: `octopus-desktop/frontend/src/components/Tilt.tsx`
- Test: `octopus-desktop/frontend/src/components/Tilt.test.tsx`

**Interfaces:**
- Consumes: `usePointerTilt` from Task 2 (`../hooks/usePointerTilt`).
- Produces: `export function Tilt({ className, children }: { className: string; children: ReactNode }): JSX.Element` — a `<div>` wrapper with `tilt-surface` + the given `className`, ref-driven tilt attached. Consumed by Task 4 (all 6 card components).

- [ ] **Step 1: Write the failing test**

Create `octopus-desktop/frontend/src/components/Tilt.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Tilt } from "./Tilt";

describe("Tilt", () => {
  it("merender children dengan class tilt-surface + class tambahan", () => {
    render(
      <Tilt className="card card-metric">
        <span>isi</span>
      </Tilt>,
    );
    const el = screen.getByText("isi").parentElement;
    expect(el?.className).toBe("tilt-surface card card-metric");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd octopus-desktop/frontend && npx vitest run src/components/Tilt.test.tsx`
Expected: FAIL with "Cannot find module './Tilt'".

- [ ] **Step 3: Write the implementation**

Create `octopus-desktop/frontend/src/components/Tilt.tsx`:

```tsx
import type { ReactNode } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";

export function Tilt({ className, children }: { className: string; children: ReactNode }) {
  const ref = usePointerTilt<HTMLDivElement>();
  return (
    <div ref={ref} className={`tilt-surface ${className}`}>
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd octopus-desktop/frontend && npx vitest run src/components/Tilt.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
cd octopus-desktop/frontend && git add src/components/Tilt.tsx src/components/Tilt.test.tsx
git commit -m "feat(desktop): tambah komponen Tilt wrapper untuk card"
```

---

### Task 4: Apply depth/tilt across cards + modals, add elevation CSS

**Files:**
- Create: `octopus-desktop/frontend/src/chat/UserBubble.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/ActionCard.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/ApprovalCard.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/ErrorCard.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/MetricCard.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/TableCard.tsx`
- Modify: `octopus-desktop/frontend/src/chat/cards/TextCard.tsx`
- Modify: `octopus-desktop/frontend/src/setup/LoginView.tsx`
- Modify: `octopus-desktop/frontend/src/setup/SettingsView.tsx`
- Modify: `octopus-desktop/frontend/src/style.css`

**Interfaces:**
- Consumes: `Tilt` from Task 3 (`../../components/Tilt`), `usePointerTilt` from Task 2 (`../hooks/usePointerTilt`).
- Produces: `export function UserBubble({ text }: { text: string }): JSX.Element`, consumed by Task 5 (`ChatView.tsx`).
- Note: `.card` currently has almost no visual chrome (`padding: 1.15rem` only — see `style.css:271-273`) while `.futuristic-card` already has the full glass-panel treatment. This task merges them onto one shared rule so answer cards actually look like elevated panels (this is why the UI reads as "flat" today, not just a missing-3D problem) — matches spec's "General Cards" polish under the "Semua permukaan utama" scope the user chose.

- [ ] **Step 1: Add elevation tokens to `:root` in `style.css`**

In `octopus-desktop/frontend/src/style.css`, find:

```css
:root {
    --bg-primary: #080c14;
    --bg-secondary: #0f172a;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.5);
    --accent-hover: #2563eb;
    --text-main: #f1f5f9;
    --text-muted: #64748b;
    --card-bg: rgba(13, 20, 35, 0.65);
    --border-color: rgba(59, 130, 246, 0.2);
    --danger: #ef4444;
    --danger-hover: #dc2626;
    --warning: #f59e0b;
    --success: #10b981;
}
```

Replace with:

```css
:root {
    --bg-primary: #080c14;
    --bg-secondary: #0f172a;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.5);
    --accent-hover: #2563eb;
    --text-main: #f1f5f9;
    --text-muted: #64748b;
    --card-bg: rgba(13, 20, 35, 0.65);
    --border-color: rgba(59, 130, 246, 0.2);
    --danger: #ef4444;
    --danger-hover: #dc2626;
    --warning: #f59e0b;
    --success: #10b981;
    --elevation-1: 0 2px 8px rgba(0, 0, 0, 0.25);
    --elevation-2: 0 8px 24px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(59, 130, 246, 0.08);
    --elevation-3: 0 16px 40px rgba(0, 0, 0, 0.45), 0 0 24px rgba(59, 130, 246, 0.12);
}
```

- [ ] **Step 2: Add the `.tilt-surface` utility class**

In `octopus-desktop/frontend/src/style.css`, find:

```css
::-webkit-scrollbar-thumb:hover {
    background: rgba(59, 130, 246, 0.6);
}

/* App Container Layout */
```

Replace with:

```css
::-webkit-scrollbar-thumb:hover {
    background: rgba(59, 130, 246, 0.6);
}

/* Depth / Tilt System */
.tilt-surface {
    transform: perspective(600px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg));
    transition: transform 0.15s ease-out;
}

/* App Container Layout */
```

- [ ] **Step 3: Merge `.card` chrome into `.futuristic-card` with elevation levels**

In `octopus-desktop/frontend/src/style.css`, find:

```css
/* Cyberpunk / Futuristic Card Design */
.futuristic-card {
    position: relative;
    background-color: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    backdrop-filter: blur(12px) saturate(180%);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.futuristic-card:hover {
    border-color: rgba(59, 130, 246, 0.4);
    box-shadow: 0 8px 32px 0 rgba(59, 130, 246, 0.1);
}
```

Replace with:

```css
/* Cyberpunk / Futuristic Card Design */
.futuristic-card,
.card {
    position: relative;
    background-color: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    box-shadow: var(--elevation-2);
    backdrop-filter: blur(12px) saturate(180%);
    transition: box-shadow 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s ease;
}

.futuristic-card:hover,
.card:hover {
    border-color: rgba(59, 130, 246, 0.4);
    box-shadow: var(--elevation-3);
}
```

- [ ] **Step 4: Remove the now-redundant flat `.card` rule**

In `octopus-desktop/frontend/src/style.css`, find:

```css
/* General Cards */
.card {
    padding: 1.15rem;
}
```

Replace with:

```css
/* General Cards */
.card {
    padding: 1.15rem;
    box-shadow: var(--elevation-1);
}
```

(This intentionally overrides the shared `--elevation-2` down to `--elevation-1` for plain non-hovered cards since `.card` rules declared later in the file win by cascade order — keeps small answer cards visually lighter than the modal panels, hover still raises to `--elevation-3` via the shared rule above.)

- [ ] **Step 5: Extract `UserBubble` component**

Create `octopus-desktop/frontend/src/chat/UserBubble.tsx`:

```tsx
import { usePointerTilt } from "../hooks/usePointerTilt";

export function UserBubble({ text }: { text: string }) {
  const ref = usePointerTilt<HTMLDivElement>();
  return (
    <div ref={ref} className="msg-user tilt-surface">
      {text}
    </div>
  );
}
```

- [ ] **Step 6: Wrap the 6 card components with `Tilt`**

Modify `octopus-desktop/frontend/src/chat/cards/ActionCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

export function ActionCard({ action, running, output }: { action: string; running: boolean; output: string }) {
  return (
    <Tilt className="card card-action">
      <div className="card-title">
        {action} {running && <span className="spinner">⏳</span>}
      </div>
      {output && <pre className="card-pre">{output}</pre>}
    </Tilt>
  );
}
```

Modify `octopus-desktop/frontend/src/chat/cards/ApprovalCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

export function ApprovalCard({
  planId,
  summary,
  decided,
  onApprove,
  onReject,
}: {
  planId: string;
  summary: string;
  decided: "" | "approved" | "rejected";
  onApprove: (planId: string) => void;
  onReject: (planId: string) => void;
}) {
  const disabled = decided !== "";
  return (
    <Tilt className="card card-approval">
      <div className="card-title">Butuh persetujuan</div>
      <pre className="approval-summary">{summary}</pre>
      <div className="approval-buttons">
        <button disabled={disabled} onClick={() => onApprove(planId)}>
          Approve
        </button>
        <button disabled={disabled} className="danger" onClick={() => onReject(planId)}>
          Reject
        </button>
      </div>
      {decided !== "" && <div className="approval-decided">{decided}</div>}
    </Tilt>
  );
}
```

Modify `octopus-desktop/frontend/src/chat/cards/ErrorCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

export function ErrorCard({ message, retryable, onRetry }: { message: string; retryable: boolean; onRetry?: () => void }) {
  return (
    <Tilt className="card card-error">
      <span>{message}</span>
      {retryable && onRetry && <button onClick={onRetry}>Coba lagi</button>}
    </Tilt>
  );
}
```

Modify `octopus-desktop/frontend/src/chat/cards/MetricCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

const PCT_RE = /([A-Za-z /]+)?:?\s*(\d+(?:\.\d+)?)\s*%/g;

export function MetricCard({ action, output }: { action: string; output: string }) {
  const metrics = [...output.matchAll(PCT_RE)].map((m) => ({
    label: (m[1] ?? action).trim(),
    value: parseFloat(m[2]),
  }));
  if (metrics.length === 0) {
    return <pre className="card card-pre">{output}</pre>;
  }
  return (
    <Tilt className="card card-metric">
      <div className="card-title">{action}</div>
      {metrics.map((m, i) => (
        <div key={i} className="metric-row">
          <span className="metric-label">{m.label}</span>
          <div className="metric-bar">
            <div
              className={`metric-fill ${m.value > 85 ? "danger" : m.value > 65 ? "warn" : ""}`}
              style={{ width: `${Math.min(m.value, 100)}%` }}
            />
          </div>
          <span className="metric-value">{m.value}%</span>
        </div>
      ))}
      <details>
        <summary>output mentah</summary>
        <pre>{output}</pre>
      </details>
    </Tilt>
  );
}
```

Modify `octopus-desktop/frontend/src/chat/cards/TableCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

export interface ParsedTable {
  header: string[];
  rows: string[][];
}

export function parseColumns(output: string): ParsedTable | null {
  const lines = output.split("\n").filter((l) => l.trim() !== "");
  if (lines.length < 2) return null;
  const header = lines[0].trim().split(/\s{2,}/);
  if (header.length < 2) return null;
  const rows = lines.slice(1).map((l) => l.trim().split(/\s{2,}/));
  return { header, rows };
}

export function TableCard({ action, output }: { action: string; output: string }) {
  const table = parseColumns(output);
  if (!table) return <pre className="card card-pre">{output}</pre>;
  return (
    <Tilt className="card card-table">
      <div className="card-title">{action}</div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {table.header.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tilt>
  );
}
```

Modify `octopus-desktop/frontend/src/chat/cards/TextCard.tsx` — replace entire file:

```tsx
import { Tilt } from "../../components/Tilt";

export function TextCard({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <Tilt className="card card-text">
      <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>
      {streaming && <span className="cursor">▌</span>}
    </Tilt>
  );
}
```

(Fallback `<pre className="card card-pre">` branches in `MetricCard`/`TableCard` are left un-tilted intentionally — they're a degenerate parse-failure path, not the primary card UI.)

- [ ] **Step 7: Add tilt ref to `LoginView` and `SettingsView` root panels**

In `octopus-desktop/frontend/src/setup/LoginView.tsx`, find:

```tsx
import { useEffect, useRef, useState } from "react";
```

Replace with:

```tsx
import { useEffect, useRef, useState } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";
```

Then find:

```tsx
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);
```

Replace with:

```tsx
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);
  const tiltRef = usePointerTilt<HTMLDivElement>();
```

Then find:

```tsx
    <div className="login-view futuristic-card">
```

Replace with:

```tsx
    <div ref={tiltRef} className="login-view futuristic-card tilt-surface">
```

In `octopus-desktop/frontend/src/setup/SettingsView.tsx`, find:

```tsx
import { useEffect, useState } from "react";
```

Replace with:

```tsx
import { useEffect, useState } from "react";
import { usePointerTilt } from "../hooks/usePointerTilt";
```

Then find:

```tsx
  const [downloading, setDownloading] = useState(false);
```

Replace with:

```tsx
  const [downloading, setDownloading] = useState(false);
  const tiltRef = usePointerTilt<HTMLDivElement>();
```

Then find:

```tsx
    <div className="settings-view futuristic-card">
```

Replace with:

```tsx
    <div ref={tiltRef} className="settings-view futuristic-card tilt-surface">
```

- [ ] **Step 8: Run full test suite and build to verify nothing broke**

Run: `cd octopus-desktop/frontend && npx vitest run && npm run build`
Expected: All existing tests pass unchanged (`cards.test.tsx`, `setup.test.tsx`, `reducer.test.ts`, `recorder.test.ts` — wrapping card roots in an extra `Tilt` div does not change any `getByText`/`getByRole` query results), plus the new `Tilt.test.tsx`/`usePointerTilt.test.tsx`. `npm run build` succeeds with zero TypeScript errors.

- [ ] **Step 9: Commit**

```bash
cd octopus-desktop/frontend && git add src/chat/UserBubble.tsx src/chat/cards src/setup/LoginView.tsx src/setup/SettingsView.tsx src/style.css
git commit -m "feat(desktop): terapkan efek tilt dan elevation ke card, bubble, dan modal"
```

---

### Task 5: `ChatView` pending state + send button tilt

**Files:**
- Modify: `octopus-desktop/frontend/src/chat/ChatView.tsx`
- Create: `octopus-desktop/frontend/src/chat/ChatView.test.tsx`

**Interfaces:**
- Consumes: `UserBubble` from Task 4 (`./UserBubble`), `usePointerTilt` from Task 2 (`../hooks/usePointerTilt`).
- Produces: `ChatView` gains prop `onPendingChange?: (pending: boolean) => void`, called `true` synchronously in `submit()` and `false` whenever the last message becomes an assistant message with `done === true`. Consumed by Task 8 (`App.tsx`).

- [ ] **Step 1: Write the failing test**

Create `octopus-desktop/frontend/src/chat/ChatView.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatView } from "./ChatView";
import type { IncomingEvent } from "./types";

let chatEventCb: ((ev: IncomingEvent) => void) | null = null;

beforeEach(() => {
  chatEventCb = null;
  (window as any).go = {
    main: {
      App: {
        SendChat: vi.fn().mockResolvedValue(undefined),
        ApprovePlan: vi.fn().mockResolvedValue(undefined),
        RejectPlan: vi.fn().mockResolvedValue(true),
      },
    },
  };
  (window as any).runtime = {
    EventsOn: vi.fn((_name: string, cb: (payload: unknown) => void) => {
      chatEventCb = cb as (ev: IncomingEvent) => void;
      return () => {};
    }),
  };
});

describe("ChatView onPendingChange", () => {
  it("melaporkan pending=true saat submit, false saat pesan assistant selesai", () => {
    const onPendingChange = vi.fn();
    render(<ChatView onPendingChange={onPendingChange} />);

    const input = screen.getByPlaceholderText(/ketik perintah/i);
    fireEvent.change(input, { target: { value: "halo" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onPendingChange).toHaveBeenCalledWith(true);

    chatEventCb?.({ msgId: "m-1", type: "final", data: { text: "Halo juga" } });

    expect(onPendingChange).toHaveBeenLastCalledWith(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd octopus-desktop/frontend && npx vitest run src/chat/ChatView.test.tsx`
Expected: FAIL — `onPendingChange` is never called (prop doesn't exist yet on `ChatView`).

- [ ] **Step 3: Implement `onPendingChange` and wire `UserBubble`/tilt send button**

Modify `octopus-desktop/frontend/src/chat/ChatView.tsx` — replace entire file:

```tsx
import { useEffect, useRef, useState } from "react";
import { approvePlan, onChatEvent, rejectPlan, sendChat } from "./bindings";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message, Part } from "./types";
import { ActionCard } from "./cards/ActionCard";
import { ApprovalCard } from "./cards/ApprovalCard";
import { ErrorCard } from "./cards/ErrorCard";
import { MetricCard } from "./cards/MetricCard";
import { StatusLine } from "./cards/StatusLine";
import { TableCard } from "./cards/TableCard";
import { TextCard } from "./cards/TextCard";
import { UserBubble } from "./UserBubble";
import { usePointerTilt } from "../hooks/usePointerTilt";

const METRIC_ACTIONS = new Set(["memory", "disk", "server_status", "docker_stats"]);
const TABLE_ACTIONS = new Set(["docker_ps", "docker_images", "docker_compose_ps", "processes"]);

let counter = 0;
const newMsgId = () => `m-${Date.now()}-${counter++}`;

export function ChatView({
  onFinal,
  onPendingChange,
  inputExtra,
  registerSubmit,
}: {
  onFinal?: (text: string) => void;
  onPendingChange?: (pending: boolean) => void;
  inputExtra?: React.ReactNode; // slot untuk tombol mic (Task 11)
  registerSubmit?: (fn: (text: string) => void) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const lastFinal = useRef("");
  const sendButtonRef = usePointerTilt<HTMLButtonElement>();

  useEffect(() => {
    return onChatEvent((ev) => setMessages((prev) => applyEvent(prev, ev)));
  }, []);

  useEffect(() => {
    registerSubmit?.(submit);
  }, [registerSubmit]);

  useEffect(() => {
    const handleVoiceDraft = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      setDraft(customEvent.detail);
    };
    window.addEventListener("voice:draft", handleVoiceDraft);
    return () => window.removeEventListener("voice:draft", handleVoiceDraft);
  }, []);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.done && lastMsg.finalText && lastMsg.finalText !== lastFinal.current) {
      lastFinal.current = lastMsg.finalText;
      onFinal?.(lastMsg.finalText);
    }
  }, [messages, onFinal]);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.done) {
      onPendingChange?.(false);
    }
  }, [messages, onPendingChange]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const msgId = newMsgId();
    setMessages((prev) => [...prev, { msgId: `u-${msgId}`, role: "user", text: trimmed }]);
    onPendingChange?.(true);
    void sendChat(msgId, trimmed);
    setDraft("");
  };

  const decide = (msg: AssistantMessage, planId: string, decision: "approved" | "rejected") => {
    setMessages((prev) =>
      prev.map((m) =>
        m.msgId === msg.msgId && m.role === "assistant"
          ? {
              ...m,
              parts: m.parts.map((p) =>
                p.kind === "approval" && p.planId === planId ? { ...p, decided: decision } : p,
              ),
            }
          : m,
      ),
    );
    if (decision === "approved") void approvePlan(newMsgId(), planId);
    else void rejectPlan(planId);
  };

  const renderPart = (msg: AssistantMessage, p: Part, i: number) => {
    switch (p.kind) {
      case "status":
        return <StatusLine key={i} text={p.text} />;
      case "text":
        return <TextCard key={i} text={p.text} streaming={p.streaming} />;
      case "action":
        if (!p.running && METRIC_ACTIONS.has(p.action))
          return <MetricCard key={i} action={p.action} output={p.output} />;
        if (!p.running && TABLE_ACTIONS.has(p.action))
          return <TableCard key={i} action={p.action} output={p.output} />;
        return <ActionCard key={i} action={p.action} running={p.running} output={p.output} />;
      case "approval":
        return (
          <ApprovalCard
            key={i}
            planId={p.planId}
            summary={p.summary}
            decided={p.decided}
            onApprove={(id) => decide(msg, id, "approved")}
            onReject={(id) => decide(msg, id, "rejected")}
          />
        );
      case "error":
        return <ErrorCard key={i} message={p.message} retryable={p.retryable} />;
    }
  };

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.map((m) =>
          m.role === "user" ? (
            <UserBubble key={m.msgId} text={m.text} />
          ) : (
            <div key={m.msgId} className="msg-assistant">
              {m.parts.map((p, i) => renderPart(m, p, i))}
            </div>
          ),
        )}
      </div>
      <div className="chat-input">
        {inputExtra}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(draft)}
          placeholder="Ketik perintah… (atau tahan tombol mic)"
        />
        <button ref={sendButtonRef} className="tilt-surface" onClick={() => submit(draft)}>
          Kirim
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd octopus-desktop/frontend && npx vitest run src/chat/ChatView.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Run full test suite**

Run: `cd octopus-desktop/frontend && npx vitest run`
Expected: All tests pass, including `cards.test.tsx` (unaffected — `ChatView` rendering isn't exercised there).

- [ ] **Step 6: Commit**

```bash
cd octopus-desktop/frontend && git add src/chat/ChatView.tsx src/chat/ChatView.test.tsx
git commit -m "feat(desktop): tambah onPendingChange di ChatView dan tilt tombol kirim"
```

---

### Task 6: `AiOrb` 3D component

**Files:**
- Create: `octopus-desktop/frontend/src/orb/orbMaterial.ts`
- Create: `octopus-desktop/frontend/src/orb/AiOrb.tsx`

**Interfaces:**
- Consumes: `computeOrbUniforms`, `OrbState` from Task 1 (`./orbState`).
- Produces: `export function AiOrb({ state, amplitude }: { state: OrbState; amplitude?: number }): JSX.Element`. Consumed by Task 8 (`App.tsx`).
- No automated unit test for this task: jsdom has no WebGL context, and stubbing enough of the WebGL API surface for `three.js`'s `WebGLRenderer` to initialize would require mocking dozens of GL entry points — brittle and low-value versus this project's existing test philosophy (test logic, not rendering pixels). The logic this component depends on (`computeOrbUniforms`) is already unit-tested in Task 1. This task's deliverable is verified via `npm run build` (type-check + bundle) and manual visual check in Task 8's final step.

- [ ] **Step 1: Create the custom shader material**

Create `octopus-desktop/frontend/src/orb/orbMaterial.ts`:

```ts
import { shaderMaterial } from "@react-three/drei";
import { extend } from "@react-three/fiber";
import * as THREE from "three";

const OrbMaterialImpl = shaderMaterial(
  {
    uTime: 0,
    uDistortion: 0.08,
    uColorA: new THREE.Color("#3b82f6"),
    uColorB: new THREE.Color("#10b981"),
    uColorC: new THREE.Color("#f59e0b"),
    uColorMix: 0,
  },
  `
    uniform float uTime;
    uniform float uDistortion;
    varying vec3 vNormal;
    varying vec3 vPosition;

    float noise(vec3 p) {
      return sin(p.x * 3.0 + uTime) * sin(p.y * 3.0 + uTime) * sin(p.z * 3.0 + uTime);
    }

    void main() {
      vNormal = normalize(normalMatrix * normal);
      vec3 displaced = position + normal * noise(position) * uDistortion;
      vPosition = displaced;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
    }
  `,
  `
    uniform vec3 uColorA;
    uniform vec3 uColorB;
    uniform vec3 uColorC;
    uniform float uColorMix;
    varying vec3 vNormal;
    varying vec3 vPosition;

    void main() {
      float fresnel = pow(1.0 - abs(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0))), 2.0);
      vec3 base = mix(uColorA, uColorB, 0.5 + 0.5 * sin(vPosition.y * 2.0));
      vec3 withGlow = mix(base, uColorC, uColorMix);
      gl_FragColor = vec4(withGlow * (0.4 + fresnel * 1.2), 0.85);
    }
  `,
);

extend({ orbMaterial: OrbMaterialImpl });

declare module "@react-three/fiber" {
  interface ThreeElements {
    orbMaterial: any;
  }
}

export { OrbMaterialImpl };
```

- [ ] **Step 2: Create the `AiOrb` component**

Create `octopus-desktop/frontend/src/orb/AiOrb.tsx`:

```tsx
import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import "./orbMaterial";
import { computeOrbUniforms, type OrbState } from "./orbState";

function OrbMesh({ state, amplitude }: { state: OrbState; amplitude: number }) {
  const materialRef = useRef<any>(null);
  const meshRef = useRef<THREE.Mesh>(null);
  const elapsed = useRef(0);

  useFrame((_, delta) => {
    elapsed.current += delta;
    const u = computeOrbUniforms(state, amplitude, elapsed.current);
    if (meshRef.current) {
      meshRef.current.rotation.y += u.rotationSpeed * delta;
      meshRef.current.scale.setScalar(1 + u.breathScale);
    }
    if (materialRef.current) {
      materialRef.current.uTime = elapsed.current;
      materialRef.current.uDistortion = u.distortion;
      materialRef.current.uColorMix = u.colorMix;
    }
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 4]} />
      <orbMaterial ref={materialRef} transparent />
    </mesh>
  );
}

export function AiOrb({ state, amplitude = 0 }: { state: OrbState; amplitude?: number }) {
  return (
    <Canvas camera={{ position: [0, 0, 2.5], fov: 40 }} gl={{ alpha: true, antialias: true }}>
      <ambientLight intensity={0.6} />
      <pointLight position={[2, 2, 2]} intensity={1.2} />
      <OrbMesh state={state} amplitude={amplitude} />
    </Canvas>
  );
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd octopus-desktop/frontend && npm run build`
Expected: `tsc` reports zero errors, `vite build` succeeds and emits the new orb module in `dist/`.

- [ ] **Step 4: Commit**

```bash
cd octopus-desktop/frontend && git add src/orb/orbMaterial.ts src/orb/AiOrb.tsx
git commit -m "feat(desktop): tambah komponen AiOrb 3d dengan shader kustom"
```

---

### Task 7: Audio-reactive `speak()`

**Files:**
- Modify: `octopus-desktop/frontend/src/voice/tts.ts`
- Create: `octopus-desktop/frontend/src/voice/tts.test.ts`

**Interfaces:**
- Produces: `export function computeRmsAmplitude(data: Uint8Array): number` (pure, 0..1), `export async function speak(text: string, onAmplitude?: (level: number) => void): Promise<void>` — now resolves on the audio `ended` event (not on playback start), and drives `onAmplitude` via a Web Audio `AnalyserNode` when provided. Consumed by Task 8 (`App.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `octopus-desktop/frontend/src/voice/tts.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computeRmsAmplitude, speak } from "./tts";

describe("computeRmsAmplitude", () => {
  it("mengembalikan 0 untuk data hening (semua 128)", () => {
    expect(computeRmsAmplitude(new Uint8Array(8).fill(128))).toBe(0);
  });

  it("meng-clamp hasil ke maksimum 1", () => {
    expect(computeRmsAmplitude(new Uint8Array(8).fill(255))).toBe(1);
  });
});

class FakeAudio extends EventTarget {
  src: string;
  constructor(src: string) {
    super();
    this.src = src;
  }
  play = vi.fn(() => {
    queueMicrotask(() => this.dispatchEvent(new Event("ended")));
    return Promise.resolve();
  });
}

class FakeAudioContextCtor {
  static instances: FakeAudioContextCtor[] = [];
  destination = {};
  createMediaElementSource = vi.fn(() => ({ connect: vi.fn() }));
  createAnalyser = vi.fn(() => ({
    fftSize: 0,
    frequencyBinCount: 32,
    connect: vi.fn(),
    getByteTimeDomainData: (arr: Uint8Array) => arr.fill(128),
  }));
  close = vi.fn().mockResolvedValue(undefined);
  constructor() {
    FakeAudioContextCtor.instances.push(this);
  }
}

beforeEach(() => {
  FakeAudioContextCtor.instances = [];
  (window as any).go = { main: { App: { Speak: vi.fn().mockResolvedValue(btoa("data")) } } };
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("AudioContext", FakeAudioContextCtor);
  URL.createObjectURL = vi.fn(() => "blob:fake");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("speak", () => {
  it("resolve setelah event ended dan revoke object URL", async () => {
    await expect(speak("halo")).resolves.toBeUndefined();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
  });

  it("tidak membuat AudioContext bila onAmplitude tidak diberikan", async () => {
    await speak("halo");
    expect(FakeAudioContextCtor.instances).toHaveLength(0);
  });

  it("membuat AudioContext dan menutupnya saat onAmplitude diberikan", async () => {
    await speak("halo", () => {});
    expect(FakeAudioContextCtor.instances).toHaveLength(1);
    expect(FakeAudioContextCtor.instances[0].close).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd octopus-desktop/frontend && npx vitest run src/voice/tts.test.ts`
Expected: FAIL — `computeRmsAmplitude` is not exported, and current `speak()` resolves on `play()` rather than `ended`, so no `AudioContext` bookkeeping exists yet.

- [ ] **Step 3: Rewrite `tts.ts`**

Modify `octopus-desktop/frontend/src/voice/tts.ts` — replace entire file:

```ts
export function computeRmsAmplitude(data: Uint8Array): number {
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    const norm = (data[i] - 128) / 128;
    sumSquares += norm * norm;
  }
  return Math.min(1, Math.sqrt(sumSquares / data.length) * 4);
}

export async function speak(text: string, onAmplitude?: (level: number) => void): Promise<void> {
  const b64 = await window.go.main.App.Speak(text);
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const audio = new Audio(url);

  let audioCtx: AudioContext | null = null;
  let rafId: number | null = null;

  if (onAmplitude) {
    audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(audio);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      onAmplitude(computeRmsAmplitude(data));
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  try {
    await new Promise<void>((resolve, reject) => {
      audio.addEventListener("ended", () => resolve(), { once: true });
      audio.addEventListener("error", () => reject(new Error("Playback gagal")), { once: true });
      audio.play().catch(reject);
    });
  } finally {
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (audioCtx) await audioCtx.close();
    URL.revokeObjectURL(url);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd octopus-desktop/frontend && npx vitest run src/voice/tts.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Run full test suite**

Run: `cd octopus-desktop/frontend && npx vitest run`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd octopus-desktop/frontend && git add src/voice/tts.ts src/voice/tts.test.ts
git commit -m "feat(desktop): buat speak() reaktif terhadap amplitudo audio asli"
```

---

### Task 8: Wire orb + tilt into `App.tsx`, header layout, background parallax

**Files:**
- Modify: `octopus-desktop/frontend/src/App.tsx`
- Modify: `octopus-desktop/frontend/src/style.css`

**Interfaces:**
- Consumes: `AiOrb` from Task 6 (`./orb/AiOrb`), `deriveAiState` from Task 1 (`./orb/orbState`), `speak` from Task 7 (`./voice/tts`), `ChatView`'s `onPendingChange` from Task 5.

- [ ] **Step 1: Restructure the header CSS to a 3-column grid**

In `octopus-desktop/frontend/src/style.css`, find:

```css
.app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.85rem 2rem;
    background-color: rgba(8, 12, 20, 0.8);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-color);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    z-index: 10;
}
```

Replace with:

```css
.app-header {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    padding: 0.85rem 2rem;
    background-color: rgba(8, 12, 20, 0.8);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-color);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    z-index: 10;
}

.app-header-orb {
    width: 64px;
    height: 64px;
    justify-self: center;
}
```

Then find:

```css
.settings-toggle-btn {
    background: none;
    border: 1px solid rgba(59, 130, 246, 0.3);
    font-size: 1.1rem;
    color: #60a5fa;
    cursor: pointer;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 50%;
    transition: all 0.3s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgba(59, 130, 246, 0.05);
}
```

Replace with:

```css
.settings-toggle-btn {
    background: none;
    border: 1px solid rgba(59, 130, 246, 0.3);
    font-size: 1.1rem;
    color: #60a5fa;
    cursor: pointer;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 50%;
    transition: all 0.3s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgba(59, 130, 246, 0.05);
    justify-self: end;
}
```

- [ ] **Step 2: Make the background grid parallax-reactive**

In `octopus-desktop/frontend/src/style.css`, find:

```css
/* Futuristic grid/radar background pattern */
body::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
        linear-gradient(rgba(18, 24, 38, 0.5) 1px, transparent 1px),
        linear-gradient(90deg, rgba(18, 24, 38, 0.5) 1px, transparent 1px);
    background-size: 24px 24px;
    background-position: center;
    pointer-events: none;
    z-index: 1;
}
```

Replace with:

```css
/* Futuristic grid/radar background pattern */
body::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
        linear-gradient(rgba(18, 24, 38, 0.5) 1px, transparent 1px),
        linear-gradient(90deg, rgba(18, 24, 38, 0.5) 1px, transparent 1px);
    background-size: 24px 24px;
    background-position: calc(50% + var(--bg-parallax-x, 0px)) calc(50% + var(--bg-parallax-y, 0px));
    pointer-events: none;
    z-index: 1;
}
```

- [ ] **Step 3: Wire `AiOrb`, `aiState`, pending state, and background parallax into `App.tsx`**

Modify `octopus-desktop/frontend/src/App.tsx` — replace entire file:

```tsx
import { useEffect, useRef, useState } from "react";
import { ChatView } from "./chat/ChatView";
import { VoiceBar } from "./voice/VoiceBar";
import { speak } from "./voice/tts";
import { LoginView } from "./setup/LoginView";
import { SettingsView } from "./setup/SettingsView";
import { AiOrb } from "./orb/AiOrb";
import { deriveAiState } from "./orb/orbState";
import "./style.css";

export default function App() {
  const [screen, setScreen] = useState<"loading" | "login" | "chat">("loading");
  const [showSettings, setShowSettings] = useState(false);
  const [jarvis, setJarvis] = useState(true);
  const [pending, setPending] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const submitRef = useRef<((text: string) => void) | null>(null);

  const aiState = deriveAiState(pending, isSpeaking);

  useEffect(() => {
    window.go.main.App.IsLoggedIn().then((loggedIn) => {
      if (loggedIn) {
        setScreen("chat");
      } else {
        setScreen("login");
      }
    });
  }, []);

  useEffect(() => {
    if (screen === "chat") {
      window.go.main.App.GetSettings().then((s) => setJarvis(Boolean(s.jarvis_mode)));
    }
  }, [screen]);

  useEffect(() => {
    if (screen !== "chat") return;
    const handleMove = (e: PointerEvent) => {
      const px = (e.clientX / window.innerWidth - 0.5) * 2;
      const py = (e.clientY / window.innerHeight - 0.5) * 2;
      document.documentElement.style.setProperty("--bg-parallax-x", `${(px * 6).toFixed(2)}px`);
      document.documentElement.style.setProperty("--bg-parallax-y", `${(py * 6).toFixed(2)}px`);
    };
    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, [screen]);

  const handleTranscript = (text: string) => {
    if (jarvis) {
      submitRef.current?.(text); // auto-send
    } else {
      window.dispatchEvent(new CustomEvent("voice:draft", { detail: text }));
    }
  };

  const handleFinal = (text: string) => {
    if (!jarvis) return;
    setIsSpeaking(true);
    void speak(text, (level) => setAmplitude(level))
      .catch(() => {}) // TTS gagal tidak boleh ganggu chat
      .finally(() => {
        setIsSpeaking(false);
        setAmplitude(0);
      });
  };

  const handleLogout = async () => {
    await window.go.main.App.Logout();
    setShowSettings(false);
    setScreen("login");
  };

  if (screen === "loading") {
    return <div className="loading-screen">Memuat...</div>;
  }

  if (screen === "login") {
    return <LoginView onPaired={() => setScreen("chat")} />;
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Octopus Desktop</h1>
        <div className="app-header-orb">
          <AiOrb state={aiState} amplitude={amplitude} />
        </div>
        <button className="settings-toggle-btn" onClick={() => setShowSettings(true)}>⚙️</button>
      </header>
      <main className="app-main">
        <ChatView
          onFinal={handleFinal}
          onPendingChange={setPending}
          registerSubmit={(fn) => (submitRef.current = fn)}
          inputExtra={
            <VoiceBar onTranscript={handleTranscript} jarvis={jarvis} onToggleJarvis={() => {
              const nextJarvis = !jarvis;
              setJarvis(nextJarvis);
              window.go.main.App.GetSettings().then(s => {
                window.go.main.App.SaveSettings({ ...s, jarvis_mode: nextJarvis });
              });
            }} />
          }
        />
      </main>
      {showSettings && (
        <div className="modal-overlay">
          <SettingsView onClose={() => setShowSettings(false)} onLogout={handleLogout} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the full test suite and build**

Run: `cd octopus-desktop/frontend && npx vitest run && npm run build`
Expected: All tests pass (orbState, usePointerTilt, Tilt, ChatView, tts, cards, reducer, recorder, setup — 9 files), `npm run build` succeeds with zero TypeScript errors.

- [ ] **Step 5: Manual visual verification**

Run: `cd octopus-desktop && wails dev`
Expected: App launches; header shows a rotating glowing orb centered between the title and settings button. Sending a chat message shows the orb speed up/shift toward amber while a response streams in (thinking), then pulse while the reply is read aloud if Jarvis mode is on (speaking). Hovering over answer cards, chat bubbles, the send button, and the login/settings panels shows a subtle tilt following the cursor, with cards now showing visible background/border/shadow instead of flat text. Move the mouse around the empty chat area and confirm the background grid shifts subtly (parallax).

- [ ] **Step 6: Commit**

```bash
cd octopus-desktop/frontend && git add src/App.tsx src/style.css
git commit -m "feat(desktop): pasang orb ai dan parallax background di App"
```

---

## Post-plan notes (scope decisions made during planning, not in the original spec)

- `.card` (chat answer cards) had almost no visual chrome before this plan (`style.css:271-273` was just `padding: 1.15rem`). Task 4 merges it with `.futuristic-card`'s glass-panel styling — without this, adding tilt/shadow to an invisible box would have no visible effect. This is why the app read as "flat," not only a missing-3D issue.
- The spec listed `.approval-buttons button` and `.cyber-btn` as tilt targets. Both sit *inside* an already tilt-wrapped parent (`ApprovalCard`'s `Tilt`, `LoginView`'s tilted root). Nesting two independent perspective-tilt transforms compounds unpredictably, so this plan applies tilt only to `.chat-input button` (not nested in any tilted ancestor) and skips individual tilt on buttons already inside a tilted card/panel.
- `AiOrb.tsx` has no automated render test — jsdom has no WebGL context, and mocking enough of `WebGLRenderingContext` for `three.js` to initialize would be brittle busywork with little payoff. Its logic dependency (`orbState.ts`) is fully unit-tested instead, and the visual result is checked manually in Task 8.
