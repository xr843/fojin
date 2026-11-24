import { describe, it, expect } from "vitest";
import { locateQuote, normalizeQuote } from "./excerptHighlight";

function mount(html: string): HTMLElement {
  const el = document.createElement("div");
  el.innerHTML = html;
  document.body.appendChild(el);
  return el;
}

describe("locateQuote", () => {
  it("跨硬换行、跨行号锚点、跳过校勘标记找回原文", () => {
    const el = mount(
      '<p><span class="cbeta-line" data-ref="0413a06"></span>善男子！有十四音<sup class="apparatus-marker">[3]</sup>名\n' +
        '<span class="cbeta-line" data-ref="0413a07"></span>為字義，所言字者</p>',
    );
    // 划选时 toString 带进了换行与校勘标记
    const r = locateQuote(el, "有十四音[3]名\n為字義", "0413a06");
    expect(r).not.toBeNull();
    expect(normalizeQuote(r!.toString())).toBe("有十四音[3]名為字義".replace("[3]", ""));
    el.remove();
  });

  it("同一句出现两次时，取记下的那一行之后的那处", () => {
    const el = mount(
      '<p><span class="cbeta-line" data-ref="0001a01"></span>如是我聞。</p>' +
        '<p><span class="cbeta-line" data-ref="0002b05"></span>復次，如是我聞。</p>',
    );
    const r = locateQuote(el, "如是我聞", "0002b05")!;
    expect(r.startContainer.textContent).toBe("復次，如是我聞。");
    el.remove();
  });

  it("行号对不上时退回全卷第一处；原文不在就返回 null", () => {
    const el = mount('<p><span class="cbeta-line" data-ref="0001a01"></span>如是我聞。</p>');
    expect(locateQuote(el, "如是我聞", "9999z99")).not.toBeNull();
    expect(locateQuote(el, "一時佛在", "0001a01")).toBeNull();
    el.remove();
  });
});
