import type { AgentState, BoardCol, Role } from "../../state/types";

export const WORLD_W = 1280;
export const WORLD_H = 800;

/** constant walking speed shared by the mock scheduler and the renderer,
 *  so logical arrival (store) and visual arrival (canvas) stay in sync */
export const AGENT_SPEED = 150;

export interface Zone {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export const ZONES: Zone[] = [
  { name: "Kantor Manajer", x: 500, y: 34, w: 280, h: 150 },
  { name: "Riset", x: 34, y: 34, w: 210, h: 150 },
  { name: "Dev Bay", x: 34, y: 214, w: 300, h: 250 },
  { name: "QA Corner", x: 34, y: 494, w: 300, h: 272 },
  { name: "Ruang Review", x: 366, y: 560, w: 300, h: 206 },
  { name: "Meja Rapat", x: 520, y: 300, w: 240, h: 170 },
  { name: "Deploy Station", x: 1010, y: 214, w: 236, h: 220 },
  { name: "Server Room", x: 1010, y: 464, w: 236, h: 302 },
];

export const zoneBy = (name: string): Zone => {
  const z = ZONES.find((zo) => zo.name === name);
  if (!z) throw new Error(`unknown zone: ${name}`);
  return z;
};

export const center = (z: Zone): { x: number; y: number } => ({
  x: z.x + z.w / 2,
  y: z.y + z.h / 2,
});

export const MEET = center(zoneBy("Meja Rapat"));
export const SERVER = center(zoneBy("Server Room"));
export const REVIEW = center(zoneBy("Ruang Review"));

export interface RoleDef {
  label: string;
  color: string;
  icon: string;
}

export const ROLE: Record<Role, RoleDef> = {
  manager: { label: "Manajer IT", color: "#f5a623", icon: "🧭" },
  coder: { label: "Coder", color: "#23c4a8", icon: "💻" },
  tester: { label: "Tester QA", color: "#9b7bff", icon: "🧪" },
  reviewer: { label: "Reviewer", color: "#4aa3ff", icon: "🔍" },
  deployer: { label: "Ops/Deploy", color: "#ff7a59", icon: "🚀" },
  researcher: { label: "Peneliti", color: "#4fc56b", icon: "📡" },
};

export interface StatusDef {
  txt: string;
  /** palette key -> maps to a --st-* CSS variable */
  c: "idle" | "work" | "approval" | "review" | "done" | "error";
}

export const STATUS: Record<AgentState, StatusDef> = {
  idle: { txt: "Menganggur", c: "idle" },
  to_srv: { txt: "Menuju server", c: "work" },
  working: { txt: "Bekerja", c: "work" },
  to_meet: { txt: "Menuju rapat", c: "approval" },
  await: { txt: "Menunggu approval", c: "approval" },
  to_rev: { txt: "Menuju review", c: "review" },
  review: { txt: "Direview", c: "review" },
  ret: { txt: "Kembali", c: "idle" },
  patrol: { txt: "Mengkoordinasi", c: "work" },
};

export const cssVar = (c: StatusDef["c"]): string => `var(--st-${c})`;

export const BOARD_COLS: { k: BoardCol; t: string }[] = [
  { k: "todo", t: "Antre" },
  { k: "doing", t: "Dikerjakan" },
  { k: "review", t: "Review" },
  { k: "done", t: "Selesai" },
];
