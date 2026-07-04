/**
 * PersonPage — SPA 交互式人物页 /person/:id
 *
 * 读取 /api/kg/entities/{id}（已含 relations[]），展示人物档案。
 * 路由：/person/:id（注意是单数，避免与后端 /persons/:id SEO 页冲突）
 */
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  Spin,
  Typography,
  Button,
  Divider,
  Tooltip,
  Empty,
} from "antd";
import {
  ApartmentOutlined,
  LinkOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { getKGEntity } from "../api/client";
import type { EntityRelationItem } from "../api/client";
import "../styles/person.css";

// ── 外部权威库 URI 映射 ────────────────────────────────────────────
// fojin 不发明自己的 entity URI；改为把权威库的稳定 ID 暴露出来作为
// LOD 节点的桥梁（参见 ctext.org Linked Open Data 模式）。新增权威
// 库只需在此表添加一项。

interface SameAsLink {
  key: string;          // external_ids 的 key（wikidata / dila / ...）
  authorityLabelKey: string; // 权威库名的 i18n key，渲染时 t() 取值
  idLabel: string;      // 例如 "Q12345" or "P0000001"
  url: string;          // 直接可点击的稳定 URL
}

const AUTHORITY_MAP: Record<
  string,
  { labelKey: string; urlFor: (id: string) => string }
> = {
  wikidata: {
    labelKey: "person.authority_wikidata",
    urlFor: (id) => `https://www.wikidata.org/wiki/${encodeURIComponent(id)}`,
  },
  dila: {
    labelKey: "person.authority_dila",
    urlFor: (id) =>
      `https://authority.dila.edu.tw/person/?fromInner=${encodeURIComponent(id)}`,
  },
  bdrc: {
    labelKey: "person.authority_bdrc",
    urlFor: (id) =>
      `https://library.bdrc.io/show/bdr:${encodeURIComponent(id)}`,
  },
  viaf: {
    labelKey: "person.authority_viaf",
    urlFor: (id) => `https://viaf.org/viaf/${encodeURIComponent(id)}`,
  },
  loc: {
    labelKey: "person.authority_loc",
    urlFor: (id) =>
      `https://id.loc.gov/authorities/names/${encodeURIComponent(id)}`,
  },
};

function buildSameAsLinks(
  externalIds: Record<string, string> | null | undefined,
): SameAsLink[] {
  if (!externalIds) return [];
  const links: SameAsLink[] = [];
  for (const [key, value] of Object.entries(externalIds)) {
    if (!value) continue;
    const entry = AUTHORITY_MAP[key];
    if (!entry) continue; // 未知权威库静默跳过——不要破前端
    links.push({
      key,
      authorityLabelKey: entry.labelKey,
      idLabel: value,
      url: entry.urlFor(value),
    });
  }
  return links;
}

interface PersonJsonLd {
  "@context": "https://schema.org";
  "@type": "Person";
  name: string;
  url?: string;
  alternateName?: string[];
  description?: string;
  identifier?: Array<{
    "@type": "PropertyValue";
    propertyID: string;
    value: string;
  }>;
  sameAs?: string[];
}

function buildPersonJsonLd(
  entity: {
    id: number;
    name_zh: string;
    name_en?: string | null;
    name_sa?: string | null;
    name_pi?: string | null;
    name_bo?: string | null;
    description?: string | null;
    external_ids?: Record<string, string> | null;
  },
  sameAs: SameAsLink[],
): PersonJsonLd {
  const alt = [entity.name_en, entity.name_sa, entity.name_pi, entity.name_bo].filter(
    (a): a is string => Boolean(a),
  );
  const payload: PersonJsonLd = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: entity.name_zh || `佛教人物 #${entity.id}`, // i18n-exempt — JSON-LD payload for crawlers, not rendered UI
    url: `https://fojin.app/person/${entity.id}`,
  };
  if (alt.length) payload.alternateName = alt;
  if (entity.description) payload.description = entity.description.slice(0, 500);
  if (entity.external_ids) {
    const ids = Object.entries(entity.external_ids)
      .filter(([, v]) => Boolean(v))
      .map(([k, v]) => ({
        "@type": "PropertyValue" as const,
        propertyID: k,
        value: String(v),
      }));
    if (ids.length) payload.identifier = ids;
  }
  if (sameAs.length) payload.sameAs = sameAs.map((s) => s.url);
  return payload;
}

// ── 属性提取（与 seo_persons.py 逻辑对等） ─────────────────────────

function personDisplayDates(props: Record<string, unknown> | null | undefined): string {
  if (!props || typeof props !== "object") return "";
  const birth = (props["birth_year"] as string | undefined) || (props["birth"] as string | undefined);
  const death = (props["death_year"] as string | undefined) || (props["death"] as string | undefined);
  if (birth && death) return `（${birth}–${death}）`;
  if (birth) return `（${birth}–）`;
  if (death) return `（–${death}）`;
  return "";
}

function personDynasty(props: Record<string, unknown> | null | undefined): string {
  if (!props || typeof props !== "object") return "";
  return ((props["dynasty"] as string | undefined) || (props["era"] as string | undefined) || "").trim();
}

function personNationality(props: Record<string, unknown> | null | undefined): string {
  if (!props || typeof props !== "object") return "";
  return (
    (props["nationality"] as string | undefined) ||
    (props["country"] as string | undefined) ||
    ""
  ).trim();
}

function personSchool(props: Record<string, unknown> | null | undefined): string {
  if (!props || typeof props !== "object") return "";
  return ((props["school"] as string | undefined) || (props["tradition"] as string | undefined) || "").trim();
}

// ── 关系分组与标签 ──────────────────────────────────────────────────

const PREDICATE_LABEL_KEYS: Record<string, string> = {
  translated: "kg.pred_translated",
  active_in: "kg.pred_active_in",
  alt_translation: "kg.pred_alt_translation",
  parallel_text: "kg.pred_parallel_text",
  member_of_school: "entity.pred_member_of_school",
  teacher_of: "geo.lineage",
  cites: "kg.pred_cites",
  commentary_on: "kg.pred_commentary_on",
  associated_with: "kg.pred_associated_with",
};

// 按展示优先级排列
const PREDICATE_ORDER = [
  "teacher_of",
  "translated",
  "commentary_on",
  "active_in",
  "member_of_school",
  "associated_with",
  "cites",
  "alt_translation",
  "parallel_text",
];

const TYPE_META: Record<string, { labelKey: string; className: string }> = {
  person:    { labelKey: "geo.type_person", className: "kg-type-tag kg-type-tag--person" },
  text:      { labelKey: "geo.type_text", className: "kg-type-tag kg-type-tag--text" },
  monastery: { labelKey: "geo.type_temple", className: "kg-type-tag kg-type-tag--monastery" },
  school:    { labelKey: "geo.type_school", className: "kg-type-tag kg-type-tag--school" },
  place:     { labelKey: "geo.type_place", className: "kg-type-tag kg-type-tag--place" },
  concept:   { labelKey: "geo.type_concept", className: "kg-type-tag kg-type-tag--concept" },
  dynasty:   { labelKey: "geo.type_dynasty", className: "kg-type-tag kg-type-tag--dynasty" },
};

const SOURCE_LABEL_KEYS: Record<string, string> = {
  dila_catalog: "entity.source_dila_catalog",
  dila: "entity.source_dila",
  "auto:cbeta_metadata": "entity.source_cbeta_metadata",
  "seed:lineage": "entity.source_seed_lineage",
  "seed:person_place": "entity.source_seed_person_place",
  "seed:school_affiliation": "entity.source_seed_school_affiliation",
};

function prettifySource(t: TFunction, source: string): string {
  if (SOURCE_LABEL_KEYS[source]) return t(SOURCE_LABEL_KEYS[source]);
  if (source.startsWith("seed:")) return t("entity.source_seed_generic");
  if (source.startsWith("auto:")) return t("entity.source_auto_generic");
  if (source.startsWith("dila")) return t("entity.source_dila");
  return source;
}

/** 根据目标实体类型决定链接路径 */
function targetLink(rel: EntityRelationItem): string {
  if (rel.target_type === "text") return `/texts/${rel.target_id}`;
  if (rel.target_type === "person") return `/person/${rel.target_id}`;
  return `/kg?id=${rel.target_id}`;
}

// ── 主组件 ─────────────────────────────────────────────────────────

export default function PersonPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: entity, isLoading, isError } = useQuery({
    queryKey: ["kgEntity", id],
    queryFn: () => getKGEntity(Number(id)),
    enabled: !!id,
    retry: 1,
  });

  // ── 加载中 ──
  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  // ── 未找到 / 非人物 ──
  if (isError || !entity || entity.entity_type !== "person") {
    return (
      <div className="person-page">
        <Empty
          description={
            <span style={{ fontFamily: '"Noto Serif SC", serif', color: "#7a6e5c" }}>
              {t("person.not_found")}
            </span>
          }
          style={{ padding: "80px 0" }}
        />
        <div style={{ textAlign: "center" }}>
          <Button onClick={() => navigate("/kg")}>{t("person.back_to_kg")}</Button>
        </div>
      </div>
    );
  }

  // ── 属性提取 ──
  const props = entity.properties as Record<string, unknown> | null;
  const dates = personDisplayDates(props);
  const dynasty = personDynasty(props);
  const nationality = personNationality(props);
  const school = personSchool(props);
  const sameAsLinks = buildSameAsLinks(entity.external_ids);
  const jsonLd = buildPersonJsonLd(entity, sameAsLinks);

  // ── 关系分组 ──
  const relationsByPredicate: Record<string, EntityRelationItem[]> = {};
  for (const rel of entity.relations ?? []) {
    if (!relationsByPredicate[rel.predicate]) {
      relationsByPredicate[rel.predicate] = [];
    }
    relationsByPredicate[rel.predicate].push(rel);
  }

  // 按优先级排序 predicate key 列表
  const sortedPredicates = [
    ...PREDICATE_ORDER.filter((p) => p in relationsByPredicate),
    ...Object.keys(relationsByPredicate).filter((p) => !PREDICATE_ORDER.includes(p)),
  ];

  const metaBits = [dynasty, nationality, school].filter(Boolean);

  const helmetTitle = t("person.helmet_title", { name: entity.name_zh, dates });
  const helmetDesc = (
    entity.description ||
    t("person.helmet_desc_fallback", {
      name: entity.name_zh,
      meta: metaBits.length ? "（" + metaBits.join(" · ") + "）" : "",
    })
  ).slice(0, 200);

  return (
    <div className="person-page">
      <Helmet>
        <title>{helmetTitle}</title>
        <meta name="description" content={helmetDesc} />
        <link rel="canonical" href={`https://fojin.app/person/${entity.id}`} />
        <link rel="alternate" hrefLang="x-default" href={`https://fojin.app/person/${entity.id}`} />
        <link rel="alternate" hrefLang="zh" href={`https://fojin.app/person/${entity.id}`} />
        <link rel="alternate" hrefLang="en" href={`https://fojin.app/person/${entity.id}?lang=en`} />
        <link rel="alternate" hrefLang="zh-Hant" href={`https://fojin.app/person/${entity.id}?lang=zh-Hant`} />
        <meta property="og:type" content="profile" />
        <meta property="og:title" content={helmetTitle} />
        <meta property="og:description" content={helmetDesc} />
        <meta property="og:url" content={`https://fojin.app/person/${entity.id}`} />
        <meta property="og:site_name" content={t("person.og_site_name")} />
        <script type="application/ld+json">{JSON.stringify(jsonLd)}</script>
      </Helmet>

      {/* ── 面包屑 ── */}
      <nav className="person-breadcrumb">
        <span
          className="person-breadcrumb-link"
          onClick={() => navigate("/")}
        >
          {t("person.breadcrumb_home")}
        </span>
        <span className="person-breadcrumb-sep">›</span>
        <span
          className="person-breadcrumb-link"
          onClick={() => navigate("/kg")}
        >
          {t("nav.kg")}
        </span>
        <span className="person-breadcrumb-sep">›</span>
        <span className="person-breadcrumb-current">{entity.name_zh}</span>
      </nav>

      {/* ── 主卡片 ── */}
      <div className="person-card">
        {/* 标题行 */}
        <div className="person-header">
          <div className="person-title-row">
            <h1 className="person-name">
              {entity.name_zh}
              {dates && <span className="person-dates">{dates}</span>}
            </h1>
            <span className="kg-type-tag kg-type-tag--person">{t("geo.type_person")}</span>
          </div>

          {/* 元信息徽章行 */}
          {metaBits.length > 0 && (
            <div className="person-meta">
              {metaBits.map((bit, i) => (
                <span key={i} className="person-meta-chip">{bit}</span>
              ))}
            </div>
          )}
        </div>

        {/* 多语言名称 */}
        {(entity.name_sa || entity.name_pi || entity.name_bo || entity.name_en) && (
          <div className="person-altnames">
            {entity.name_sa && (
              <div className="person-altname-row">
                <span className="person-altname-lang">{t("lang.sa")}</span>
                <span className="person-altname-val">{entity.name_sa}</span>
              </div>
            )}
            {entity.name_pi && (
              <div className="person-altname-row">
                <span className="person-altname-lang">{t("person.lang_pi")}</span>
                <span className="person-altname-val">{entity.name_pi}</span>
              </div>
            )}
            {entity.name_bo && (
              <div className="person-altname-row">
                <span className="person-altname-lang">{t("lang.bo")}</span>
                <span className="person-altname-val">{entity.name_bo}</span>
              </div>
            )}
            {entity.name_en && (
              <div className="person-altname-row">
                <span className="person-altname-lang">{t("lang.en")}</span>
                <span className="person-altname-val">{entity.name_en}</span>
              </div>
            )}
          </div>
        )}

        {/* 简介 */}
        {entity.description && (
          <Typography.Paragraph className="person-description">
            {entity.description}
          </Typography.Paragraph>
        )}

        {/* 标准标识符 — 标记 fojin 为 LOD 节点的桥梁 */}
        {sameAsLinks.length > 0 && (
          <div className="person-extlinks">
            <div className="person-extlinks-label">{t("person.identifiers")}</div>
            {sameAsLinks.map((link) => (
              <a
                key={link.key}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="person-extlink"
                title={t("person.authority_tooltip", { name: t(link.authorityLabelKey) })}
              >
                <LinkOutlined style={{ marginRight: 4 }} />
                {t(link.authorityLabelKey)} {link.idLabel}
              </a>
            ))}
          </div>
        )}

        {/* 在知识图谱中查看 */}
        <div className="person-kg-link">
          <Button
            icon={<ApartmentOutlined />}
            onClick={() => navigate(`/kg?id=${entity.id}`)}
            className="person-kg-btn"
          >
            {t("person.view_in_kg")}
          </Button>
        </div>
      </div>

      {/* ── 关系面板 ── */}
      {sortedPredicates.length > 0 && (
        <div className="person-card person-relations-card">
          <h2 className="person-section-title">{t("person.relations_title")}</h2>
          {sortedPredicates.map((predicate) => {
            const rels = relationsByPredicate[predicate];
            return (
              <div key={predicate} className="person-rel-group">
                <div className="person-rel-group-head">
                  <span className="person-rel-label">
                    {PREDICATE_LABEL_KEYS[predicate] ? t(PREDICATE_LABEL_KEYS[predicate]) : predicate}
                  </span>
                  <span className="person-rel-count">{rels.length}</span>
                </div>
                <div className="person-rel-items">
                  {rels.map((rel) => {
                    const relMeta = TYPE_META[rel.target_type];
                    const relTypeLabel = relMeta ? t(relMeta.labelKey) : rel.target_type;
                    const relTypeClassName = relMeta?.className ?? "kg-type-tag";
                    return (
                      <Link
                        key={`${rel.predicate}-${rel.target_id}-${rel.direction}`}
                        to={targetLink(rel)}
                        className="person-rel-item"
                      >
                        {rel.direction === "outgoing" ? (
                          <ArrowRightOutlined className="person-rel-arrow" />
                        ) : (
                          <ArrowLeftOutlined className="person-rel-arrow" />
                        )}
                        <span
                          className={relTypeClassName}
                          style={{ fontSize: 9, lineHeight: "16px", padding: "0 4px" }}
                        >
                          {relTypeLabel}
                        </span>
                        <span className="person-rel-name">{rel.target_name}</span>
                        {rel.source && (
                          <Tooltip title={t("entity.relation_source_tooltip", { source: rel.source })}>
                            <span className="person-rel-source">
                              {t("entity.source_according_to", { name: prettifySource(t, rel.source) })}
                            </span>
                          </Tooltip>
                        )}
                      </Link>
                    );
                  })}
                </div>
                <Divider className="person-rel-divider" />
              </div>
            );
          })}
        </div>
      )}

      {/* 无关系时提示 */}
      {sortedPredicates.length === 0 && (
        <div className="person-card">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span style={{ color: "#9a8e7a", fontFamily: '"Noto Serif SC", serif' }}>
                {t("person.no_relations")}
              </span>
            }
          />
        </div>
      )}
    </div>
  );
}

// Explicit named export for use in EntityCard navigation
export { UserOutlined };
