import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Typography, Spin, Button, Card, Tag, Breadcrumb } from "antd";
import {
  ReadOutlined,
  HomeOutlined,
  BookOutlined,
  ExportOutlined,
  SoundOutlined,
} from "@ant-design/icons";
import { getTextDetail, getAvailableAudio } from "../api/client";
import { useTranslation } from "react-i18next";
import { buildCbetaReadUrl } from "../utils/sourceUrls";
import { getLastPosition } from "../utils/readingHistory";
import BookmarkButton from "../components/BookmarkButton";
import { RelatedTextsStandalone as RelatedTexts } from "../components/RelatedTexts";
import OtherVersions from "../components/OtherVersions";
import CrossCanonEntry from "../components/CrossCanonEntry";
import SourceAttribution from "../components/SourceAttribution";
import SameTitleTexts from "../components/SameTitleTexts";
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

  // 与 /read-aloud 索引页共用同一份缓存（目录很小，第一期只有一部经），
  // 所以这里不是额外一次请求。详情页访客比阅读页还多（90 天 1,355 vs 1,132），
  // 有音频却不在这里露出，等于白丢两成触达。
  const { data: audioCatalog } = useQuery({
    queryKey: ["audioCatalog"],
    queryFn: getAvailableAudio,
    staleTime: 5 * 60 * 1000,
  });
  const audioItem = audioCatalog?.items.find((it) => it.text_id === Number(id));

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
  // 藏别标签：优先分类（与搜索结果卡同源），没有分类时用藏经名（GRETIL 等非汉文条目只有后者）。
  const canonTag = text.category || text.canon_label || null;
  // 定义列表只放标签没说过的事：典藏与标签相同就不写，经号已是标签，外文题名与标题相同也不写；
  // 译者行不再拼朝代（朝代自有一行）；CBETA 的译者字段本身常以朝代开头（「十六國 鳩摩羅什」），
  // 那时朝代行就是重复，不再单列。
  const metaRows: [string, string][] = [];
  if (text.translator) metaRows.push([t("textDetail.translator"), text.translator]);
  if (text.dynasty && !(text.translator && text.translator.startsWith(text.dynasty))) {
    metaRows.push([t("textDetail.dynasty"), text.dynasty]);
  }
  if (text.fascicle_count) {
    metaRows.push([t("textDetail.fascicles"), t("textDetail.fascicleCount", { count: text.fascicle_count })]);
  }
  if (text.subcategory && text.subcategory !== canonTag) {
    metaRows.push([t("textDetail.collection"), text.subcategory]);
  }
  for (const [label, value] of [
    [t("textDetail.sanskritTitle"), text.title_sa],
    [t("textDetail.paliTitle"), text.title_pi],
    [t("textDetail.tibetanTitle"), text.title_bo],
  ] as const) {
    if (value && value !== text.title_zh) metaRows.push([label, value]);
  }
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
      <Breadcrumb
        className="td-breadcrumb"
        items={[
          { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}><HomeOutlined /> {t("nav.home", "首页")}</span> },
          { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/search")}>{t("nav.search", "搜索")}</span> },
          { title: t("textDetail.breadcrumbDetails") },
        ]}
      />

      <Card className="td-header">
        <Title level={3} className="td-title">
          {text.title_zh}
        </Title>
        {/* 标签写法照搜索结果卡（ResultCard）：中性底色的小号 antd Tag。
            经号与藏别已经在这里，下面的定义列表就不再重复这两项。 */}
        <div className="td-tags">
          <Tag title={t("textDetail.cbetaId")}>{text.cbeta_id}</Tag>
          {text.taisho_id && text.taisho_id !== text.cbeta_id && (
            <Tag>{text.taisho_id}</Tag>
          )}
          {canonTag && <Tag>{canonTag}</Tag>}
        </div>
        {/* 数据源署名。上面那些标签是**藏经**与分类，不是来源 ——
            CBETA(CC BY-NC-SA) 与 84000 都把署名列为许可条件。 */}
        <SourceAttribution textId={text.id} />

        {metaRows.length > 0 && (
          <dl className="td-meta">
            {metaRows.map(([label, value]) => (
              <div key={label} className="td-meta-row">
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* 只有一颗主按钮：有本地全文时是「在线阅读 / 继续阅读」，没有时 CBETA 外链补位。
            其余一律同款描边次级按钮——收藏组件默认是文字按钮，这里显式要描边款。 */}
        <div className="td-actions">
          {text.has_content && (
            <Button
              type="primary"
              size="large"
              className="td-primary"
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
              type={text.has_content ? "default" : "primary"}
              size="large"
              className={text.has_content ? undefined : "td-primary"}
              icon={<ReadOutlined />}
              href={cbetaUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("textDetail.readOnCbeta")}
            </Button>
          )}
          {audioItem && (
            <Button
              size="large"
              icon={<SoundOutlined />}
              onClick={() =>
                navigate(`/texts/${text.id}/read?juan=${audioItem.juans[0]?.juan_num ?? 1}`)
              }
            >
              {t("reader.audio.button")}
            </Button>
          )}
          <BookmarkButton textId={text.id} size="large" type="default" />
          <Button
            size="large"
            icon={<ExportOutlined />}
            onClick={() => setCitationOpen(true)}
          >
            {t("textDetail.exportCitation")}
          </Button>
        </div>
      </Card>

      <CitationGenerator
        textId={text.id}
        textData={text}
        open={citationOpen}
        onClose={() => setCitationOpen(false)}
      />

      {/* 下方各块各自判断有没有数据，没有就整块不渲染（不放空态占位）。 */}
      <div className="td-sections">
        <CrossCanonEntry textId={text.id} />
        <OtherVersions textId={text.id} />
        <SameTitleTexts textId={text.id} />
        <RelatedTexts textId={text.id} />
      </div>
    </div>
  );
}
