import { useParams, useNavigate, Navigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import {
  Typography,
  Card,
  Button,
  Breadcrumb,
  Row,
  Col,
  Tag,
  Divider,
  Space,
} from "antd";
import {
  HomeOutlined,
  ReadOutlined,
  RobotOutlined,
  BookOutlined,
} from "@ant-design/icons";
import {
  getSutraBySlug,
  getRelatedSutras,
  popularSutras,
} from "../data/popularSutras";
import { useTranslation } from "react-i18next";

const { Title, Paragraph, Text } = Typography;

export default function SutraLandingPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const sutra = slug ? getSutraBySlug(slug) : undefined;

  if (!sutra) {
    return <Navigate to="/404" replace />;
  }

  const related = getRelatedSutras(sutra.slug, 4);
  const canonicalUrl = `https://fojin.app/sutras/${sutra.slug}`;

  const schemaBook = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: sutra.title_zh,
    alternateName: [sutra.title_en, sutra.title_sa].filter(Boolean),
    url: canonicalUrl,
    inLanguage: "lzh",
    ...(sutra.translator && {
      translator: { "@type": "Person", name: sutra.translator },
    }),
    ...(sutra.dynasty && { temporalCoverage: sutra.dynasty }),
    genre: "Buddhist Scripture",
    isPartOf: {
      "@type": "Collection",
      name: t("sutra_landing.cbeta_name"),
      url: "https://www.cbeta.org/",
    },
    provider: {
      "@type": "WebSite",
      name: t("sutra_landing.site_name"),
      url: "https://fojin.app/",
    },
  };

  const schemaBreadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: t("sutra_landing.home"),
        item: "https://fojin.app/",
      },
      {
        "@type": "ListItem",
        position: 2,
        name: sutra.title_zh,
        item: canonicalUrl,
      },
    ],
  };

  return (
    <div
      className="sutra-landing-page"
      style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px" }}
    >
      <Helmet>
        <title>{sutra.meta_title}</title>
        <meta name="description" content={sutra.meta_description} />
        <meta name="keywords" content={sutra.keywords.join(",")} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="x-default" href={canonicalUrl} />
        <link rel="alternate" hrefLang="zh" href={canonicalUrl} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={sutra.meta_title} />
        <meta property="og:description" content={sutra.meta_description} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:site_name" content={t("sutra_landing.site_name")} />
        <meta property="og:locale" content="zh_CN" />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content={sutra.meta_title} />
        <meta
          name="twitter:description"
          content={sutra.meta_description}
        />
        <script type="application/ld+json">
          {JSON.stringify(schemaBook)}
        </script>
        <script type="application/ld+json">
          {JSON.stringify(schemaBreadcrumb)}
        </script>
      </Helmet>

      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {/* Breadcrumb */}
        <Breadcrumb
          items={[
            {
              title: (
                <span
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate("/")}
                >
                  <HomeOutlined /> {t("sutra_landing.home")}
                </span>
              ),
            },
            { title: t("sutra_landing.popular_sutras") },
            { title: sutra.title_zh.length > 10
                ? sutra.title_zh.slice(0, 10) + "..."
                : sutra.title_zh },
          ]}
        />

        {/* Title Block */}
        <Card>
          <Title level={2} style={{ marginBottom: 4 }}>
            {sutra.title_zh}
          </Title>
          {sutra.title_en && (
            <Text
              type="secondary"
              style={{ fontSize: 16, display: "block", marginBottom: 4 }}
            >
              {sutra.title_en}
            </Text>
          )}
          {sutra.title_sa && (
            <Text
              type="secondary"
              italic
              style={{ fontSize: 14, display: "block", marginBottom: 12 }}
            >
              {sutra.title_sa}
            </Text>
          )}
          <Space wrap style={{ marginBottom: 12 }}>
            <Tag color="blue">{sutra.cbeta_id}</Tag>
            {sutra.dynasty && (
              <Tag color="gold">{sutra.dynasty}</Tag>
            )}
            {sutra.translator && (
              <Tag color="geekblue">{t("sutra_landing.translator_tag", { translator: sutra.translator })}</Tag>
            )}
            {sutra.fascicle_count > 0 && (
              <Tag>{t("sutra_landing.fascicle_count", { count: sutra.fascicle_count })}</Tag>
            )}
          </Space>
        </Card>

        {/* Introduction */}
        <Card title={t("sutra_landing.introduction_title")}>
          <Typography>
            {sutra.introduction.map((para, i) => (
              <Paragraph key={i} style={{ fontSize: 15, lineHeight: 1.8 }}>
                {para}
              </Paragraph>
            ))}
          </Typography>
        </Card>

        {/* CTA Actions */}
        <Card>
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} sm={8}>
              <Button
                type="primary"
                size="large"
                icon={<ReadOutlined />}
                block
                onClick={() => navigate(`/texts/${sutra.text_id}/read`)}
              >
                {t("sutra_landing.start_reading")}
              </Button>
            </Col>
            <Col xs={24} sm={8}>
              <Button
                size="large"
                icon={<BookOutlined />}
                block
                onClick={() => navigate(`/texts/${sutra.text_id}`)}
              >
                {t("sutra_landing.text_details")}
              </Button>
            </Col>
            <Col xs={24} sm={8}>
              <Button
                size="large"
                icon={<RobotOutlined />}
                block
                onClick={() =>
                  navigate(
                    `/chat?q=${encodeURIComponent(t("sutra_landing.chat_prompt", { title: sutra.title_zh }))}`
                  )
                }
              >
                {t("sutra_landing.ai_qa")}
              </Button>
            </Col>
          </Row>
        </Card>

        {/* Related Sutras */}
        <div>
          <Divider>
            <Text strong style={{ fontSize: 16 }}>
              {t("sutra_landing.more_popular_sutras")}
            </Text>
          </Divider>
          <Row gutter={[16, 16]}>
            {related.map((r) => (
              <Col xs={12} sm={6} key={r.slug}>
                <Card
                  hoverable
                  size="small"
                  onClick={() => navigate(`/sutras/${r.slug}`)}
                  style={{ textAlign: "center", height: "100%" }}
                >
                  <Text strong style={{ display: "block", marginBottom: 4 }}>
                    {r.title_zh.length > 8
                      ? r.title_zh.replace(
                          /^(.*?)(经|论)$/,
                          (_, p1, p2) =>
                            p1.length > 6 ? p1.slice(0, 6) + "..." + p2 : p1 + p2
                        )
                      : r.title_zh}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {r.title_en}
                  </Text>
                </Card>
              </Col>
            ))}
          </Row>

          {/* Full list link */}
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <Space wrap>
              {popularSutras
                .filter((s) => s.slug !== sutra.slug)
                .slice(4)
                .map((s) => (
                  <Tag
                    key={s.slug}
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/sutras/${s.slug}`)}
                  >
                    {s.title_en}
                  </Tag>
                ))}
            </Space>
          </div>
        </div>

        {/* Attribution */}
        <div
          style={{
            textAlign: "center",
            padding: "16px 0",
            color: "var(--fj-ink-muted, #9a8e7a)",
            fontSize: 13,
          }}
        >
          {t("sutra_landing.data_provided_by")}{" "}
          <a
            href="https://www.cbeta.org/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--fj-accent, #8b2500)" }}
          >
            {t("sutra_landing.cbeta_association")}
          </a>{" "}
          {t("sutra_landing.provided")}
        </div>
      </Space>
    </div>
  );
}
