import type { IncomingEvent } from "./types";
import type { AvatarEvent } from "../avatar/types";

type GoApp = {
  SendChat(msgId: string, text: string): Promise<void>;
  ApprovePlan(msgId: string, planId: string): Promise<void>;
  RejectPlan(planId: string): Promise<boolean>;
  Transcribe(wavB64: string): Promise<string>;
  Speak(text: string): Promise<string>;
  DownloadAssets(): Promise<void>;
  BinaryStatus(): Promise<Record<string, string>>;
  GetSettings(): Promise<Record<string, unknown>>;
  SaveSettings(s: Record<string, unknown>): Promise<void>;
  IsLoggedIn(): Promise<boolean>;
  Logout(): Promise<void>;
  StartLogin(): Promise<Record<string, unknown>>;
  PollLogin(code: string): Promise<string>;
  GetProvider(): Promise<Record<string, any>>;
  SetProvider(provider: string, model: string): Promise<void>;
  GetAgents(): Promise<Record<string, any>>;
  ToggleAgent(agentId: string, enabled: boolean): Promise<void>;
  GetPersonalKey(): Promise<string>;
  SavePersonalKey(key: string): Promise<void>;
  DeletePersonalKey(): Promise<void>;
};

declare global {
  interface Window {
    go: { main: { App: GoApp } };
    runtime: {
      EventsOn(name: string, cb: (payload: unknown) => void): () => void;
    };
  }
}

export const sendChat = (msgId: string, text: string) => window.go.main.App.SendChat(msgId, text);
export const approvePlan = (msgId: string, planId: string) => window.go.main.App.ApprovePlan(msgId, planId);
export const rejectPlan = (planId: string) => window.go.main.App.RejectPlan(planId);

// Di luar Wails (vite dev di browser) runtime tidak ada — degradasi jadi no-op
// supaya UI tetap bisa dirender dan diperiksa visual.
export function onChatEvent(cb: (ev: IncomingEvent) => void): () => void {
  if (!window.runtime?.EventsOn) return () => {};
  return window.runtime.EventsOn("chat:event", (payload) => cb(payload as IncomingEvent));
}

export function onAvatarEvent(cb: (ev: AvatarEvent) => void): () => void {
  if (!window.runtime?.EventsOn) return () => {};
  return window.runtime.EventsOn("avatar:event", (payload) => cb(payload as AvatarEvent));
}
