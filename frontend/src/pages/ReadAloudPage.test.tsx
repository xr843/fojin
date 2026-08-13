import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";

import ReadAloudPage from "./ReadAloudPage";
import { formatDuration } from "../audio/format";
import * as client from "../api/client";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // 把插值也带出来，否则「{{n}} 卷」这类键测不出数字是否传对
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "n" in opts ? `${key}:${opts.n}` : key,
    i18n: { language: "zh" },
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ReadAloudPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

const XINJING = {
  text_id: 9,
  title_zh: "般若波羅蜜多心經",
  translator: "玄奘",
  dynasty: "唐",
  taisho_id: "T0251",
  engine: "minimax",
  juan_count: 1,
  total_duration_ms: 101_363,
  juans: [{ juan_num: 1, duration_ms: 101_363, url: "/audio/9/1-7891dd17.mp3" }],
};

const DIZANG = {
  text_id: 24,
  title_zh: "地藏菩薩本願經",
  translator: "實叉難陀",
  dynasty: "唐",
  taisho_id: "T0412",
  engine: "minimax",
  juan_count: 2,
  total_duration_ms: 5_940_000,
  juans: [
    { juan_num: 1, duration_ms: 3_000_000, url: "/audio/24/1-aaaa.mp3" },
    { juan_num: 2, duration_ms: 2_940_000, url: "/audio/24/2-bbbb.mp3" },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("formatDuration", () => {
  it("不足一小时用 m:ss", () => {
    expect(formatDuration(101_363)).toBe("1:41");
    expect(formatDuration(9_000)).toBe("0:09");
  });

  it("超过一小时用 h:mm:ss —— 壇經一卷 134 分钟，写成「134:00」没人看得懂", () => {
    expect(formatDuration(5_940_000)).toBe("1:39:00");
    expect(formatDuration(8_040_000)).toBe("2:14:00");
  });

  it("四舍五入到秒，不出现小数", () => {
    expect(formatDuration(1_600)).toBe("0:02");
  });
});

describe("ReadAloudPage", () => {
  it("列出可听的经，链接落到阅读页（播放器与逐句高亮都在那里）", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [XINJING] });
    renderPage();
    // ⚠️ 库里存的是繁体，简体语境下 localizeHan 会转 —— 断言必须写转换后的形态，
    //    否则这条用例只是在测「我记不记得数据库是繁体的」。
    const link = await screen.findByText("般若波罗蜜多心经");
    expect(link.closest("a")).toHaveAttribute("href", "/texts/9/read?juan=1");
    expect(screen.getByText("1:41")).toBeInTheDocument();
  });

  it("繁体经名按当前语境转写 —— 简体用户不该看到「般若波羅蜜多心經」", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [XINJING] });
    renderPage();
    await screen.findByText("般若波罗蜜多心经");
    expect(screen.queryByText("般若波羅蜜多心經")).not.toBeInTheDocument();
  });

  it("译者与朝代一并显示 —— 同一部经常有多个译本，不写清楚点不对", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [XINJING] });
    renderPage();
    expect(await screen.findByText(/唐 玄奘/)).toBeInTheDocument();
    expect(screen.getByText(/T0251/)).toBeInTheDocument();
  });

  it("多卷时给出逐卷直达", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [DIZANG] });
    renderPage();
    expect(await screen.findByText("readaloud.juan:1")).toBeInTheDocument();
    const j2 = screen.getByText("readaloud.juan:2");
    expect(j2.closest("a")).toHaveAttribute("href", "/texts/24/read?juan=2");
  });

  it("单卷不渲染卷次直达 —— 只有一颗按钮的空行是噪音", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [XINJING] });
    renderPage();
    await screen.findByText("般若波罗蜜多心经");
    expect(screen.queryByText("readaloud.juan:1")).not.toBeInTheDocument();
  });

  it("诚信标注必须在页首出现，而不是只藏在播放条里", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 1, items: [XINJING] });
    renderPage();
    expect(await screen.findByText("readaloud.synthetic_notice")).toBeInTheDocument();
  });

  it("空目录显示空态而不是崩掉", async () => {
    vi.spyOn(client, "getAvailableAudio").mockResolvedValue({ total: 0, items: [] });
    renderPage();
    expect(await screen.findByText("readaloud.empty")).toBeInTheDocument();
  });
});
