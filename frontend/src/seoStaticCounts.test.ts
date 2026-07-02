import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const STATIC_SEO_FILES = ["index.html", "vite.config.ts"];

const SOURCE_COUNT_PATTERNS = [
  /聚合全球\s+\d+\s+个佛教数字资源/g,
  /全球\s+\d+\s+个佛教数字资源/g,
  /跨\s+\d+\s+个数据源/g,
  /Aggregating\s+\d+\s+Buddhist digital resources/gi,
];

describe("static source SEO copy", () => {
  it("does not hardcode the active source count", () => {
    const matches = STATIC_SEO_FILES.flatMap((file) => {
      const text = readFileSync(resolve(process.cwd(), file), "utf-8");
      return SOURCE_COUNT_PATTERNS.flatMap((pattern) =>
        Array.from(text.matchAll(pattern), (match) => `${file}: ${match[0]}`),
      );
    });

    expect(matches).toEqual([]);
  });
});
