import type { AssistantMessage, IncomingEvent, Message, Part } from "./types";

const STATUS_TYPES = new Set(["thinking", "observing", "reflecting", "retrying"]);

function withoutStatus(parts: Part[]): Part[] {
  return parts.filter((p) => p.kind !== "status");
}

function updateAssistant(msg: AssistantMessage, ev: IncomingEvent): AssistantMessage {
  const d = ev.data;
  if (STATUS_TYPES.has(ev.type)) {
    return { ...msg, parts: [...withoutStatus(msg.parts), { kind: "status", text: String(d.message ?? "") }] };
  }
  switch (ev.type) {
    case "intent_classified":
      return {
        ...msg,
        parts: [
          ...withoutStatus(msg.parts),
          { kind: "status", text: `intent: ${d.intent} (${d.confidence})` },
        ],
      };
    case "text_chunk": {
      const parts = [...msg.parts];
      const lastPart = parts[parts.length - 1];
      if (lastPart?.kind === "text" && lastPart.streaming) {
        parts[parts.length - 1] = { ...lastPart, text: lastPart.text + String(d.text ?? "") };
      } else {
        parts.push({ kind: "text", text: String(d.text ?? ""), streaming: true });
      }
      return { ...msg, parts };
    }
    case "action_started":
      return {
        ...msg,
        parts: [...msg.parts, { kind: "action", action: String(d.action ?? ""), running: true, output: "" }],
      };
    case "action_result":
      return {
        ...msg,
        parts: msg.parts.map((p) =>
          p.kind === "action" && p.action === d.action && p.running
            ? { ...p, running: false, output: String(d.output ?? "") }
            : p,
        ),
      };
    case "approval_required":
      return {
        ...msg,
        parts: [
          ...msg.parts,
          { kind: "approval", planId: String(d.plan_id ?? ""), summary: String(d.summary ?? ""), decided: "" },
        ],
      };
    case "final": {
      const finalText = String(d.text ?? "");
      let parts = withoutStatus(msg.parts).map((p) =>
        p.kind === "text" ? { ...p, streaming: false } : p,
      );
      if (!parts.some((p) => p.kind === "text" || p.kind === "action")) {
        parts = [...parts, { kind: "text", text: finalText, streaming: false }];
      }
      return { ...msg, parts, done: true, finalText };
    }
    case "error":
      return {
        ...msg,
        parts: [...withoutStatus(msg.parts), { kind: "error", message: String(d.message ?? ""), retryable: false }],
        done: true,
      };
    case "stream_error":
      return {
        ...msg,
        parts: [...withoutStatus(msg.parts), { kind: "error", message: String(d.message ?? ""), retryable: true }],
        done: true,
      };
    default:
      return msg;
  }
}

export function applyEvent(messages: Message[], ev: IncomingEvent): Message[] {
  const idx = messages.findIndex((m) => m.msgId === ev.msgId && m.role === "assistant");
  if (idx === -1) {
    const fresh: AssistantMessage = { msgId: ev.msgId, role: "assistant", parts: [], done: false, finalText: "" };
    return [...messages, updateAssistant(fresh, ev)];
  }
  const next = [...messages];
  next[idx] = updateAssistant(next[idx] as AssistantMessage, ev);
  return next;
}
