import { useState, useMemo, memo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, List, Tag, Typography, Button, Spin, Empty } from "antd";
import { SwapOutlined, ReadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router";
import { getTextRelations } from "../api/client";

const RELATION_LABELS: Record<string, { labelKey: string; color: string }> = {
  alt_translation: { labelKey: "reader.related.relation.alt_translation", color: "orange" },
  parallel: { labelKey: "reader.related.relation.parallel", color: "blue" },
  commentary: { labelKey: "reader.related.relation.commentary", color: "green" },
  cites: { labelKey: "reader.related.relation.cites", color: "red" },
};

function RelatedTextsContent({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(textId),
    enabled: !!textId,
  });

  const availableTypes = useMemo(() => {
    if (!data?.relations.length) return [];
    const types = new Set(data.relations.map((r) => r.relation_type));
    return Object.keys(RELATION_LABELS).filter((t) => types.has(t));
  }, [data]);

  const filtered = useMemo(() => {
    if (!data?.relations) return [];
    if (activeTypes.size === 0) return data.relations;
    return data.relations.filter((r) => activeTypes.has(r.relation_type));
  }, [data, activeTypes]);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  if (isLoading) {
    return <Spin />;
  }

  if (!data?.relations.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t("reader.related.empty")}
        style={{ padding: "16px 0" }}
      />
    );
  }

  return (
    <>
      {availableTypes.length > 1 && (
        <div style={{ marginBottom: 12 }}>
          {availableTypes.map((type) => {
            const meta = RELATION_LABELS[type];
            const isActive = activeTypes.has(type);
            return (
              <Tag.CheckableTag
                key={type}
                checked={isActive}
                onChange={() => toggleType(type)}
                style={{
                  borderColor: isActive ? undefined : meta.color,
                  color: isActive ? undefined : meta.color,
                }}
              >
                {t(meta.labelKey)}
              </Tag.CheckableTag>
            );
          })}
        </div>
      )}
      <List
        size="small"
        dataSource={filtered}
        renderItem={(item) => {
          const meta = RELATION_LABELS[item.relation_type] || {
            labelKey: item.relation_type,
            color: "default",
          };
          return (
            <List.Item
              actions={[
                <Button
                  type="link"
                  size="small"
                  icon={<ReadOutlined />}
                  onClick={() =>
                    navigate(`/parallel/${textId}?compare=${item.text_id}`)
                  }
                >
                  {t("reader.related.compare")}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Button
                    type="link"
                    style={{ padding: 0, height: "auto" }}
                    onClick={() => navigate(`/texts/${item.text_id}`)}
                  >
                    {item.title_zh}
                    <Tag color={meta.color} style={{ marginLeft: 8 }}>
                      {RELATION_LABELS[item.relation_type] ? t(meta.labelKey) : item.relation_type}
                    </Tag>
                  </Button>
                }
                description={
                  <Typography.Text type="secondary">
                    {item.dynasty && `${item.dynasty} · `}
                    {item.translator || t("reader.common.anonymous")}
                    {item.lang !== "lzh" && ` · ${item.lang}`}
                  </Typography.Text>
                }
              />
            </List.Item>
          );
        }}
      />
    </>
  );
}

/** Standalone card version (used in TextDetailPage) */
function RelatedTextsCard({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(textId),
    enabled: !!textId,
  });

  if (!data?.relations.length) return null;

  return (
    <Card
      title={
        <span>
          <SwapOutlined /> {t("reader.related.title")}
        </span>
      }
      size="small"
    >
      <RelatedTextsContent textId={textId} />
    </Card>
  );
}

/** Inline version (used in ReaderSidebar tabs) */
const RelatedTexts = memo(RelatedTextsContent);
export default RelatedTexts;
export const RelatedTextsStandalone = memo(RelatedTextsCard);
