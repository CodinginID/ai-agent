import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Tilt } from "./Tilt";

describe("Tilt", () => {
  it("merender children dengan class tilt-surface + class tambahan", () => {
    render(
      <Tilt className="card card-metric">
        <span>isi</span>
      </Tilt>,
    );
    const el = screen.getByText("isi").parentElement;
    expect(el?.className).toBe("tilt-surface card card-metric");
  });
});
