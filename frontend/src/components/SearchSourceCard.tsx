import { useEffect } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { BookOutlined } from "@ant-design/icons";
import { verifyQuote } from "../api/client";
import { looksLikeSourceQuery, pickSourceMatch } from "../utils/searchSource";

function track(event: string, data: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(event, data);
}

/**
 * 搜索页「出处」卡片：查询像一段原文时，和搜索并行调用 /verify/quote，
 * 逐字命中且最早的一部是经/律/论，才在结果上方写出原典。
 * 其余情况（没命中、命中的是经录/语录/注疏、接口出错）一律不渲染，搜索结果照常。
 */
export default function SearchSourceCard({ query }: { query: string }) {
  const { t } = useTranslation();
  const q = Array.from(query.trim()).slice(0, 400).join("");
  const enabled = looksLikeSourceQuery(q);
  const { data } = useQuery({
    queryKey: ["searchSource", q],
    // 卡片可有可无：限流（429）、太短（422）、网络错误都当「没有出处」，不进 React Query 的出错状态。
    queryFn: () => verifyQuote(q).catch(() => null),
    enabled,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const match = enabled ? pickSourceMatch(data) : null;

  useEffect(() => {
    if (match) track("search_source_show", { cbeta: match.cbeta_id ?? "" });
  }, [match]);

  if (!match) return null;

  const title = match.title_zh ?? match.cbeta_id ?? "";
  return (
    <div className="s-source-card" role="note" aria-label={t("search.source.label")}>
      <BookOutlined className="s-source-icon" />
      <div className="s-source-body">
        <div className="s-source-line">
          <span className="s-source-label">{t("search.source.label")}</span>
          <Link
            className="s-source-title"
            to={`/texts/${match.text_id}/read?juan=${match.juan_num}`}
            onClick={() => track("search_source_open", { to: "reader", cbeta: match.cbeta_id ?? "" })}
          >
            《{title}》{t("search.source.juan", { n: match.juan_num })}
          </Link>
          {match.cbeta_id && <span className="s-source-id">{match.cbeta_id}</span>}
          <Link
            className="s-source-verify"
            to={`/verify?q=${encodeURIComponent(q)}`}
            onClick={() => track("search_source_open", { to: "verify", cbeta: match.cbeta_id ?? "" })}
          >
            {t("search.source.verify")}
          </Link>
        </div>
        <div className="s-source-hint">{t("search.source.hint")}</div>
      </div>
    </div>
  );
}
