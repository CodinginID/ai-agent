import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsView } from "./SettingsView";

const mockApp = () => ({
  GetSettings: vi.fn().mockResolvedValue({ gateway_url: "http://x", jarvis_mode: true, language: "id" }),
  SaveSettings: vi.fn().mockResolvedValue(undefined),
  GetPersonalKey: vi.fn().mockResolvedValue(""),
  SavePersonalKey: vi.fn().mockResolvedValue(undefined),
  DeletePersonalKey: vi.fn().mockResolvedValue(undefined),
  GetProvider: vi.fn().mockResolvedValue({ provider: "ollama", model: "qwen2.5:14b" }),
  SetProvider: vi.fn().mockResolvedValue(undefined),
  GetAgents: vi.fn().mockResolvedValue({ agents: [] }),
  ToggleAgent: vi.fn().mockResolvedValue(undefined),
  DownloadAssets: vi.fn().mockResolvedValue(undefined),
});

let app: ReturnType<typeof mockApp>;

beforeEach(() => {
  app = mockApp();
  (window as any).go = { main: { App: app } };
  (window as any).runtime = { EventsOn: vi.fn().mockReturnValue(() => {}) };
});

const openProviderTab = async () => {
  fireEvent.click(screen.getByRole("button", { name: /AI Provider/ }));
  await waitFor(() => expect(screen.getByRole("radiogroup")).toBeTruthy());
};

describe("SettingsView tab provider", () => {
  it("menampilkan kartu ollama & anthropic dengan radio, tanpa judul dobel", async () => {
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    await openProviderTab();
    expect(screen.getByText("Ollama")).toBeTruthy();
    expect(screen.getByText("Anthropic Claude")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
  });

  it("memilih anthropic memunculkan toggle api key personal, ollama menyembunyikannya", async () => {
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    await openProviderTab();
    expect(screen.queryByText(/kunci api saya sendiri/i)).toBeNull();
    fireEvent.click(screen.getByText("Anthropic Claude"));
    expect(screen.getByText(/kunci api saya sendiri/i)).toBeTruthy();
    fireEvent.click(screen.getByText("Ollama"));
    expect(screen.queryByText(/kunci api saya sendiri/i)).toBeNull();
  });
});

describe("SettingsView feedback simpan", () => {
  it("perubahan menandai belum-disimpan, simpan memanggil backend dan kembali tersimpan tanpa menutup modal", async () => {
    const onClose = vi.fn();
    render(<SettingsView onClose={onClose} onLogout={() => {}} />);
    await waitFor(() => expect(app.GetSettings).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText("http://localhost:8080"), {
      target: { value: "http://baru:9090" },
    });
    expect(screen.getByText("Belum disimpan")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Simpan" }));
    await waitFor(() => expect(app.SaveSettings).toHaveBeenCalled());
    expect(app.SetProvider).toHaveBeenCalledWith("ollama", "qwen2.5:14b");
    await waitFor(() => expect(screen.getAllByText("Tersimpan").length).toBeGreaterThan(0));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("kegagalan simpan tampil sebagai error inline, bukan alert", async () => {
    app.SaveSettings.mockRejectedValueOnce(new Error("gateway mati"));
    render(<SettingsView onClose={() => {}} onLogout={() => {}} />);
    await waitFor(() => expect(app.GetSettings).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Simpan" }));
    await waitFor(() => expect(screen.getByText(/gateway mati/)).toBeTruthy());
  });
});

describe("SettingsView aksesibilitas", () => {
  it("punya tombol tutup ✕ yang memanggil onClose", async () => {
    const onClose = vi.fn();
    render(<SettingsView onClose={onClose} onLogout={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Tutup pengaturan" }));
    expect(onClose).toHaveBeenCalled();
  });
});
