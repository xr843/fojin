import { describe, it, expect, vi } from "vitest";
import { api, getSentenceParallels, type SentenceAlignmentResponse } from "./client";

describe("getSentenceParallels", () => {
  it("calls the sentence endpoint and returns typed pairs", async () => {
    const mockResp: SentenceAlignmentResponse = {
      text_id: 1,
      juan_num: 5,
      total: 1,
      pairs: [
        {
          side_a: { char_start: 0, char_end: 10, lang: "lzh", text: "如是我聞。" },
          side_b: {
            text_id: 9,
            juan_num: 1,
            char_start: 0,
            char_end: 20,
            lang: "pi",
            title: "MN 10",
            text: "Evaṁ me sutaṁ.",
          },
          similarity: 0.94,
          align_type: "1-1",
          method: "sentence-bertalign",
          is_verified: true,
        },
      ],
    };
    const spy = vi.spyOn(api, "get").mockResolvedValueOnce({ data: mockResp });

    const r = await getSentenceParallels(1, 5);

    expect(spy).toHaveBeenCalledWith("/alignment/sentences/1/5");
    expect(r.total).toBe(1);
    expect(r.pairs[0].side_b.lang).toBe("pi");
    expect(r.pairs[0].align_type).toBe("1-1");
    spy.mockRestore();
  });
});
