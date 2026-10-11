import { describe, expect, it } from "vitest";
import { pickCoreSubgraph } from "./coreSubgraph";
import type { KGGraphLink, KGGraphNode } from "../../api/client";
import type { KGEntityId } from "../../types/branded";

const kid = (n: number) => n as KGEntityId;

const node = (id: number, entity_type = "text"): KGGraphNode => ({ id: kid(id), name: `n${id}`, entity_type, description: null });
const link = (source: number, target: number, predicate: string): KGGraphLink => ({
  source: kid(source),
  target: kid(target),
  predicate,
  confidence: 1,
  provenance: null,
  evidence: null,
});

/** 仿玄奘：中心 1 号，60 部译经（translated）、20 位师承（teacher_of）、5 个活动地（active_in）、1 个宗派。 */
function xuanzangLike() {
  const nodes: KGGraphNode[] = [node(1, "person")];
  const links: KGGraphLink[] = [];
  for (let i = 0; i < 60; i++) {
    nodes.push(node(100 + i, "text"));
    links.push(link(1, 100 + i, "translated"));
  }
  for (let i = 0; i < 20; i++) {
    nodes.push(node(200 + i, "person"));
    links.push(link(1, 200 + i, "teacher_of"));
  }
  for (let i = 0; i < 5; i++) {
    nodes.push(node(300 + i, "place"));
    links.push(link(1, 300 + i, "active_in"));
  }
  nodes.push(node(400, "school"));
  links.push(link(1, 400, "member_of_school"));
  // 两部译经之间互相引用 —— 度数更高，应优先入选
  links.push(link(158, 159, "cites"));
  links.push(link(159, 157, "cites"));
  return { nodes, links };
}

describe("pickCoreSubgraph", () => {
  it("小图原样返回，不隐藏任何节点", () => {
    const g = { nodes: [node(1), node(2)], links: [link(1, 2, "translated")] };
    const r = pickCoreSubgraph(g, kid(1), 30);
    expect(r.nodes).toHaveLength(2);
    expect(r.links).toHaveLength(1);
    expect(r.hiddenCount).toBe(0);
  });

  it("大图裁到上限，且保留中心节点", () => {
    const g = xuanzangLike();
    const r = pickCoreSubgraph(g, kid(1), 30);
    expect(r.nodes).toHaveLength(30);
    expect(r.nodes.map((n) => n.id)).toContain(1);
    expect(r.hiddenCount).toBe(g.nodes.length - 30);
  });

  it("各关系类型都有代表，不被数量最多的译经独占", () => {
    const r = pickCoreSubgraph(xuanzangLike(), kid(1), 30);
    const types = new Set(r.nodes.map((n) => n.entity_type));
    expect(types).toEqual(new Set(["person", "text", "place", "school"]));
    const persons = r.nodes.filter((n) => n.entity_type === "person").length - 1; // 去掉中心
    const texts = r.nodes.filter((n) => n.entity_type === "text").length;
    expect(persons).toBeGreaterThanOrEqual(8);
    expect(texts).toBeGreaterThanOrEqual(8);
  });

  it("同一关系内按度数挑：被引用多的译经先入选", () => {
    const r = pickCoreSubgraph(xuanzangLike(), kid(1), 30);
    const ids = r.nodes.map((n) => n.id);
    expect(ids).toEqual(expect.arrayContaining([157, 158, 159]));
  });

  it("只保留两端都入选的边", () => {
    const r = pickCoreSubgraph(xuanzangLike(), kid(1), 30);
    const kept = new Set(r.nodes.map((n) => n.id));
    for (const l of r.links) {
      expect(kept.has(l.source) && kept.has(l.target)).toBe(true);
    }
    // 中心的每个入选邻居都至少有一条连向中心的边
    expect(r.links.filter((l) => (l.source as number) === 1 || (l.target as number) === 1)).toHaveLength(29);
  });

  it("中心不在图里（数据异常）时原样返回，不硬裁", () => {
    const g = xuanzangLike();
    const r = pickCoreSubgraph(g, kid(9999), 30);
    expect(r.nodes).toHaveLength(g.nodes.length);
    expect(r.hiddenCount).toBe(0);
  });

  it("结果确定：同样输入两次挑出同一批节点", () => {
    const a = pickCoreSubgraph(xuanzangLike(), kid(1), 30).nodes.map((n) => n.id);
    const b = pickCoreSubgraph(xuanzangLike(), kid(1), 30).nodes.map((n) => n.id);
    expect(a).toEqual(b);
  });
});
