export type AvatarEventType =
  | "worker:started"
  | "worker:progress"
  | "worker:completed"
  | "worker:error";

export interface AvatarEvent {
  type: AvatarEventType;
  workerId: string;
  workerName: string;
  workerType: string;
  progress?: number;
  error?: string;
}

export type AvatarWorkerState = "idle" | "working" | "error";

export interface WorkerAvatar {
  id: string;
  name: string;
  type: string;
  color: string;
  state: AvatarWorkerState;
  task?: string;
}
