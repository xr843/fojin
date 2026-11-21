import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Empty, Spin } from "antd";
import { browseTaisho } from "../api/client";
import { getLocalizedCollections } from "../data/collections";
import { getLocalizedPopularSutras } from "../data/popularSutras";
import { TAISHO_SECTIONS } from "../data/taishoSections";
import { satTextUrl } from "../utils/satUrls";
import { LangAlternates } from "../seo/LangAlternates";
import { scriptForLanguage } from "../utils/hanLocale";
import { localizeHan } from "../utils/hanScript";
import { getReadingHistory } from "../utils/readingHistory";
import "../styles/sources.css";
import "../styles/read.css";

/**
 * 读经（/read）——替代导航里的「经典专题」。
 *
 * 全站用得最多的是阅读页（2026-11 Umami 30 天 1,669 访客），导航里却没有读经入口；
 * 经典专题 30 天 171 访客、无人 4 天以上回访。本页从上到下：继续读（本地阅读记录）
 * → 常读经典 → 按大正藏部类浏览（?bu= 部名，可分享、可后退）→ 专题导读（原 /collections 不变）。
 */
export default function ReadPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const traditional = scriptForLanguage(lang) === "traditional";

  const [history] = useState(() => getReadingHistory().slice(0, 4));
  // 已在「继续读」里的经不再在常读经典重复出现
  const popular = useMemo(() => {
    const reading = new Set(history.map((e) => e.textId));
    return getLocalizedPopularSutras(lang).filter((s) => !reading.has(s.text_id));
  }, [lang, history]);
  const collections = useMemo(() => getLocalizedCollections(lang), [lang]);

  const [searchParams, setSearchParams] = useSearchParams();
  const bu = searchParams.get("bu");
  const section = TAISHO_SECTIONS.find((s) => s.name === bu) ?? null;
  const sectionLabel = (s: { name: string; nameHans: string }) => (traditional ? s.name : s.nameHans);

  const { data: texts, isLoading, isError } = useQuery({
    queryKey: ["taishoBrowse", section?.from, section?.to],
    queryFn: () => browseTaisho(section!.from, section!.to),
    enabled: section !== null,
    staleTime: 60 * 60_000,
  });

  // 第 56–84 册（T2185–T2731，日本撰述）CBETA 未收，佛津只有目录。这几个部类原本只给
  // 一个「暂无可在线阅读」的空态（2026-11-21 用户反馈：SAT 里有日系俱舍注疏，佛津
  // 续论疏部却是 0 部）。没有可读经文时改为列出经目、每部外链 SAT 原页 —— SAT 条款
  // 当前禁止再分发全文，只能外链。
  const satOnlySection = section !== null && section.from >= 2185 && section.to <= 2731;
  const { data: catalogTexts } = useQuery({
    queryKey: ["taishoBrowseCatalog", section?.from, section?.to],
    queryFn: () => browseTaisho(section!.from, section!.to, true),
    enabled: satOnlySection && texts !== undefined && texts.length === 0,
    staleTime: 60 * 60_000,
  });
  const showSatCatalog = satOnlySection && texts?.length === 0 && !!catalogTexts && catalogTexts.length > 0;

  // 点开一个部类后把经目滚进视野——桌面上部类按钮已在首屏底部，列表会落在折线以下。
  // 只在点击时滚；带 ?bu= 直接打开时不抢用户的滚动位置。
  const listRef = useRef<HTMLDivElement>(null);
  const scrollPending = useRef(false);
  useEffect(() => {
    if (!scrollPending.current || !bu) return;
    scrollPending.current = false;
    listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [bu]);

  const selectSection = (name: string) => {
    // 再点一次已选中的部类 = 收起
    const closing = name === bu;
    scrollPending.current = !closing;
    setSearchParams(closing ? {} : { bu: name });
  };

  return (
    <div className="sources-page read-page">
      <Helmet>
        <title>{t("read.page_title")}</title>
        <meta name="description" content={t("read.page_desc")} />
      </Helmet>
      <LangAlternates path="/read" />

      <div className="sources-header">
        <h1 className="sources-title">{t("read.title")}</h1>
        <p className="sources-desc">{t("read.subtitle")}</p>
      </div>

      {history.length > 0 && (
        <section className="read-section">
          <h2 className="read-h2">{t("read.continue")}</h2>
          <div className="read-cards">
            {history.map((e) => (
              <Link key={e.textId} className="read-card" to={`/texts/${e.textId}/read?juan=${e.juan}`}>
                <span className="read-card-title">《{localizeHan(e.title, lang)}》</span>
                <span className="read-card-meta">{t("home.juan_n", { n: e.juan })}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="read-section">
        <h2 className="read-h2">{t("read.popular")}</h2>
        <div className="read-cards">
          {popular.map((s) => (
            <Link key={s.slug} className="read-card" to={`/texts/${s.text_id}`}>
              <span className="read-card-title">{s.title}</span>
              <span className="read-card-meta">
                {[s.translator, t("read.fascicles", { n: s.fascicle_count })].filter(Boolean).join(" · ")}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="read-section">
        <h2 className="read-h2">{t("read.browse")}</h2>
        <p className="read-hint">{t("read.browse_hint")}</p>
        <div className="read-chips" role="group" aria-label={t("read.browse")}>
          {TAISHO_SECTIONS.map((s) => (
            <button
              key={s.name}
              type="button"
              className={`read-chip${s.name === bu ? " read-chip-active" : ""}`}
              aria-pressed={s.name === bu}
              data-umami-event="read_section"
              data-umami-event-bu={s.name}
              onClick={() => selectSection(s.name)}
            >
              {sectionLabel(s)}
            </button>
          ))}
        </div>

        {section && (
          <div className="read-list-wrap" ref={listRef}>
            <div className="read-list-head">
              <strong>{sectionLabel(section)}</strong>
              <span className="read-list-range">
                T{String(section.from).padStart(4, "0")}–T{String(section.to).padStart(4, "0")}
              </span>
              {showSatCatalog ? (
                <span className="read-list-count">{t("read.sat_count", { n: catalogTexts!.length })}</span>
              ) : (
                texts && <span className="read-list-count">{t("read.count", { n: texts.length })}</span>
              )}
            </div>
            {isLoading ? (
              <div className="read-list-state"><Spin /></div>
            ) : isError ? (
              <div className="read-list-state">{t("read.load_failed")}</div>
            ) : showSatCatalog ? (
              <>
                <p className="read-sat-note">{t("read.sat_note")}</p>
                <ol className="read-list">
                  {catalogTexts!.map((x) => (
                    <li key={x.id}>
                      <a
                        className="read-list-title"
                        href={satTextUrl(x.cbeta_id) ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-umami-event="read_sat_out"
                        data-umami-event-id={x.cbeta_id}
                      >
                        {localizeHan(x.title_zh, lang)}
                      </a>
                      <span className="read-list-meta">
                        {[x.dynasty && localizeHan(x.dynasty, lang), x.translator && localizeHan(x.translator, lang)]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                      {/* 与标题同一个去处；读屏和 Tab 只认标题那一个链接，避免重复播报 */}
                      <a
                        className="read-list-sat"
                        href={satTextUrl(x.cbeta_id) ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        tabIndex={-1}
                        aria-hidden="true"
                      >
                        {t("read.sat_link")} ↗
                      </a>
                      <span className="read-list-id">{x.cbeta_id}</span>
                    </li>
                  ))}
                </ol>
              </>
            ) : !texts || texts.length === 0 ? (
              <Empty description={t("read.empty")} />
            ) : (
              <ol className="read-list">
                {texts.map((x) => (
                  <li key={x.id}>
                    <Link className="read-list-title" to={`/texts/${x.id}`}>
                      {localizeHan(x.title_zh, lang)}
                    </Link>
                    <span className="read-list-meta">
                      {[
                        x.dynasty && localizeHan(x.dynasty, lang),
                        x.translator && localizeHan(x.translator, lang),
                        x.fascicle_count ? t("read.fascicles", { n: x.fascicle_count }) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    <span className="read-list-id">{x.cbeta_id}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </section>

      {collections.length > 0 && (
        <section className="read-section">
          <h2 className="read-h2">{t("read.topics")}</h2>
          <div className="read-topics">
            {collections.map((c) => (
              <Link key={c.id} className="read-topic" to={`/collections/${c.id}`}>
                {c.name}
              </Link>
            ))}
            <Link className="read-topic read-topic-all" to="/collections">
              {t("read.topics_all")}
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
