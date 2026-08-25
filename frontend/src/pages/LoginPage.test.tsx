import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import LoginPage from "./LoginPage";

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
  // react-helmet-async 默认 defer: true，把 <title> 写入排到 requestAnimationFrame；
  // jsdom 下这个 rAF 不会自己跑，document.title 永远是空串。这里让它走宏任务。
  window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
});

describe("LoginPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    await i18n.changeLanguage("zh");
  });

  it("renders social login copy in the active UI language", () => {
    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <LoginPage />
        </MemoryRouter>
      </HelmetProvider>,
    );

    expect(screen.getByText("or continue with a third-party account")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Log in with GitHub/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Log in with Google/ })).toBeInTheDocument();
  });

  // /login 此前没有 <title>，浏览器标签、历史记录、分享卡片都显示首页标题
  //（2026-08-25 Playwright 走查实测）。
  it("sets a page-specific document title", async () => {
    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <LoginPage />
        </MemoryRouter>
      </HelmetProvider>,
    );
    await waitFor(() => expect(document.title).toMatch(/Log in|登录/));
    expect(document.title).toMatch(/FoJin|佛津/);
  });
});
