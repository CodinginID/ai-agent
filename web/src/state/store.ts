import { create } from "zustand";
import { approvePlan, rejectPlan, runTask } from "../net/api";
import type {
  Agent,
  Approval,
  BoardCard,
  BoardCol,
  FeedColor,
  Role,
  RoomEvent,
  ServerApproval,
  Task,
  Theme,
} from "./types";
import {
  AGENT_SPEED,
  center,
  MEET,
  REVIEW,
  ROLE,
  SERVER,
  WORLD_H,
  WORLD_W,
  zoneBy,
} from "../room/engine/scene";

/** Roster entry hasil CRUD backend (/room/roster, event roster.updated /
 *  room.snapshot) — cuma identitas, bukan runtime state (posisi/tugas/log). */
export interface RosterEntry {
  id: string;
  name: string;
  role: Role;
}

// ── small helpers ──
const rand = (a: number, b: number): number => a + Math.random() * (b - a);
const choice = <T>(arr: T[]): T => arr[(Math.random() * arr.length) | 0];
const clamp = (v: number, lo: number, hi: number): number =>
  v < lo ? lo : v > hi ? hi : v;
const dist = (ax: number, ay: number, bx: number, by: number): number =>
  Math.hypot(ax - bx, ay - by);
const now = (): string => new Date().toTimeString().slice(0, 8);
// feed messages are rendered as HTML; escape any user-provided text at the boundary
const escapeHtml = (s: string): string =>
  s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

// ── task pool (ported from the mockup) ──
const TASKS: Omit<Task, "id">[] = [
  { desc: "perbaiki timeout Ollama", role: "coder", review: true },
  { desc: "audit log error container docker", role: "researcher" },
  { desc: "cek penggunaan disk VPS", role: "researcher" },
  { desc: "optimasi query pgvector", role: "coder", review: true },
  { desc: "review PR #77", role: "reviewer" },
  { desc: "scan dependency keamanan", role: "tester" },
  { desc: "restart aiagent_bot", role: "deployer", risky: true },
  { desc: "deploy image terbaru ke VPS", role: "deployer", risky: true },
  { desc: "backup database Postgres", role: "deployer", risky: true },
  { desc: "jalankan unit test backend", role: "tester" },
  { desc: "rotasi kredensial API", role: "deployer", risky: true },
  { desc: "profil beban CPU worker", role: "researcher" },
];

// ── initial roster ──
function mk(
  id: string,
  name: string,
  role: Role,
  x: number,
  y: number,
  state: Agent["state"] = "idle",
): Agent {
  return {
    id,
    name,
    role,
    state,
    task: null,
    progress: 0,
    logs: [],
    homeX: x,
    homeY: y,
    targetX: x,
    targetY: y,
    posX: x,
    posY: y,
    travel: 0,
    workT: 0,
    workDur: 0,
  };
}

// Zona kantor per peran — dipakai baik untuk penempatan awal maupun agen baru
// hasil CRUD roster (lihat homeFor).
const ZONE_FOR_ROLE: Record<Role, string> = {
  manager: "Kantor Manajer",
  coder: "Dev Bay",
  tester: "QA Corner",
  reviewer: "Ruang Review",
  deployer: "Deploy Station",
  researcher: "Riset",
};

/** Slot tempat tinggal (home) agen ke-`index` (0-based, di antara agen
 *  seperan lain) di dalam zona kantor perannya — grid 3 kolom, spasi merata
 *  supaya banyak agen seperan tak bertumpuk di satu titik. */
function homeFor(role: Role, index: number): { x: number; y: number } {
  const zone = zoneBy(ZONE_FOR_ROLE[role]);
  if (role === "manager") {
    const c = center(zone);
    return { x: c.x, y: c.y + 8 };
  }
  const cols = 3;
  const col = index % cols;
  const row = Math.floor(index / cols);
  const pad = 70;
  const stepX = cols > 1 ? (zone.w - pad * 2) / (cols - 1) : 0;
  return {
    x: clamp(zone.x + pad + col * stepX, zone.x + 24, zone.x + zone.w - 24),
    y: clamp(zone.y + pad + row * 90, zone.y + 24, zone.y + zone.h - 24),
  };
}

const VALID_ROLES = new Set<string>(Object.keys(ROLE));

/** Validasi payload agents dari event server (boundary tak terpercaya) —
 *  entri dengan id kosong atau peran tak dikenal dibuang, bukan bikin crash. */
function parseRosterEntries(raw: unknown): RosterEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: RosterEntry[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) continue;
    const id = String((item as { id?: unknown }).id ?? "").trim();
    const name = String((item as { name?: unknown }).name ?? "").trim();
    const role = String((item as { role?: unknown }).role ?? "");
    if (!id || !name || !VALID_ROLES.has(role)) continue;
    out.push({ id, name, role: role as Role });
  }
  return out;
}

/** selectedId tetap valid setelah reconcile — null-kan kalau agennya dibuang. */
function keepSelected(selectedId: string | null, agents: Agent[]): string | null {
  if (selectedId === null) return null;
  return agents.some((a) => a.id === selectedId) ? selectedId : null;
}

function initialAgents(): Agent[] {
  return reconcileAgents([], [
    { id: "octo", name: "Octo", role: "manager" },
    { id: "nadia", name: "Nadia", role: "coder" },
    { id: "bima", name: "Bima", role: "coder" },
    { id: "sari", name: "Sari", role: "tester" },
    { id: "rangga", name: "Rangga", role: "reviewer" },
    { id: "dewi", name: "Dewi", role: "deployer" },
    { id: "yusuf", name: "Yusuf", role: "researcher" },
  ]).map((a) => (a.role === "manager" ? { ...a, state: "patrol" } : a));
}

/** Reconcile roster server (CRUD /room/roster, event roster.updated /
 *  room.snapshot) ke agents runtime: agen yang sudah ada mempertahankan
 *  posisi/tugas/log-nya (cuma nama/peran yang disinkronkan), agen baru
 *  ditempatkan via homeFor, agen yang sudah tak ada di roster dibuang. */
function reconcileAgents(current: Agent[], roster: RosterEntry[]): Agent[] {
  const byId = new Map(current.map((a) => [a.id, a]));
  const roleCounts = new Map<Role, number>();
  const next: Agent[] = [];
  for (const r of roster) {
    const idx = roleCounts.get(r.role) ?? 0;
    roleCounts.set(r.role, idx + 1);
    const existing = byId.get(r.id);
    if (existing) {
      next.push(
        existing.name === r.name && existing.role === r.role
          ? existing
          : { ...existing, name: r.name, role: r.role },
      );
    } else {
      const home = homeFor(r.role, idx);
      next.push(mk(r.id, r.name, r.role, home.x, home.y));
    }
  }
  return next;
}

function initialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem("octopus-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

interface RoomState {
  agents: Agent[];
  approvals: Approval[];
  serverApprovals: ServerApproval[];
  events: RoomEvent[];
  board: BoardCard[];
  queue: Task[];
  selectedId: string | null;
  theme: Theme;
  managerName: string;
  /** pasukan (worker) online — dari /room/state + event worker.online/offline */
  workers: number;
  /** true begitu backend nyata mengendalikan ruangan → matikan spawner mock */
  live: boolean;

  // actions
  select: (id: string | null) => void;
  submitCommand: (text: string) => void;
  applyServerEvent: (ev: Record<string, unknown>) => void;
  /** Sinkronkan agents dengan roster server (CRUD /room/roster / event
   *  roster.updated / room.snapshot) — lihat reconcileAgents. */
  applyRoster: (roster: RosterEntry[]) => void;
  approve: (id: number) => void;
  reject: (id: number) => void;
  approveServer: (planId: string) => void;
  rejectServer: (planId: string) => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  startScheduler: () => () => void;
}

const MANAGER = "Octo";
const TICK = 0.2; // scheduler step in seconds (5 Hz)

export const useStore = create<RoomState>((set, get) => {
  // ── mutable-ish counters kept in closure ──
  let taskSeq = 0;
  let apprSeq = 0;
  let eventSeq = 0;
  let spawnT = rand(2, 4);

  // ── internal mutation on the current agents array (already cloned by caller) ──
  const feedInto = (
    events: RoomEvent[],
    msg: string,
    color: FeedColor,
  ): RoomEvent[] => {
    const next = [...events, { id: ++eventSeq, t: now(), msg, color }];
    return next.length > 40 ? next.slice(next.length - 40) : next;
  };

  const logInto = (a: Agent, msg: string): void => {
    a.logs = [{ t: now(), msg }, ...a.logs].slice(0, 5);
  };

  const moveTo = (a: Agent, x: number, y: number): void => {
    a.targetX = clamp(x, 24, WORLD_W - 24);
    a.targetY = clamp(y, 24, WORLD_H - 24);
    a.travel = Math.max(
      dist(a.posX, a.posY, a.targetX, a.targetY) / AGENT_SPEED,
      0.35,
    );
  };

  // ── board helpers (operate on a cloned board array) ──
  const addCard = (board: BoardCard[], task: Task, col: BoardCol): void => {
    if (!board.some((c) => c.id === task.id)) {
      board.push({
        id: task.id,
        desc: task.desc,
        role: task.role,
        col,
        doneT: 0,
      });
    }
  };
  const setCol = (
    board: BoardCard[],
    id: number | string,
    col: BoardCol,
  ): void => {
    const c = board.find((bc) => bc.id === id);
    if (c) {
      c.col = col;
      if (col === "done") c.doneT = 0;
    }
  };
  const removeCard = (board: BoardCard[], id: number | string): void => {
    const i = board.findIndex((c) => c.id === id);
    if (i >= 0) board.splice(i, 1);
  };

  const idleCandidates = (agents: Agent[], role: Role): Agent[] => {
    const idle = agents.filter((a) => a.role !== "manager" && a.state === "idle");
    const match = idle.filter((a) => a.role === role);
    return match.length ? match : idle;
  };

  // begin executing a task on an agent (mutates draft agent / board / events)
  const begin = (
    a: Agent,
    task: Task,
    board: BoardCard[],
    events: RoomEvent[],
    approvals: Approval[],
  ): RoomEvent[] => {
    a.task = task;
    setCol(board, task.id, "doing");
    let ev = feedInto(
      events,
      `<b>${MANAGER}</b> menugaskan “${task.desc}” ke <b>${a.name}</b>`,
      "work",
    );
    logInto(a, `Ditugaskan: ${task.desc}`);
    if (task.risky) {
      a.state = "to_meet";
      moveTo(a, MEET.x + rand(-34, 34), MEET.y + rand(-18, 18));
    } else {
      a.state = "to_srv";
      moveTo(a, SERVER.x + rand(-40, 40), SERVER.y + rand(-30, 30));
    }
    void approvals;
    return ev;
  };

  // assign a task: pick an idle candidate or queue it
  const assign = (
    task: Task,
    agents: Agent[],
    board: BoardCard[],
    events: RoomEvent[],
    approvals: Approval[],
    queue: Task[],
  ): RoomEvent[] => {
    addCard(board, task, "todo");
    const cands = idleCandidates(agents, task.role);
    if (!cands.length) {
      queue.push(task);
      return feedInto(events, `Tugas <b>${task.desc}</b> masuk antrean`, "idle");
    }
    return begin(choice(cands), task, board, events, approvals);
  };

  const startWork = (a: Agent): void => {
    a.state = "working";
    a.progress = 0;
    a.workT = 0;
    a.workDur = rand(5, 9);
    logInto(a, "Mulai eksekusi");
  };

  const returnHome = (a: Agent): void => {
    a.state = "ret";
    moveTo(a, a.homeX, a.homeY);
  };

  return {
    agents: initialAgents(),
    approvals: [],
    serverApprovals: [],
    events: [
      {
        id: ++eventSeq,
        t: now(),
        msg: "🐙 Ruang Octopus online — Manajer & 6 agen siap",
        color: "done",
      },
    ],
    board: [],
    queue: [],
    selectedId: null,
    theme: initialTheme(),
    managerName: MANAGER,
    workers: 0,
    live: false,

    select: (id) => set({ selectedId: id }),

    setTheme: (t) => {
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", t);
      }
      if (typeof window !== "undefined") {
        window.localStorage.setItem("octopus-theme", t);
      }
      set({ theme: t });
    },

    toggleTheme: () => {
      const next = get().theme === "dark" ? "light" : "dark";
      get().setTheme(next);
    },

    submitCommand: (text) => {
      const txt = text.trim();
      if (!txt) return;
      const safe = escapeHtml(txt);

      // Ruangan kini dikendalikan backend nyata → matikan simulasi mock.
      set((s) => ({
        live: true,
        events: feedInto(
          s.events,
          `📩 <b>${MANAGER}</b> menerima perintahmu: “${safe}”`,
          "work",
        ),
      }));

      // Kirim ke Manajer IT nyata (TaskRunner): PM pecah tugas → dispatch
      // per-role ke pasukan. Kartu kanban + avatar digerakkan event
      // /room/stream (task.card); hasil akhir → feed.
      void runTask(txt).then((res) => {
        if (!res) return;
        set((s) => ({
          events: feedInto(
            s.events,
            res.ok
              ? `✅ <b>${MANAGER}</b> selesai (${res.outcomes.length} langkah): ${escapeHtml(res.summary)}`
              : `⚠️ <b>${MANAGER}</b> berhenti: ${escapeHtml(res.note)}`,
            res.ok ? "done" : "error",
          ),
        }));
      });
    },

    applyServerEvent: (ev) => {
      const type = String((ev as { type?: unknown }).type ?? "");
      set((s) => {
        if (type === "activity") {
          const level = String((ev as { level?: unknown }).level ?? "info");
          const color: FeedColor =
            level === "error" ? "error" : level === "done" ? "done" : "work";
          const text = escapeHtml(String((ev as { text?: unknown }).text ?? ""));
          return { events: feedInto(s.events, `🛰️ ${text}`, color) };
        }
        if (type === "approval.request") {
          const planId = String((ev as { id?: unknown }).id ?? "");
          const rawDesc = String((ev as { desc?: unknown }).desc ?? "");
          const exists = s.serverApprovals.some((a) => a.planId === planId);
          return {
            serverApprovals: exists
              ? s.serverApprovals
              : [...s.serverApprovals, { planId, desc: rawDesc }],
            events: feedInto(
              s.events,
              `⚠️ Backend minta persetujuan: <b>${escapeHtml(rawDesc)}</b>`,
              "approval",
            ),
          };
        }
        if (type === "approval.resolved") {
          const planId = String((ev as { id?: unknown }).id ?? "");
          return {
            serverApprovals: s.serverApprovals.filter((a) => a.planId !== planId),
          };
        }
        if (type === "room.snapshot") {
          const w = Number((ev as { workers?: unknown }).workers ?? 0);
          const roster = parseRosterEntries((ev as { agents?: unknown }).agents);
          const agents = roster.length ? reconcileAgents(s.agents, roster) : s.agents;
          return {
            workers: Number.isFinite(w) ? w : 0,
            live: w > 0 || s.live,
            agents,
            selectedId: keepSelected(s.selectedId, agents),
          };
        }
        if (type === "roster.updated") {
          const roster = parseRosterEntries((ev as { agents?: unknown }).agents);
          if (!roster.length) return {};
          const agents = reconcileAgents(s.agents, roster);
          return { agents, selectedId: keepSelected(s.selectedId, agents) };
        }
        if (type === "worker.online") {
          return {
            workers: s.workers + 1,
            live: true,
            events: feedInto(s.events, "🟢 Pasukan bergabung (worker online)", "done"),
          };
        }
        if (type === "worker.offline") {
          return {
            workers: Math.max(0, s.workers - 1),
            events: feedInto(s.events, "⚪ Pasukan keluar (worker offline)", "idle"),
          };
        }
        if (type === "task.card") {
          const id = String((ev as { id?: unknown }).id ?? "");
          if (!id) return {};
          const col = String((ev as { col?: unknown }).col ?? "") as BoardCol;
          const board = s.board.map((c) => ({ ...c }));
          // Kartu baru (doing) → animasikan avatar role terkait via mesin assign.
          if (col === "doing" && !board.some((c) => c.id === id)) {
            const desc = escapeHtml(String((ev as { desc?: unknown }).desc ?? ""));
            const role = String((ev as { role?: unknown }).role ?? "researcher") as Role;
            const agents = s.agents.map((a) => ({ ...a }));
            const approvals = s.approvals.map((r) => ({ ...r }));
            const queue = [...s.queue];
            const task: Task = { id, desc, role };
            const events = assign(task, agents, board, s.events, approvals, queue);
            return { live: true, agents, board, approvals, queue, events };
          }
          // Update kolom (done/todo) = kebenaran backend.
          setCol(board, id, col || "done");
          return { live: true, board };
        }
        return {};
      });
    },

    applyRoster: (roster) => {
      set((s) => {
        const agents = reconcileAgents(s.agents, roster);
        return { agents, selectedId: keepSelected(s.selectedId, agents) };
      });
    },

    approve: (id) => {
      set((s) => {
        const i = s.approvals.findIndex((r) => r.id === id);
        if (i < 0) return {};
        const approvals = [...s.approvals];
        const req = approvals.splice(i, 1)[0];
        const agents = s.agents.map((a) => ({ ...a }));
        const a = agents.find((ag) => ag.id === req.agentId);
        let events = feedInto(
          s.events,
          `👍 Kamu menyetujui: <b>${req.task.desc}</b>`,
          "done",
        );
        if (a) {
          logInto(a, "Disetujui — lanjut eksekusi");
          a.state = "to_srv";
          moveTo(a, SERVER.x + rand(-40, 40), SERVER.y + rand(-30, 30));
        }
        return { approvals, agents, events };
      });
    },

    reject: (id) => {
      set((s) => {
        const i = s.approvals.findIndex((r) => r.id === id);
        if (i < 0) return {};
        const approvals = [...s.approvals];
        const req = approvals.splice(i, 1)[0];
        const agents = s.agents.map((a) => ({ ...a }));
        const board = s.board.map((c) => ({ ...c }));
        const a = agents.find((ag) => ag.id === req.agentId);
        let events = feedInto(
          s.events,
          `🚫 Kamu menolak: <b>${req.task.desc}</b>`,
          "error",
        );
        removeCard(board, req.task.id);
        if (a) {
          logInto(a, "Ditolak — dibatalkan");
          a.task = null;
          returnHome(a);
        }
        return { approvals, agents, board, events };
      });
    },

    approveServer: (planId) => {
      void approvePlan(planId);
      set((s) => ({
        serverApprovals: s.serverApprovals.filter((a) => a.planId !== planId),
        events: feedInto(s.events, "👍 Kamu menyetujui aksi backend", "done"),
      }));
    },

    rejectServer: (planId) => {
      void rejectPlan(planId);
      set((s) => ({
        serverApprovals: s.serverApprovals.filter((a) => a.planId !== planId),
        events: feedInto(s.events, "🚫 Kamu menolak aksi backend", "error"),
      }));
    },

    startScheduler: () => {
      // ensure the DOM theme attribute matches the store on boot
      get().setTheme(get().theme);
      const handle = setInterval(() => {
        const dt = TICK;
        set((s) => {
          const agents = s.agents.map((a) => ({ ...a }));
          const board = s.board.map((c) => ({ ...c }));
          const approvals = s.approvals.map((r) => ({ ...r }));
          const queue = [...s.queue];
          let events = s.events;

          // ── manager auto-scheduler (mock) — mati begitu backend nyata live ──
          if (!s.live) {
            spawnT -= dt;
            if (spawnT <= 0) {
              spawnT = rand(4.5, 8);
              const active = agents.filter(
                (a) => a.role !== "manager" && a.state !== "idle",
              ).length;
              if (active < 4 && Math.random() < 0.85) {
                const t: Task = { ...choice(TASKS), id: ++taskSeq };
                events = assign(t, agents, board, events, approvals, queue);
              }
            }
          }

          // ── per-agent lifecycle ──
          for (const a of agents) {
            if (a.role === "manager") continue;

            if (a.travel > 0) {
              a.travel -= dt;
              if (a.travel <= 0) {
                a.travel = 0;
                a.posX = a.targetX;
                a.posY = a.targetY;
                // arrival transition
                switch (a.state) {
                  case "to_meet": {
                    a.state = "await";
                    apprSeq += 1;
                    approvals.push({
                      id: apprSeq,
                      agentId: a.id,
                      task: a.task as Task,
                      age: 0,
                    });
                    logInto(a, "Menunggu persetujuan");
                    events = feedInto(
                      events,
                      `⚠️ <b>${a.name}</b> minta persetujuan: <b>${a.task?.desc}</b>`,
                      "approval",
                    );
                    break;
                  }
                  case "to_srv":
                    startWork(a);
                    break;
                  case "to_rev":
                    a.state = "review";
                    a.workT = 0;
                    a.workDur = rand(2.5, 4);
                    a.progress = 0;
                    logInto(a, "Diperiksa reviewer");
                    break;
                  case "ret":
                    a.state = "idle";
                    a.task = null;
                    logInto(a, "Kembali standby");
                    // drain queue
                    if (queue.length) {
                      events = assign(
                        queue.shift() as Task,
                        agents,
                        board,
                        events,
                        approvals,
                        queue,
                      );
                    }
                    break;
                  default:
                    break;
                }
              }
            }

            // ── work / review progress ──
            if (a.state === "working" || a.state === "review") {
              a.workT += dt;
              a.progress = clamp(a.workT / a.workDur, 0, 1);
              if (a.workT >= a.workDur) {
                if (a.state === "working") {
                  logInto(a, "Eksekusi selesai");
                  events = feedInto(
                    events,
                    `✅ <b>${a.name}</b> menyelesaikan “${a.task?.desc}”`,
                    "done",
                  );
                  if (a.task?.review) {
                    setCol(board, a.task.id, "review");
                    a.state = "to_rev";
                    moveTo(a, REVIEW.x + rand(-40, 40), REVIEW.y + rand(-24, 24));
                  } else {
                    if (a.task) setCol(board, a.task.id, "done");
                    returnHome(a);
                  }
                } else {
                  if (a.task) setCol(board, a.task.id, "done");
                  events = feedInto(
                    events,
                    `✅ <b>${a.name}</b> lolos review “${a.task?.desc}”`,
                    "done",
                  );
                  returnHome(a);
                }
              }
            }
          }

          // ── auto-resolve stale approvals (demo keeps flowing) ──
          for (const r of approvals) {
            r.age += dt;
          }
          const stale = approvals.find((r) => r.age > 14);

          // ── board: fade & sweep done cards ──
          for (let i = board.length - 1; i >= 0; i--) {
            if (board[i].col === "done") {
              board[i].doneT += dt;
              if (board[i].doneT > 6) board.splice(i, 1);
            }
          }

          const partial: Partial<RoomState> = {
            agents,
            board,
            approvals,
            queue,
            events,
          };
          // trigger auto-approve after committing this tick's state
          if (stale) {
            queueMicrotask(() => {
              const cur = get();
              if (cur.approvals.some((r) => r.id === stale.id)) {
                set((s2) => ({
                  events: feedInto(
                    s2.events,
                    `⏱️ Persetujuan “${stale.task.desc}” otomatis (timeout demo)`,
                    "approval",
                  ),
                }));
                cur.approve(stale.id);
              }
            });
          }
          return partial;
        });
      }, TICK * 1000);
      return () => clearInterval(handle);
    },
  };
});
