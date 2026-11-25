import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { passageFontFamily, passageInScript, pickDaily, quotePassage, splitClauses } from "../utils/dailyPassage";

/**
 * 首页「今日经句」：直接显示当天那一句（北京时间零点换），点进 /daily 看白话、做分享图、读原文。
 * 原先只是热门检索行里的一个小按钮，读者看着像检索词、不点开就看不到经句（2026-11-25 用户反馈）。
 * 不引 hanScript（OpenCC 会进首屏），繁简靠池里预先算好的字段。
 */
export default function HomeDaily() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [{ passage }] = useState(() => pickDaily(new Date()));
  const { text, title } = passageInScript(passage, lang);
  const quoted = quotePassage(text, lang);

  return (
    <Link to="/daily" className="home-daily" data-umami-event="home_daily" aria-label={`${t("daily.home_tag")}：${quoted} ——《${title}》`}>
      <span className="home-daily-label">{t("daily.home_tag")}</span>
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
