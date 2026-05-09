import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import InfoTooltip from "../InfoTooltip";

describe("InfoTooltip", () => {
  it("초기에는 툴팁 본문이 보이지 않는다", () => {
    render(<InfoTooltip content="설명" />);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("버튼 클릭 시 툴팁이 열린다", async () => {
    render(<InfoTooltip content="설명입니다" />);
    await userEvent.click(screen.getByRole("button", { name: /설명/ }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("설명입니다");
  });

  it("ESC 누르면 닫힌다", async () => {
    render(<InfoTooltip content="설명" />);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("ariaLabel 이 버튼에 적용된다", () => {
    render(<InfoTooltip content="x" ariaLabel="custom-label" />);
    expect(
      screen.getByRole("button", { name: "custom-label" }),
    ).toBeInTheDocument();
  });
});
