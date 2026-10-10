import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import { useAuthStore, type UserProfile } from "../stores/authStore";
import api from "../api/client";
import LoginPage from "./LoginPage";

vi.mock("../api/client", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

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

const RETURN_TO_KEY = "fojin.login.returnTo";

const fakeUser: UserProfile = {
  id: 1,
  username: "user1",
  email: "u@e.com",
  display_name: null,
  role: "user",
  is_active: true,
  created_at: "",
};

/** 落地页把自己的地址和「怎么来的」（PUSH/REPLACE）都亮出来，断言才能区分 replace。 */
function Landed({ name }: { name: string }) {
  const loc = useLocation();
  const navType = useNavigationType();
  return <div data-testid="landed">{`${name} ${loc.pathname}${loc.search} ${navType}`}</div>;
}

function renderLoginRoutes(initialPath = "/login") {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Landed name="home" />} />
          <Route path="/dictionary" element={<Landed name="dict" />} />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
}

// 生产实测（2026-10-10）：已登录用户打开 /login 仍是整张登录/注册表单，浏览器
// 还把账号密码自动填上，没有任何「你已登录」的迹象。已登录就不该停在这一页。
describe("LoginPage when already signed in", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    useAuthStore.setState({ token: null, user: null });
    sessionStorage.clear();
    vi.mocked(api.get).mockReset();
    vi.mocked(api.post).mockReset();
  });

  afterEach(async () => {
    useAuthStore.setState({ token: null, user: null });
    sessionStorage.clear();
    await i18n.changeLanguage("zh");
  });

  it("goes home (replacing /login in history) when there is no returnTo", async () => {
    useAuthStore.setState({ token: "t", user: fakeUser });
    renderLoginRoutes();

    await waitFor(() => expect(screen.getByTestId("landed")).toHaveTextContent("home / REPLACE"));
    expect(screen.queryByRole("button", { name: /Log in with GitHub/ })).not.toBeInTheDocument();
  });

  it("follows a same-site returnTo (query kept) and consumes it", async () => {
    useAuthStore.setState({ token: "t", user: fakeUser });
    sessionStorage.setItem(RETURN_TO_KEY, "/dictionary?q=般若");
    renderLoginRoutes();

    await waitFor(() =>
      expect(screen.getByTestId("landed")).toHaveTextContent("dict /dictionary?q=般若 REPLACE"),
    );
    expect(sessionStorage.getItem(RETURN_TO_KEY)).toBeNull();
  });

  it.each(["https://evil.example/", "//evil.example/path", "javascript:alert(1)"])(
    "refuses an off-site returnTo %s and goes home instead",
    async (evil) => {
      useAuthStore.setState({ token: "t", user: fakeUser });
      sessionStorage.setItem(RETURN_TO_KEY, evil);
      renderLoginRoutes();

      await waitFor(() => expect(screen.getByTestId("landed")).toHaveTextContent("home / REPLACE"));
    },
  );

  it("still shows the form to a guest", () => {
    renderLoginRoutes();

    expect(screen.queryByTestId("landed")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Log in with GitHub/ })).toBeInTheDocument();
  });

  // 只对「到达时就已登录」生效。若改成盯着实时 user，刚在本页登录成功的那一刻
  // setAuth 先让 user 变非空，这条跳转会抢在 handleLogin 自己的 navigate 之后
  // 再跑一次 consumeReturnTo() —— 那时键已被消费，于是把人从 returnTo 拽回首页。
  it("does not hijack a fresh sign-in made on this page", async () => {
    sessionStorage.setItem(RETURN_TO_KEY, "/dictionary");
    vi.mocked(api.post).mockResolvedValue({ data: { access_token: "fresh" } });
    vi.mocked(api.get).mockResolvedValue({ data: fakeUser });
    const { container } = renderLoginRoutes();

    fireEvent.change(container.querySelector("input#username")!, { target: { value: "user1" } });
    fireEvent.change(container.querySelector("input#password")!, { target: { value: "pw123456" } });
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() => expect(screen.getByTestId("landed")).toHaveTextContent("dict /dictionary"));
    // 再等一拍，确认没有第二次跳转把人拽回首页。
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("landed")).toHaveTextContent("dict /dictionary");
  });
});
