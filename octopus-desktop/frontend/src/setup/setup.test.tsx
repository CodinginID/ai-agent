import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginView } from "./LoginView";

beforeEach(() => {
  (window as any).go = {
    main: {
      App: {
        StartLogin: vi.fn().mockResolvedValue({ code: "ABCD", login_url: "https://x" }),
        PollLogin: vi.fn().mockResolvedValueOnce("pending").mockResolvedValueOnce("paired"),
      },
    },
  };
});

describe("LoginView", () => {
  it("menampilkan kode setelah start dan memanggil onPaired saat paired", async () => {
    const onPaired = vi.fn();
    render(<LoginView onPaired={onPaired} pollIntervalMs={1} />);
    fireEvent.click(screen.getByRole("button", { name: /connect/i }));
    await waitFor(() => expect(screen.getByText("ABCD")).toBeTruthy());
    await waitFor(() => expect(onPaired).toHaveBeenCalled(), { timeout: 2000 });
  });
});
