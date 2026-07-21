import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import Layout from "./Layout";

/** 把当前路径渲染出来，供断言导航是否真的发生 */
function LocationProbe() {
  return <div data-testid="pathname">{useLocation().pathname}</div>;
}

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<LocationProbe />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Layout 顶部导航", () => {
  // 跨藏对照（1,016 部经 · 91 万组逐段对照）与开放数据下载此前只能靠猜 URL 到达：
  // 页面早就建好并跑在生产上，但导航里没有任何入口。
  it("跨藏对照有导航入口，点击进入 /cross-canon", () => {
    renderLayout();

    fireEvent.click(screen.getByText("跨藏对照"));

    expect(screen.getByTestId("pathname")).toHaveTextContent("/cross-canon");
  });

  it("开放数据有导航入口，点击进入 /exports", () => {
    renderLayout();

    fireEvent.click(screen.getByText("开放数据"));

    expect(screen.getByTestId("pathname")).toHaveTextContent("/exports");
  });

  it("既有导航项不受影响", () => {
    renderLayout();

    for (const label of ["数据源", "AI 问答", "佛学辞典", "知识图谱", "佛教地理", "经典专题"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
