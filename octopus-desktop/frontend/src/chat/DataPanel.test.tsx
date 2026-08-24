import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataPanel } from "./DataPanel";
import type { Part } from "./types";

describe("DataPanel", () => {
  it("tidak merender saat hanya ada teks/status", () => {
    const parts: Part[] = [
      { kind: "text", text: "halo", streaming: false },
      { kind: "status", text: "thinking" },
    ];
    const { container } = render(<DataPanel parts={parts} />);
    expect(container.querySelector(".data-panel")).toBeNull();
  });

  it("merender baris accordion untuk action & error", () => {
    const parts: Part[] = [
      { kind: "action", action: "docker_ps", running: false, output: "x" },
      { kind: "error", message: "gagal", retryable: true },
    ];
    render(<DataPanel parts={parts} />);
    expect(screen.getByText("docker_ps")).toBeTruthy();
    expect(screen.getByText("Error")).toBeTruthy();
    expect(screen.getByText("Hasil (2)")).toBeTruthy();
  });
});
