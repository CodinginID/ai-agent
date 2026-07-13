import { describe, expect, it } from "vitest";
import { applyEvent } from "./reducer";
import type { AssistantMessage, Message } from "./types";

const ev = (type: string, data: Record<string, unknown> = {}, msgId = "m1") => ({
  msgId,
  type,
  data,
});

const last = (msgs: Message[]) => msgs[msgs.length - 1] as AssistantMessage;

describe("applyEvent", () => {
  it("membuat assistant message baru untuk msgId baru", () => {
    const out = applyEvent([], ev("thinking", { message: "mikir" }));
    expect(out).toHaveLength(1);
    expect(last(out).parts).toEqual([{ kind: "status", text: "mikir" }]);
  });

  it("mengganti status, bukan menumpuk", () => {
    let msgs = applyEvent([], ev("thinking", { message: "a" }));
    msgs = applyEvent(msgs, ev("observing", { message: "b" }));
    const statuses = last(msgs).parts.filter((p) => p.kind === "status");
    expect(statuses).toEqual([{ kind: "status", text: "b" }]);
  });

  it("menggabungkan text_chunk menjadi satu part streaming", () => {
    let msgs = applyEvent([], ev("text_chunk", { text: "Ha" }));
    msgs = applyEvent(msgs, ev("text_chunk", { text: "lo" }));
    expect(last(msgs).parts).toContainEqual({ kind: "text", text: "Halo", streaming: true });
  });

  it("action_started lalu action_result mengisi output", () => {
    let msgs = applyEvent([], ev("action_started", { action: "memory" }));
    msgs = applyEvent(msgs, ev("action_result", { action: "memory", output: "RAM 60%" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "action",
      action: "memory",
      running: false,
      output: "RAM 60%",
    });
  });

  it("approval_required menghasilkan part approval", () => {
    const msgs = applyEvent([], ev("approval_required", { plan_id: "p1", summary: "restart web" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "approval",
      planId: "p1",
      summary: "restart web",
      decided: "",
    });
  });

  it("final menutup pesan dan menyimpan finalText", () => {
    let msgs = applyEvent([], ev("thinking", { message: "mikir" }));
    msgs = applyEvent(msgs, ev("final", { text: "beres" }));
    const m = last(msgs);
    expect(m.done).toBe(true);
    expect(m.finalText).toBe("beres");
    expect(m.parts.some((p) => p.kind === "status")).toBe(false);
  });

  it("stream_error menghasilkan error retryable", () => {
    const msgs = applyEvent([], ev("stream_error", { message: "putus" }));
    expect(last(msgs).parts).toContainEqual({
      kind: "error",
      message: "putus",
      retryable: true,
    });
    expect(last(msgs).done).toBe(true);
  });
});
