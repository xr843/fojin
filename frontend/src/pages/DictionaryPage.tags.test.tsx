import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import DictionaryPage from "./DictionaryPage";
import type { DictEntry, DictGroupedResult, DictSourceInfo } from "../api/client";
import {
  getDictionarySources,
  searchDictionaryGrouped,
  getDictConcept,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getDictionarySources: vi.fn(),
    searchDictionaryGrouped: vi.fn(),
    getDictConcept: vi.fn(),
  };
});

// 与生产 /api/dictionary/sources 的真实形状一致（2026-10-10 取样）：
// 佛光登记的语言是 zh，但词条 lang 实际是 lzh —— 两者都显示为「中文」。
const SOURCES: DictSourceInfo[] = [
  { id: 1, code: "foguang", name_zh: "佛光大辭典", name_en: null, entry_count: 32132, languages: ["zh"], base_url: null },
  { id: 2, code: "dpd-dict", name_zh: "数字巴利辞典 DPD", name_en: null, entry_count: 88785, languages: ["pi", "en"], base_url: null },
  { id: 3, code: "84000-glossary", name_zh: "84000翻译术语表", name_en: null, entry_count: 25356, languages: ["bo", "en"], base_url: null },
];

let nextId = 1;
function entry(source_code: string, source_name: string, lang: string, headword: string): DictEntry {
  return { id: nextId++, headword, reading: null, definition: `${headword} 释义`, lang, source_code, source_name } as DictEntry;
}

function group(source_code: string, source_name: string, entries: DictEntry[]): DictGroupedResult {
  return { source_code, source_name, total: entries.length, entries };
}

function renderWith(groups: DictGroupedResult[], sources: DictSourceInfo[] = SOURCES) {
  vi.mocked(getDictionarySources).mockResolvedValue(sources);
  vi.mocked(searchDictionaryGrouped).mockResolvedValue({ total: 9, page: 1, page_size: 20, groups } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dictionary?q=x"]}>
          <DictionaryPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

/** 每个词条里出现的标签文字，按分组返回。 */
function tagsByGroup(container: HTMLElement): string[][][] {
  return [...container.querySelectorAll(".dict-group")].map((g) =>
    [...g.querySelectorAll(".dict-entry-item")].map((item) =>
      [...item.querySelectorAll(".ant-tag")].map((t) => t.textContent ?? ""),
    ),
  );
}

beforeEach(() => {
  nextId = 1;
  vi.mocked(getDictConcept).mockResolvedValue(null as never);
});

/**
 * 按辞典分组的视图里，分组标题已经写着辞典名（「佛光大辭典 100」），
 * 每条再挂一个「佛光大辭典」标签、一个「中文」标签是纯噪音：生产实测
 * 「般若」一屏 40 条词条挂了 80 个 11px 标签，没有一个带来新信息。
 * 标签只在它说了分组标题没说的事时才出现。
 */
describe("分组视图里的词条标签", () => {
  it("同一辞典、语言就是辞典默认语言：词条既不重复辞典名，也不挂语言标签", async () => {
    const { container } = renderWith([
      group("foguang", "佛光大辭典", [
        entry("foguang", "佛光大辭典", "lzh", "般若"),
        entry("foguang", "佛光大辭典", "lzh", "般若學"),
      ]),
    ]);
    await waitFor(() => expect(container.querySelectorAll(".dict-entry-item")).toHaveLength(2));
    // sources 晚到时也要收敛到无标签
    await waitFor(() => expect(tagsByGroup(container)).toEqual([[[], []]]));
  });

  it("分组内语言不唯一时，每条都标出语言（但仍不重复辞典名）", async () => {
    const { container } = renderWith([
      group("dpd-dict", "数字巴利辞典 DPD", [
        entry("dpd-dict", "数字巴利辞典 DPD", "pi", "dhamma"),
        entry("dpd-dict", "数字巴利辞典 DPD", "en", "dharma"),
      ]),
    ]);
    await waitFor(() => expect(container.querySelectorAll(".dict-entry-item")).toHaveLength(2));
    await waitFor(() => expect(tagsByGroup(container)).toEqual([[["巴利文"], ["英文"]]]));
  });

  it("分组内语言唯一但不是该辞典的默认语言时，仍标出语言", async () => {
    // 生产真实情况：84000 登记为藏/英，搜 dharma 命中的全是 en 词条。
    const { container } = renderWith([
      group("84000-glossary", "84000翻译术语表", [entry("84000-glossary", "84000翻译术语表", "en", "dharma")]),
    ]);
    await waitFor(() => expect(container.querySelectorAll(".dict-entry-item")).toHaveLength(1));
    await waitFor(() => expect(tagsByGroup(container)).toEqual([[["英文"]]]));
  });

  it("词条来源与分组不一致时，辞典名标签照常显示", async () => {
    const { container } = renderWith([
      group("foguang", "佛光大辭典", [entry("dpd-dict", "数字巴利辞典 DPD", "lzh", "般若")]),
    ]);
    await waitFor(() => expect(container.querySelectorAll(".dict-entry-item")).toHaveLength(1));
    await waitFor(() => expect(tagsByGroup(container)).toEqual([[["数字巴利辞典 DPD"]]]));
  });

  it("拿不到辞典信息时不猜默认语言，语言标签照常显示", async () => {
    const { container } = renderWith(
      [group("foguang", "佛光大辭典", [entry("foguang", "佛光大辭典", "lzh", "般若")])],
      [],
    );
    await waitFor(() => expect(container.querySelectorAll(".dict-entry-item")).toHaveLength(1));
    await waitFor(() => expect(tagsByGroup(container)).toEqual([[["中文"]]]));
  });
});
