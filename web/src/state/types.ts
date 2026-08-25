export type Role =
  | "manager"
  | "coder"
  | "tester"
  | "reviewer"
  | "deployer"
  | "researcher";

export type AgentState =
  | "idle"
  | "to_srv"
  | "working"
  | "to_meet"
  | "await"
  | "to_rev"
  | "review"
  | "ret"
  | "patrol";

export interface LogEntry {
  t: string;
  msg: string;
}

export interface Task {
  id: number;
  desc: string;
  role: Role;
  risky?: boolean;
  review?: boolean;
}

export interface Agent {
  id: string;
  name: string;
  role: Role;
  state: AgentState;
  task: Task | null;
  progress: number;
  logs: LogEntry[];
  /** home / anchor slot in world coordinates */
  homeX: number;
  homeY: number;
  /** logical anchor the engine lerps the render position toward */
  targetX: number;
  targetY: number;
  /** last settled logical position (used to size travel time) */
  posX: number;
  posY: number;
  /** seconds remaining until the agent reaches targetX/targetY */
  travel: number;
  /** elapsed / total work duration for working & review states */
  workT: number;
  workDur: number;
}

export interface Approval {
  id: number;
  agentId: string;
  task: Task;
  /** seconds since the request was raised */
  age: number;
}

/** Approval nyata dari backend (via /room/stream) — plan_id string + deskripsi. */
export interface ServerApproval {
  planId: string;
  desc: string;
}

export type FeedColor =
  | "idle"
  | "work"
  | "approval"
  | "review"
  | "done"
  | "error";

export interface RoomEvent {
  id: number;
  t: string;
  msg: string;
  color: FeedColor;
}

export type BoardCol = "todo" | "doing" | "review" | "done";

export interface BoardCard {
  id: number;
  desc: string;
  role: Role;
  col: BoardCol;
  doneT: number;
}

export type Theme = "light" | "dark";
