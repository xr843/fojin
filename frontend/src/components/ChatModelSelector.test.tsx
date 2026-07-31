import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ChatModelSelector from "./ChatModelSelector";
import { fetchChatModels, type ChatModelOption } from "../api/chatModels";

vi.mock("../api/chatModels", async () => {
  const actual = await vi.importActual<typeof import("../api/chatModels")>("../api/chatModels");
  return { ...actual, fetchChatModels: vi.fn() };
});

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

function model(over: Partial<ChatModelOption> & { id: string }): ChatModelOption {
  return {
    provider: "deepseek", label: over.id, description: "", vision: false,
    available: true, requires_byok: false, ...over,
  };
}

/** 目录里多数厂商没有平台 Key，所以 available 为假的是常态而非例外。 */
const CATALOG: ChatModelOption[] = [
  model({ id: "deepseek:v4-pro", label: "DeepSeek V4 Pro" }),
  model({ id: "deepseek:v4-flash", label: "DeepSeek V4 Flash" }),
  model({ id: "moonshot:kimi-k3", label: "Kimi K3", provider: "moonshot", available: false, requires_byok: true }),
  model({ id: "openai:gpt-5.6-sol", label: "GPT-5.6 Sol", provider: "openai", available: false, requires_byok: true }),
  model({ id: "gemini:gemini-3.6-flash", label: "Gemini 3.6 Flash", provider: "gemini", available: false, requires_byok: true }),
];

async function openDropdown() {
  const { container } = render(
    <ChatModelSelector value="deepseek:v4-pro" onChange={onChange} onConfigureKey={onConfigureKey} />,
  );
  await waitFor(() => {
    expect(container.querySelector(".ant-select-selector")).not.toBeNull();
  });
  fireEvent.mouseDown(container.querySelector(".ant-select-selector")!);
  await waitFor(() => {
    expect(document.querySelectorAll(".ant-select-item-option").length).toBeGreaterThan(0);
  });
  return container;
}

/** 下拉里实际列出的文案。已选项也印着同样的文字，所以断言必须限定在下拉内。 */
function optionTexts(): string[] {
  return [...document.querySelectorAll(".ant-select-item-option-content")]
    .map((e) => e.textContent?.trim() ?? "");
}

const onChange = vi.fn();
const onConfigureKey = vi.fn();

beforeEach(() => {
  onChange.mockClear();
  onConfigureKey.mockClear();
  vi.mocked(fetchChatModels).mockResolvedValue(CATALOG);
});

describe("ChatModelSelector", () => {
  // 承重点。改之前 5 项里只有 2 项能点；目录还要继续加厂商，全列出来会变成
  // 「10 项里 2 项能点」——那不是"能力更全"，是把下拉变成一排点不动的灰条。
  it("只列当前真能用的模型，不可用的不出现在列表里", async () => {
    await openDropdown();
    // 断言必须限定在下拉内：已选项 .ant-select-selection-item 上也印着同样的文案，
    // 用 screen.getByText 会撞上两个节点。
    const listed = optionTexts();
    expect(listed).toEqual([
      "DeepSeek V4 Pro",
      "DeepSeek V4 Flash",
      "配置其他厂商模型…",
    ]);
  });

  it("入口排在所有模型之后", async () => {
    await openDropdown();
    const listed = optionTexts();
    expect(listed[listed.length - 1]).toContain("配置其他厂商模型");
  });

  // 承重点。末项不是模型：若不拦，它的哨兵值会被当成 modelId 写进 localStorage
  // 并发给后端 —— 后端查不到这个 id，会静默退回默认模型，用户看到的选择器却显示
  // 「配置其他厂商模型…」。
  it("承重点: 点末项只跳转，不当作模型选中", async () => {
    await openDropdown();
    fireEvent.click(screen.getByText("配置其他厂商模型…"));
    await waitFor(() => {
      expect(onConfigureKey).toHaveBeenCalledTimes(1);
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("点真模型正常回传 id", async () => {
    await openDropdown();
    fireEvent.click(screen.getByText("DeepSeek V4 Flash"));
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith("deepseek:v4-flash");
    });
    expect(onConfigureKey).not.toHaveBeenCalled();
  });

  // 用户配了 Kimi 的 Key 之后，后端把 available 翻成真 —— 它就该出现在列表里。
  // 这条是"只列可用"这个策略成立的前提：可用集合是随用户变化的，不是写死的。
  it("配了某厂商 Key 后，该厂商模型出现在列表里", async () => {
    vi.mocked(fetchChatModels).mockResolvedValue(
      CATALOG.map((m) => (m.id === "moonshot:kimi-k3" ? { ...m, available: true } : m)),
    );
    await openDropdown();
    const listed = optionTexts();
    expect(listed).toContain("Kimi K3");
    expect(listed.some((x) => x.includes("GPT-5.6 Sol"))).toBe(false);
  });
});
