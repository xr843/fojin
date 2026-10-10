import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import ContentCard from "./ContentCard";
import type { ContentSearchHit } from "../../api/client";
import type { TextId } from "../../types/branded";

function makeHit(overrides: Partial<ContentSearchHit> = {}): ContentSearchHit {
  return {
    text_id: 12326 as TextId,
    cbeta_id: "X0348",
    title_zh: "維摩經無我疏",
    translator: "傳燈著",
    dynasty: "明",
    juan_num: 10,
    lang: "lzh",
    source_code: "cbeta",
    highlight: ["...釋入<em>不二法門</em>品二..."],
    score: 1.0,
    matched_juan_count: 1,
    matched_juans: [{ juan_num: 10, highlight: ["...釋入<em>不二法門</em>品二..."], score: 1.0 }],
    ...overrides,
  };
}

function renderCard(hit: ContentSearchHit) {
  return render(
    <MemoryRouter>
      <ContentCard hit={hit} />
    </MemoryRouter>,
  );
}

describe("ContentCard 组件", () => {
  // 全文命中是搜索页的主力结果。此前这张卡唯一的出口是站外 CBETA 链接，
  // 等于把用户从自家全文索引直接送走，而站内阅读器才带标注/校勘/跨藏对照。
  it("命中卷链接到站内阅读器 /texts/{text_id}/read?juan={juan_num}", () => {
    renderCard(makeHit({ text_id: 99 as TextId, juan_num: 7 }));

    const readLink = screen.getByText("阅读").closest("a");
    expect(readLink).toHaveAttribute("href", "/texts/99/read?juan=7");
  });

  it("展开的其他匹配卷各自链接到对应卷", () => {
    renderCard(
      makeHit({
        text_id: 99 as TextId,
        juan_num: 7,
        matched_juan_count: 2,
        matched_juans: [
          { juan_num: 7, highlight: ["a"], score: 1.0 },
          { juan_num: 12, highlight: ["b"], score: 0.9 },
        ],
      }),
    );

    fireEvent.click(screen.getByText(/展开/));

    const links = screen.getAllByText("阅读").map((el) => el.closest("a"));
    expect(links.map((a) => a?.getAttribute("href"))).toContain("/texts/99/read?juan=12");
  });

  it("站外 CBETA 链接保留，作为次要出口", () => {
    renderCard(makeHit({ cbeta_id: "T0251" }));

    const cbetaLink = screen.getByText(/CBETA/).closest("a");
    expect(cbetaLink).toHaveAttribute("href", "https://cbetaonline.dila.edu.tw/zh/T0251");
    expect(cbetaLink).toHaveAttribute("target", "_blank");
  });

  // 经名即去详情页的主链接；「阅读」「CBETA 阅读」退为次级文字入口——此前「阅读」是
  // 实心朱砂按钮，和每张经文标题卡上的「查看详情」一起把一页摊成十几个视觉重点。
  it("经名是指向 /texts/{text_id} 的链接，卡内没有实心主按钮", () => {
    const { container } = renderCard(makeHit({ text_id: 99 as TextId }));

    expect(screen.getByRole("link", { name: "維摩經無我疏" })).toHaveAttribute("href", "/texts/99");
    expect(container.querySelector(".ant-btn-primary")).toBeNull();
  });

  // <a><button> 是无效嵌套：一个入口两个 Tab 停靠点，读屏念成「链接 按钮 阅读」。
  it("「阅读」是单一链接，不再是链接里套按钮", () => {
    renderCard(makeHit());

    const readLink = screen.getByText("阅读").closest("a")!;
    expect(readLink.querySelector("button")).toBeNull();
  });

  it("不渲染排名序号", () => {
    const { container } = renderCard(makeHit());

    expect(container.querySelector(".s-card-rank")).toBeNull();
    expect(screen.queryByText(/^#\d+$/)).not.toBeInTheDocument();
  });
});

describe("ContentCard 语种标签用中性色", () => {
  it("非汉文语种标签不再是 antd 蓝色 Tag", () => {
    const { container } = renderCard(makeHit({ lang: "en" }));
    expect(screen.getByText("英文")).toBeInTheDocument();
    expect(container.querySelector(".ant-tag-blue, .ant-tag-geekblue")).toBeNull();
  });
});
