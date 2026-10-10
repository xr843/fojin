import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
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
function renderCard(hit: SemanticSearchHit) {
  return render(
    <MemoryRouter>
      <SemanticCard hit={hit} />
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

  // 相似度从 40px 彩色圆环降为一行小字：一页 6~20 个红绿蓝圆环把视觉重心从经名上抢走，
  // 而余弦相似度的 70%/50% 分档本身是任意切点，配上「绿=好」的颜色是在暗示并不存在的判断。
  it("相似度不再画成彩色圆环，降为带标签的小字", () => {
    const { container } = renderCard(makeHit({ similarity_score: 0.64 }));

    expect(container.querySelector(".ant-progress")).toBeNull();
    const score = container.querySelector(".s-card-score");
    expect(score).not.toBeNull();
    expect(score!.textContent).toMatch(/相似度\s*64%/);
  });

  // 经名即去详情页的主链接，和「经文标题」区的卡片同一个出口。
  it("经名是指向 /texts/{text_id} 的链接", () => {
    renderCard(makeHit({ text_id: 99 as TextId, title_zh: "金剛經解義" }));

    expect(screen.getByRole("link", { name: "金剛經解義" })).toHaveAttribute("href", "/texts/99");
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

  // 「#N」窄栏占宽度又不传达信息——顺序本身就是排序。
  it("不渲染排名序号", () => {
    const { container } = renderCard(makeHit());

    expect(container.querySelector(".s-card-rank")).toBeNull();
    expect(screen.queryByText(/^#\d+$/)).not.toBeInTheDocument();
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

// 生产 /search?q=金剛經 上仅剩的 3 个 .ant-tag-geekblue 就是这里的来源标签（cbeta）。
describe("SemanticCard 来源标签用中性色", () => {
  it("不再有 antd 蓝色系 Tag", () => {
    const { container } = renderCard(makeHit({ source_code: "cbeta" }));
    expect(screen.getByText("cbeta")).toBeInTheDocument();
    expect(container.querySelector(".ant-tag-blue, .ant-tag-geekblue")).toBeNull();
  });
});
