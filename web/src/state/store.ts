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
  SERVER,
  WORLD_H,
  WORLD_W,
  zoneBy,
} from "../room/engine/scene";

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
  name: string,
  role: Role,
  x: number,
  y: number,
  state: Agent["state"] = "idle",
): Agent {
  return {
    id: name.toLowerCase(),
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

function initialAgents(): Agent[] {
  const devBay = zoneBy("Dev Bay");
  const qa = zoneBy("QA Corner");
  const rev = zoneBy("Ruang Review");
  const deploy = zoneBy("Deploy Station");
  const research = zoneBy("Riset");
  const mgr = center(zoneBy("Kantor Manajer"));
  return [
    mk("Octo", "manager", mgr.x, mgr.y + 8, "patrol"),
    mk("Nadia", "coder", devBay.x + 80, devBay.y + 95),
    mk("Bima", "coder", devBay.x + 210, devBay.y + 150),
    mk("Sari", "tester", qa.x + 90, qa.y + 110),
    mk("Rangga", "reviewer", rev.x + 95, rev.y + 95),
    mk("Dewi", "deployer", deploy.x + 118, deploy.y + 110),
    mk("Yusuf", "researcher", research.x + 105, research.y + 90),
  ];
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

  // actions
  select: (id: string | null) => void;
  submitCommand: (text: string) => void;
  applyServerEvent: (ev: Record<string, unknown>) => void;
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
  const setCol = (board: BoardCard[], id: number, col: BoardCol): void => {
    const c = board.find((bc) => bc.id === id);
    if (c) {
      c.col = col;
      if (col === "done") c.doneT = 0;
    }
  };
  const removeCard = (board: BoardCard[], id: number): void => {
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
      const risky =
        /(restart|deploy|hapus|reboot|rotasi|kredensial|drop|matikan|down)/i.test(
          txt,
        );
      const review = /(perbaiki|fix|refactor|tulis|buat|implement|kode|optimasi)/i.test(
        txt,
      );
      let role: Role = "coder";
      if (/(deploy|restart|backup|kredensial|reboot)/i.test(txt)) role = "deployer";
      else if (/(test|uji|scan)/i.test(txt)) role = "tester";
      else if (/(review|periksa)/i.test(txt)) role = "reviewer";
      else if (/(cek|audit|analisa|riset|profil|disk|log)/i.test(txt))
        role = "researcher";

      // Kirim ke Manajer IT nyata (TaskRunner): PM pecah tugas → dispatch
      // per-role ke pasukan. Progres live via /room/stream; hasil akhir → feed.
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
      const safe = escapeHtml(txt);
      set((s) => {
        const agents = s.agents.map((a) => ({ ...a }));
        const board = s.board.map((c) => ({ ...c }));
        const queue = [...s.queue];
        const approvals = s.approvals;
        let events = feedInto(
          s.events,
          `📩 <b>${MANAGER}</b> menerima perintahmu: “${safe}”`,
          "work",
        );
        const task: Task = { id: ++taskSeq, desc: safe, role, risky, review };
        events = assign(task, agents, board, events, approvals, queue);
        return { agents, board, queue, events };
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
        return {};
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

          // ── manager auto-scheduler ──
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
