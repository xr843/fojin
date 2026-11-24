import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Button, Empty, Spin } from "antd";
import { getTibetanZhIndex } from "../api/tibetanZh";
import TibetanZhNotice from "../components/TibetanZhNotice";
import { groupItems } from "../utils/tibetanZhIndex";
import "../styles/sources.css";
import "../styles/tibetan-zh.css";

/**
 * 藏译汉稿（/tibetan-zh）——展示开源项目 tibetan-canon-zh 的 AI 汉译稿。
 *
 * ⚠️ AI 译稿，未经懂藏文的专家审定：只做展示，不进 AI 问答、不进检索（见后端
 * services/tibetan_zh.py）。页顶的提示是这一条的对外表达，不要删。
 */

export default function TibetanZhListPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["tibetanZhIndex"],
    queryFn: getTibetanZhIndex,
    staleTime: 10 * 60_000,
  });
  const groups = useMemo(() => groupItems(data?.items ?? []), [data]);

  return (
    <div className="sources-page tz-list-page">
      <Helmet>
        <title>{t("tibetanZh.page_title")}</title>
        <meta name="description" content={t("tibetanZh.page_desc")} />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">{t("tibetanZh.title")}</h1>
        <p className="sources-desc">{t("tibetanZh.subtitle")}</p>
      </div>

      <TibetanZhNotice />

      {isLoading ? (
        <div className="tz-state">
          <Spin />
        </div>
      ) : isError ? (
        <div className="tz-state">
          <p>{t("tibetanZh.load_failed")}</p>
          <Button onClick={() => refetch()}>{t("tibetanZh.retry")}</Button>
        </div>
      ) : groups.length === 0 ? (
        <Empty description={t("tibetanZh.empty")} />
      ) : (
        <>
          <p className="tz-count">{t("tibetanZh.count", { n: data!.items.length })}</p>
          {groups.map((g) => (
            <section key={g.part} className="tz-part">
              <h2 className="tz-part-title">
                {g.labelKey ? t(g.labelKey) : g.part}
                <span className="tz-part-count">{t("tibetanZh.count", { n: g.count })}</span>
              </h2>
              {g.cats.map((c) => (
                <div key={c.cat} className="tz-cat">
                  <h3 className="tz-cat-title">{c.cat}</h3>
                  <ol className="tz-items">
                    {c.items.map((it) => (
                      <li key={it.id} className="tz-item">
                        <span className="tz-item-id">{it.id}</span>
                        <Link className="tz-item-title" to={`/tibetan-zh/${encodeURIComponent(it.id)}`}>
                          《{it.title}》
                        </Link>
                        {it.au && <span className="tz-item-au">{it.au}</span>}
                        {it.rv && <span className="tz-item-rv">{it.rv}</span>}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
