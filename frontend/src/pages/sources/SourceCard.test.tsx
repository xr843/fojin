import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
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
    // 与库里的 server_default 一致，别让 fixture 编造一个生产里不存在的初值。
    health_confidence: "high",
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

describe("SourceCard 只对跨点位成立的判词打徽章", () => {
  // 巡检跑在单台新加坡 VPS 上：超时、DNS 失败，以及 CDN 边缘节点回自己的
  // 默认证书，说的都是探测点而非站点。0172 为此加了 health_confidence，但
  // 徽章从没接上去，于是牛津博德利、普林斯顿、CNKI 这些实测活着的站一直被
  // 标成坏的。
  const LOW_CONFIDENCE_CASES = [
    { status: "unreachable" as const, label: "巡检未达", why: "VPS 连不上但别处 200（牛津/普林斯顿）" },
    { status: "cert_invalid" as const, label: "证书异常", why: "CDN 边缘回默认证书（CNKI）" },
  ];

  it.each(LOW_CONFIDENCE_CASES)(
    "$status 且 confidence=low 时不打徽章（$why）",
    ({ status, label }) => {
      renderCard(
        makeSource({
          health_status: status,
          health_confidence: "low",
          health_detail: "timeout",
        }),
      );
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    },
  );

  it("同样的状态在 confidence=high 时照常打徽章", () => {
    renderCard(
      makeSource({
        health_status: "unreachable",
        health_confidence: "high",
        health_detail: "HTTP 522",
      }),
    );
    expect(screen.getByText("巡检未达")).toBeInTheDocument();
  });
});
