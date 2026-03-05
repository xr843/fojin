import { useState, useMemo, memo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, List, Tag, Typography, Button, Spin } from "antd";
import { SwapOutlined, ReadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getTextRelations } from "../api/client";

const RELATION_LABELS: Record<string, { label: string; color: string }> = {
  alt_translation: { label: "异译", color: "orange" },
  parallel: { label: "平行文本", color: "blue" },
  commentary: { label: "注疏", color: "green" },
  cites: { label: "引用", color: "red" },
};

function RelatedTextsInner({ textId }: { textId: number }) {
  const navigate = useNavigate();
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(textId),
    enabled: !!textId,
  });

  // Collect the relation types that actually exist in the data
  const availableTypes = useMemo(() => {
    if (!data?.relations.length) return [];
    const types = new Set(data.relations.map((r) => r.relation_type));
    // Return in the order defined by RELATION_LABELS
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
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  if (isLoading) {
    return <Spin />;
  }

  if (!data?.relations.length) {
    return null;
  }

  return (
    <Card
      title={
        <span>
          <SwapOutlined /> 关联文本
        </span>
      }
      size="small"
    >
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
                {meta.label}
              </Tag.CheckableTag>
            );
          })}
        </div>
      )}
      <List
        dataSource={filtered}
        renderItem={(item) => {
          const meta = RELATION_LABELS[item.relation_type] || {
            label: item.relation_type,
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
                  对照
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
                      {meta.label}
                    </Tag>
                  </Button>
                }
                description={
                  <Typography.Text type="secondary">
                    {item.dynasty && `${item.dynasty} · `}
                    {item.translator || "佚名"}
                    {item.lang !== "lzh" && ` · ${item.lang}`}
                  </Typography.Text>
                }
              />
            </List.Item>
          );
        }}
      />
    </Card>
  );
}

export default memo(RelatedTextsInner);
