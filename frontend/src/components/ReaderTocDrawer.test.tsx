import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ReaderTocDrawer, { type TocEntry } from "./ReaderTocDrawer";

const TOC: TocEntry[] = [
  [1, "1 分別界品", 1, "0001a08"],
  [1, "2 分別根品", 3, "0013b11"],
  [2, "小節", 4, "0018b11"],
];

describe("ReaderTocDrawer", () => {
  it("按层级缩进，标出当前卷；点一条把卷号与行号交出去", () => {
    const onJump = vi.fn();
    render(<ReaderTocDrawer open onClose={() => {}} toc={TOC} currentJuan={3} onJump={onJump} placement="left" />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((el) => el.querySelector(".reader-toc-title")?.textContent)).toEqual(["1 分別界品", "2 分別根品", "小節"]);
    expect(items[1].className).toContain("is-current");
    expect(items[0].className).not.toContain("is-current");
    expect(items[2].style.paddingInlineStart).toBe("32px");
    fireEvent.click(items[1]);
    expect(onJump).toHaveBeenCalledWith(3, "0013b11");
  });
});
