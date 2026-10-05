import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, Link, useSearchParams, useParams } from "react-router";
import TextReaderRoute from "./TextReaderRoute";

const mounts = vi.fn();

// 模拟真实阅读器的关键行为：卷号是惰性 state，只在挂载时读一次 ?juan=
vi.mock("./TextReaderPage", () => ({
  default: function FakeReader() {
    const { id } = useParams();
    const [sp] = useSearchParams();
    const [juan] = useState(() => {
      mounts();
      return Number(sp.get("juan") ?? 1);
    });
    return (
      <div>
        <span data-testid="where">
          {id}:{juan}
        </span>
        <Link to="/texts/36/read?juan=21">goto-36-21</Link>
        <Link to="/texts/7/read?juan=3">goto-7-3</Link>
      </div>
    );
  },
}));

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/texts/:id/read" element={<TextReaderRoute />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TextReaderRoute 阅读器内跳转", () => {
  it("跳到另一部经的指定卷：重新挂载并读到新卷号（不是沿用上一部的卷）", () => {
    mounts.mockClear();
    renderAt("/texts/7/read");
    expect(screen.getByTestId("where").textContent).toBe("7:1");
    fireEvent.click(screen.getByText("goto-36-21"));
    expect(screen.getByTestId("where").textContent).toBe("36:21");
    expect(mounts).toHaveBeenCalledTimes(2);
  });

  it("同一部经换到另一卷的链接也生效", () => {
    mounts.mockClear();
    renderAt("/texts/7/read?juan=1");
    fireEvent.click(screen.getByText("goto-7-3"));
    expect(screen.getByTestId("where").textContent).toBe("7:3");
  });
});
