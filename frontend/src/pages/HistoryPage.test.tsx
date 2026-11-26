import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HistoryPage from "./HistoryPage";

// 地图依赖 WebGL，jsdom 里换成只列出点的替身
vi.mock("../components/history/HistoryMap", () => ({
  default: ({ points }: { points: Array<{ label: string }> }) => <ul data-testid="map">{points.map((p) => <li key={p.label}>{p.label}</li>)}</ul>,
}));

vi.mock("../data/historyTours.json", () => ({
  default: {
    tours: [
      {
        id: "weishi",
        title: "唯識傳承",
        intro: "玄奘傳窺基。",
        steps: [
          { id: "A000294", y: 645, t: "貞觀十九年回長安譯經。", pl: [108.95, 34.27, "長安"] },
          { id: "A001019", y: 670, t: "從玄奘學。", pl: [108.95, 34.27, "大慈恩寺"] },
        ],
      },
      {
        id: "tree",
        g: "禪宗",
        title: "分叉",
        intro: "一師二徒。",
        steps: [
          { id: "A000294", y: 645, t: "師。" },
          { id: "A001019", y: 670, t: "徒一。", p: 0 },
          { id: "A001719", y: 680, t: "徒二（隔代）。", p: 0, gap: true },
        ],
      },
    ],
  },
}));
import type { HistoryData, HistoryPerson } from "../utils/historyTimeline";

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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DATA), { status: 200 })));
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
    fireEvent.click(screen.getByRole("button", { name: "唯识传承" }));
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
    expect(document.querySelector(".history-tours-gname")?.textContent).toBe("禅宗");
    expect(screen.getByText("禅宗 · 分叉")).toBeInTheDocument();
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
});
