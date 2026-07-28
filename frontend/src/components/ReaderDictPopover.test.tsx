import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ReaderDictPopover } from "./ReaderDictPopover";
import type { DictPopoverState } from "./ReaderDictPopover.types";
import type { DictEntry, DictGroupedSearchResponse } from "../api/client";

const LONG_DEF =
  "梵語 prajñā 的音譯，指能洞見一切諸法真實相狀的智慧，為三無漏學之一，非世間聰辯之慧可比。";

function entry(o: Partial<DictEntry> = {}): DictEntry {
  return {
    id: 1 as DictEntry["id"],
    headword: "般若",
    reading: "bō rě",
    definition: LONG_DEF,
    lang: "lzh",
    source_code: "foguang",
    source_name: "佛光大辭典",
    ...o,
  };
}

function makeResult(groups: DictGroupedSearchResponse["groups"]): DictGroupedSearchResponse {
  return { total: groups.length, page: 1, page_size: 20, groups };
}

function makeState(o: Partial<DictPopoverState> = {}): DictPopoverState {
  return { visible: true, text: "般若", x: 100, y: 100, loading: false, result: null, ...o };
}

function renderPopover(state: DictPopoverState) {
  const onAsk = vi.fn();
  const onClose = vi.fn();
  render(
    <MemoryRouter>
      <ReaderDictPopover state={state} onClose={onClose} onAsk={onAsk} />
    </MemoryRouter>,
  );
  return { onAsk, onClose };
}

describe("ReaderDictPopover 划词词典浮层", () => {
  it("不可见时不渲染任何内容", () => {
    renderPopover(makeState({ visible: false }));
    expect(screen.queryByText("般若")).toBeNull();
    expect(screen.queryByRole("button", { name: /问小津/ })).toBeNull();
  });

  it("短词命中：完整释义不截断 + 发音 + 词典名 + 查看全部释义链接", () => {
    renderPopover(
      makeState({
        result: makeResult([
          { source_code: "foguang", source_name: "佛光大辭典", total: 1, entries: [entry()] },
        ]),
      }),
    );
    // 关键词与发音
    expect(screen.getByText("般若")).toBeInTheDocument();
    expect(screen.getByText("bō rě")).toBeInTheDocument();
    // 释义完整呈现，且没有旧实现的截断省略号
    expect(screen.getByText(LONG_DEF)).toBeInTheDocument();
    expect(screen.queryByText(/…/)).toBeNull();
    // 词典名
    expect(screen.getByText("佛光大辭典")).toBeInTheDocument();
    // 查看全部释义链接
    expect(screen.getByText(/查看全部释义/)).toBeInTheDocument();
  });

  it("多部词典：中文释义类辞典排在多语对照类之前", () => {
    renderPopover(
      makeState({
        result: makeResult([
          // 非高质量源在前，应被重排到后面
          { source_code: "dpd", source_name: "Digital Pali Dictionary", total: 1, entries: [entry({ id: 2 as DictEntry["id"], source_code: "dpd", source_name: "Digital Pali Dictionary", definition: "wisdom" })] },
          { source_code: "foguang", source_name: "佛光大辭典", total: 1, entries: [entry()] },
        ]),
      }),
    );
    const sources = screen.getAllByText(/佛光大辭典|Digital Pali Dictionary/).map((el) => el.textContent);
    expect(sources[0]).toBe("佛光大辭典");
  });

  it("同一词典多义项：最多渲染前 2 条", () => {
    renderPopover(
      makeState({
        result: makeResult([
          {
            source_code: "foguang",
            source_name: "佛光大辭典",
            total: 3,
            entries: [
              entry({ id: 1 as DictEntry["id"], definition: "义项一" }),
              entry({ id: 2 as DictEntry["id"], definition: "义项二" }),
              entry({ id: 3 as DictEntry["id"], definition: "义项三超出上限不应显示" }),
            ],
          },
        ]),
      }),
    );
    expect(screen.getByText("义项一")).toBeInTheDocument();
    expect(screen.getByText("义项二")).toBeInTheDocument();
    expect(screen.queryByText("义项三超出上限不应显示")).toBeNull();
  });

  it("发音跨词典兜底：首选词典无注音时取后续词典的 reading", () => {
    renderPopover(
      makeState({
        result: makeResult([
          { source_code: "foguang", source_name: "佛光大辭典", total: 1, entries: [entry({ reading: null })] },
          { source_code: "bs-yiqiejing-yinyi", source_name: "一切經音義", total: 1, entries: [entry({ id: 9 as DictEntry["id"], source_code: "bs-yiqiejing-yinyi", source_name: "一切經音義", reading: "bō rě" })] },
        ]),
      }),
    );
    expect(screen.getByText("bō rě")).toBeInTheDocument();
  });

  it("辞典未收录：优雅降级提示可问小津", () => {
    renderPopover(makeState({ result: makeResult([]) }));
    expect(screen.getByText("辞典未收录，可问小津")).toBeInTheDocument();
  });

  it("整句选择（>20字）：只显示问小津，不查辞典、不显示查看全部释义", () => {
    const longText = "观自在菩萨行深般若波罗蜜多时照见五蕴皆空度一切苦厄";
    expect(longText.length).toBeGreaterThan(20);
    renderPopover(makeState({ text: longText, result: null }));
    expect(screen.getByRole("button", { name: /问小津/ })).toBeInTheDocument();
    expect(screen.queryByText(/查看全部释义/)).toBeNull();
    expect(screen.queryByText("辞典未收录，可问小津")).toBeNull();
  });

  it("点击问小津：用选中文字回调 onAsk 并关闭", () => {
    const { onAsk, onClose } = renderPopover(makeState({ text: "涅槃", result: makeResult([]) }));
    screen.getByRole("button", { name: /问小津/ }).click();
    expect(onAsk).toHaveBeenCalledWith("涅槃");
    expect(onClose).toHaveBeenCalled();
  });
});
