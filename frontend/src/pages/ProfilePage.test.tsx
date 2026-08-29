import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  logoutAllDevices,
} from "../api/client";

vi.mock("../api/client", () => ({
  getApiKeyStatus: vi.fn(),
  getChatQuota: vi.fn(),
  getBookmarks: vi.fn(),
  getHistory: vi.fn(),
  saveApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  changePassword: vi.fn(),
  logoutAllDevices: vi.fn(),
}));

/** 把当前 URL 渲染出来，好断言返回按钮跳去了哪。 */
function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="loc">{loc.pathname + loc.search}</span>;
}

function renderPage(ui: ReactNode, initialPath = "/profile", injected?: QueryClient) {
  // 默认 staleTime 是 0（任何情况都重取）。要复现「缓存活过登录」这类缺陷，
  // 用例必须自己注入一个带生产 staleTime 的客户端，并跨两次渲染复用它。
  const client = injected ?? new QueryClient({
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

  // 与 /chat 上那个 bug 同源（#1196）：后端对**过期 token** 返回的是游客配额
  // （limit 10），与"没带 token"一模一样。这个页面只有登录用户看得到，把那个
  // 10 填进「每日 N 次」，等于告诉一个上限 200 的人他只有 10 次——恰好是上面
  // 那段注释当初要消灭的硬编码 10。
  it("承重点: token 过期时不得把游客上限（10）当成本人上限报出来", async () => {
    useAuthStore.setState({
      token: "expired-but-still-in-localstorage",
      user: {
        id: 1, username: "reader", email: "reader@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-10T00:00:00Z",
      },
    });
    // 后端此刻返回的就是这个：游客配额 + authenticated=false
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 10, used: 0, remaining: 10, has_byok: false, authenticated: false,
    });
    const { container } = renderPage(<ProfilePage />, "/profile?tab=apikey");

    // 必须等 quota 真的落地再断言。只 findByText 兜底文案的话，初始渲染
    // （quota 还是 undefined）就已经匹配上了——断言在 query 解析前跑完，
    // 无论有没有修复都绿。实测过：撤掉修复时这条不会红。
    await waitFor(() => expect(vi.mocked(getChatQuota)).toHaveBeenCalled());
    await waitFor(() => {
      expect(container.textContent).toMatch(/Adding your own AI API key lifts the platform/);
      expect(container.textContent).not.toMatch(/free questions a day/);
    });
  });

  // 上一条只覆盖了「票死着」的那一刻。真实反馈（2026-08-18，user 638）是**重新
  // 登录之后它还在**：过期期间那份 authenticated:false 被缓存到本人 id 名下，
  // 重登后 id 没变、queryKey 没变，5 分钟 staleTime 内继续端旧答案 —— 上限又
  // 变回 10。#1199 给键加 user id 只隔开了「游客↔本人」，隔不开「本人·票已死
  // ↔ 本人·刚重新登录」。
  it("回归: 同一人重新登录后，不得继续沿用过期期间缓存的游客上限", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 5 * 60 * 1000 } },
    });
    const READER = {
      id: 638, username: "reader", email: "reader@example.com", display_name: null,
      role: "user", is_active: true, created_at: "2026-01-10T00:00:00Z",
    };

    // 阶段一：票已死，后端回游客配额，这份答案进了缓存。
    useAuthStore.setState({ token: "dead", user: READER });
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 10, used: 0, remaining: 10, has_byok: false, authenticated: false,
    });
    const first = renderPage(<ProfilePage />, "/profile?tab=apikey", client);
    await waitFor(() => expect(vi.mocked(getChatQuota)).toHaveBeenCalled());
    first.unmount();

    // 阶段二：重新登录成功——同一个人。
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 200, used: 1, remaining: 199, has_byok: false, authenticated: true,
    });
    act(() => { useAuthStore.getState().setAuth("fresh", READER); });
    const { container } = renderPage(<ProfilePage />, "/profile?tab=apikey", client);

    // 承重断言：必须看到真实上限 200，而不是缓存里那个 10。
    await waitFor(() => {
      expect(container.textContent).toMatch(/200 free questions a day/);
    });
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
  // ── 退出所有设备 ────────────────────────────────────────────────
  //
  // token 现在活 30 天且没有服务端会话表，唯一的吊销手段就是 password_version。
  // 这个按钮是长寿命 token 的安全对冲，所以它的两条承重行为都要钉住：真的调了
  // 接口，以及**把返回的新 token 存下来**——不存的话，这台设备会被自己踢掉。

  function signedIn() {
    useAuthStore.setState({
      token: "old-token",
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
  }

  async function openSecurityTabAndConfirmLogoutAll() {
    fireEvent.click(screen.getByRole("tab", { name: /Account security/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Sign out everywhere" }));
    // Popconfirm 的确认键与触发键同名，取弹层里那一个（后出现的）。
    const buttons = await screen.findAllByRole("button", { name: "Sign out everywhere" });
    await act(async () => {
      fireEvent.click(buttons[buttons.length - 1]);
    });
  }

  it("确认弹层的两个按钮都是译文，不是原始键名", async () => {
    // 上线时这里写的是 t("common.cancel")，而这个键不存在 —— i18next 把
    // 缺失键原样渲染，线上真的显示了一个写着「common.cancel」的按钮。
    // typecheck / lint / 其余用例全绿，只有真去看渲染结果才看得见。
    signedIn();
    renderPage(<ProfilePage />);

    fireEvent.click(screen.getByRole("tab", { name: /Account security/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Sign out everywhere" }));

    expect(await screen.findByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByText(/^[a-z_]+\.[a-zA-Z_]+$/)).not.toBeInTheDocument();
  });

  it("退出所有设备：调用接口并换上返回的新 token（否则当前设备被自己踢掉）", async () => {
    signedIn();
    vi.mocked(logoutAllDevices).mockResolvedValue({
      access_token: "token-at-new-version",
      token_type: "bearer",
    });

    renderPage(<ProfilePage />);
    await openSecurityTabAndConfirmLogoutAll();

    await waitFor(() => expect(logoutAllDevices).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(useAuthStore.getState().token).toBe("token-at-new-version"));
    expect(useAuthStore.getState().user?.id).toBe(1);
  });

  it("退出所有设备失败时不动本地 token —— 别把还能用的登录状态弄丢", async () => {
    signedIn();
    vi.mocked(logoutAllDevices).mockRejectedValue(new Error("boom"));

    renderPage(<ProfilePage />);
    await openSecurityTabAndConfirmLogoutAll();

    await waitFor(() => expect(logoutAllDevices).toHaveBeenCalledTimes(1));
    expect(useAuthStore.getState().token).toBe("old-token");
  });

  it("?s= 不是数字时退回 /chat，不把脏值拼进 URL", () => {
    loginAndRender("/profile?tab=apikey&from=chat&s=../../evil");
    fireEvent.click(screen.getByRole("button", { name: /Back to AI Q&A/ }));
    expect(screen.getByTestId("loc").textContent).toBe("/chat");
  });
});
