import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReaderDictPopover } from "./ReaderDictPopover";
import { createExcerpt } from "../api/client";
import type { DictPopoverState } from "./ReaderDictPopover.types";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, createExcerpt: vi.fn() };
});
const mockCreate = vi.mocked(createExcerpt);

const QUOTE = "有十四音名為字義，所言字者，名曰涅槃";
const state: DictPopoverState = { visible: true, text: QUOTE, x: 100, y: 100, selTop: 80, loading: false, result: null };
const context = { textId: 15, juanNum: 8, title: "大般涅槃經", cbetaId: "T0374", lineRef: "0413a07" };

function renderPopover(loggedIn: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReaderDictPopover
          state={state}
          onClose={vi.fn()}
          onAsk={vi.fn()}
          context={context}
          endLineRef="0413a08"
          loggedIn={loggedIn}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => mockCreate.mockReset());

describe("划词浮层「摘录」", () => {
  it("未登录：提示登录，不发请求", () => {
    renderPopover(false);
    fireEvent.click(screen.getByRole("button", { name: "摘录" }));
    expect(screen.getByText(/摘录会存进你的账号/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "去登录" })).toBeInTheDocument();
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("已登录：带起讫行号、原文、笔记保存，成功后给出「查看我的摘录」", async () => {
    mockCreate.mockResolvedValue({} as never);
    renderPopover(true);
    fireEvent.click(screen.getByRole("button", { name: "摘录" }));
    expect(screen.getByText(/仅自己可见/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/写一句笔记/), { target: { value: " 字本即涅槃 " } });
    fireEvent.click(screen.getByRole("button", { name: "保存摘录" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "查看我的摘录" })).toBeInTheDocument());
    expect(mockCreate).toHaveBeenCalledWith({
      text_id: 15,
      juan_num: 8,
      line_ref: "0413a07",
      end_line_ref: "0413a08",
      quote: QUOTE,
      note: "字本即涅槃",
    });
    expect(screen.getByRole("link", { name: "查看我的摘录" }).getAttribute("href")).toBe("/profile?tab=excerpts");
  });

  it("不笔记也能存：note 为 null", async () => {
    mockCreate.mockResolvedValue({} as never);
    renderPopover(true);
    fireEvent.click(screen.getByRole("button", { name: "摘录" }));
    fireEvent.click(screen.getByRole("button", { name: "保存摘录" }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0].note).toBeNull();
  });
});
