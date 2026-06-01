import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SourceCard from "./SourceCard";
import type { DataSource } from "../../api/client";
import type { SourceId } from "../../types/branded";

/** 构造 mock 数据源 */
function makeSource(overrides: Partial<DataSource> = {}): DataSource {
  return {
    id: 1 as SourceId,
    code: "CBETA",
    name_zh: "中華電子佛典協會",
    name_en: "CBETA",
    base_url: "https://cbetaonline.dila.edu.tw",
    description: null,
    access_type: "external",
    region: null,
    languages: "zh",
    research_fields: null,
    supports_search: false,
    supports_fulltext: false,
    has_local_fulltext: false,
    has_remote_fulltext: false,
    supports_iiif: false,
    supports_api: false,
    sort_order: 0,
    is_active: true,
    health_status: "ok",
    health_checked_at: null,
    health_detail: null,
    distributions: [],
    ...overrides,
  };
}

function renderCard(source: DataSource) {
  return render(
    <MemoryRouter>
      <SourceCard source={source} searchQuery="" />
    </MemoryRouter>,
  );
}

describe("SourceCard 健康徽章 tooltip", () => {
  it("ok 源不显示健康徽章", () => {
    renderCard(makeSource());
    expect(screen.queryByText("巡检未达")).not.toBeInTheDocument();
    expect(screen.queryByText("访问受限")).not.toBeInTheDocument();
  });

  it("非 moved 状态在 tooltip 中显示 health_detail", async () => {
    const user = userEvent.setup();
    renderCard(
      makeSource({
        health_status: "degraded",
        health_detail: "HTTP 404",
        health_checked_at: "2026-05-16T04:30:00Z",
      }),
    );
    await user.hover(screen.getByText("访问受限"));
    expect(await screen.findByText(/详情：HTTP 404/)).toBeInTheDocument();
  });

  it("moved 状态保留「现重定向至」措辞", async () => {
    const user = userEvent.setup();
    renderCard(
      makeSource({
        health_status: "moved",
        health_detail: "https://example.org/new",
        health_checked_at: "2026-05-16T04:30:00Z",
      }),
    );
    await user.hover(screen.getByText("站点已迁移"));
    expect(
      await screen.findByText(/现重定向至：https:\/\/example\.org\/new/),
    ).toBeInTheDocument();
  });

  it("非 ok 但 health_detail 为空时不显示「详情」行", async () => {
    const user = userEvent.setup();
    renderCard(
      makeSource({ health_status: "unreachable", health_detail: null }),
    );
    await user.hover(screen.getByText("巡检未达"));
    // 通用 tip 仍在，但不应出现「详情：」前缀。
    // 注：此断言依赖 HEALTH_BADGE 各 tip 文案均不含「详情：」子串——
    // 若日后某 tip 引入该词，需改为对 tooltip 容器作用域断言。
    expect(await screen.findByText(/浏览器通常仍可正常访问/)).toBeInTheDocument();
    expect(screen.queryByText(/详情：/)).not.toBeInTheDocument();
  });
});
