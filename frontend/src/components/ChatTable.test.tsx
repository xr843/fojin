import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ChatTable, { EXPAND_MIN_ROWS } from "./ChatTable";

function md(bodyRows: number) {
  const rows = Array.from({ length: bodyRows }, (_, i) => `| ${i + 1} | ${(i + 1) * 100} |`).join("\n");
  return `| 卷 | 字数 |\n| --- | --- |\n${rows}\n`;
}

const renderMd = (src: string) =>
  render(<div className="chat-markdown"><Markdown remarkPlugins={[remarkGfm]} components={{ table: ChatTable }}>{src}</Markdown></div>);

describe("ChatTable", () => {
  it("short tables get no full-screen button", () => {
    renderMd(md(EXPAND_MIN_ROWS - 2)); // 表头 1 行 + 6 行 = 7 < 8
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /全屏看表/ })).toBeNull();
  });

  it("long tables open the whole table in a dialog", () => {
    renderMd(md(20));
    fireEvent.click(screen.getByRole("button", { name: /全屏看表/ }));
    const dialog = screen.getByRole("dialog");
    const table = within(dialog).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(21);
    expect(within(table).getByText("2000")).toBeInTheDocument();
  });
});
