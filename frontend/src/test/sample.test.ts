import { describe, expect, it } from "vitest";
import { wrap, makePosition } from "./factories";

describe("test bootstrap sanity", () => {
  it("wrap() 은 ApiResponse 형식으로 감싼다", () => {
    const r = wrap({ x: 1 });
    expect(r).toEqual({ success: true, data: { x: 1 }, message: "" });
  });

  it("makePosition() 은 기본 필드를 채운 객체를 만든다", () => {
    const p = makePosition({ ticker: "035720" });
    expect(p.ticker).toBe("035720");
    expect(p.profit_rate).toBeCloseTo(2.86, 2);
  });
});
