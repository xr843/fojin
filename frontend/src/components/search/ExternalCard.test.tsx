import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ExternalCard from "./ExternalCard";
import type { DataSource } from "../../api/client";

const source = {
  code: "sat",
  name_zh: "SAT 大正藏数据库",
  name_en: "SAT",
  access_type: "external",
  region: "日本",
  languages: "lzh",
  base_url: "https://example.org",
} as unknown as DataSource;

// 外部源一页 12 行，每行原有一颗实心朱砂「前往原站搜索」——结果区已按 #1299 收成
// 「每卡最多一个视觉重点、次级入口用无边框文字链接」，这里的 12 颗主按钮反倒成了全页
// 最抢眼的东西。两个入口改用与结果卡「阅读 / CBETA」同一套 .s-card-action。
describe("ExternalCard 入口降为次级文字链接", () => {
  it("不再有实心主按钮，两个入口都是 .s-card-action", () => {
    const { container } = render(<ExternalCard source={source} query="金剛經" />);
    expect(container.querySelector(".s-card-btn-primary")).toBeNull();
    expect(container.querySelector(".s-card-btn")).toBeNull();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    for (const a of links) {
      expect(a).toHaveClass("s-card-action");
      expect(a).toHaveAttribute("target", "_blank");
      expect(a).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });
});
