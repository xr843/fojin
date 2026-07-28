import { useParams, useNavigate, Navigate, Link } from "react-router";
import { Helmet } from "react-helmet-async";
import {
  Typography,
  Card,
  List,
  Tag,
  Breadcrumb,
  Spin,
  Space,
  Empty,
} from "antd";
import {
  HomeOutlined,
  SwapOutlined,
  ReadOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getWork, getWorkWitnesses } from "../api/client";
import { workLangLabel, workCanonLabel, witnessHref } from "../utils/works";

const { Title, Text, Paragraph } = Typography;

/**
 * 作品详情页 /works/:slug —— FRBR Work 的落地页。
 * 聚合一部作品的全部跨语言 / 跨藏经见证本，各自链向其阅读页。
 * 这是"作品级全版本视图"的独立可分享 / 可 SEO 入口。
 */
export default function WorkDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const {
    data: work,
    isLoading: workLoading,
    error: workError,
  } = useQuery({
    queryKey: ["work", slug],
    queryFn: () => getWork(slug!),
    enabled: !!slug,
    retry: false,
  });

  const { data: witnesses = [], isLoading: witLoading } = useQuery({
    queryKey: ["work-witnesses", slug],
    queryFn: () => getWorkWitnesses(slug!),
    enabled: !!slug,
    retry: false,
  });

  if (workLoading || witLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (workError || !work) {
    return <Navigate to="/404" replace />;
  }

  const canonicalUrl = `https://fojin.app/works/${work.slug}`;
  const altTitles = [work.title_sa, work.title_pi].filter(Boolean) as string[];
  const altTitleText = altTitles.length
    ? t("workDetail.altTitles", { titles: altTitles.join(" · ") })
    : "";
  const langs = [...new Set(witnesses.map((w) => workLangLabel(w.lang, t)))];
  const metaDesc = t("workDetail.metaDescription", {
    title: work.title_primary,
    altTitles: altTitleText,
    count: work.witness_count,
    langs: langs.join(t("workDetail.listSeparator")),
  });

  const schemaBook = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: work.title_primary,
    alternateName: altTitles,
    url: canonicalUrl,
    genre: "Buddhist Scripture",
    provider: { "@type": "WebSite", name: t("app.name"), url: "https://fojin.app/" },
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px" }}>
      <Helmet>
        <title>{t("workDetail.pageTitle", { title: work.title_primary })}</title>
        <meta name="description" content={metaDesc} />
        <link rel="canonical" href={canonicalUrl} />
        <link rel="alternate" hrefLang="x-default" href={canonicalUrl} />
        <link rel="alternate" hrefLang="zh" href={canonicalUrl} />
        <link rel="alternate" hrefLang="en" href={`${canonicalUrl}?lang=en`} />
        <link rel="alternate" hrefLang="zh-Hant" href={`${canonicalUrl}?lang=zh-Hant`} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={t("workDetail.ogTitle", { title: work.title_primary })} />
        <meta property="og:description" content={metaDesc} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:site_name" content={t("app.name")} />
        <script type="application/ld+json">{JSON.stringify(schemaBook)}</script>
      </Helmet>

      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Breadcrumb
          items={[
            {
              title: (
                <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}>
                  <HomeOutlined /> {t("nav.home", "首页")}
                </span>
              ),
            },
            { title: t("workDetail.breadcrumbWorks") },
            { title: work.title_primary },
          ]}
        />

        <div>
          <Title level={2} style={{ marginBottom: 8 }}>
            <SwapOutlined style={{ marginRight: 8, color: "#8b6914" }} />
            {work.title_primary}
          </Title>
          <Space size={[8, 8]} wrap>
            {work.title_sa && <Tag color="purple">{t("workDetail.sanskritTag", { title: work.title_sa })}</Tag>}
            {work.title_pi && <Tag color="cyan">{t("workDetail.paliTag", { title: work.title_pi })}</Tag>}
            {work.sc_root_uid && <Tag>SuttaCentral {work.sc_root_uid}</Tag>}
            {work.toh_number && <Tag>Toh {work.toh_number}</Tag>}
            <Tag color="gold">{t("workDetail.witnessCount", { count: work.witness_count })}</Tag>
          </Space>
          <Paragraph type="secondary" style={{ marginTop: 12 }}>
            {t("workDetail.intro")}
          </Paragraph>
        </div>

        <Card title={t("workDetail.allVersions")} size="small">
          {witnesses.length === 0 ? (
            <Empty description={t("workDetail.noWitnesses")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={witnesses}
              rowKey={(w) => String(w.text_id)}
              renderItem={(w) => {
                const canon = workCanonLabel(w.canon);
                const canonLabel = workCanonLabel(w.canon, t);
                return (
                  <List.Item
                    actions={[
                      <Link key="read" to={witnessHref(w)}>
                        {w.has_content ? (
                          <>
                            <ReadOutlined /> {t("workDetail.read")}
                          </>
                        ) : (
                          <>
                            <BookOutlined /> {t("workDetail.details")}
                          </>
                        )}
                      </Link>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Link to={witnessHref(w)} style={{ fontWeight: 500 }}>
                          {w.title || w.cbeta_id}
                          {w.role === "root" && (
                            <Tag color="gold" style={{ marginLeft: 8 }}>
                              {t("workDetail.rootText")}
                            </Tag>
                          )}
                        </Link>
                      }
                      description={
                        <Text type="secondary">
                          <Tag color="blue">{workLangLabel(w.lang, t)}</Tag>
                          {canon && canonLabel && <Tag>{canonLabel}</Tag>}
                          {w.cbeta_id}
                        </Text>
                      }
                    />
                  </List.Item>
                );
              }}
            />
          )}
        </Card>
      </Space>
    </div>
  );
}
