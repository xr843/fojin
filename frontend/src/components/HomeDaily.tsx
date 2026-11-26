import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { festivalName, passageFontFamily, passageInScript, pickDaily, quotePassage, splitClauses } from "../utils/dailyPassage";

/**
 * 首页「今日经句」：直接显示当天那一句（北京时间零点换），点进 /daily 看白话、做分享图、读原文。
 * 原先只是热门检索行里的一个小按钮，读者看着像检索词、不点开就看不到经句（2026-11-25 用户反馈）。
 * 不引 hanScript（OpenCC 会进首屏），繁简靠池里预先算好的字段。
 */
export default function HomeDaily() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [{ passage, festival }] = useState(() => pickDaily(new Date()));
  const { text, title } = passageInScript(passage, lang);
  const quoted = quotePassage(text, lang);
  // 佛教节日当天，标签换成节日名（如「观世音菩萨圣诞」），读者一眼知道今天为何是这一句
  const label = festivalName(festival, lang) ?? t("daily.home_tag");

  return (
    <Link to="/daily" className="home-daily" data-umami-event="home_daily" aria-label={`${label}：${quoted} ——《${title}》`}>
      <span className={festival ? "home-daily-label home-daily-label--festival" : "home-daily-label"}>{label}</span>
      <span className="home-daily-text" lang="zh" style={{ fontFamily: passageFontFamily(lang) }}>
        {splitClauses(quoted).map((c, i) => (
          <span key={i} className="home-daily-clause">
            {c}
          </span>
        ))}
      </span>
      <span className="home-daily-source">——《{title}》</span>
    </Link>
  );
}
