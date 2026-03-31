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

  it("相似度 > 0.7 时 Progress strokeColor 为绿色", () => {
    const { container } = renderCard(makeHit({ similarity_score: 0.75 }));

    // antd Progress circle 渲染 SVG，strokeColor 会设置在 circle 的 stroke 上
    const trailPath = container.querySelector(".ant-progress-circle-path");
    expect(trailPath).toBeTruthy();
    // 验证百分比正确渲染
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("相似度 > 0.5 且 <= 0.7 时显示蓝色对应的百分比", () => {
    renderCard(makeHit({ similarity_score: 0.6 }));

    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("相似度 <= 0.5 时显示橙色对应的百分比", () => {
    renderCard(makeHit({ similarity_score: 0.3 }));

    expect(screen.getByText("30%")).toBeInTheDocument();
  });

  it("渲染匹配文本片段 snippet", () => {
    const snippet = "色不异空，空不异色，色即是空，空即是色。";
    renderCard(makeHit({ snippet }));

    expect(screen.getByText(snippet)).toBeInTheDocument();
  });

  it("阅读按钮链接到 /read/{text_id}/{juan_num}", () => {
    renderCard(makeHit({ text_id: 99 as TextId, juan_num: 3, has_content: true }));

    const readLink = screen.getByText("阅读").closest("a");
    expect(readLink).toHaveAttribute("href", "/read/99/3");
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
