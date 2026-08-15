/** 文本页的来源署名。
 *
 * 2026-08-15 审计发现的缺口：`source_url`（如 https://suttacentral.net/{uid}）
 * 一直存在库里、API 也返回，但 `getTextIdentifiers()` 在前端**一处都没有被调用** ——
 * 读者在页面上看不到任何来源信息，只有一个藏经名徽章（大正藏 / 甘珠尔 / 巴利三藏），
 * 那是**藏经**不是**数据源**。
 *
 * 为什么这不只是体验问题：
 *   · CBETA 是 CC BY-NC-SA —— 署名是许可条件，而「大正藏」并不等于署名 CBETA；
 *   · 84000 的条款白纸黑字写明，只写译者或译经团体、不写「84000」本身，
 *     **不满足**其署名要求，而页面只显示「甘珠尔」。
 * 反倒是 SuttaCentral（CC0）根本不要求署名。真正有义务的两家此前没被署名。
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SourceAttribution from "./SourceAttribution";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getTextIdentifiers: vi.fn() };
});

import { getTextIdentifiers } from "../api/client";
import type { SourceId } from "../types/branded";

function renderWith(textId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SourceAttribution textId={textId} />
    </QueryClientProvider>,
  );
}

const SC = {
  id: 196,
  source_id: 161 as SourceId,
  source_code: "suttacentral",
  source_name: "SuttaCentral 巴利经藏",
  source_uid: "pli-tv-ab",
  source_url: "https://suttacentral.net/pli-tv-ab",
};

describe("SourceAttribution", () => {
  beforeEach(() => vi.mocked(getTextIdentifiers).mockReset());

  it("显示数据源名，并链回该源的原始页面", async () => {
    vi.mocked(getTextIdentifiers).mockResolvedValue([SC]);
    const { container } = renderWith();

    const link = await waitFor(() => {
      const a = container.querySelector<HTMLAnchorElement>(".source-attribution a");
      expect(a).not.toBeNull();
      return a!;
    });
    expect(link.textContent).toContain("SuttaCentral 巴利经藏");
    expect(link.href).toBe("https://suttacentral.net/pli-tv-ab");
  });

  it("外链必须带 noopener noreferrer —— 站外链接的既定安全约束", async () => {
    vi.mocked(getTextIdentifiers).mockResolvedValue([SC]);
    const { container } = renderWith();
    const link = await waitFor(() => {
      const a = container.querySelector<HTMLAnchorElement>(".source-attribution a");
      expect(a).not.toBeNull();
      return a!;
    });
    expect(link.rel).toContain("noopener");
    expect(link.rel).toContain("noreferrer");
    expect(link.target).toBe("_blank");
  });

  it("一个文本有多个来源时全部署名", async () => {
    vi.mocked(getTextIdentifiers).mockResolvedValue([
      SC,
      { ...SC, id: 197, source_code: "cbeta", source_name: "CBETA", source_url: "https://cbeta.org/T0001" },
    ]);
    const { container } = renderWith();
    await waitFor(() =>
      expect(container.querySelectorAll(".source-attribution a")).toHaveLength(2),
    );
  });

  it("没有来源时不渲染任何东西（不留空壳）", async () => {
    vi.mocked(getTextIdentifiers).mockResolvedValue([]);
    const { container } = renderWith();
    await waitFor(() => expect(getTextIdentifiers).toHaveBeenCalled());
    expect(container.querySelector(".source-attribution")).toBeNull();
  });

  it("来源没有 URL 时仍然署名，只是不做成链接", async () => {
    vi.mocked(getTextIdentifiers).mockResolvedValue([{ ...SC, source_url: null }]);
    const { container } = renderWith();
    await screen.findByText(/SuttaCentral 巴利经藏/);
    expect(container.querySelector(".source-attribution a")).toBeNull();
  });

  // 「接口失败时不渲染」没有单独的用例，是有意的：出错时 useQuery 的 data 是
  // undefined，走的正是上面那条空数组用例已经覆盖的 `!data?.length` 分支 ——
  // 组件里不存在第二条错误路径可测。而本仓库的 vitest 刻意把未处理错误一律判红
  // （vite.config.ts 的 onUnhandledError 只白名单了一个 React teardown 竞态），
  // 为一条零增量的用例去绕过那条策略并不值得。
});
