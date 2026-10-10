import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Button, Card } from "antd";
import { BookOutlined } from "@ant-design/icons";
import { Link } from "react-router";
import { getTextRelations, getTextVersions, getWorkByText } from "../api/client";

/** 默认露出的条数；其余按需展开。 */
const COLLAPSED = 8;

/**
 * 「同名经典」：/texts/{id}/versions 里**按题名**找到的其他文本（relation_type 为空的那些行）。
 *
 * 为什么要这一块：生产 /texts/7（羅什譯《金剛經》）的 relations 是空的、works 只挂了它自己，
 * 详情页下方三分之二屏空白——而 /versions 早就按同名找到了菩提流支、真諦两译，只是没有任何
 * 界面在用这个接口。
 *
 * 标题刻意叫「同名」而不是「异译本」：这一路只比题名，同名的往往是同经异译，但也会撞上
 * 同名的另一部著作（例如道川《金剛經註》与僧肇《金剛經註》）。叫「异译」就是在说一件
 * 接口并没有核实过的事。
 *
 * relation_type 非空的行来自 text_relations，「关联文本」卡已经列了；已在「其他版本」
 * （works 见证本）里出现的也不重复。三个查询与那两张卡共用同一个 queryKey，不多打请求。
 */
export default function SameTitleTexts({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const { data: versions } = useQuery({
    queryKey: ["text-versions", textId],
    queryFn: () => getTextVersions(textId),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const { data: relations } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(textId),
    enabled: !!textId,
  });
  const { data: work } = useQuery({
    queryKey: ["work-by-text", textId],
    queryFn: () => getWorkByText(textId),
    enabled: !!textId,
  });

  const items = useMemo(() => {
    if (!versions) return [];
    const shown = new Set<number>([textId]);
    relations?.relations.forEach((r) => shown.add(Number(r.text_id)));
    work?.witnesses.forEach((w) => shown.add(w.text_id));
    return versions.translations.filter((v) => v.relation_type == null && !shown.has(v.text_id));
  }, [versions, relations, work, textId]);

  if (items.length === 0) return null;
  const visible = expanded ? items : items.slice(0, COLLAPSED);

  return (
    <Card
      className="td-section"
      size="small"
      title={
        <span>
          <BookOutlined /> {t("textDetail.sameTitle.title", { n: items.length })}
        </span>
      }
    >
      <p className="td-section-hint">{t("textDetail.sameTitle.hint")}</p>
      <ul className="td-grid-list">
        {visible.map((v) => (
          <li key={v.text_id}>
            <Link to={`/texts/${v.text_id}`} className="td-item-title">
              {v.title_zh || v.title_en}
            </Link>
            <span className="td-item-meta">
              {/* 有译者只写译者：CBETA 译者字段自带朝代前缀，再拼 dynasty 既重复，又会把
                  两字段互相矛盾的数据拼成「元 · 魏 菩提流支」这种错话（菩提流支本即如此）。 */}
              {[v.translator || v.dynasty, v.lang && v.lang !== "lzh" ? t(`lang.${v.lang}`, v.lang) : null]
                .filter(Boolean)
                .join(" · ") || t("reader.common.anonymous")}
            </span>
          </li>
        ))}
      </ul>
      {items.length > COLLAPSED && (
        <Button type="link" size="small" className="td-more" onClick={() => setExpanded((e) => !e)}>
          {expanded ? t("textDetail.showLess") : t("textDetail.showAll", { n: items.length })}
        </Button>
      )}
    </Card>
  );
}
