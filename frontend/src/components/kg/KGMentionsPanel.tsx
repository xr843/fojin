/**
 * KGMentionsPanel — 描述中提及的实体面板
 *
 * 当一个实体在结构化 kg_relations 里没有关系（DILA 收录的孤岛节点常态），
 * 改为扫描其 description 中提及的其它已知实体，作为软关联展示。
 * 点击实体名跳转到对应实体页。
 *
 * 不写入 kg_relations，仅在 UI 层呈现，用「描述中提及」标签与正式关系区分。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Spin, Empty, Tag } from "antd";
import { TYPE_COLORS, TYPE_LABEL_KEYS } from "../ForceGraph";
import { getKGEntityMentions } from "../../api/client";
import type { KGMentionItem } from "../../api/client";

interface KGMentionsPanelProps {
  entityId: number;
  entityName: string;
  onEntityClick: (id: number) => void;
}

export default function KGMentionsPanel({
  entityId,
  entityName,
  onEntityClick,
}: KGMentionsPanelProps) {
  const { t } = useTranslation();
  const [mentions, setMentions] = useState<KGMentionItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMentions(null);
    getKGEntityMentions(entityId)
      .then((res) => {
        if (cancelled) return;
        setMentions(res.mentions);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? t("kg.load_failed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, t]);

  if (loading) {
    return (
      <div className="kg-mentions-loading">
        <Spin />
      </div>
    );
  }

  if (error) {
    return <div className="kg-mentions-error">{t("kg.mentions_load_failed", { msg: error })}</div>;
  }

  if (!mentions || mentions.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t("kg.mentions_empty", { name: entityName })}
      />
    );
  }

  return (
    <div className="kg-mentions-panel">
      <div className="kg-mentions-header">
        <span className="kg-mentions-title">{t("kg.mentions_title")}</span>
        <span className="kg-mentions-hint">
          {t("kg.mentions_hint", { n: mentions.length })}
        </span>
      </div>
      <div className="kg-mentions-list">
        {mentions.map((m) => {
          const color = TYPE_COLORS[m.entity_type] ?? "#888";
          const label = TYPE_LABEL_KEYS[m.entity_type] ? t(TYPE_LABEL_KEYS[m.entity_type]) : m.entity_type;
          return (
            <button
              type="button"
              key={m.id}
              className="kg-mentions-item"
              onClick={() => onEntityClick(m.id)}
              title={m.snippet ?? undefined}
            >
              <Tag color={color} bordered={false} style={{ marginRight: 6 }}>
                {label}
              </Tag>
              <span className="kg-mentions-name">{m.name_zh}</span>
              {m.snippet && (
                <span className="kg-mentions-snippet">… {m.snippet} …</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
