import { useQuery } from "@tanstack/react-query";
import { Drawer, List, Tag, Typography, Empty, Spin, Space } from "antd";
import { getJuanApparatus, type ApparatusEntryItem } from "../api/client";

const { Text } = Typography;

interface ApparatusPanelProps {
  textId: number;
  juanNum: number;
  visible: boolean;
  onClose: () => void;
}

/**
 * Critical apparatus (校勘异文) panel: lists this juan's variant readings —
 * the base text (底本) lemma against the readings witnessed by other canons
 * (宋/元/明/麗…). Footnote-style list; inline highlighting is a later iteration
 * (the reader reflows text, so char offsets don't map to the rendered DOM).
 */
function readingText(reading: string, isOmission: boolean): string {
  return isOmission ? "（無此字）" : reading;
}

export default function ApparatusPanel({ textId, juanNum, visible, onClose }: ApparatusPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["juanApparatus", textId, juanNum],
    queryFn: () => getJuanApparatus(textId, juanNum),
    enabled: visible && !!textId,
  });

  const entries: ApparatusEntryItem[] = data?.entries ?? [];

  return (
    <Drawer
      title={`校勘异文 · 第${juanNum}卷`}
      placement="right"
      width={440}
      open={visible}
      onClose={onClose}
    >
      {isLoading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : entries.length === 0 ? (
        <Empty description="此卷暂无校勘异文" />
      ) : (
        <>
          <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            底本与宋 / 元 / 明 / 麗等校本的异读，共 {entries.length} 条
          </Text>
          <List
            size="small"
            dataSource={entries}
            renderItem={(e) => (
              <List.Item>
                <div style={{ width: "100%" }}>
                  <Space size={6} wrap>
                    {e.lemma_siglum && <Tag color="gold">{e.lemma_siglum}</Tag>}
                    <Text strong>{e.lemma}</Text>
                  </Space>
                  <div style={{ marginTop: 6 }}>
                    {e.readings.map((r, i) => (
                      <div key={i} style={{ marginTop: 2 }}>
                        <Space size={4} wrap>
                          {r.witnesses.map((w) => (
                            <Tag key={w} style={{ marginInlineEnd: 0 }}>
                              {w}
                            </Tag>
                          ))}
                          <Text>{readingText(r.reading, r.is_omission)}</Text>
                          {r.resp && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              （{r.resp} 校）
                            </Text>
                          )}
                        </Space>
                      </div>
                    ))}
                  </div>
                </div>
              </List.Item>
            )}
          />
        </>
      )}
    </Drawer>
  );
}
