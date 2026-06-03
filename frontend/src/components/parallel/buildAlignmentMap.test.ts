import { describe, it, expect } from "vitest";
import { buildAlignmentMap } from "./buildAlignmentMap";
import type { JuanAlignmentResponse } from "../../api/client";

function alignmentFixture(
  text_id: number,
  entries: Array<{ chunk_index: number; parallels: Array<{ text_id: number; chunk_index: number }> }>,
): JuanAlignmentResponse {
  return {
    text_id,
    juan_num: 1,
    total_chunks: entries.length,
    chunks_with_parallels: entries.length,
    entries: entries.map((e) => ({
      chunk_index: e.chunk_index,
      chunk_text: `chunk_${e.chunk_index}_of_${text_id}`,
      parallels: e.parallels.map((p) => ({
        text_id: p.text_id,
        juan_num: 1,
        chunk_index: p.chunk_index,
        chunk_text: `chunk_${p.chunk_index}_of_${p.text_id}`,
        lang: "lzh",
        title: "",
        confidence: 1.0,
      })),
    })),
  };
}

describe("buildAlignmentMap", () => {
  it("returns empty map for empty input", () => {
    expect(buildAlignmentMap([])).toEqual({});
  });

  it("indexes A → B with A's alignment data", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
      { chunk_index: 1, parallels: [{ text_id: 200, chunk_index: 6 }] },
    ]);
    const map = buildAlignmentMap([a]);
    expect(map[100][0][200]).toBe(5);
    expect(map[100][1][200]).toBe(6);
  });

  it("builds bidirectional index when both sides provided", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
    ]);
    const b = alignmentFixture(200, [
      { chunk_index: 5, parallels: [{ text_id: 100, chunk_index: 0 }] },
    ]);
    const map = buildAlignmentMap([a, b]);
    expect(map[100][0][200]).toBe(5);
    expect(map[200][5][100]).toBe(0);
  });

  it("handles chunks with multiple parallels (picks first per text)", () => {
    const a = alignmentFixture(100, [
      {
        chunk_index: 0,
        parallels: [
          { text_id: 200, chunk_index: 5 },
          { text_id: 300, chunk_index: 7 },
        ],
      },
    ]);
    const map = buildAlignmentMap([a]);
    expect(map[100][0][200]).toBe(5);
    expect(map[100][0][300]).toBe(7);
  });

  it("ignores null alignment entries (failed API)", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
    ]);
    const map = buildAlignmentMap([a, null]);
    expect(map[100][0][200]).toBe(5);
  });
});
