// fojin.ai 首页 public/trace.html + trace.js 不在 React 构建里，tsc / eslint 都不检查它。
// 2026-11-22 一次重构误删了 el()/sourceLink() 等函数，node --check 只查语法没拦住，
// 线上首页每次核对都抛 ReferenceError。这里在测试环境（jsdom）里把页面脚本真正跑一遍：
// 模拟接口返回 → 逐句渲染 → 原文连着的句子合成一张卡片 → 引语前缀灰显。
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PUBLIC = resolve(__dirname, "../../public");

const src = (hl: string) => ({
  text_id: 7, juan_num: 1, title_zh: "般若波羅蜜多心經", cbeta_id: "T0251", canon_class: "sutra",
  reader_url: `https://fojin.app/texts/7/read?juan=1&anchor=p0848c06&hl=${hl}`,
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("fojin.ai 首页脚本 trace.js", () => {
  it("核对一段文字：不抛错，原文相接的句子合成一张卡片，前缀灰显", async () => {
    const html = readFileSync(resolve(PUBLIC, "trace.html"), "utf8");
    document.body.innerHTML = html.slice(html.indexOf("<body>") + 6, html.indexOf("</body>"));
    const errors: string[] = [];
    const onError = (e: ErrorEvent) => errors.push(String(e.error ?? e.message));
    window.addEventListener("error", onError);
    const sent: { sentences: string[] }[] = [];
    vi.stubGlobal("fetch", async (_url: string, init: { body: string }) => {
      const body = JSON.parse(init.body) as { sentences: string[] };
      sent.push(body);
      const items = body.sentences.map((t, i) =>
        i < 2
          ? { text: t, result: { verdict: "sutra", source_class: "sutra",
              segments: [{ text: t, found: true, sources: [src(i === 0 ? "19-47" : "51-89")] }] } }
          : { text: t, prefix: "佛言：", result: { verdict: "absent", segments: [{ text: t, found: false, sources: [] }] } },
      );
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => ({ items, dominant: null }) };
    });

    new Function(readFileSync(resolve(PUBLIC, "trace.js"), "utf8"))();
    (document.getElementById("trace-text") as HTMLTextAreaElement).value =
      "观自在菩萨，行深般若波罗蜜多时。舍利子，色不异空。佛言：放下执念便得自在。";
    document.getElementById("trace-form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 300));
    window.removeEventListener("error", onError);

    expect(errors).toEqual([]);
    expect(document.getElementById("status")?.textContent).toBe("");
    // 贴进来的文字不进地址栏（统计会记下网址）
    expect(window.location.search).toBe("");
    // 整句送检（前缀由后端判断），不在页面里去掉
    expect(sent[0].sentences[2]).toBe("佛言：放下执念便得自在。");
    const cards = [...document.querySelectorAll("#result > li")];
    expect(cards).toHaveLength(2);
    expect(cards[0].querySelector(".runinfo")?.textContent).toBe("第 1–2 句，原文连成一段");
    expect(cards[0].querySelector(".meta a")?.getAttribute("href")).toContain("hl=19-89");
    expect(cards[1].querySelector(".pre")?.textContent).toBe("佛言：");
    expect(document.getElementById("summary")?.textContent).toBe(
      "共 3 句，2 句出自佛经，1 句藏经中未见（未见不等于伪造，可能是改写或出自未收录的典籍）。",
    );
    // 底部不再有常驻说明
    expect(document.querySelector(".notes")).toBeNull();
  });
});

describe("fojin.ai 首页：贴进来的文字不进统计", () => {
  it("统计脚本带 data-exclude-search", () => {
    const html = readFileSync(resolve(PUBLIC, "trace.html"), "utf8");
    expect(html).toMatch(/analytics\.fojin\.app\/script\.js"[^>]*data-exclude-search="true"/);
    // 只在自己的域名上统计：复制走的页面（曾有 lobster-ai.net）不再往统计库里写
    expect(html).toMatch(/analytics\.fojin\.app\/script\.js"[^>]*data-domains="fojin\.ai,www\.fojin\.ai,fojin\.app,www\.fojin\.app"/);
  });

  it("打开分享链接：先把 ?q= 从地址栏清掉，再核对", () => {
    const html = readFileSync(resolve(PUBLIC, "trace.html"), "utf8");
    document.body.innerHTML = html.slice(html.indexOf("<body>") + 6, html.indexOf("</body>"));
    window.history.replaceState(null, "", "/?q=" + encodeURIComponent("一切有为法，如梦幻泡影"));
    vi.stubGlobal("fetch", async () => new Promise(() => {}));  // 核对挂起即可，只看地址栏
    new Function(readFileSync(resolve(PUBLIC, "trace.js"), "utf8"))();
    expect(window.location.search).toBe("");
    expect((document.getElementById("trace-text") as HTMLTextAreaElement).value).toBe("一切有为法，如梦幻泡影");
  });
});

// 2026-11-24 用户截图：卡片标签写「出自论典」，汇总却写「21 句出自论疏或祖师著作」——
// 汇总把所有非佛经类别并成一类。改为按类别分开计数，与卡片标签同一套叫法。
describe("fojin.ai 首页：汇总按出处类别分开计数", () => {
  it("论典与注疏分开写，叫法与卡片标签一致", async () => {
    const html = readFileSync(resolve(PUBLIC, "trace.html"), "utf8");
    document.body.innerHTML = html.slice(html.indexOf("<body>") + 6, html.indexOf("</body>"));
    window.history.replaceState(null, "", "/");
    const classes = ["treatise", "treatise", "commentary", "sutra"];
    vi.stubGlobal("fetch", async (_url: string, init: { body: string }) => {
      const body = JSON.parse(init.body) as { sentences: string[] };
      const items = body.sentences.map((t, i) => ({
        text: t,
        result: {
          verdict: classes[i] === "sutra" ? "sutra" : "not_sutra",
          source_class: classes[i],
          segments: [{ text: t, found: true, sources: [{ ...src(`${i * 20}-${i * 20 + 5}`), text_id: 10 + i, canon_class: classes[i] }] }],
        },
      }));
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => ({ items, dominant: null }) };
    });
    new Function(readFileSync(resolve(PUBLIC, "trace.js"), "utf8"))();
    (document.getElementById("trace-text") as HTMLTextAreaElement).value = "甲句之文字。乙句之文字。丙句之文字。丁句之文字。";
    document.getElementById("trace-form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 300));
    expect(document.getElementById("summary")?.textContent).toBe(
      "共 4 句，1 句出自佛经，2 句出自论典，1 句出自注疏。",
    );
    // 全部找到时不出现「未见不等于伪造」
    expect(document.getElementById("summary")?.textContent).not.toContain("伪造");
  });
});
