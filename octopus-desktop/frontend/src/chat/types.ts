export type ChatEventPayload = Record<string, unknown>;

export interface IncomingEvent {
  msgId: string;
  type: string; // thinking|intent_classified|approval_required|action_started|action_result|text_chunk|final|error|observing|reflecting|retrying|stream_error
  data: ChatEventPayload;
}

export type Part =
  | { kind: "status"; text: string }
  | { kind: "text"; text: string; streaming: boolean }
  | { kind: "action"; action: string; running: boolean; output: string }
  | { kind: "approval"; planId: string; summary: string; decided: "" | "approved" | "rejected" }
  | { kind: "error"; message: string; retryable: boolean };

export interface AssistantMessage {
  msgId: string;
  role: "assistant";
  parts: Part[];
  done: boolean;
  finalText: string; // untuk TTS
}

export interface UserMessage {
  msgId: string;
  role: "user";
  text: string;
}

export type Message = UserMessage | AssistantMessage;
