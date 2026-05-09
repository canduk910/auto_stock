import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConfirmModal from "../ConfirmModal";

describe("ConfirmModal", () => {
  it("open=false 면 아무것도 렌더링하지 않는다", () => {
    const { container } = render(
      <ConfirmModal
        open={false}
        title="t"
        message="m"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("title/message 를 표시한다", () => {
    render(
      <ConfirmModal
        open
        title="매매 시작"
        message="정말 시작하시겠습니까?"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByText("매매 시작")).toBeInTheDocument();
    expect(screen.getByText("정말 시작하시겠습니까?")).toBeInTheDocument();
  });

  it("확인 버튼 클릭 시 onConfirm 호출", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmModal
        open
        title="t"
        message="m"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /확인|시작|확정|네/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("취소 버튼 클릭 시 onCancel 호출", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        open
        title="t"
        message="m"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /취소|아니오|닫/ }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("loading=true 면 두 버튼 모두 disabled", () => {
    render(
      <ConfirmModal
        open
        title="t"
        message="m"
        onConfirm={() => {}}
        onCancel={() => {}}
        loading
      />,
    );
    const buttons = screen.getAllByRole("button");
    buttons.forEach((b) => expect(b).toBeDisabled());
  });
});
