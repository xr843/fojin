import { useParams, useNavigate, Navigate } from "react-router";
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
  getLocalizedPopularSutras,
} from "../data/popularSutras";
import { useTranslation } from "react-i18next";

const { Title, Paragraph, Text } = Typography;

function compactTitle(title: string) {
  const maxLength = /[\u3400-\u9fff]/.test(title) ? 10 : 18;
  if (title.length <= maxLength) return title;
  return `${title.slice(0, maxLength)}...`;
}

function ogLocale(language: string) {
  if (language.startsWith("en")) return "en_US";
  if (language.startsWith("zh-Hant") || language.startsWith("zh-TW") || language.startsWith("zh-HK")) {
    return "zh_TW";
  }
  return "zh_CN";
}

export default function SutraLandingPage() {
  const { t, i18n } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const sutra = slug ? getSutraBySlug(slug, i18n.language) : undefined;

  if (!sutra) {
    return <Navigate to="/404" replace />;
  }

  const related = getRelatedSutras(sutra.slug, 4, i18n.language);
  const sutras = getLocalizedPopularSutras(i18n.language);
  const canonicalUrl = `https://fojin.app/sutras/${sutra.slug}`;

  const schemaBook = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: sutra.title,
    alternateName: [sutra.alternateTitle, sutra.sanskritTitle].filter(Boolean),
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
        name: sutra.title,
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
        <title>{sutra.metaTitle}</title>
        <meta name="description" content={sutra.metaDescription} />
        <meta name="keywords" content={sutra.keywords.join(",")} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="x-default" href={canonicalUrl} />
        <link rel="alternate" hrefLang="zh" href={canonicalUrl} />
        <link rel="alternate" hrefLang="en" href={`${canonicalUrl}?lang=en`} />
        <link rel="alternate" hrefLang="zh-Hant" href={`${canonicalUrl}?lang=zh-Hant`} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={sutra.metaTitle} />
        <meta property="og:description" content={sutra.metaDescription} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:site_name" content={t("sutra_landing.site_name")} />
        <meta property="og:locale" content={ogLocale(i18n.language)} />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content={sutra.metaTitle} />
        <meta
          name="twitter:description"
          content={sutra.metaDescription}
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
            { title: compactTitle(sutra.title) },
          ]}
        />

        {/* Title Block */}
        <Card>
          <Title level={2} style={{ marginBottom: 4 }}>
            {sutra.title}
          </Title>
          {sutra.alternateTitle && (
            <Text
              type="secondary"
              style={{ fontSize: 16, display: "block", marginBottom: 4 }}
            >
              {sutra.alternateTitle}
            </Text>
          )}
          {sutra.sanskritTitle && (
            <Text
              type="secondary"
              italic
              style={{ fontSize: 14, display: "block", marginBottom: 12 }}
            >
              {sutra.sanskritTitle}
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
                    `/chat?q=${encodeURIComponent(t("sutra_landing.chat_prompt", { title: sutra.title }))}`
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
                    {compactTitle(r.title)}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {compactTitle(r.alternateTitle)}
                  </Text>
                </Card>
              </Col>
            ))}
          </Row>

          {/* Full list link */}
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <Space wrap>
              {sutras
                .filter((s) => s.slug !== sutra.slug)
                .slice(4)
                .map((s) => (
                  <Tag
                    key={s.slug}
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/sutras/${s.slug}`)}
                  >
                    {s.title}
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
            color: "var(--fj-ink-muted, var(--fj-ink-muted))",
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
