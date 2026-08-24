import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "./ApprovalCard";
import { MetricCard } from "./MetricCard";
import { TableCard, parseColumns } from "./TableCard";

describe("MetricCard", () => {
  it("mengekstrak persentase dari output", () => {
    render(<MetricCard action="memory" output={"Memory usage: 62.5%\nSwap: 10%"} />);
    expect(screen.getAllByText(/62.5%/).length).toBeGreaterThan(0);
  });

  it("fallback pre saat tidak ada persentase", () => {
    render(<MetricCard action="memory" output="tidak ada angka" />);
    expect(screen.getByText("tidak ada angka")).toBeTruthy();
  });
});

describe("TableCard", () => {
  const psOutput = [
    "CONTAINER ID   IMAGE          STATUS         NAMES",
    "abc123def456   nginx:latest   Up 2 hours     web",
    "789ghi012jkl   redis:7        Up 5 minutes   cache",
  ].join("\n");

  it("parseColumns memecah header dan baris berdasarkan 2+ spasi", () => {
    const t = parseColumns(psOutput);
    expect(t?.header).toEqual(["CONTAINER ID", "IMAGE", "STATUS", "NAMES"]);
    expect(t?.rows).toHaveLength(2);
    expect(t?.rows[0][3]).toBe("web");
  });

  it("render table dengan sel dari output", () => {
    render(<TableCard action="docker_ps" output={psOutput} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("nginx:latest")).toBeTruthy();
  });

  it("fallback pre bila bukan kolumnar", () => {
    render(<TableCard action="docker_ps" output="cuma satu kolom" />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("cuma satu kolom")).toBeTruthy();
  });
});

describe("ApprovalCard", () => {
  it("memanggil onApprove dengan planId", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalCard planId="p1" summary="restart web" decided="" onApprove={onApprove} onReject={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onApprove).toHaveBeenCalledWith("p1");
  });

  it("tombol disabled setelah decided", () => {
    render(
      <ApprovalCard planId="p1" summary="s" decided="approved" onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    const btn = screen.getByRole("button", { name: /approve/i }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
