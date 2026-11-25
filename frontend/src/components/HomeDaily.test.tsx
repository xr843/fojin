import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import HomeDaily from "./HomeDaily";
import { pickDaily } from "../utils/dailyPassage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => (k === "daily.home_tag" ? "今日经句" : k), i18n: { language: "zh" } }),
}));

describe("首页今日经句", () => {
  it("直接显示当天经句（简体）与经名，整块链到 /daily", () => {
    const { passage } = pickDaily(new Date());
    render(
      <MemoryRouter>
        <HomeDaily />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/daily");
    expect(link.textContent).toContain(passage.text_hans);
    expect(link.textContent).toContain(`《${passage.title_hans}》`);
  });
});
