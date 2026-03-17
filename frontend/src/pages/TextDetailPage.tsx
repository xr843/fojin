import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import {
  Typography,
  Descriptions,
  Spin,
  Button,
  Space,
  Card,
  Tag,
  Breadcrumb,
} from "antd";
import {
  ReadOutlined,
  FileImageOutlined,
  HomeOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { getTextDetail, getTextManifests, getTextIdentifiers } from "../api/client";
import { buildCbetaReadUrl } from "../utils/sourceUrls";
import ResourceList from "../components/ResourceList";
import BookmarkButton from "../components/BookmarkButton";
import RelatedTexts from "../components/RelatedTexts";
import CitationGenerator from "../components/CitationGenerator";
import { addViewHistory } from "../utils/history";

const { Title } = Typography;

export default function TextDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [citationOpen, setCitationOpen] = useState(false);

  const { data: text, isLoading } = useQuery({
    queryKey: ["text", id],
    queryFn: () => getTextDetail(Number(id)),
    enabled: !!id,
  });

  const { data: manifests } = useQuery({
    queryKey: ["manifests", id],
    queryFn: () => getTextManifests(Number(id)),
    enabled: !!id,
  });

  const { data: identifiers } = useQuery({
    queryKey: ["identifiers", id],
    queryFn: () => getTextIdentifiers(Number(id)),
    enabled: !!id,
  });

  useEffect(() => {
    if (text && id) {
      addViewHistory(text.id, text.title_zh, `/texts/${id}`);
    }
  }, [text, id]);

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!text) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Typography.Text type="secondary">经典未找到</Typography.Text>
      </div>
    );
  }

  const resources = [];
  // CBETA 在线阅读链接
  const cbetaUrl = text.cbeta_url || buildCbetaReadUrl(text.cbeta_id);
  if (cbetaUrl) {
    resources.push({ label: "CBETA 在线阅读", url: cbetaUrl });
  }
  // 多数据源链接（来自 TextIdentifier），去重 CBETA
  if (identifiers) {
    for (const ident of identifiers) {
      if (!ident.source_url) continue;
      // 跳过与 CBETA 在线阅读重复的链接
      if (cbetaUrl && ident.source_url === cbetaUrl) continue;
      resources.push({
        label: `${ident.source_name} (${ident.source_uid})`,
        url: ident.source_url,
      });
    }
  }

  return (
    <div className="text-detail-page">
      <Helmet>
        <title>{text.title_zh} — 佛津</title>
        <meta name="description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}` : ""}${text.category ? ` · ${text.category}` : ""} — 佛津佛教古籍资源`} />
        <link rel="canonical" href={`https://fojin.app/texts/${id}`} />
      </Helmet>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Breadcrumb
          items={[
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}><HomeOutlined /> 首页</span> },
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/search")}>搜索</span> },
            { title: "经典详情" },
          ]}
        />

        <Card>
          <Title level={3} style={{ marginBottom: 4 }}>
            {text.title_zh}
          </Title>
          <Space style={{ marginBottom: 16 }}>
            <Tag color="blue">{text.cbeta_id}</Tag>
            {text.taisho_id && text.taisho_id !== text.cbeta_id && (
              <Tag>{text.taisho_id}</Tag>
            )}
            {text.category && <Tag color="geekblue">{text.category}</Tag>}
          </Space>

          <Descriptions column={1} bordered size="small">
            {text.translator && (
              <Descriptions.Item label="译者">
                {text.dynasty ? `${text.dynasty} ` : ""}
                {text.translator}
              </Descriptions.Item>
            )}
            {text.dynasty && (
              <Descriptions.Item label="朝代">
                {text.dynasty}
              </Descriptions.Item>
            )}
            {text.fascicle_count && (
              <Descriptions.Item label="卷数">
                {text.fascicle_count} 卷
              </Descriptions.Item>
            )}
            {text.subcategory && (
              <Descriptions.Item label="典藏">
                {text.subcategory}
              </Descriptions.Item>
            )}
            {text.title_sa && (
              <Descriptions.Item label="梵文名">
                {text.title_sa}
              </Descriptions.Item>
            )}
            {text.title_pi && (
              <Descriptions.Item label="巴利文名">
                {text.title_pi}
              </Descriptions.Item>
            )}
            {text.title_bo && (
              <Descriptions.Item label="藏文名">
                {text.title_bo}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="CBETA 编号">
              {text.cbeta_id}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Space>
          {text.has_content && (
            <Button
              type="primary"
              size="large"
              icon={<BookOutlined />}
              onClick={() => navigate(`/texts/${text.id}/read`)}
            >
              在线阅读
            </Button>
          )}
          {cbetaUrl && (
            <Button
              size="large"
              icon={<ReadOutlined />}
              href={cbetaUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              CBETA 阅读
            </Button>
          )}
          <BookmarkButton textId={text.id} />
          {manifests && manifests.length > 0 && (
            <Button
              icon={<FileImageOutlined />}
              onClick={() => navigate(`/manuscripts/${text.id}`)}
            >
              手稿影像 ({manifests.length})
            </Button>
          )}
          {/* TODO: 引用格式生成器和笔记功能待后端完善后启用
          <Button
            icon={<BookOutlined />}
            onClick={() => setCitationOpen(true)}
          >
            引用
          </Button>
          <Button
            icon={<FileTextOutlined />}
            onClick={() => navigate("/notes")}
          >
            笔记
          </Button>
          */}
        </Space>

        <CitationGenerator
          textId={text.id}
          open={citationOpen}
          onClose={() => setCitationOpen(false)}
        />

        <ResourceList resources={resources} />

        <RelatedTexts textId={text.id} />
      </Space>
    </div>
  );
}
