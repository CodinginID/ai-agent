import { useEffect, useRef, useState } from "react";
import { approvePlan, onChatEvent, rejectPlan, sendChat } from "./bindings";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message } from "./types";

let counter = 0;
const newMsgId = () => `m-${Date.now()}-${counter++}`;

export interface UseChat {
  messages: Message[];
  current?: AssistantMessage; // giliran assistant terbaru
  pending: boolean;
  submit: (text: string) => void;
  decide: (msg: AssistantMessage, planId: string, decision: "approved" | "rejected") => void;
  retryLast: (onRetry?: (text: string) => void) => void;
}

// Logika chat bersama: langganan event gateway, kirim pesan, approve/reject,
// retry. Dipakai layout orb-centric maupun chat-log lama.
export function useChat(): UseChat {
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);

  useEffect(() => onChatEvent((ev) => setMessages((prev) => applyEvent(prev, ev))), []);

  const last = messages[messages.length - 1];
  const current = last?.role === "assistant" ? last : undefined;

  const doneRef = useRef<string>("");
  useEffect(() => {
    if (current?.done && current.msgId !== doneRef.current) {
      doneRef.current = current.msgId;
      setPending(false);
    }
  }, [current?.done, current?.msgId]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const msgId = newMsgId();
    setMessages((prev) => [...prev, { msgId: `u-${msgId}`, role: "user", text: trimmed }]);
    setPending(true);
    void sendChat(msgId, trimmed);
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

  const retryLast = (onRetry?: (text: string) => void) => {
    if (!current?.done) return;
    const lastTextPart = current.parts.find((p) => p.kind === "text");
    if (lastTextPart && lastTextPart.kind === "text") onRetry?.(lastTextPart.text);
  };

  return { messages, current, pending, submit, decide, retryLast };
}
