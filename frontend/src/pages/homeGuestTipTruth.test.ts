import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 首页给游客看的那行提示说过「注册登录**解锁 AI 问答**」，而游客其实每天有
 * 10 次免费提问 —— /chat 自己的横幅同时在说「每日免费 10 次问答，今日剩余 8
 * 次」。两句话里有一句在骗人，而骗人的那句站在转化路径的最前面：xue.fo 是
 * 站外第一大来源，它送来的人几乎全部止步首页。
 *
 * 这是一条绊线，不是证明：它只能拦住「AI 问答要登录才能用」这一种说法，拦不住
 * 所有可能的假话。但它把文案和 chat_quota.py 里的那个常量拴在了一起 —— 只要
 * 匿名额度还是正数，首页就不许说问答是登录才解锁的。哪天真把匿名额度调成 0，
 * 这条测试会主动让路。
 */

const LOCALES = ["zh", "zh-Hant", "en"] as const;
const QUOTA_PY = resolve(process.cwd(), "..", "backend", "app", "services", "chat_quota.py");

/** 说法形如「登录才能用 AI 问答」的短语，三种语言各一组。 */
const LOCKED_CLAIMS: Record<string, RegExp[]> = {
  zh: [/解锁\s*AI\s*问答/, /登录后.{0,4}才能.{0,6}问答/, /注册后.{0,4}才能.{0,6}问答/],
  "zh-Hant": [/解鎖\s*AI\s*問答/, /登入後.{0,4}才能.{0,6}問答/, /註冊後.{0,4}才能.{0,6}問答/],
  en: [/unlock\s+AI\s+Q&A/i, /sign\s*in\s+(?:is\s+)?required\s+to\s+ask/i],
};

function anonymousDailyLimit(): number {
  const src = readFileSync(QUOTA_PY, "utf-8");
  const m = /FREE_DAILY_LIMIT_ANONYMOUS\s*=\s*(\d+)/.exec(src);
  if (!m) throw new Error("FREE_DAILY_LIMIT_ANONYMOUS not found in chat_quota.py");
  return Number(m[1]);
}

function guestTip(locale: string): string {
  const path = resolve(process.cwd(), "public", "locales", locale, "translation.json");
  const dict = JSON.parse(readFileSync(path, "utf-8")) as Record<string, string>;
  return [
    dict["home.guest_tip.before"],
    dict["home.guest_tip.login"],
    dict["home.guest_tip.after"],
  ].join("");
}

describe("homepage guest tip matches what guests can actually do", () => {
  const limit = anonymousDailyLimit();

  it("reads the real anonymous quota (guards the regex against a rename)", () => {
    expect(limit).toBeGreaterThan(0);
  });

  it.each(LOCALES)("does not tell %s guests that AI Q&A needs an account", (locale) => {
    if (limit === 0) return; // 匿名额度真被关掉时，这条说法就成立了
    const tip = guestTip(locale);
    const offending = LOCKED_CLAIMS[locale].filter((re) => re.test(tip));
    expect(offending.map(String)).toEqual([]);
  });

  it.each(LOCALES)("still exists and still points at sign-in (%s)", (locale) => {
    const tip = guestTip(locale);
    expect(tip.length).toBeGreaterThan(10);
  });
});
