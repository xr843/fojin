import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
export default function ApparatusPanel({ textId, juanNum, visible, onClose }: ApparatusPanelProps) {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["juanApparatus", textId, juanNum],
    queryFn: () => getJuanApparatus(textId, juanNum),
    enabled: visible && !!textId,
  });

  const entries: ApparatusEntryItem[] = data?.entries ?? [];

  return (
    <Drawer
      title={t("reader.apparatus.title", { n: juanNum })}
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
        <Empty description={t("reader.apparatus.empty")} />
      ) : (
        <>
          <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            {t("reader.apparatus.summary", { n: entries.length })}
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
                          <Text>{r.is_omission ? t("reader.apparatus.omission") : r.reading}</Text>
                          {r.resp && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {t("reader.apparatus.corrector", { resp: r.resp })}
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
