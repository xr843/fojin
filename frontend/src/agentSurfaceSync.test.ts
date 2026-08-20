import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The agent-facing surfaces — `/agents` and `llms.txt` — are hand-written static
 * files, so nothing made them follow the MCP server when a tool was added. They
 * did drift: `commentaries` shipped as the eighth tool on 2026-08-16 and both
 * files still announced "七个工具" / "Seven read-only tools" five days later,
 * telling every crawler and every model a number that was wrong.
 *
 * These files are what an AI reads to decide what FoJin can do, so a stale count
 * there costs more than a stale README. The checks below are self-consistency
 * checks against the server itself, not hardcoded expectations, so they cannot
 * go stale in the same way.
 */

const SERVER_PY = resolve(process.cwd(), "..", "mcp-server", "fojin_mcp", "server.py");
const AGENTS_HTML = resolve(process.cwd(), "public", "agents.html");
const LLMS_TXT = resolve(process.cwd(), "public", "llms.txt");

/** Tool names, in definition order, from the `@mcp.tool()`-decorated functions. */
function declaredTools(source: string): string[] {
  return Array.from(
    source.matchAll(/@mcp\.tool\(\)\s*\n\s*async def\s+([a-z_]+)\s*\(/g),
    (m) => m[1],
  );
}

const CHINESE_NUMERALS: Record<number, string> = {
  5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十", 11: "十一", 12: "十二",
};
const ENGLISH_NUMERALS: Record<number, string> = {
  5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
  11: "Eleven", 12: "Twelve",
};

describe("agent-facing surfaces track the MCP server", () => {
  const tools = declaredTools(readFileSync(SERVER_PY, "utf-8"));

  it("finds the tools (guards the regex itself against a refactor)", () => {
    // If the server switches decorator style this goes to 0 and every
    // assertion below would pass vacuously — fail loudly here instead.
    expect(tools.length).toBeGreaterThanOrEqual(5);
    expect(tools).toContain("search_corpus");
  });

  it("lists every tool in the /agents tools table", () => {
    const html = readFileSync(AGENTS_HTML, "utf-8");
    // Scope to the tools table, not the whole page: the portal name-drops tools
    // in prose elsewhere, so a page-wide search would pass while the table —
    // the part that actually documents the tool — was missing a row.
    const table = /个工具[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/.exec(html)?.[1];
    expect(table, "could not locate the tools table in agents.html").toBeTruthy();
    const missing = tools.filter((t) => !table!.includes(`<code>${t}</code>`));
    expect(missing).toEqual([]);
  });

  it("states the right tool count on /agents", () => {
    const html = readFileSync(AGENTS_HTML, "utf-8");
    const expected = CHINESE_NUMERALS[tools.length];
    expect(expected, `no Chinese numeral mapped for ${tools.length} tools`).toBeTruthy();
    expect(html).toContain(`${expected}个工具`);
  });

  it("states the right tool count in llms.txt", () => {
    const txt = readFileSync(LLMS_TXT, "utf-8");
    const expected = ENGLISH_NUMERALS[tools.length];
    expect(expected, `no English numeral mapped for ${tools.length} tools`).toBeTruthy();
    expect(txt).toContain(`${expected} read-only tools`);
  });
});
