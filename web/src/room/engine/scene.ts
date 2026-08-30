import type { AgentState, BoardCol, Role } from "../../state/types";

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

export type LayoutKind = "landscape" | "portrait";

interface SceneLayout {
  kind: LayoutKind;
  worldW: number;
  worldH: number;
  zones: Zone[];
  /** role -> home zone name, for this layout */
  roleZone: Record<Role, string>;
  meetZone: string;
  reviewZone: string;
  serverZone: string;
}

// ── landscape (desktop) world — unchanged from the original single-layout
// scene, kept byte-for-byte so desktop visuals never move. ──
const LANDSCAPE_ZONES: Zone[] = [
  { name: "Kantor Manajer", x: 500, y: 34, w: 280, h: 150 },
  { name: "Riset", x: 34, y: 34, w: 210, h: 150 },
  { name: "Dev Bay", x: 34, y: 214, w: 300, h: 250 },
  { name: "QA Corner", x: 34, y: 494, w: 300, h: 272 },
  { name: "Ruang Review", x: 366, y: 560, w: 300, h: 206 },
  { name: "Meja Rapat", x: 520, y: 300, w: 240, h: 170 },
  { name: "Deploy Station", x: 1010, y: 214, w: 236, h: 220 },
  { name: "Server Room", x: 1010, y: 464, w: 236, h: 302 },
];

const LANDSCAPE: SceneLayout = {
  kind: "landscape",
  worldW: 1280,
  worldH: 800,
  zones: LANDSCAPE_ZONES,
  roleZone: {
    manager: "Kantor Manajer",
    coder: "Dev Bay",
    tester: "QA Corner",
    reviewer: "Ruang Review",
    deployer: "Deploy Station",
    researcher: "Riset",
  },
  meetZone: "Meja Rapat",
  reviewZone: "Ruang Review",
  serverZone: "Server Room",
};

// ── portrait (mobile "Ruangan" tab) world — 390×560 CSS-px room, matching
// the approved mockup grid (2 columns, 16px margins, ~18px gutters). ──
const PORTRAIT_ZONES: Zone[] = [
  { name: "Meja Manajer", x: 16, y: 18, w: 170, h: 150 },
  { name: "Ruang Review", x: 204, y: 18, w: 170, h: 150 },
  { name: "Area Kerja", x: 16, y: 190, w: 358, h: 190 },
  { name: "Server", x: 16, y: 402, w: 170, h: 130 },
  { name: "Meeting", x: 204, y: 402, w: 170, h: 130 },
];

const PORTRAIT: SceneLayout = {
  kind: "portrait",
  worldW: 390,
  worldH: 560,
  zones: PORTRAIT_ZONES,
  roleZone: {
    manager: "Meja Manajer",
    coder: "Area Kerja",
    tester: "Area Kerja",
    reviewer: "Ruang Review",
    deployer: "Server",
    researcher: "Area Kerja",
  },
  meetZone: "Meeting",
  reviewZone: "Ruang Review",
  serverZone: "Server",
};

let active: SceneLayout = LANDSCAPE;

/** Switch the scene the engine/store operate on. No-op safe to call every
 *  render — callers should still guard redundant calls themselves. */
export function setSceneLayout(kind: LayoutKind): void {
  active = kind === "portrait" ? PORTRAIT : LANDSCAPE;
}

export function getLayout(): { kind: LayoutKind; worldW: number; worldH: number; zones: Zone[] } {
  return active;
}

export const zoneBy = (name: string): Zone => {
  const z = active.zones.find((zo) => zo.name === name);
  if (!z) throw new Error(`unknown zone: ${name}`);
  return z;
};

export const center = (z: Zone): { x: number; y: number } => ({
  x: z.x + z.w / 2,
  y: z.y + z.h / 2,
});

/** Home zone for a role in the *active* layout. */
export const homeZoneFor = (role: Role): Zone => zoneBy(active.roleZone[role]);

export const meetPoint = (): { x: number; y: number } => center(zoneBy(active.meetZone));
export const reviewPoint = (): { x: number; y: number } => center(zoneBy(active.reviewZone));
export const serverPoint = (): { x: number; y: number } => center(zoneBy(active.serverZone));

/** true for the one zone that gets the animated server-rack drawing —
 *  landscape only; the portrait "Server" card stays a plain zone (mockup). */
export const isRackZone = (z: Zone): boolean =>
  active.kind === "landscape" && z.name === active.serverZone;

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
