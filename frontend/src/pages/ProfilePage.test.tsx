import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router";
import type { ReactNode } from "react";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import ProfilePage from "./ProfilePage";
import { useAuthStore } from "../stores/authStore";
import {
  getApiKeyStatus,
  getBookmarks,
  getChatQuota,
  getHistory,
} from "../api/client";

vi.mock("../api/client", () => ({
  getApiKeyStatus: vi.fn(),
  getChatQuota: vi.fn(),
  getBookmarks: vi.fn(),
  getHistory: vi.fn(),
  saveApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  changePassword: vi.fn(),
}));

/** 把当前 URL 渲染出来，好断言返回按钮跳去了哪。 */
function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="loc">{loc.pathname + loc.search}</span>;
}

function renderPage(ui: ReactNode, initialPath = "/profile") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

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
});

describe("ProfilePage", () => {
  beforeEach(async () => {
    vi.mocked(getApiKeyStatus).mockResolvedValue({
      has_api_key: false,
      provider: null,
      model: null,
      key_preview: null,
    });
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 200, used: 3, remaining: 197, has_byok: false, authenticated: true,
    });
    vi.mocked(getBookmarks).mockResolvedValue({ total: 0, page: 1, size: 20, items: [] });
    vi.mocked(getHistory).mockResolvedValue({ total: 0, page: 1, size: 20, items: [] });
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    useAuthStore.setState({ token: null, user: null });
    await i18n.changeLanguage("zh");
  });

  it("renders the logged-out state in the active UI language", () => {
    renderPage(<ProfilePage />);

    expect(screen.getByText("Please log in first")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to log in" })).toBeInTheDocument();
  });

  it("renders profile metadata labels in the active UI language", () => {
    useAuthStore.setState({
      token: "token",
      user: {
        id: 1,
        username: "reader",
        email: "reader@example.com",
        display_name: null,
        role: "user",
        is_active: true,
        created_at: "2026-01-10T00:00:00Z",
      },
    });

    renderPage(<ProfilePage />);

    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("Personal info")).toBeInTheDocument();
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Display name")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Joined")).toBeInTheDocument();
  });

  // ── BYOK 说明里的额度数字 ─────────────────────────────────────────
  //
  // 这段文案原先硬编码「每日 10 次」——那是**匿名**用户的限额，而这个页面只有
  // 登录用户看得到（他们的实际上限是 200）。少说了 20 倍，还是注册用户唯一能
  // 看到额度的地方。根因是数字在翻译文件和后端常量里各写了一处。

  it("额度数字来自接口，不是翻译文件里的写死值", async () => {
    useAuthStore.setState({
      token: "token",
      user: {
        id: 1, username: "reader", email: "reader@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-10T00:00:00Z",
      },
    });
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 999, used: 0, remaining: 999, has_byok: false, authenticated: true,   // 故意取一个不可能写死的值
    });
    renderPage(<ProfilePage />, "/profile?tab=apikey");

    expect(await screen.findByText(/999 free questions a day/)).toBeInTheDocument();
  });

  it("拿不到额度时退回不带数字的说法，而不是显示错的数字", async () => {
    useAuthStore.setState({
      token: "token",
      user: {
        id: 1, username: "reader", email: "reader@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-10T00:00:00Z",
      },
    });
    vi.mocked(getChatQuota).mockRejectedValue(new Error("boom"));
    const { container } = renderPage(<ProfilePage />, "/profile?tab=apikey");

    await screen.findByText(/Adding your own AI API key lifts the platform/);
    // 兜底文案里一个具体次数都不该出现
    expect(container.textContent).not.toMatch(/\d+\s*(free questions|次)/);
  });

  // ── 从 /chat 来的返回入口 ──────────────────────────────────────────
  //
  // API Key 面板全站只有 /chat 的三个「配置 Key」按钮进得来，所以从那儿来的人
  // 需要一条回头路。但从头像菜单进个人中心的人不该看到它，所以判据是 from=chat。

  function loginAndRender(path: string) {
    useAuthStore.setState({
      token: "token",
      user: {
        id: 1, username: "reader", email: "reader@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-10T00:00:00Z",
      },
    });
    return renderPage(<ProfilePage />, path);
  }

  it("不是从 /chat 来时，不出现返回按钮", () => {
    loginAndRender("/profile?tab=apikey");
    expect(screen.queryByRole("button", { name: /Back to AI Q&A/ })).toBeNull();
  });

  // 承重点：必须带回原来那个会话。只跳 /chat 的话会落在空白新对话上 ——
  // 和点顶部导航没有任何区别，这个按钮也就白加了。
  it("从 /chat 带会话来时，返回按钮回到那个会话", () => {
    loginAndRender("/profile?tab=apikey&from=chat&s=42");
    fireEvent.click(screen.getByRole("button", { name: /Back to AI Q&A/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/chat?s=42");
  });

  it("从 /chat 来但没有会话（新对话未发言）时，回到 /chat", () => {
    loginAndRender("/profile?tab=apikey&from=chat");
    fireEvent.click(screen.getByRole("button", { name: /Back to AI Q&A/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/chat");
  });

  // s 来自地址栏，是可被随意编辑的输入。非数字不该被原样拼进跳转目标。
  it("?s= 不是数字时退回 /chat，不把脏值拼进 URL", () => {
    loginAndRender("/profile?tab=apikey&from=chat&s=../../evil");
    fireEvent.click(screen.getByRole("button", { name: /Back to AI Q&A/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/chat");
  });
});
