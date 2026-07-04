import { useState, useEffect, useMemo } from "react";
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
  ExportOutlined,
} from "@ant-design/icons";
import { getTextDetail } from "../api/client";
import { useTranslation } from "react-i18next";
import { buildCbetaReadUrl } from "../utils/sourceUrls";
import { getLastPosition } from "../utils/readingHistory";
import BookmarkButton from "../components/BookmarkButton";
import { RelatedTextsStandalone as RelatedTexts } from "../components/RelatedTexts";
import OtherVersions from "../components/OtherVersions";
import CrossCanonEntry from "../components/CrossCanonEntry";
import CitationGenerator from "../components/CitationGenerator";
import { addViewHistory } from "../utils/history";

const { Title } = Typography;

export default function TextDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [citationOpen, setCitationOpen] = useState(false);
  // 续读：有本地阅读记录时，主按钮变为"继续阅读·第N卷"。
  // useMemo 按 id 重算：相关经典跳转复用同一路由实例，useState 初始化会 stale。
  const lastRead = useMemo(() => getLastPosition(Number(id)), [id]);

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
        <Typography.Text type="secondary">{t("textDetail.notFound")}</Typography.Text>
      </div>
    );
  }

  const cbetaUrl = text.cbeta_url || buildCbetaReadUrl(text.cbeta_id);
  const seoParts = [
    text.title_zh,
    text.translator ? t("textDetail.metaTranslator", { translator: text.translator }) : null,
    text.dynasty,
    text.category,
  ].filter(Boolean).join(" · ");
  const seoDescription = t("textDetail.seoDescription", { details: seoParts });
  const shortDescription = [
    text.title_zh,
    text.translator ? t("textDetail.metaTranslator", { translator: text.translator }) : null,
    text.category,
  ].filter(Boolean).join(" · ");

  return (
    <div className="text-detail-page">
      <Helmet>
        <title>{t("textDetail.pageTitle", { title: text.title_zh })}</title>
        <meta name="description" content={seoDescription} />
        <link rel="canonical" href={`https://fojin.app/texts/${id}`} />
        <link rel="alternate" hrefLang="x-default" href={`https://fojin.app/texts/${id}`} />
        <link rel="alternate" hrefLang="zh" href={`https://fojin.app/texts/${id}`} />
        <link rel="alternate" hrefLang="en" href={`https://fojin.app/texts/${id}?lang=en`} />
        <link rel="alternate" hrefLang="zh-Hant" href={`https://fojin.app/texts/${id}?lang=zh-Hant`} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={t("textDetail.pageTitle", { title: text.title_zh })} />
        <meta property="og:description" content={shortDescription} />
        <meta property="og:url" content={`https://fojin.app/texts/${id}`} />
        <meta property="og:site_name" content={t("app.name")} />
        <meta property="og:locale" content="zh_CN" />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content={t("textDetail.pageTitle", { title: text.title_zh })} />
        <meta name="twitter:description" content={shortDescription} />
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
              "name": t("textDetail.schemaCollectionName"),
              "url": "https://fojin.app/"
            },
            "provider": {
              "@type": "WebSite",
              "name": t("app.name"),
              "url": "https://fojin.app/"
            }
          })}
        </script>
      </Helmet>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Breadcrumb
          items={[
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}><HomeOutlined /> {t("nav.home", "首页")}</span> },
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/search")}>{t("nav.search", "搜索")}</span> },
            { title: t("textDetail.breadcrumbDetails") },
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
              <Descriptions.Item label={t("textDetail.translator")}>
                {text.dynasty ? `${text.dynasty} ` : ""}
                {text.translator}
              </Descriptions.Item>
            )}
            {text.dynasty && (
              <Descriptions.Item label={t("textDetail.dynasty")}>
                {text.dynasty}
              </Descriptions.Item>
            )}
            {text.fascicle_count && (
              <Descriptions.Item label={t("textDetail.fascicles")}>
                {t("textDetail.fascicleCount", { count: text.fascicle_count })}
              </Descriptions.Item>
            )}
            {text.subcategory && (
              <Descriptions.Item label={t("textDetail.collection")}>
                {text.subcategory}
              </Descriptions.Item>
            )}
            {text.title_sa && (
              <Descriptions.Item label={t("textDetail.sanskritTitle")}>
                {text.title_sa}
              </Descriptions.Item>
            )}
            {text.title_pi && (
              <Descriptions.Item label={t("textDetail.paliTitle")}>
                {text.title_pi}
              </Descriptions.Item>
            )}
            {text.title_bo && (
              <Descriptions.Item label={t("textDetail.tibetanTitle")}>
                {text.title_bo}
              </Descriptions.Item>
            )}
            <Descriptions.Item label={t("textDetail.cbetaId")}>
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
              onClick={() =>
                navigate(
                  lastRead
                    ? `/texts/${text.id}/read?juan=${lastRead.juan}`
                    : `/texts/${text.id}/read`,
                )
              }
            >
              {lastRead ? t("textDetail.continueReading", { n: lastRead.juan }) : t("textDetail.readOnline")}
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
              {t("textDetail.readOnCbeta")}
            </Button>
          )}
          <BookmarkButton textId={text.id} />
          <Button
            type="text"
            icon={<ExportOutlined />}
            onClick={() => setCitationOpen(true)}
          >
            {t("textDetail.exportCitation")}
          </Button>
        </Space>

        <CitationGenerator
          textId={text.id}
          textData={text}
          open={citationOpen}
          onClose={() => setCitationOpen(false)}
        />

        <CrossCanonEntry textId={text.id} />

        <OtherVersions textId={text.id} />

        <RelatedTexts textId={text.id} />
      </Space>
    </div>
  );
}
