import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SemanticCard from "./SemanticCard";
import type { SemanticSearchHit } from "../../api/client";
import type { TextId } from "../../types/branded";

/** 构造 mock hit 数据 */
function makeHit(overrides: Partial<SemanticSearchHit> = {}): SemanticSearchHit {
  return {
    text_id: 42 as TextId,
    juan_num: 1,
    title_zh: "般若波罗蜜多心经",
    translator: "玄奘",
    dynasty: "唐",
    category: "般若部",
    source_code: "CBETA",
    cbeta_id: "T0251",
    cbeta_url: "https://cbetaonline.dila.edu.tw/T0251",
    has_content: true,
    snippet: "观自在菩萨，行深般若波罗蜜多时，照见五蕴皆空。",
    similarity_score: 0.85,
    ...overrides,
  };
}

/** 用 MemoryRouter 包裹渲染 */
function renderCard(hit: SemanticSearchHit, rank = 1) {
  return render(
    <MemoryRouter>
      <SemanticCard hit={hit} rank={rank} />
    </MemoryRouter>,
  );
}

describe("SemanticCard 组件", () => {
  it("渲染基本信息：标题、译者、朝代", () => {
    renderCard(makeHit());

    expect(screen.getByText("般若波罗蜜多心经")).toBeInTheDocument();
    // 译者和朝代组合在同一个 Tag 中：[唐] 玄奘
    expect(screen.getByText(/\[唐\]\s*玄奘/)).toBeInTheDocument();
  });

  it("相似度分数显示为百分比", () => {
    renderCard(makeHit({ similarity_score: 0.85 }));

    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  // 分档断言锁的是语义 token，不是具体色值：调色是我们希望能自由做的事，写死
  // #52c41a 只会让每次调色都误报。反过来，这三条此前只查了百分比文字却顶着
  // "为绿色/蓝色/橙色" 的名字，结果三档颜色被整体换掉时它们照样全绿。
  /** 取 antd Progress 环形路径上的 stroke（antd 以内联 style 写入 strokeColor）。 */
  function strokeOf(container: HTMLElement): string {
    const path = container.querySelector<SVGElement>(".ant-progress-circle-path");
    expect(path).toBeTruthy();
    return path!.style.stroke;
  }

  it("相似度 > 0.7 归入 success 档", () => {
    const { container } = renderCard(makeHit({ similarity_score: 0.75 }));

    expect(strokeOf(container)).toBe("var(--fj-success)");
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("相似度 > 0.5 且 <= 0.7 归入 info 档", () => {
    const { container } = renderCard(makeHit({ similarity_score: 0.6 }));

    expect(strokeOf(container)).toBe("var(--fj-info)");
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("相似度 <= 0.5 归入 warning 档", () => {
    const { container } = renderCard(makeHit({ similarity_score: 0.3 }));

    expect(strokeOf(container)).toBe("var(--fj-warning)");
    expect(screen.getByText("30%")).toBeInTheDocument();
  });

  // 边界取的是闭区间（代码用 >= 70 / >= 50），把它钉住：这类边界一旦被误改成
  // 严格大于，只有 70% / 50% 这两个点会变，日常几乎看不出来。
  it("分档边界：正好 70% 归 success，正好 50% 归 info", () => {
    const { container: at70 } = renderCard(makeHit({ similarity_score: 0.7 }));
    expect(strokeOf(at70)).toBe("var(--fj-success)");

    const { container: at50 } = renderCard(makeHit({ similarity_score: 0.5 }));
    expect(strokeOf(at50)).toBe("var(--fj-info)");
  });

  it("渲染匹配文本片段 snippet", () => {
    const snippet = "色不异空，空不异色，色即是空，空即是色。";
    renderCard(makeHit({ snippet }));

    expect(screen.getByText(snippet)).toBeInTheDocument();
  });

  // /read/:id/:juan 从来就不是一条路由（App.tsx 只有 /texts/:id/read），点进去必然 404。
  it("阅读按钮链接到站内阅读器 /texts/{text_id}/read?juan={juan_num}", () => {
    renderCard(makeHit({ text_id: 99 as TextId, juan_num: 3, has_content: true }));

    const readLink = screen.getByText("阅读").closest("a");
    expect(readLink).toHaveAttribute("href", "/texts/99/read?juan=3");
  });

  it("has_content 为 false 时不渲染阅读按钮", () => {
    renderCard(makeHit({ has_content: false }));

    expect(screen.queryByText("阅读")).not.toBeInTheDocument();
  });

  it("渲染排名序号", () => {
    renderCard(makeHit(), 5);

    expect(screen.getByText("#5")).toBeInTheDocument();
  });

  it("cbeta_id 渲染为 Tag", () => {
    renderCard(makeHit({ cbeta_id: "T0251" }));

    expect(screen.getByText("T0251")).toBeInTheDocument();
  });

  it("translator 为 null 时不渲染译者 Tag", () => {
    renderCard(makeHit({ translator: null, dynasty: null }));

    // 不应该渲染包含 [唐] 玄奘 的元素
    expect(screen.queryByText(/玄奘/)).not.toBeInTheDocument();
  });

  it("卷数正确渲染", () => {
    renderCard(makeHit({ juan_num: 7 }));

    expect(screen.getByText("第7卷")).toBeInTheDocument();
  });
});
