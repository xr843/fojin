import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router";
import Layout from "./Layout";
import { useXiaojinStore } from "../stores/xiaojinStore";

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
  // 跨藏对照独立浏览页(/cross-canon)暂从导航撤下：板块呈现效果待打磨，打磨后再
  // 对外公开。路由仍可 URL 直达，但顶部导航不应出现入口(与 dashboard/research 等
  // 隐藏项一致)。取消 Layout 中对应注释即可恢复本入口——届时把此断言改回点击导航。
  it("跨藏对照暂不在顶部导航出现（板块待打磨）", () => {
    renderLayout();

    expect(screen.queryByText("跨藏对照")).not.toBeInTheDocument();
  });

  // 开放数据(/exports)已从导航撤下：后端 /api/exports/* 由 ENABLE_OPEN_DATA_EXPORTS
  // 控制且默认关闭（未鉴权、无限流，单次 kg.json 达 50MB/60s）。留一条反向断言，
  // 避免入口在后端仍关闭的情况下被无意加回来。
  it("开放数据不在导航里（后端未开放前不应有入口）", () => {
    renderLayout();

    expect(screen.queryByText("开放数据")).toBeNull();
  });

  it("既有导航项不受影响", () => {
    renderLayout();

    for (const label of ["数据源", "AI 问答", "佛学辞典", "知识图谱", "佛教地理", "经典专题"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});


describe("页脚的「唤回小津」", () => {
  beforeEach(() => useXiaojinStore.setState({ hidden: false, masterId: null }));

  it("小津在场时不显示（别添无用的噪音）", () => {
    renderLayout();
    expect(screen.queryByText("唤回小津")).not.toBeInTheDocument();
  });

  it("退出后出现，点一下把小津放回来 —— 持久退出必须成对配这个入口", () => {
    useXiaojinStore.setState({ hidden: true });
    renderLayout();
    const recall = screen.getByText("唤回小津");
    fireEvent.click(recall);
    expect(useXiaojinStore.getState().hidden).toBe(false);
    expect(screen.queryByText("唤回小津")).not.toBeInTheDocument();
  });
});
