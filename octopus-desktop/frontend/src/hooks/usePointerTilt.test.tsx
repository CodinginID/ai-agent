import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePointerTilt } from "./usePointerTilt";

function TestBox() {
  const ref = usePointerTilt<HTMLDivElement>();
  return <div ref={ref} data-testid="box" />;
}

describe("usePointerTilt", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mengatur --tilt-x/--tilt-y berdasarkan posisi pointer, reset saat pointer keluar", () => {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      right: 100,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => {},
    } as DOMRect);

    const { getByTestId } = render(<TestBox />);
    const box = getByTestId("box");

    fireEvent.pointerMove(box, { clientX: 100, clientY: 0 });
    expect(box.style.getPropertyValue("--tilt-y")).toBe("6.00deg");
    expect(box.style.getPropertyValue("--tilt-x")).toBe("6.00deg");

    fireEvent.pointerLeave(box);
    expect(box.style.getPropertyValue("--tilt-x")).toBe("0deg");
    expect(box.style.getPropertyValue("--tilt-y")).toBe("0deg");
  });
});
