import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import NotFoundPage from "./NotFoundPage";

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
  // react-helmet-async 默认把 head 写入排到 rAF；jsdom 不跑 rAF，改走宏任务。
  window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
});

function SearchLanded() {
  const loc = useLocation();
  return <div data-testid="search-landed">{loc.pathname + loc.search}</div>;
}

function renderNotFound() {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={["/no-such-page"]}>
        <Routes>
          <Route path="/search" element={<SearchLanded />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
}

// 生产实测（2026-10-10）：404 页是 antd Result 的默认插画（蓝问号、蓝裤子小人、
// 绿仙人掌），唯一出口是「返回首页」，且 <meta robots> 仍是 index.html 的
// "index, follow" —— nginx 对未知路由回 200，这一页等于一个可被收录的软 404。
describe("NotFoundPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    await i18n.changeLanguage("zh");
    document.head.querySelectorAll("meta[name='robots'][data-rh]").forEach((m) => m.remove());
  });

  it("drops the stock antd illustration", () => {
    const { container } = renderNotFound();
    expect(container.querySelector(".ant-result")).toBeNull();
  });

  it("tells crawlers not to index it and gets its own title", async () => {
    renderNotFound();
    await waitFor(() =>
      expect(document.head.querySelector("meta[name='robots'][content='noindex']")).not.toBeNull(),
    );
    expect(document.title).toMatch(/not found/i);
    expect(document.title).toMatch(/FoJin|佛津/);
  });

  it("offers the main sections as real links", () => {
    renderNotFound();
    const hrefs = screen
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining(["/", "/chat", "/dictionary", "/sources"]));
  });

  it("searches the site from the 404 page", async () => {
    renderNotFound();
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "金刚经 般若" } });
    fireEvent.keyDown(box, { key: "Enter", code: "Enter", keyCode: 13 });
    await waitFor(() =>
      expect(screen.getByTestId("search-landed")).toHaveTextContent(
        `/search?q=${encodeURIComponent("金刚经 般若")}`,
      ),
    );
  });

  it("ignores an empty search instead of landing on a blank results page", () => {
    renderNotFound();
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "   " } });
    fireEvent.keyDown(box, { key: "Enter", code: "Enter", keyCode: 13 });
    expect(screen.queryByTestId("search-landed")).toBeNull();
  });
});
