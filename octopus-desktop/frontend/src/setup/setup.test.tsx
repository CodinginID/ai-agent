import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginView } from "./LoginView";
import { SettingsView } from "./SettingsView";

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
    fireEvent.click(screen.getByRole("button", { name: /hubungkan/i }));
    await waitFor(() => expect(screen.getByText("ABCD")).toBeTruthy());
    await waitFor(() => expect(onPaired).toHaveBeenCalled(), { timeout: 2000 });
  });
});

describe("SettingsView binary status", () => {
  const mockApp = (bins: Record<string, string>) => {
    (window as any).go = {
      main: {
        App: {
          GetSettings: vi.fn().mockResolvedValue({ jarvis_mode: true, tts_enabled: true }),
          GetPersonalKey: vi.fn().mockResolvedValue(""),
          GetProvider: vi.fn().mockResolvedValue({}),
          GetAgents: vi.fn().mockResolvedValue({ agents: [] }),
          BinaryStatus: vi.fn().mockResolvedValue(bins),
          DownloadAssets: vi.fn().mockResolvedValue(undefined),
        },
      },
    };
    (window as any).runtime = { EventsOn: vi.fn().mockReturnValue(() => {}) };
  };

  it("menampilkan hint brew saat whisper tidak ditemukan dan path saat piper ada", async () => {
    mockApp({ whisper: "", piper: "/x/bin/piper/piper" });
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    await waitFor(() => expect(screen.getByText(/brew install whisper-cpp/i)).toBeTruthy());
    expect(screen.getByText(/\/x\/bin\/piper\/piper/)).toBeTruthy();
  });

  it("menampilkan fallback say saat piper tidak ada tapi say tersedia", async () => {
    mockApp({ whisper: "/opt/homebrew/bin/whisper-cli", piper: "", say: "/usr/bin/say" });
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    await waitFor(() => expect(screen.getByText(/say/)).toBeTruthy());
    expect(screen.queryByText(/piper tidak ditemukan|piper not found/i)).toBeNull();
  });

  it("refresh status binary setelah unduh aset", async () => {
    mockApp({ whisper: "", piper: "" });
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    const app = (window as any).go.main.App;
    await waitFor(() => expect(app.BinaryStatus).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: /unduh|download/i }));
    await waitFor(() => expect(app.DownloadAssets).toHaveBeenCalled());
    await waitFor(() => expect(app.BinaryStatus).toHaveBeenCalledTimes(2));
  });
});
