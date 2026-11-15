/**
 * 搜索页「出处」卡片：用户贴一段原文来搜时，在结果上方直接给出原典。
 *
 * 搜索结果按「这段在一卷里出现几次」打分，注疏反复引用名句，会把原典挤下去
 * （2026-11-15 生产实测：搜「应无所住而生其心」，鸠摩罗什译《金刚经》排第 40）。
 * 核对接口 /verify/quote 已经按藏经编号（经 → 律 → 论 → 注疏）给出逐字命中的
 * 出处，这里只决定「什么时候问它」和「什么时候敢把它的第一条摆出来」。
 */
import type { CanonClass, QuoteVerdict, QuoteMatch } from "../api/client";
import { hasQuestionCue } from "../pages/homeSuggest";
import { hanCount } from "./searchAskAi";

/** 少于 8 个汉字多半是术语或经名片段（「般若波罗蜜」在上千部经里都有），谈不上「出处」。 */
export const SOURCE_MIN_HAN = 8;

// 以经名后缀结尾、或整个用书名号括起来的，是在找这部书，不是在找一段话的出处。
const TITLE_END = /(經|经|論|论|疏|註|鈔|钞|記|记|錄|录|集|頌|颂|儀|仪|傳|传|咒|陀羅尼|陀罗尼)》?\s*$/;
const BOOK_TITLE = /^《[^》]*》$/;

export function looksLikeSourceQuery(query: string): boolean {
  const q = query.trim();
  if (hanCount(q) < SOURCE_MIN_HAN) return false;
  if (hasQuestionCue(q)) return false;
  if (TITLE_END.test(q) || BOOK_TITLE.test(q)) return false;
  return true;
}

/**
 * 只有经、律、论才当「出处」摆出来。按藏经编号排第一的也可能是经录（只列了经名）、
 * 史传、语录或注疏——那时说「这段见于某书」会误导，宁可不显示卡片。
 */
const SOURCE_CLASSES: ReadonlySet<CanonClass> = new Set(["sutra", "vinaya", "treatise"]);

export function pickSourceMatch(verdict: QuoteVerdict | null | undefined): QuoteMatch | null {
  if (!verdict || !verdict.verbatim) return null;
  const first = verdict.matches[0];
  if (!first || !first.canon_class || !SOURCE_CLASSES.has(first.canon_class)) return null;
  return first;
}
