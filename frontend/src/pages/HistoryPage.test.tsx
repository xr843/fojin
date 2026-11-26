import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HistoryPage from "./HistoryPage";
import type { HistoryData, HistoryPerson } from "../utils/historyTimeline";

function person(over: Partial<HistoryPerson>): HistoryPerson {
  return { id: "A0", n: "某", dn: "某", alt: [], dy: "唐", b: null, d: null, monk: true, tr: false, bio: "", te: [], st: [], bios: [], men: [], works: [], wn: 0, ...over };
}

const DATA: HistoryData = {
  source: "DILA", source_url: "", license: "CC BY-SA 3.0", license_url: "",
  people: [
    person({
      id: "A000294", n: "玄奘", dn: "玄奘", b: [602, 603], d: [664, 664], tr: true, wn: 78, st: ["A001019"],
      bio: "俗姓陳，唯識宗創始人。",
      bios: [{ t: "唐高僧傳 · 釋玄奘傳", u: "/texts/71/read?juan=4&anchor=p0446c08", lh: "T50n2060_p0446c08" }],
      works: [{ t: "成唯識論", c: "T1585", u: "/texts/44" }],
    }),
    person({ id: "A001019", n: "窺基", dn: "窺基", b: [632, 632], d: [682, 682], te: ["A000294"] }),
    person({ id: "A001719", n: "慧能", dn: "惠能", b: [638, 638], d: [713, 713] }),
    person({ id: "A000366", n: "安世高", dn: "安清", dy: "東漢", tr: true, wn: 34, bio: "建和二年（148），至洛陽譯經" }),
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
});
