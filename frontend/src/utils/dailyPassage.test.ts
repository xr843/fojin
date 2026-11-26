import { describe, expect, it } from "vitest";
import { beijingDateKey, dailyIndex, festivalFor, festivalName, pickDaily, passageFontFamily, passageInScript, quotePassage, splitClauses, DAILY_FESTIVALS, DAILY_PASSAGES, type DailyFestival, type DailyPassage } from "./dailyPassage";
import { wrapCjk } from "./shareCard";
import { localizeHan } from "./hanScript";
import glyphs from "../data/dailyFontGlyphs.json";

const P = (n: number): DailyPassage => ({
  text: `段${n}`, title_zh: "經", cbeta_id: `T${n}`, text_id: n, juan_num: 1, reader_path: `/texts/${n}/read?juan=1`,
});

describe("每日一段", () => {
  it("按北京时间切日：UTC 16:00 已是北京第二天", () => {
    expect(beijingDateKey(new Date("2026-11-24T15:59:00Z"))).toBe("2026-11-24");
    expect(beijingDateKey(new Date("2026-11-24T16:00:00Z"))).toBe("2026-11-25");
  });

  it("同一天同一段，相邻两天不同段，按池子长度循环", () => {
    const pool = [P(1), P(2), P(3)];
    const a = pickDaily(new Date("2026-11-24T01:00:00Z"), pool);
    const b = pickDaily(new Date("2026-11-24T12:00:00Z"), pool);
    const c = pickDaily(new Date("2026-11-25T01:00:00Z"), pool);
    expect(a.passage).toBe(b.passage);
    expect(c.passage).not.toBe(a.passage);
    expect(dailyIndex("2026-01-01", 3)).toBe(0);
    expect(dailyIndex("2026-01-04", 3)).toBe(0);
    expect(dailyIndex("2025-12-31", 3)).toBe(2); // 起点之前也不出负数
  });

  it("段落池里每条都带站内阅读器链接与出处", () => {
    expect(DAILY_PASSAGES.length).toBeGreaterThanOrEqual(30);
    for (const p of DAILY_PASSAGES) {
      expect(p.reader_path).toMatch(/^\/texts\/\d+\/read\?juan=\d+/);
      expect(p.title_zh && p.cbeta_id && p.text).toBeTruthy();
      // 每句是完整的自然句：以句末标点收尾；引号由页面加，池里不带
      expect(p.text, p.text).toMatch(/[。？！]$/);
      expect(p.text, p.text).not.toMatch(/^[「“]/);
    }
    // 相邻两条不是同一部经（生成时已按经打散）
    for (let i = 1; i < DAILY_PASSAGES.length; i++) {
      if (DAILY_PASSAGES[i].cbeta_id === DAILY_PASSAGES[i - 1].cbeta_id) {
        // 只有某部经条目多到轮不开时才允许相邻，且只能发生在末尾
        expect(i).toBeGreaterThan(DAILY_PASSAGES.length - 4);
      }
    }
  });
});

describe("经句引号", () => {
  it("繁体界面用「」，简体和英文界面用“”", () => {
    expect(quotePassage("應無所住而生其心。", "zh-Hant")).toBe("「應無所住而生其心。」");
    expect(quotePassage("应无所住而生其心。", "zh")).toBe("“应无所住而生其心。”");
    expect(quotePassage("应无所住而生其心。", "en")).toBe("“应无所住而生其心。”");
  });
});

describe("经句字体子集", () => {
  it("池里每句在简体、繁体界面要显示的字，都在 /daily 专用字体子集里（加了新句要重跑 build_daily_fonts.py）", () => {
    const brush = new Set(Array.from(glyphs.brush));
    const kai = new Set(Array.from(glyphs.kai));
    const PUNCT = "，。；：？！、“”「」";
    for (const p of [...DAILY_PASSAGES, ...DAILY_FESTIVALS]) {
      for (const lang of ["zh", "zh-Hant"]) {
        for (const c of Array.from(quotePassage(localizeHan(p.text, lang), lang))) {
          expect(kai.has(c), `文楷子集缺「${c}」（${p.text}）`).toBe(true);
          if (lang === "zh" && !PUNCT.includes(c)) expect(brush.has(c), `毛笔子集缺「${c}」（${p.text}）`).toBe(true);
        }
      }
    }
  });

  it("繁体界面不用毛笔体（马善政没有繁体字形）", () => {
    expect(passageFontFamily("zh-Hant")).not.toMatch(/Brush/);
    expect(passageFontFamily("zh")).toMatch(/^"FoJin Daily Brush", "FoJin Daily Kai"/);
  });
});

describe("经句按分句换行", () => {
  it("每段带自己的标点，引号跟着首尾分句", () => {
    expect(splitClauses("“若以色见我，以音声求我，是人行邪道，不能见如来。”")).toEqual([
      "“若以色见我，", "以音声求我，", "是人行邪道，", "不能见如来。”",
    ]);
    expect(splitClauses("「應無所住而生其心。」")).toEqual(["「應無所住而生其心。」"]);
  });

  it("池里每句切完拼回去一字不差", () => {
    for (const p of DAILY_PASSAGES) {
      const q = quotePassage(p.text, "zh");
      expect(splitClauses(q).join("")).toBe(q);
    }
  });
});

describe("分享图断行", () => {
  const measure = (s: string) => Array.from(s).length * 10;

  it("按宽度断行", () => {
    expect(wrapCjk(measure, "一二三四五六七", 30)).toEqual(["一二三", "四五六", "七"]);
  });

  it("优先在逗号处换行，不把半个词留在行尾", () => {
    // 每行最多 13 字：逐字断会成「一切有為法，如夢幻泡影，如」+「露亦如電，應作如是觀」
    expect(wrapCjk(measure, "一切有為法，如夢幻泡影，如露亦如電，應作如是觀", 130)).toEqual([
      "一切有為法，如夢幻泡影，",
      "如露亦如電，應作如是觀",
    ]);
  });

  it("后引号不放行首", () => {
    expect(wrapCjk(measure, "一二三。”", 30)).toEqual(["一二三。”"]);
  });

  it("标点不放行首，跟在上一行末尾", () => {
    expect(wrapCjk(measure, "一二三，四五", 30)).toEqual(["一二三，", "四五"]);
  });
});

describe("首页经句的繁简（不经 OpenCC）", () => {
  it("池里预算的简体字段与 OpenCC 转换一致（重跑 build_daily_passages.py 后要跑 node scripts/daily-hans.mjs）", () => {
    for (const p of DAILY_PASSAGES) {
      expect(p.text_hans, p.text).toBe(localizeHan(p.text, "zh"));
      expect(p.title_hans, p.title_zh).toBe(localizeHan(p.title_zh, "zh"));
    }
  });

  it("繁体界面取原文，简体与英文界面取简体字段", () => {
    const p = DAILY_PASSAGES[0];
    expect(passageInScript(p, "zh-Hant")).toEqual({ text: p.text, title: p.title_zh });
    expect(passageInScript(p, "zh")).toEqual({ text: p.text_hans, title: p.title_hans });
    expect(passageInScript(p, "en").text).toBe(p.text_hans);
  });
});

describe("佛教节日经句", () => {
  it("按农历日期换句：腊八、佛诞、观音诞", () => {
    expect(festivalFor("2027-01-15")?.name).toBe("释迦牟尼佛成道日"); // 腊月初八
    expect(festivalFor("2027-05-13")?.name).toBe("释迦牟尼佛圣诞"); // 四月初八
    expect(festivalFor("2027-03-26")?.name).toBe("观世音菩萨圣诞"); // 二月十九
    expect(festivalFor("2026-11-26")).toBeNull(); // 十月十八，平日
  });

  it("三十日的节日遇小月在廿九过；大月的廿九不算", () => {
    expect(festivalFor("2027-10-28")?.name).toBe("药师佛圣诞"); // 九月小月，廿九
    expect(festivalFor("2027-08-31")?.name).toBe("地藏菩萨圣诞"); // 七月大月，三十
    expect(festivalFor("2027-08-30")).toBeNull(); // 七月廿九，大月不提前
  });

  it("节日当天替换轮换句，平日照常轮换", () => {
    const fest = pickDaily(new Date("2027-01-15T04:00:00Z"));
    expect(fest.festival?.name).toBe("释迦牟尼佛成道日");
    expect(fest.passage.text).toBe(fest.festival?.text);
    const plain = pickDaily(new Date("2027-01-16T04:00:00Z"));
    expect(plain.festival).toBeNull();
    expect(DAILY_PASSAGES).toContain(plain.passage);
  });

  it("节日名只给中文界面，繁体界面用繁体", () => {
    const f = festivalFor("2027-03-26") as DailyFestival;
    expect(festivalName(f, "zh")).toBe("观世音菩萨圣诞");
    expect(festivalName(f, "zh-Hant")).toBe("觀世音菩薩聖誕");
    expect(festivalName(f, "en")).toBeNull();
  });

  it("每个节日经句都带阅读器链接（定位到行，至少到卷）、简体字段，并且是完整自然句", () => {
    expect(DAILY_FESTIVALS.length).toBeGreaterThanOrEqual(16);
    for (const f of DAILY_FESTIVALS) {
      expect(f.key).toMatch(/^\d{2}-\d{2}$/);
      // 行号定位不到时（少室六门等）退回到卷，与轮换池同一标准
      expect(f.reader_path, f.name).toMatch(/^\/texts\/\d+\/read\?juan=\d+/);
      expect(f.text_hans && f.title_hans && f.name_hant, f.name).toBeTruthy();
      expect("。？！").toContain(f.text.slice(-1));
    }
  });
});
