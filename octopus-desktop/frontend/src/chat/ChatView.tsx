import { forwardRef, useEffect, useRef, useState } from "react";
import { approvePlan, onAvatarEvent, onChatEvent, rejectPlan, sendChat } from "./bindings";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message, Part } from "./types";
import { ActionCard } from "./cards/ActionCard";
import { ApprovalCard } from "./cards/ApprovalCard";
import { ErrorCard } from "./cards/ErrorCard";
import { MetricCard } from "./cards/MetricCard";
import { StatusLine } from "./cards/StatusLine";
import { TableCard } from "./cards/TableCard";
import { TextCard } from "./cards/TextCard";
import { UserBubble } from "./UserBubble";
import { AvatarSystem } from "../avatar/AvatarSystem";
import { usePointerTilt } from "../hooks/usePointerTilt";
import { useI18n } from "../i18n/useI18n";

const METRIC_ACTIONS = new Set(["memory", "disk", "server_status", "docker_stats"]);
const TABLE_ACTIONS = new Set(["docker_ps", "docker_images", "docker_compose_ps", "processes"]);

let counter = 0;
const newMsgId = () => `m-${Date.now()}-${counter++}`;

interface ChatViewProps {
  onFinal?: (text: string) => void;
  onPendingChange?: (pending: boolean) => void;
  inputExtra?: React.ReactNode;
  registerSubmit?: (fn: (text: string) => void) => void;
  onRetry?: (text: string) => void;
}

export const ChatView = forwardRef<HTMLInputElement, ChatViewProps>(({
  onFinal,
  onPendingChange,
  inputExtra,
  registerSubmit,
  onRetry,
}, inputRef) => {
  const { t } = useI18n();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const lastFinal = useRef("");
  const sendButtonRef = usePointerTilt<HTMLButtonElement>();
  const messagesRef = useRef<HTMLDivElement>(null);

  // Auto-scroll ke bawah setiap kali pesan berubah
  useEffect(() => {
    const el = messagesRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [messages.length]);

  useEffect(() => {
    return onChatEvent((ev) => setMessages((prev) => applyEvent(prev, ev)));
  }, []);

  useEffect(() => {
    return onAvatarEvent(() => {}); // Subscribe to avatar events (AvatarSystem handles them)
  }, []);

  useEffect(() => {
    registerSubmit?.(submit);
  }, [registerSubmit]);

  useEffect(() => {
    const handleVoiceDraft = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      setDraft(customEvent.detail);
    };
    window.addEventListener("voice:draft", handleVoiceDraft);
    return () => window.removeEventListener("voice:draft", handleVoiceDraft);
  }, []);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.done && lastMsg.finalText && lastMsg.finalText !== lastFinal.current) {
      lastFinal.current = lastMsg.finalText;
      onFinal?.(lastMsg.finalText);
    }
  }, [messages, onFinal]);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.done) {
      onPendingChange?.(false);
    }
  }, [messages, onPendingChange]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const msgId = newMsgId();
    setMessages((prev) => [...prev, { msgId: `u-${msgId}`, role: "user", text: trimmed }]);
    onPendingChange?.(true);
    void sendChat(msgId, trimmed);
    setDraft("");
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

  const retryLastError = () => {
    const last = messages[messages.length - 1] as AssistantMessage | undefined;
    if (!last || !last.done) return;
    const lastTextPart = last.parts.find((p) => p.kind === "text");
    if (lastTextPart) {
      onRetry?.(lastTextPart.text);
    }
  };

  const renderPart = (msg: AssistantMessage, p: Part, i: number) => {
    switch (p.kind) {
      case "status":
        return <StatusLine key={i} text={p.text} />;
      case "text":
        return <TextCard key={i} text={p.text} streaming={p.streaming} />;
      case "action":
        if (!p.running && METRIC_ACTIONS.has(p.action))
          return <MetricCard key={i} action={p.action} output={p.output} />;
        if (!p.running && TABLE_ACTIONS.has(p.action))
          return <TableCard key={i} action={p.action} output={p.output} />;
        return <ActionCard key={i} action={p.action} running={p.running} output={p.output} />;
      case "approval":
        return (
          <ApprovalCard
            key={i}
            planId={p.planId}
            summary={p.summary}
            decided={p.decided}
            onApprove={(id) => decide(msg, id, "approved")}
            onReject={(id) => decide(msg, id, "rejected")}
          />
        );
      case "error":
        return (
          <ErrorCard
            key={i}
            message={p.message}
            retryable={p.retryable}
            onRetry={retryLastError}
          />
        );
    }
  };

  return (
    <div className="chat-view">
      <div
        ref={messagesRef}
        className="chat-messages"
        role="log"
        aria-label={t("chat_messages_aria")}
        aria-live="polite"
      >
        {messages.map((m) =>
          m.role === "user" ? (
            <UserBubble key={m.msgId} text={m.text} />
          ) : (
            <div key={m.msgId} className="msg-assistant">
              {m.parts.map((p, i) => renderPart(m, p, i))}
            </div>
          ),
        )}
      </div>
      <AvatarSystem />
      <div className="chat-input">
        {inputExtra}
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(draft)}
          placeholder={t("chat_input_placeholder")}
          aria-label={t("chat_write_aria")}
        />
        <button
          ref={sendButtonRef}
          className="tilt-surface"
          onClick={() => submit(draft)}
          aria-label={t("chat_send_aria")}
        >
          {t("chat_send")}
        </button>
      </div>
    </div>
  );
});
