import { memo } from "react";
import { useQuery } from "@tanstack/react-query";
import { List, Typography, Tag, Button, Spin, Empty } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getSimilarPassages } from "../api/client";

function SimilarPassagesInner({
  textId,
  juanNum,
}: {
  textId: number;
  juanNum: number;
}) {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["similarPassages", textId, juanNum],
    queryFn: () => getSimilarPassages(textId, juanNum),
    enabled: !!textId && !!juanNum,
    staleTime: 600_000, // 10 minutes cache
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 24 }}>
        <Spin size="small" />
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--fj-ink-muted)" }}>
          正在查找相似段落…
        </div>
      </div>
    );
  }

  if (!data?.passages.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无相似段落"
        style={{ padding: "16px 0" }}
      />
    );
  }

  return (
    <List
      size="small"
      dataSource={data.passages}
      renderItem={(item) => (
        <List.Item
          style={{ padding: "8px 0", alignItems: "flex-start" }}
          actions={[
            <Button
              type="link"
              size="small"
              icon={<ReadOutlined />}
              onClick={() => navigate(`/texts/${item.text_id}/read`)}
            >
              阅读
            </Button>,
          ]}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ marginBottom: 4 }}>
              <Button
                type="link"
                size="small"
                style={{ padding: 0, height: "auto", fontWeight: 500 }}
                onClick={() => navigate(`/texts/${item.text_id}`)}
              >
                {item.title_zh}
              </Button>
              <Tag
                color="blue"
                style={{ marginLeft: 6, fontSize: 11 }}
              >
                {Math.round(item.score * 100)}%
              </Tag>
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {item.dynasty && `${item.dynasty} · `}
              {item.translator || "佚名"}
              {` · 第${item.juan_num}卷`}
            </Typography.Text>
            <Typography.Paragraph
              type="secondary"
              ellipsis={{ rows: 2 }}
              style={{
                fontSize: 13,
                margin: "4px 0 0",
                lineHeight: 1.6,
                color: "var(--fj-ink-light)",
              }}
            >
              {item.chunk_text}
            </Typography.Paragraph>
          </div>
        </List.Item>
      )}
    />
  );
}

export default memo(SimilarPassagesInner);
