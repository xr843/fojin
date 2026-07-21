import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ParallelSentenceCard from "./ParallelSentenceCard";
import type { ParallelSentenceHit } from "../../api/client";
import type { TextId } from "../../types/branded";

function makeHit(overrides: Partial<ParallelSentenceHit> = {}): ParallelSentenceHit {
  return {
    zh_text: "色即是空",
    foreign_text: "rūpaṃ śūnyatā",
    foreign_lang: "sa",
    taisho_id: "T0251",
    text_id: 42 as TextId,
    title: "般若波羅蜜多心經",
    juan_num: 1,
    mitra_e_score: 0.82,
    source: "mitra-parallel",
    license: "CC-BY-SA-4.0",
    ...overrides,
  };
}

function renderCard(hit: ParallelSentenceHit, rank = 1) {
  return render(
    <MemoryRouter>
      <ParallelSentenceCard hit={hit} rank={rank} />
    </MemoryRouter>,
  );
}

describe("ParallelSentenceCard 组件", () => {
  it("并排渲染汉文句与外语句", () => {
    renderCard(makeHit());
    expect(screen.getByText("色即是空")).toBeInTheDocument();
    expect(screen.getByText("rūpaṃ śūnyatā")).toBeInTheDocument();
  });

  it("渲染外语语种标签（梵文）", () => {
    renderCard(makeHit({ foreign_lang: "sa" }));
    expect(screen.getByText("梵文")).toBeInTheDocument();
    // 汉文侧标签
    expect(screen.getByText("汉文")).toBeInTheDocument();
  });

  it("外语为藏文时渲染藏文标签", () => {
    renderCard(makeHit({ foreign_lang: "bo", foreign_text: "gzugs stong pa" }));
    expect(screen.getByText("藏文")).toBeInTheDocument();
    expect(screen.getByText("gzugs stong pa")).toBeInTheDocument();
  });

  it("渲染出处：taisho_id + 标题 + 卷数", () => {
    renderCard(makeHit({ taisho_id: "T0251", title: "般若波羅蜜多心經", juan_num: 3 }));
    expect(screen.getByText("T0251")).toBeInTheDocument();
    expect(screen.getByText("般若波羅蜜多心經")).toBeInTheDocument();
    expect(screen.getByText("第3卷")).toBeInTheDocument();
  });

  it("渲染 MITRA / CC BY-SA 授权来源标注", () => {
    renderCard(makeHit());
    expect(screen.getByText(/MITRA/)).toBeInTheDocument();
    expect(screen.getByText(/CC BY-SA/)).toBeInTheDocument();
  });

  it("mitra_e_score 存在时渲染质量分标签", () => {
    renderCard(makeHit({ mitra_e_score: 0.82 }));
    expect(screen.getByText(/0\.82/)).toBeInTheDocument();
  });

  it("mitra_e_score 为 null 时不渲染质量分（NULL 宽容）", () => {
    renderCard(makeHit({ mitra_e_score: null }));
    // 卡片仍然渲染核心内容
    expect(screen.getByText("色即是空")).toBeInTheDocument();
    expect(screen.queryByText(/对齐质量/)).not.toBeInTheDocument();
  });

  // /read/:id/:juan 从来就不是一条路由（App.tsx 只有 /texts/:id/read），点进去必然 404。
  it("text_id 有效时阅读按钮链接到站内阅读器 /texts/{text_id}/read?juan={juan_num}", () => {
    renderCard(makeHit({ text_id: 99 as TextId, juan_num: 2 }));
    const readLink = screen.getByText("阅读").closest("a");
    expect(readLink).toHaveAttribute("href", "/texts/99/read?juan=2");
  });

  it("text_id 为 0 时不渲染阅读按钮", () => {
    renderCard(makeHit({ text_id: 0 as TextId }));
    expect(screen.queryByText("阅读")).not.toBeInTheDocument();
  });

  it("渲染排名序号", () => {
    renderCard(makeHit(), 4);
    expect(screen.getByText("#4")).toBeInTheDocument();
  });
});
