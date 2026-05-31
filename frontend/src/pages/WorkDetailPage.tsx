import { useParams, useNavigate, Navigate, Link } from "react-router-dom";
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
  const langs = [...new Set(witnesses.map((w) => workLangLabel(w.lang)))];
  const metaDesc =
    `《${work.title_primary}》的跨语言 / 跨藏经全版本对照` +
    (altTitles.length ? `（${altTitles.join(" · ")}）` : "") +
    `，共 ${work.witness_count} 个见证本，涵盖 ${langs.join("、")}。`;

  const schemaBook = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: work.title_primary,
    alternateName: altTitles,
    url: canonicalUrl,
    genre: "Buddhist Scripture",
    provider: { "@type": "WebSite", name: "佛津 FoJin", url: "https://fojin.app/" },
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px" }}>
      <Helmet>
        <title>{`${work.title_primary} — 全版本对照 | 佛津 FoJin`}</title>
        <meta name="description" content={metaDesc} />
        <link rel="canonical" href={canonicalUrl} />
        <meta property="og:type" content="book" />
        <meta property="og:title" content={`${work.title_primary} — 全版本对照`} />
        <meta property="og:description" content={metaDesc} />
        <meta property="og:url" content={canonicalUrl} />
        <meta property="og:site_name" content="佛津 FoJin" />
        <script type="application/ld+json">{JSON.stringify(schemaBook)}</script>
      </Helmet>

      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Breadcrumb
          items={[
            {
              title: (
                <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}>
                  <HomeOutlined /> 首页
                </span>
              ),
            },
            { title: "作品" },
            { title: work.title_primary },
          ]}
        />

        <div>
          <Title level={2} style={{ marginBottom: 8 }}>
            <SwapOutlined style={{ marginRight: 8, color: "#8b6914" }} />
            {work.title_primary}
          </Title>
          <Space size={[8, 8]} wrap>
            {work.title_sa && <Tag color="purple">梵 {work.title_sa}</Tag>}
            {work.title_pi && <Tag color="cyan">巴利 {work.title_pi}</Tag>}
            {work.sc_root_uid && <Tag>SuttaCentral {work.sc_root_uid}</Tag>}
            {work.toh_number && <Tag>Toh {work.toh_number}</Tag>}
            <Tag color="gold">{work.witness_count} 个见证本</Tag>
          </Space>
          <Paragraph type="secondary" style={{ marginTop: 12 }}>
            本作品聚合了跨语言 / 跨藏经的不同译本与见证本。点击任一版本即可阅读，
            或在阅读器内使用「跨藏对照」逐经 / 逐段对读。
          </Paragraph>
        </div>

        <Card title="全部版本" size="small">
          {witnesses.length === 0 ? (
            <Empty description="暂无见证本" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={witnesses}
              rowKey={(w) => String(w.text_id)}
              renderItem={(w) => {
                const canon = workCanonLabel(w.canon);
                return (
                  <List.Item
                    actions={[
                      <Link key="read" to={witnessHref(w)}>
                        {w.has_content ? (
                          <>
                            <ReadOutlined /> 阅读
                          </>
                        ) : (
                          <>
                            <BookOutlined /> 详情
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
                              底本
                            </Tag>
                          )}
                        </Link>
                      }
                      description={
                        <Text type="secondary">
                          <Tag color="blue">{workLangLabel(w.lang)}</Tag>
                          {canon && <Tag>{canon}</Tag>}
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
