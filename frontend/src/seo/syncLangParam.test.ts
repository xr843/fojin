import { describe, expect, it } from "vitest";
import { syncLangParam } from "./syncLangParam";

function fake(href: string) {
  const loc = { href } as Location;
  const calls: string[] = [];
  const hist = {
    state: { idx: 3 },
    replaceState: (_s: unknown, _t: string, url: string) => calls.push(url),
  } as unknown as History;
  return { loc, hist, calls };
}

describe("syncLangParam", () => {
  it("adds lang for non-default languages and keeps other params and the hash", () => {
    const f = fake("https://fojin.app/search?q=%E5%BF%83%E7%BB%8F#top");
    syncLangParam("zh-Hant", f.loc, f.hist);
    expect(f.calls).toEqual(["/search?q=%E5%BF%83%E7%BB%8F&lang=zh-Hant#top"]);
  });

  it("replaces an existing lang value", () => {
    const f = fake("https://fojin.app/texts/1?lang=zh-Hant");
    syncLangParam("en", f.loc, f.hist);
    expect(f.calls).toEqual(["/texts/1?lang=en"]);
  });

  it("removes lang when switching back to zh", () => {
    const f = fake("https://fojin.app/texts/1?lang=en");
    syncLangParam("zh", f.loc, f.hist);
    expect(f.calls).toEqual(["/texts/1"]);
  });
});
