import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import "../i18n";
import KnowledgeGraphPage from "./KnowledgeGraphPage";
import { getKGEntityGraph } from "../api/client";
import type { KGGraphLink, KGGraphNode, KGGraphResponse } from "../api/client";
import type { KGEntityId } from "../types/branded";

// d3 force layout needs real layout — jsdom has none. What's under test is
// *what* the page hands to the graph, so the stub just reports the counts.
vi.mock("../components/ForceGraph", () => ({
  default: ({ nodes, links }: { nodes: unknown[]; links: unknown[] }) => (
    <div data-testid="force-graph" data-nodes={nodes.length} data-links={links.length} />
  ),
}));
vi.mock("../components/EntityCard", () => ({ default: () => <div data-testid="entity-card" /> }));
vi.mock("../components/kg/KGTimeline", () => ({ default: () => null }));
vi.mock("../components/kg/KGMentionsPanel", () => ({ default: () => null }));

const CENTER = 54714 as KGEntityId;

/** 生产上玄奘一层邻域的形状：110 个邻居（76 部译经 + 26 位师承 + 8 处地点/朝代/宗派）。 */
function xuanzangDepth1(truncated = false): KGGraphResponse {
  const nodes: KGGraphNode[] = [{ id: CENTER, name: "玄奘", entity_type: "person", description: null }];
  const links: KGGraphLink[] = [];
  const add = (i: number, type: string, predicate: string) => {
    const id = (100000 + i) as KGEntityId;
    nodes.push({ id, name: `n${i}`, entity_type: type, description: null });
    links.push({ source: CENTER, target: id, predicate, confidence: 1, provenance: null, evidence: null });
  };
  let i = 0;
  for (let k = 0; k < 76; k++) add(i++, "text", "translated");
  for (let k = 0; k < 26; k++) add(i++, "person", "teacher_of");
  for (let k = 0; k < 8; k++) add(i++, "place", "active_in");
  return { nodes, links, truncated };
}

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getKGStats: vi.fn().mockResolvedValue({ entities: {}, relations: {}, total_entities: 0, total_relations: 0 }),
    getKGTimeline: vi.fn().mockResolvedValue({ entities: [] }),
    searchKGEntities: vi.fn().mockResolvedValue({
      results: [{ id: 54714, name_zh: "玄奘", entity_type: "person", relation_count: 110 }],
      total: 1,
    }),
    getKGEntity: vi.fn().mockResolvedValue({ id: 54714, name_zh: "玄奘", entity_type: "person", relations: [] }),
    getKGEntityGraph: vi.fn(),
  };
});

const graphMock = vi.mocked(getKGEntityGraph);

function renderPage(url = "/kg") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <KnowledgeGraphPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const shownNodes = async () => Number((await screen.findByTestId("force-graph")).getAttribute("data-nodes"));

describe("KnowledgeGraphPage 默认视图", () => {
  beforeEach(() => {
    graphMock.mockReset();
    graphMock.mockResolvedValue(xuanzangDepth1());
  });

  it("默认只取一层关系（桌面也一样），不再一打开就拉两层 150 节点", async () => {
    renderPage();
    await screen.findByTestId("force-graph");
    expect(graphMock).toHaveBeenCalled();
    const [entityId, depth] = graphMock.mock.calls[0];
    expect(entityId).toBe(54714);
    expect(depth).toBe(1);
  });

  it("默认图谱只画核心节点（25–40 个），并告诉用户还有多少没显示", async () => {
    renderPage();
    const n = await shownNodes();
    expect(n).toBeGreaterThanOrEqual(25);
    expect(n).toBeLessThanOrEqual(40);
    expect(screen.getByRole("button", { name: /显示全部/ })).toBeInTheDocument();
  });

  it("默认状态不出现「节点超出」类警告——即使后端回了 truncated", async () => {
    graphMock.mockResolvedValue(xuanzangDepth1(true));
    renderPage();
    await screen.findByTestId("force-graph");
    expect(screen.queryByText(/超出|过多/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("点「显示全部」一步拿回完整一层图谱", async () => {
    renderPage();
    await shownNodes();
    fireEvent.click(screen.getByRole("button", { name: /显示全部/ }));
    await waitFor(async () => expect(await shownNodes()).toBe(111));
    // 也能一步回到核心视图
    fireEvent.click(screen.getByRole("button", { name: /只看核心/ }));
    await waitFor(async () => expect(await shownNodes()).toBeLessThanOrEqual(40));
  });

  it("用户主动加深度导致超限时才提示，且文案告诉用户怎么办", async () => {
    graphMock.mockResolvedValue({ ...xuanzangDepth1(true) });
    renderPage("/kg?q=玄奘&id=54714&depth=2");
    await screen.findByTestId("force-graph");
    expect(graphMock.mock.calls[0][1]).toBe(2);
    // 用户自己调的深度：不再裁剪
    expect(await shownNodes()).toBe(111);
    const hint = await screen.findByText(/已显示前 111 个/);
    expect(hint.textContent).toMatch(/搜索/);
    expect(hint.textContent).not.toMatch(/超出|过多/);
  });
});
