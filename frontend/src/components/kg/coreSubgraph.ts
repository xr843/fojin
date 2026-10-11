// 知识图谱「核心视图」的节点挑选。
//
// 为什么在前端裁：后端 /kg/entities/{id}/graph 只有 max_nodes 硬上限，超出时用
// set 的任意顺序截断（services/knowledge_graph.py 的 BFS），既不按重要性挑、也
// 不保证各类关系都有代表——用它直接取 30 个，玄奘的图里只剩随机的师承和译经。
// 一层邻域本身也不小（玄奘 110 个邻居，其中 76 部译经），所以默认视图先取完整的
// 一层，再在这里按「关系类型轮转 + 同类按度数」挑出可读的核心。
//
// 规则：
//   1. 中心节点必留。
//   2. 每个邻居归入它与中心之间优先级最高的那种关系（师承 > 宗派 > 地点 … > 引用）。
//   3. 各关系组轮流出一个节点，直到凑满上限——数量最多的译经不会把师承挤掉，
//      小组（宗派、朝代）取完后名额自然让给大组。
//   4. 组内按子图里的度数降序（被别的邻居引用/关联得多的先上），再按 id 升序保证确定。
//   5. 只保留两端都入选的边。

import type { KGGraphLink, KGGraphNode } from "../../api/client";
import type { KGEntityId } from "../../types/branded";

/** 默认视图的节点数（含中心）。产品定的区间是 25–40。 */
export const CORE_NODE_LIMIT = 30;

const PREDICATE_PRIORITY = [
  "teacher_of",
  "member_of_school",
  "active_in",
  "translated_at",
  "translated",
  "commentary_on",
  "alt_translation",
  "parallel_text",
  "associated_with",
  "cites",
];

const priorityOf = (predicate: string) => {
  const i = PREDICATE_PRIORITY.indexOf(predicate);
  return i === -1 ? PREDICATE_PRIORITY.length : i;
};

export interface CoreSubgraph {
  nodes: KGGraphNode[];
  links: KGGraphLink[];
  /** 被核心视图隐藏的节点数（0 = 原样展示）。 */
  hiddenCount: number;
}

export function pickCoreSubgraph(
  graph: { nodes: KGGraphNode[]; links: KGGraphLink[] },
  centerId: KGEntityId,
  limit: number = CORE_NODE_LIMIT,
): CoreSubgraph {
  const { nodes, links } = graph;
  if (nodes.length <= limit || !nodes.some((n) => n.id === centerId)) {
    return { nodes, links, hiddenCount: 0 };
  }

  const degree = new Map<number, number>();
  for (const l of links) {
    degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
    degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
  }

  // 邻居 → 与中心之间最优先的关系
  const bestPriority = new Map<number, number>();
  for (const l of links) {
    const other = l.source === centerId ? l.target : l.target === centerId ? l.source : null;
    if (other == null || other === centerId) continue;
    const p = priorityOf(l.predicate);
    const prev = bestPriority.get(other);
    if (prev === undefined || p < prev) bestPriority.set(other, p);
  }

  // 分组；与中心不直接相连的节点（深度>1 时才会有）排在最后一组
  const OTHER = PREDICATE_PRIORITY.length + 1;
  const groups = new Map<number, KGGraphNode[]>();
  for (const n of nodes) {
    if (n.id === centerId) continue;
    const g = bestPriority.get(n.id) ?? OTHER;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g)!.push(n);
  }
  const queues = [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, members]) =>
      members.sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.id - b.id),
    );

  const kept = new Set<number>([centerId]);
  let round = 0;
  while (kept.size < limit) {
    let took = false;
    for (const q of queues) {
      if (kept.size >= limit) break;
      if (round < q.length) {
        kept.add(q[round].id);
        took = true;
      }
    }
    if (!took) break;
    round++;
  }

  return {
    nodes: nodes.filter((n) => kept.has(n.id)),
    links: links.filter((l) => kept.has(l.source) && kept.has(l.target)),
    hiddenCount: nodes.length - kept.size,
  };
}
