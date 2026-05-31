import { useQuery } from "@tanstack/react-query";
import { Card, List, Tag, Typography } from "antd";
import { SwapOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { getWorkByText } from "../api/client";
import { workLangLabel, workCanonLabel, witnessHref } from "../utils/works";

const { Text } = Typography;

/**
 * 「其他版本 / 对照本」面板：展示当前文本所属 FRBR Work 下、除自身以外的
 * 全部见证本（跨语言/跨藏经的同一经的不同版本），各自链向其阅读页。
 *
 * 不渲染的情况：加载中 / 无数据 / 接口 404（null）/ 仅有自身一个见证本。
 */
export default function OtherVersions({ textId }: { textId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["work-by-text", textId],
    queryFn: () => getWorkByText(textId),
    enabled: !!textId,
  });

  if (isLoading) return null;
  if (!data) return null;

  const siblings = data.witnesses.filter((w) => w.text_id !== textId);
  if (siblings.length === 0) return null;

  return (
    <Card
      title={
        <span>
          <SwapOutlined /> 其他版本 · {data.witness_count} 个见证本
        </span>
      }
      size="small"
      style={{ marginBottom: 12 }}
    >
      <List
        size="small"
        dataSource={siblings}
        rowKey={(w) => String(w.text_id)}
        renderItem={(w) => {
          const lang = workLangLabel(w.lang);
          const canon = workCanonLabel(w.canon);
          return (
            <List.Item>
              <List.Item.Meta
                title={
                  <Link to={witnessHref(w)} style={{ fontWeight: 500 }}>
                    {w.title || w.cbeta_id}
                    {w.role === "root" && (
                      <Tag color="gold" style={{ marginLeft: 8 }}>
                        底本
                      </Tag>
                    )}
                  </Link>
                }
                description={
                  <Text type="secondary">
                    <Tag color="blue">{lang}</Tag>
                    {canon && <Tag>{canon}</Tag>}
                    {w.cbeta_id}
                  </Text>
                }
              />
            </List.Item>
          );
        }}
      />
      <div style={{ textAlign: "right", marginTop: 4 }}>
        <Link to={`/works/${data.slug}`} style={{ fontSize: 12 }}>
          查看作品全部 {data.witness_count} 个版本 →
        </Link>
      </div>
    </Card>
  );
}
