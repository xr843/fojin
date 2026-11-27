import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HistoryPage from "./HistoryPage";

// 地图依赖 WebGL，jsdom 里换成只列出点的替身
vi.mock("../utils/shareCard", () => ({
  renderShareCard: vi.fn(async () => new Blob(["png"], { type: "image/png" })),
}));
vi.mock("../components/history/HistoryMap", () => ({
  default: ({ points }: { points: Array<{ label: string }> }) => <ul data-testid="map">{points.map((p) => <li key={p.label}>{p.label}</li>)}</ul>,
}));

vi.mock("../data/historyTours.json", () => ({
  default: {
    tours: [
      {
        id: "weishi",
        group: "school",
        short: "唯識",
        title: "唯識傳承",
        intro: "玄奘傳窺基。",
        steps: [
          { id: "A000294", y: 645, t: "貞觀十九年回長安譯經。", pl: [108.95, 34.27, "長安"] },
          { id: "A001019", y: 670, t: "從玄奘學。", pl: [108.95, 34.27, "大慈恩寺"] },
        ],
      },
      {
        id: "tree",
        group: "school",
        short: "樹宗",
        family: "tree",
        branch: "主幹",
        title: "分叉",
        intro: "一師二徒。",
        steps: [
          { id: "A000294", y: 645, t: "師。" },
          { id: "A001019", y: 670, t: "徒一。", p: 0 },
          { id: "A001719", y: 680, t: "徒二（隔代）。", p: 0, gap: true },
        ],
      },
      {
        id: "roots",
        group: "school",
        short: "雙源",
        title: "兩個源頭",
        intro: "兩位初祖。",
        steps: [
          { id: "A000294", y: 645, t: "源一。" },
          { id: "A001719", y: 680, t: "源二。", p: -1 },
          { id: "A001019", y: 670, t: "源一之徒。", p: 0 },
        ],
      },
      {
        id: "tree2",
        group: "school",
        family: "tree",
        branch: "旁支",
        title: "旁支",
        intro: "只有窺基一站。",
        steps: [{ id: "A001019", y: 670, t: "窺基。" }],
      },
    ],
  },
}));
import type { HistoryData, HistoryPerson, TranslationData } from "../utils/historyTimeline";

function person(over: Partial<HistoryPerson>): HistoryPerson {
  return { id: "A0", n: "某", dn: "某", alt: [], dy: "唐", sc: "禅", b: null, d: null, monk: true, tr: false, bio: "", te: [], st: [], bios: [], men: [], works: [], wn: 0, ...over };
}

const DATA: HistoryData = {
  source: "DILA", source_url: "", license: "CC BY-SA 3.0", license_url: "",
  people: [
    person({
      id: "A000294", n: "玄奘", dn: "玄奘", sc: "唯识", b: [602, 603], d: [664, 664], tr: true, wn: 78, st: ["A001019"],
      bio: "俗姓陳，唯識宗創始人。",
      o: [112.821, 34.581, "緱氏", "high"],
      bu: [108.95, 34.15, "樊川", "high"],
      bios: [{ t: "唐高僧傳 · 釋玄奘傳", u: "/texts/71/read?juan=4&anchor=p0446c08", lh: "T50n2060_p0446c08" }],
      works: [{ t: "成唯識論", c: "T1585", u: "/texts/44" }],
    }),
    person({ id: "A001019", n: "窺基", dn: "窺基", sc: "唯识", b: [632, 632], d: [682, 682], te: ["A000294"], o: [108.9, 34.3, "長安", "high"] }),
    person({ id: "A001719", n: "慧能", dn: "惠能", b: [638, 638], d: [713, 713] }),
    person({ id: "A000366", n: "安世高", dn: "安清", dy: "東漢", sc: "译经", tr: true, wn: 34, bio: "建和二年（148），至洛陽譯經" }),
  ],
};

function Loc() {
  const l = useLocation();
  return <div data-testid="loc">{l.pathname + l.search}</div>;
}

function renderPage(url = "/history") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[url]}>
          <HistoryPage />
          <Loc />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

const TR: TranslationData = {
  source: "開元錄",
  kaiyuan: 76,
  cbeta: "T55n2154",
  items: [
    { y: 403, t: "摩訶般若波羅蜜經", j: "四十卷", w: "鳩摩羅什", h: "弘始五年癸卯四月二十三日出", ju: 4, lh: "0512b04", tid: 6 },
    { y: 406, t: "維摩詰所說經", j: "三卷", w: "鳩摩羅什", h: "弘始八年", ju: 4, lh: "0512b20" },
    { y: 645, t: "大菩薩藏經", j: "二十卷", w: "玄奘", h: "貞觀十九年", ju: 8, lh: "0555b01", tid: 9 },
  ],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => new Response(JSON.stringify(String(url).includes("translations") ? TR : DATA), { status: 200 })),
  );
  Element.prototype.scrollTo = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

describe("佛教史长卷", () => {
  it("每个人画成一条，显示通称（DILA 正名「惠能」显示为「慧能」）", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: "玄奘" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "慧能" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "安世高" })).toBeInTheDocument();
  });

  it("点名字：弹出人物卡，有僧传原文、著译链接，网址带上 ?p= 可分享", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "玄奘" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "唐高僧传 · 释玄奘传" })).toHaveAttribute("href", "/texts/71/read?juan=4&anchor=p0446c08");
    expect(within(dialog).getByRole("link", { name: "成唯识论" })).toHaveAttribute("href", "/texts/44");
    expect(within(dialog).getByText(/約602–664|约602–664/)).toBeInTheDocument();
    expect(screen.getByTestId("loc").textContent).toContain("p=A000294");
  });

  it("人物卡里点弟子：换成弟子的卡片", async () => {
    renderPage("/history?p=A000294");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "窥基" }));
    expect(screen.getByTestId("loc").textContent).toContain("p=A001019");
  });

  it("深链 ?y=650：列出那一年在世的人（只知朝代的不算）", async () => {
    renderPage("/history?y=650");
    await screen.findByText(/公元 650 年 · 唐 · 在世 3 位/);
    const bar = document.querySelector(".history-cursor-bar") as HTMLElement;
    expect(within(bar).getByRole("button", { name: "玄奘" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "窥基" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "慧能" })).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "安世高" })).toBeNull();
  });

  it("只看译经师：非译经师的条子隐藏", async () => {
    renderPage();
    await screen.findByRole("button", { name: "慧能" });
    fireEvent.click(screen.getByText("只看译经师"));
    expect(screen.queryByRole("button", { name: "慧能" })).toBeNull();
    expect(screen.getByRole("button", { name: "玄奘" })).toBeInTheDocument();
  });

  it("默认按宗派分泳道，?v=time 按年代混排", async () => {
    const { unmount } = renderPage();
    await screen.findByRole("button", { name: "玄奘" });
    const labels = [...document.querySelectorAll(".history-lane-label")].map((e) => e.textContent);
    expect(labels).toEqual(["译经1", "唯识2", "禅1"]);
    unmount();
    renderPage("/history?v=time");
    await screen.findByRole("button", { name: "玄奘" });
    expect(document.querySelectorAll(".history-lane-label")).toHaveLength(0);
  });

  it("选中一个人：画出到师、弟子的连线（弟子虚线）", async () => {
    renderPage("/history?p=A000294");
    await screen.findByRole("dialog");
    const paths = document.querySelectorAll(".history-lineage path");
    expect(paths).toHaveLength(1);
    expect(paths[0].getAttribute("class")).toBe("history-lineage-st");
  });

  it("导览：点路线 → 说明栏显示第 1 站，路线上的人标序号、其余变淡；下一站 / 方向键换站；退出", async () => {
    renderPage();
    await screen.findByRole("button", { name: "玄奘" });
    fireEvent.click(screen.getByRole("button", { name: "唯识" }));
    expect(screen.getByTestId("loc").textContent).toContain("tour=weishi");
    expect(await screen.findByText("第 1 / 2 站")).toBeInTheDocument();
    expect(screen.getByText("贞观十九年回长安译经。")).toBeInTheDocument();
    expect(document.querySelectorAll(".history-tour-num")).toHaveLength(2);
    expect(document.querySelector(".history-bar.is-tour-current")?.textContent).toContain("玄奘");
    const huineng = screen.getAllByRole("button", { name: "慧能" }).find((b) => b.classList.contains("history-bar"));
    expect(huineng?.className).toContain("is-dim");

    fireEvent.click(screen.getByRole("button", { name: "下一站" }));
    expect(await screen.findByText("第 2 / 2 站")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一站" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(await screen.findByText("第 1 / 2 站")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出导览" }));
    expect(screen.getByTestId("loc").textContent).not.toContain("tour=");
    expect(document.querySelectorAll(".history-tour-num")).toHaveLength(0);
  });

  it("分叉路线：每站连到自己的师（p），隔代画虚线；同组路线收在组名下", async () => {
    renderPage("/history?tour=tree");
    await screen.findByText("第 1 / 3 站");
    await waitFor(() => expect(document.querySelectorAll(".history-tour-num")).toHaveLength(3));
    const paths = [...document.querySelectorAll(".history-tour-path path")];
    expect(paths).toHaveLength(2);
    expect(paths.filter((x) => x.getAttribute("class") === "history-tour-gap")).toHaveLength(1);
    // 两条边都从同一个起点（玄奘）出发
    const starts = paths.map((x) => x.getAttribute("d")?.split(" C")[0]);
    expect(new Set(starts).size).toBe(1);
    // 同一家族只露一个按钮（树宗），说明栏标题是「家族短名 · 支线」，支线在说明栏里切换
    expect(screen.queryByRole("button", { name: "旁支" })).toBeInTheDocument();
    expect([...document.querySelectorAll(".history-tours button")].map((b) => b.textContent)).toEqual(["唯识", "树宗", "双源"]);
    expect(screen.getByText("树宗 · 主干")).toBeInTheDocument();
    // 切到旁支：树宗按钮仍是选中态；主干上的玄奘、慧能不变淡（同一家族），窥基是当前支线
    fireEvent.click(screen.getByRole("button", { name: "旁支" }));
    expect(screen.getByTestId("loc").textContent).toContain("tour=tree2");
    expect(screen.getByRole("button", { name: "树宗" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(document.querySelector(".history-bar.is-tour-current")?.textContent).toContain("窥基"));
    expect([...document.querySelectorAll(".history-bar.is-family")].map((b) => b.textContent).join()).toMatch(/玄奘/);
  });

  it("地图跟着变：平时标籍贯；点年份标那年在世的人；选中人标籍贯、葬地与师承；导览标各站地点", async () => {
    const { unmount } = renderPage();
    await screen.findByText(/高僧籍贯分布/);
    expect(within(screen.getByTestId("map")).getAllByRole("listitem")).toHaveLength(2); // 两人有籍贯
    unmount();

    const r2 = renderPage("/history?y=650");
    await screen.findByText("公元 650 年在世的人 · 标在籍贯");
    expect(within(screen.getByTestId("map")).getByText("玄奘")).toBeInTheDocument();
    r2.unmount();

    const r3 = renderPage("/history?p=A000294");
    await screen.findByRole("dialog");
    const m3 = within(await screen.findByTestId("map"));
    expect(m3.getByText("玄奘 · 籍贯 缑氏")).toBeInTheDocument();
    expect(m3.getByText("葬 樊川")).toBeInTheDocument();
    expect(m3.getByText("窥基")).toBeInTheDocument();
    r3.unmount();

    renderPage("/history?tour=weishi&s=1");
    const m4 = within(await screen.findByTestId("map"));
    expect(m4.getByText("玄奘 · 长安")).toBeInTheDocument();
    expect(m4.getByText("窥基 · 大慈恩寺")).toBeInTheDocument();
  });

  it("播放年代：从公元 60 年起每拍前进 5 年，暂停后停住；空格键也能播放", async () => {
    renderPage();
    await screen.findAllByRole("button", { name: "玄奘" });
    fireEvent.click(screen.getByRole("button", { name: /播放年代/ }));
    const loc = () => screen.getByTestId("loc").textContent ?? "";
    await waitFor(() => expect(loc()).toContain("y=60"));
    await waitFor(() => expect(loc()).toContain("y=65"), { timeout: 2000 });
    fireEvent.click(screen.getByRole("button", { name: /暂停/ }));
    const y = new URLSearchParams(screen.getByTestId("loc").textContent!.split("?")[1]).get("y");
    await new Promise((r) => setTimeout(r, 700));
    expect(new URLSearchParams(screen.getByTestId("loc").textContent!.split("?")[1]).get("y")).toBe(y);
    fireEvent.keyDown(window, { key: " " });
    expect(await screen.findByRole("button", { name: /暂停/ })).toBeInTheDocument();
  });

  it("p=-1：路线里另一个源头，不连线（密宗有善无畏、金刚智两位初祖）", async () => {
    renderPage("/history?tour=roots");
    await waitFor(() => expect(document.querySelectorAll(".history-tour-num")).toHaveLength(3));
    // 三站只有一条线：源一 → 源一之徒；源二不连
    expect(document.querySelectorAll(".history-tour-path path")).toHaveLength(1);
  });

  it("大事：顶部标记点开 → 跳到那一年，面板显示原文与出处链接；上一件 / 下一件；点空白处关闭", async () => {
    renderPage();
    await screen.findAllByRole("button", { name: "玄奘" });
    fireEvent.click(screen.getByRole("button", { name: "会昌法难" }));
    const loc = () => screen.getByTestId("loc").textContent ?? "";
    expect(loc()).toContain("e=huichang");
    expect(loc()).toContain("y=845");
    const panel = document.querySelector(".history-event-panel") as HTMLElement;
    expect(panel.querySelector(".history-event-quote")?.textContent).toContain("毁拆天下寺院");
    expect(within(panel).getByRole("link", { name: /《佛祖统纪》卷54/ }).getAttribute("href")).toMatch(/^\/texts\/\d+\/read\?juan=54&anchor=p0471b10/);
    fireEvent.click(within(panel).getByRole("button", { name: "下一件" }));
    expect(loc()).toContain("e=kaibao");
    fireEvent.click(document.querySelector(".history-canvas")!, { clientX: 300 });
    expect(loc()).not.toContain("e=");
    expect(document.querySelector(".history-event-panel")).toBeNull();
  });

  it("播放年代走到大事那一年会停下并打开它（公元 67 年永平求法）", async () => {
    renderPage("/history?y=55");
    await screen.findAllByRole("button", { name: "玄奘" });
    fireEvent.click(screen.getByRole("button", { name: /播放年代/ }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("e=yongping"), { timeout: 3000 });
    expect(screen.getByTestId("loc").textContent).toContain("y=67");
    fireEvent.click(screen.getByRole("button", { name: /暂停/ }));
  });

  it("导览中点大事：退出导览、显示大事面板（11-27 用户截图：导览说明栏压住了大事）；再开导览清掉大事", async () => {
    renderPage("/history?tour=weishi&s=1");
    await screen.findByText("第 2 / 2 站");
    await screen.findAllByRole("button", { name: /玄奘/ });
    fireEvent.click(screen.getByRole("button", { name: "会昌法难" }));
    const loc = () => screen.getByTestId("loc").textContent ?? "";
    expect(loc()).toContain("e=huichang");
    expect(loc()).not.toContain("tour=");
    expect(document.querySelector(".history-tour-panel")).toBeNull();
    expect(document.querySelector(".history-event-panel")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "唯识" }));
    expect(loc()).toContain("tour=weishi");
    expect(loc()).not.toContain("e=");
  });

  it("译经长河：每格是开元录记了年份的经；点一格列出这十年的经，有读经链接和开元录原文行；上一个十年；再点关掉", async () => {
    renderPage("/history?tour=weishi");
    await screen.findAllByRole("button", { name: "玄奘" });
    const loc = () => screen.getByTestId("loc").textContent ?? "";
    const bar = await screen.findByRole("button", { name: /^400–409 年 .* 译出 2 部$/ });
    fireEvent.click(bar);
    expect(loc()).toContain("r=400");
    expect(loc()).not.toContain("tour=");
    const panel = document.querySelector(".history-river-panel") as HTMLElement;
    expect(within(panel).getByRole("link", { name: "《摩诃般若波罗蜜经》" }).getAttribute("href")).toBe("/texts/6/read");
    // 没对上藏内经典的只列名，不给读经链接
    expect(within(panel).queryByRole("link", { name: "《维摩诘所说经》" })).toBeNull();
    // 夹注原文直接显示（佛津阅读页不显示夹注），出处链到 CBETA Online 那一行
    expect(panel.textContent).toContain("「弘始五年癸卯四月二十三日出」");
    expect(within(panel).getAllByRole("link", { name: /开元录卷4/ }).map((x) => x.getAttribute("href"))).toEqual([
      "https://cbetaonline.dila.edu.tw/zh/T55n2154_p0512b04",
      "https://cbetaonline.dila.edu.tw/zh/T55n2154_p0512b20",
    ]);
    expect(within(panel).getByRole("button", { name: "上一个十年" })).toBeDisabled();
    fireEvent.click(within(panel).getByRole("button", { name: "下一个十年" }));
    expect(loc()).toContain("r=640");
    fireEvent.click(screen.getByRole("button", { name: /^640–649 年/ }));
    expect(loc()).not.toContain("r=");
    expect(document.querySelector(".history-river-panel")).toBeNull();
  });

  it("分享：大事面板点「分享」出预览图；「复制链接」复制带 ?e= 的深链", async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderPage("/history?e=huichang&y=845");
    await screen.findAllByRole("button", { name: "玄奘" });
    const panel = document.querySelector(".history-event-panel") as HTMLElement;
    fireEvent.click(within(panel).getByRole("button", { name: /分享/ }));
    const img = await screen.findByRole("img", { name: /会昌法难/ });
    expect(img.getAttribute("src")).toMatch(/^data:image\/png/);
    fireEvent.click(screen.getByRole("button", { name: "复制链接" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/history\?e=huichang$/)));
  });

  it("选了年份：在世的人在长卷可见区下方时，长卷下边缘提示「下方还有 N 位在世」，点了滚过去；泳道标签显示本年人数", async () => {
    // jsdom 没有布局：让长卷可见区只够露出表头加第一行
    const ch = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return (this as HTMLElement).classList?.contains("history-scroll") ? 230 : 0;
      },
    });
    try {
      renderPage("/history?y=650");
      await screen.findAllByRole("button", { name: "玄奘" });
      const hint = await screen.findByRole("button", { name: /下方还有 \d+ 位在世/ });
      const scrollTo = Element.prototype.scrollTo as unknown as ReturnType<typeof vi.fn>;
      scrollTo.mockClear();
      fireEvent.click(hint);
      expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: expect.any(Number) }));
      expect(document.querySelectorAll(".history-lane-alive").length).toBeGreaterThan(0);
    } finally {
      if (ch) Object.defineProperty(HTMLElement.prototype, "clientHeight", ch);
    }
  });
});

