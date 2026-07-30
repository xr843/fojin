import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import ChatPage from "./ChatPage";
import { useAuthStore } from "../stores/authStore";
import {
  getApiKeyStatus,
  getChatQuota,
  getChatSessions,
  getHotQuestions,
  getMasters,
  getRandomHotQuestions,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getApiKeyStatus: vi.fn(),
    getChatQuota: vi.fn(),
    getChatSessions: vi.fn(),
    getChatSessionMessages: vi.fn(),
    getHotQuestions: vi.fn(),
    getMasters: vi.fn(),
    getRandomHotQuestions: vi.fn(),
    sendChatMessageStream: vi.fn(),
    deleteChatSession: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
    getChunkContext: vi.fn(),
  };
});

// antd (Button/Tooltip/Select) reads matchMedia via useBreakpoint under jsdom.
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

const CARDS = [
  { id: 1, category: "白话翻译" as const, display_text: "「三毒」指的是哪三种毒？" },
  { id: 2, category: "经文解读" as const, display_text: "《胜鬘经》一乘如来藏怎么讲？" },
];

const MASTERS = [
  {
    id: "huineng", name_zh: "慧能", name_en: "Huineng", tradition: "禅宗",
    dates: "638–713", description: "南宗禅。", epigraph: null,
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/chat"]}>
          <ChatPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getRandomHotQuestions).mockResolvedValue({ questions: CARDS });
  vi.mocked(getHotQuestions).mockResolvedValue({ questions: ["什么是四圣谛？"] });
  vi.mocked(getMasters).mockResolvedValue(MASTERS);
  vi.mocked(getChatSessions).mockResolvedValue([]);
  vi.mocked(getApiKeyStatus).mockResolvedValue({
    has_api_key: true, provider: "deepseek", model: null, key_preview: null,
  });
  vi.mocked(getChatQuota).mockResolvedValue({
    limit: 10, used: 0, remaining: 10, has_byok: true,
  });
  useAuthStore.setState({
    token: "t",
    user: {
      id: 1, username: "reader", email: "r@example.com", display_name: null,
      role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
    },
  });
});

afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ token: null, user: null });
});

/** 等空状态首屏就绪（建议卡片到位）后再断言结构。 */
async function renderEmpty() {
  const r = renderPage();
  await waitFor(() => {
    expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument();
  });
  return r;
}

describe("ChatPage 首屏结构", () => {
  it("空状态渲染出标题与建议卡片（脚手架自检）", async () => {
    const { container } = await renderEmpty();
    expect(screen.getByText("小津 AI 佛典问答")).toBeInTheDocument();
    expect(container.querySelector(".chat-input-shell")).not.toBeNull();
  });

  it("D1: 头部行/消息区/输入区三处各有一个 .chat-column-inner", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelectorAll(".chat-column-inner")).toHaveLength(3);
  });
});
