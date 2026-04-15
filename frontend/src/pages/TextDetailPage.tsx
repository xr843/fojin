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
  HomeOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { getTextDetail } from "../api/client";
import { buildCbetaReadUrl } from "../utils/sourceUrls";
import BookmarkButton from "../components/BookmarkButton";
import { RelatedTextsStandalone as RelatedTexts } from "../components/RelatedTexts";
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

  const cbetaUrl = text.cbeta_url || buildCbetaReadUrl(text.cbeta_id);

  return (
    <div className="text-detail-page">
      <Helmet>
        <title>{text.title_zh} — 佛津</title>
        <meta name="description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.dynasty ? ` · ${text.dynasty}` : ""}${text.category ? ` · ${text.category}` : ""} — 佛津佛教古籍数字资源平台`} />
        <link rel="canonical" href={`https://fojin.app/texts/${id}`} />
        <link rel="alternate" hrefLang="x-default" href={`https://fojin.app/texts/${id}`} />
        <link rel="alternate" hrefLang="zh" href={`https://fojin.app/texts/${id}`} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={`${text.title_zh} — 佛津`} />
        <meta property="og:description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.category ? ` · ${text.category}` : ""}`} />
        <meta property="og:url" content={`https://fojin.app/texts/${id}`} />
        <meta property="og:site_name" content="佛津 FoJin" />
        <meta property="og:locale" content="zh_CN" />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content={`${text.title_zh} — 佛津`} />
        <meta name="twitter:description" content={`${text.title_zh}${text.translator ? ` · ${text.translator}译` : ""}${text.category ? ` · ${text.category}` : ""}`} />
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Book",
            "name": text.title_zh,
            ...(text.title_sa && { "alternateName": text.title_sa }),
            "url": `https://fojin.app/texts/${id}`,
            "inLanguage": text.lang || "lzh",
            ...(text.translator && {
              "translator": { "@type": "Person", "name": text.translator }
            }),
            ...(text.dynasty && { "temporalCoverage": text.dynasty }),
            ...(text.category && { "genre": text.category }),
            "isPartOf": {
              "@type": "Collection",
              "name": "佛津 FoJin 佛教古籍数字资源",
              "url": "https://fojin.app/"
            },
            "provider": {
              "@type": "WebSite",
              "name": "佛津 FoJin",
              "url": "https://fojin.app/"
            }
          })}
        </script>
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

        <Space wrap>
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
              style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)", color: "#fff" }}
            >
              CBETA 阅读
            </Button>
          )}
          <Button
            icon={<BookOutlined />}
            onClick={() => setCitationOpen(true)}
            style={{ background: "#5b8c6b", borderColor: "#5b8c6b", color: "#fff" }}
          >
            导出引用
          </Button>
          <BookmarkButton textId={text.id} />
        </Space>

        <CitationGenerator
          textId={text.id}
          textData={text}
          open={citationOpen}
          onClose={() => setCitationOpen(false)}
        />

        <RelatedTexts textId={text.id} />
      </Space>
    </div>
  );
}
