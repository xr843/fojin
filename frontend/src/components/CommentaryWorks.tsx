import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Button, Card } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router";
import { getCommentaryCorpus, type CommentaryCorpusCommentary } from "../api/client";

const COLLAPSED = 8;
const TIER_ORDER: Record<string, number> = { A: 0, B: 1, C: 2 };

/**
 * 「历代注疏」：经注对读语料（/commentary/corpus）里注这部经的注疏。
 *
 * 这张表引文抽屉早就在取（同一个 queryKey，一天缓存），但只用来判定「这段引文是不是
 * 某部注疏」；/texts/7 有 52 家注疏、详情页却一家都不露。这里只列**书**，不做逐句
 * 对读——那个入口在引文抽屉里，有它自己的埋点与杀死条件，这里不去复制。
 *
 * 诚实标注：语料只收了做过经注对齐的注疏，「列出的注家不等于全部注家」必须写出来，
 * 否则读者会把这张清单当成完整书目。quarantine 档（母本判定存疑）不列。
 */
export default function CommentaryWorks({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const { data: corpus } = useQuery({
    queryKey: ["commentary-corpus"],
    queryFn: getCommentaryCorpus,
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  const items = useMemo<CommentaryCorpusCommentary[]>(() => {
    const baseWorks = new Set(
      (corpus?.sutras ?? []).filter((s) => s.text_id === textId).map((s) => s.base_work),
    );
    if (baseWorks.size === 0) return [];
    return (corpus?.commentaries ?? [])
      .filter((c) => c.base_work != null && baseWorks.has(c.base_work) && c.tier !== "quarantine")
      .sort(
        (a, b) =>
          (TIER_ORDER[a.tier ?? ""] ?? 9) - (TIER_ORDER[b.tier ?? ""] ?? 9) || b.anchors - a.anchors,
      );
  }, [corpus, textId]);

  if (items.length === 0) return null;
  const visible = expanded ? items : items.slice(0, COLLAPSED);

  return (
    <Card
      className="td-section"
      size="small"
      title={
        <span>
          <ReadOutlined /> {t("textDetail.commentaries.title", { n: items.length })}
        </span>
      }
    >
      <p className="td-section-hint">{t("textDetail.commentaries.caveat")}</p>
      <ul className="td-grid-list">
        {visible.map((c) => {
          const title = c.title || c.cbeta_id || c.work;
          return (
            <li key={c.work}>
              {c.text_id != null ? (
                <Link to={`/texts/${c.text_id}`} className="td-item-title">
                  {title}
                </Link>
              ) : (
                <span className="td-item-title">{title}</span>
              )}
              {c.cbeta_id && <span className="td-item-meta">{c.cbeta_id}</span>}
            </li>
          );
        })}
      </ul>
      {items.length > COLLAPSED && (
        <Button type="link" size="small" className="td-more" onClick={() => setExpanded((e) => !e)}>
          {expanded ? t("textDetail.showLess") : t("textDetail.showAll", { n: items.length })}
        </Button>
      )}
    </Card>
  );
}
