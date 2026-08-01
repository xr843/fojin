import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import ShareCard from "./ShareCard";
import { createSharedQA, type ChatSource } from "../api/client";

vi.mock("../api/client", () => ({
  createSharedQA: vi.fn(),
}));

vi.mock("qrcode", () => ({
  default: {
    toDataURL: vi.fn(() => Promise.resolve("data:image/png;base64,qr")),
  },
}));

vi.mock("html2canvas-pro", () => ({
  default: vi.fn(),
}));

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

describe("ShareCard", () => {
  const source: ChatSource = {
    text_id: 1 as ChatSource["text_id"],
    juan_num: 1,
    chunk_text: "Gate gate.",
    score: 0.9,
    title_zh: "般若波罗蜜多心经",
  };

  beforeEach(async () => {
    vi.mocked(createSharedQA).mockResolvedValue({
      id: "qa_1",
      url: "https://fojin.app/share/qa_1",
    });
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("zh");
  });

  it("renders chrome and generated share-card labels in the active UI language", async () => {
    render(
      <ShareCard
        open
        onClose={() => {}}
        question="What is emptiness?"
        answer="Form is emptiness."
        sources={[source]}
      />,
    );

    expect(await screen.findByText("Share this Buddhist Q&A")).toBeInTheDocument();
    // 二维码那块由 `{qrDataUrl && …}` 守着，而 qrDataUrl 来自 QRCode.toDataURL()
    // 这个 Promise（ShareCard.tsx:118/355）—— 它比模态框标题晚到。只等标题就同步
    // 断言它，谁先到全看时序：实测 24 轮全量里红了 1 轮（约 4%），报错时 DOM 还停在
    // ant-zoom-appear-prepare。所以这里要等**最后到的那个**，而不是加 sleep。
    expect(await screen.findByText("Scan to open")).toBeInTheDocument();
    expect(screen.getByText("AI Buddhist Q&A · Source-based answers")).toBeInTheDocument();
    expect(screen.getByText("Question")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByText("Sources Cited")).toBeInTheDocument();
    expect(screen.getByText(/Global Buddhist Classics Digital Resource Platform/)).toBeInTheDocument();
    expect(screen.getByText("Download image")).toBeInTheDocument();
    expect(screen.getByText("Copy image")).toBeInTheDocument();
    expect(screen.getByText("Copy link")).toBeInTheDocument();
    expect(screen.getByText(/Fascicle 1/)).toBeInTheDocument();

    await waitFor(() => expect(createSharedQA).toHaveBeenCalledTimes(1));
  });
});
