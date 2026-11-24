import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StudyMemoryPanel from "./StudyMemoryPanel";
import StudyContinueStrip from "./StudyContinueStrip";
import { getStudyMemory, saveStudyMemory, type StudyMemory } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getStudyMemory: vi.fn(), saveStudyMemory: vi.fn() };
});
const mockGet = vi.mocked(getStudyMemory);
const mockSave = vi.mocked(saveStudyMemory);

const MEM: StudyMemory = {
  enabled: true,
  notes: null,
  reading: [{ text_id: 7, title_zh: "阿毘達磨俱舍論", juan_num: 6, last_read_at: "2026-11-22T00:00:00Z" }],
  topics: [
    { session_id: 41, title: "种子与习气的关系", last_at: "2026-11-23T00:00:00Z" },
    { session_id: 42, title: "思所作", last_at: "2026-11-22T00:00:00Z" },
    { session_id: 43, title: "第三个主题", last_at: "2026-11-21T00:00:00Z" },
  ],
  excerpts: [],
  max_notes_chars: 300,
  used_in_answers: true,
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockGet.mockReset();
  mockSave.mockReset();
});

describe("研读记忆面板", () => {
  it("列出小津记得的，链接回到经卷与对话", async () => {
    mockGet.mockResolvedValue(MEM);
    wrap(<StudyMemoryPanel />);
    const reading = await screen.findByRole("link", { name: /俱舍[論论].*卷6/ });
    expect(reading.getAttribute("href")).toBe("/texts/7/read?juan=6");
    expect(screen.getByRole("link", { name: "种子与习气的关系" }).getAttribute("href")).toBe("/chat?s=41");
  });

  it("保存偏好：去掉首尾空白，开关不变", async () => {
    mockGet.mockResolvedValue(MEM);
    mockSave.mockResolvedValue({ ...MEM, notes: "我在学唯识" });
    wrap(<StudyMemoryPanel />);
    const box = await screen.findByRole("textbox", { name: "我的回答偏好" });
    fireEvent.change(box, { target: { value: "  我在学唯识  " } });
    fireEvent.click(screen.getByRole("button", { name: /保\s?存/ }));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ enabled: true, notes: "我在学唯识" }));
  });

  it("关掉：带着已存的偏好一起提交 enabled=false", async () => {
    mockGet.mockResolvedValue({ ...MEM, notes: "用繁体" });
    mockSave.mockResolvedValue({ ...MEM, enabled: false, notes: "用繁体", reading: [], topics: [] });
    wrap(<StudyMemoryPanel />);
    fireEvent.click(await screen.findByRole("switch"));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ enabled: false, notes: "用繁体" }));
  });
});

describe("记忆还没进入作答时", () => {
  it("说明如实写「只用于接着研读」，不收偏好", async () => {
    mockGet.mockResolvedValue({ ...MEM, used_in_answers: false });
    wrap(<StudyMemoryPanel />);
    expect(await screen.findByText(/新对话首屏的「接着研读」会用到它们/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "我的回答偏好" })).toBeNull();
    expect(screen.queryByText(/小津会参考/)).toBeNull();
  });
});

describe("新对话「接着研读」", () => {
  it("最多三个入口：经卷在前，再补主题", async () => {
    mockGet.mockResolvedValue(MEM);
    wrap(<StudyContinueStrip />);
    await screen.findByRole("link", { name: /俱舍[論论]/ });
    const chips = document.querySelectorAll(".study-continue-chip");
    expect(Array.from(chips).map((c) => c.getAttribute("href"))).toEqual(["/texts/7/read?juan=6", "/chat?s=41", "/chat?s=42"]);
    expect(screen.getByRole("link", { name: /小津记得什么/ }).getAttribute("href")).toBe("/profile?tab=memory");
  });

  it("读者关掉了记忆：不出入口，但占位容器仍在（输入框不跳）", async () => {
    mockGet.mockResolvedValue({ ...MEM, enabled: false });
    wrap(<StudyContinueStrip />);
    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    expect(screen.getByTestId("study-continue")).toBeEmptyDOMElement();
  });
});
