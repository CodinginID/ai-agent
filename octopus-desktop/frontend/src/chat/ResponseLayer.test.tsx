import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResponseLayer } from "./ResponseLayer";

describe("ResponseLayer", () => {
  it("menampilkan teks jawaban terbaru", () => {
    render(<ResponseLayer text="Halo, Boss" />);
    expect(screen.getByText("Halo, Boss")).toBeTruthy();
  });

  it("tidak merender apa pun saat teks kosong", () => {
    const { container } = render(<ResponseLayer text="   " />);
    expect(container.querySelector(".response-layer")).toBeNull();
  });
});
