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
import { Spin, Empty, Tag } from "antd";
import { TYPE_COLORS, TYPE_LABELS } from "../ForceGraph";
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
        setError(e?.message ?? "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  if (loading) {
    return (
      <div className="kg-mentions-loading">
        <Spin />
      </div>
    );
  }

  if (error) {
    return <div className="kg-mentions-error">提及加载失败：{error}</div>;
  }

  if (!mentions || mentions.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={`「${entityName}」描述中也没有可关联的已知实体`}
      />
    );
  }

  return (
    <div className="kg-mentions-panel">
      <div className="kg-mentions-header">
        <span className="kg-mentions-title">描述中提及的实体</span>
        <span className="kg-mentions-hint">
          推断关联（非结构化）— 共 {mentions.length} 条
        </span>
      </div>
      <div className="kg-mentions-list">
        {mentions.map((m) => {
          const color = TYPE_COLORS[m.entity_type] ?? "#888";
          const label = TYPE_LABELS[m.entity_type] ?? m.entity_type;
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
