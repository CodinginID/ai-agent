import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatView } from "./ChatView";
import type { IncomingEvent } from "./types";

let chatEventCb: ((ev: IncomingEvent) => void) | null = null;

beforeEach(() => {
  chatEventCb = null;
  (window as any).go = {
    main: {
      App: {
        SendChat: vi.fn().mockResolvedValue(undefined),
        ApprovePlan: vi.fn().mockResolvedValue(undefined),
        RejectPlan: vi.fn().mockResolvedValue(true),
      },
    },
  };
  (window as any).runtime = {
    EventsOn: vi.fn((_name: string, cb: (payload: unknown) => void) => {
      chatEventCb = cb as (ev: IncomingEvent) => void;
      return () => {};
    }),
  };
});

describe("ChatView onPendingChange", () => {
  it("melaporkan pending=true saat submit, false saat pesan assistant selesai", () => {
    const onPendingChange = vi.fn();
    render(<ChatView onPendingChange={onPendingChange} />);

    const input = screen.getByPlaceholderText(/ketik perintah/i);
    fireEvent.change(input, { target: { value: "halo" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onPendingChange).toHaveBeenCalledWith(true);

    act(() => {
      chatEventCb?.({ msgId: "m-1", type: "final", data: { text: "Halo juga" } });
    });

    expect(onPendingChange).toHaveBeenLastCalledWith(false);
  });
});
