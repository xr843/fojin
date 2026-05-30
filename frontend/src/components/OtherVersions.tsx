import { useQuery } from "@tanstack/react-query";
import { Card, List, Tag, Typography } from "antd";
import { SwapOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { getWorkByText, type WorkWitnessInfo } from "../api/client";

const { Text } = Typography;

/** lang code → 中文标签 */
const LANG_LABELS: Record<string, string> = {
  lzh: "中文",
  zh: "中文",
  pi: "巴利",
  pli: "巴利",
  sa: "梵文",
  san: "梵文",
  bo: "藏文",
  tib: "藏文",
  en: "英文",
};

/** canon code → 中文藏经名（仅常见者，未知则原样不展示） */
const CANON_LABELS: Record<string, string> = {
  taisho: "大正藏",
  xuzangjing: "卍續藏",
  xuzang: "卍續藏",
  pali: "巴利",
  kangyur: "甘珠爾",
  gretil: "GRETIL",
};

function langLabel(lang: string): string {
  return LANG_LABELS[lang] || lang;
}

function canonLabel(canon: string | null | undefined): string | null {
  if (!canon) return null;
  return CANON_LABELS[canon] || null;
}

function witnessHref(w: WorkWitnessInfo): string {
  return w.has_content ? `/texts/${w.text_id}/read` : `/texts/${w.text_id}`;
}

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
    >
      <List
        size="small"
        dataSource={siblings}
        rowKey={(w) => String(w.text_id)}
        renderItem={(w) => {
          const lang = langLabel(w.lang);
          const canon = canonLabel(w.canon);
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
    </Card>
  );
}
