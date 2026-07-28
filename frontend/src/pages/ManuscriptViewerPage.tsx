import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Typography, Spin, Card, List, Empty, Button, Space, Tag } from "antd";
import { ArrowLeftOutlined, FileImageOutlined, EyeOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import IIIFViewer from "../components/IIIFViewer";
import { getTextManifests, getTextDetail } from "../api/client";

export default function ManuscriptViewerPage() {
  const { t } = useTranslation();
  const { textId } = useParams<{ textId: string }>();
  const navigate = useNavigate();
  const [selectedManifestUrl, setSelectedManifestUrl] = useState<string | null>(null);

  const { data: text } = useQuery({
    queryKey: ["text", textId],
    queryFn: () => getTextDetail(Number(textId)),
    enabled: !!textId,
  });

  const { data: manifests, isLoading } = useQuery({
    queryKey: ["manifests", textId],
    queryFn: () => getTextManifests(Number(textId)),
    enabled: !!textId,
  });

  return (
    <div style={{ maxWidth: 1200, margin: "24px auto", padding: "0 16px" }}>
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="text"
          aria-label={t("manuscript.back")}
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(-1)}
        >
          {t("manuscript.back")}
        </Button>
        <Typography.Title level={3} style={{ margin: 0 }}>
          <FileImageOutlined /> {t("manuscript.title")}
          {text && <span style={{ fontWeight: "normal", fontSize: 16, marginLeft: 8 }}>{text.title_zh}</span>}
        </Typography.Title>
      </Space>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : !manifests?.length ? (
        <Card>
          <Empty description={t("manuscript.empty")} />
        </Card>
      ) : (
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Card title={t("manuscript.available_images")} size="small">
            <List
              dataSource={manifests}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      type="primary"
                      size="small"
                      aria-label={t("manuscript.view")}
                      icon={<EyeOutlined />}
                      onClick={() => setSelectedManifestUrl(item.manifest_url)}
                    >
                      {t("manuscript.view")}
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.label}
                    description={
                      <Space>
                        <Tag>{item.provider.toUpperCase()}</Tag>
                        {item.rights && <Typography.Text type="secondary">{item.rights}</Typography.Text>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>

          {selectedManifestUrl && (
            <Card title={t("manuscript.viewer")} size="small">
              <IIIFViewer manifestUrl={selectedManifestUrl} height="650px" />
            </Card>
          )}
        </Space>
      )}
    </div>
  );
}
