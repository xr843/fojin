/**
 * PersonPage — SPA 交互式人物页 /person/:id
 *
 * 读取 /api/kg/entities/{id}（已含 relations[]），展示人物档案。
 * 路由：/person/:id（注意是单数，避免与后端 /persons/:id SEO 页冲突）
 */
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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

const PREDICATE_LABELS: Record<string, string> = {
  translated: "翻译",
  active_in: "所处",
  alt_translation: "异译",
  parallel_text: "平行文本",
  member_of_school: "属于宗派",
  teacher_of: "师承",
  cites: "引用",
  commentary_on: "注疏",
  associated_with: "相关",
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

const TYPE_LABELS: Record<string, { label: string; className: string }> = {
  person:    { label: "人物", className: "kg-type-tag kg-type-tag--person" },
  text:      { label: "典籍", className: "kg-type-tag kg-type-tag--text" },
  monastery: { label: "寺院", className: "kg-type-tag kg-type-tag--monastery" },
  school:    { label: "宗派", className: "kg-type-tag kg-type-tag--school" },
  place:     { label: "地点", className: "kg-type-tag kg-type-tag--place" },
  concept:   { label: "概念", className: "kg-type-tag kg-type-tag--concept" },
  dynasty:   { label: "朝代", className: "kg-type-tag kg-type-tag--dynasty" },
};

const SOURCE_LABELS: Record<string, string> = {
  dila_catalog: "DILA 规范目录",
  dila: "DILA 规范库",
  "auto:cbeta_metadata": "CBETA 元数据",
  "seed:lineage": "师承谱系（人工校订）",
  "seed:person_place": "人物地理（人工校订）",
  "seed:school_affiliation": "宗派归属（人工校订）",
};

function prettifySource(source: string): string {
  if (SOURCE_LABELS[source]) return SOURCE_LABELS[source];
  if (source.startsWith("seed:")) return "人工校订";
  if (source.startsWith("auto:")) return "自动提取";
  if (source.startsWith("dila")) return "DILA 规范库";
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
              未找到该人物
            </span>
          }
          style={{ padding: "80px 0" }}
        />
        <div style={{ textAlign: "center" }}>
          <Button onClick={() => navigate("/kg")}>返回知识图谱</Button>
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
  const wikidataQid = entity.external_ids?.["wikidata"];

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

  return (
    <div className="person-page">
      {/* ── 面包屑 ── */}
      <nav className="person-breadcrumb">
        <span
          className="person-breadcrumb-link"
          onClick={() => navigate("/")}
        >
          首页
        </span>
        <span className="person-breadcrumb-sep">›</span>
        <span
          className="person-breadcrumb-link"
          onClick={() => navigate("/kg")}
        >
          知识图谱
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
            <span className="kg-type-tag kg-type-tag--person">人物</span>
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
                <span className="person-altname-lang">梵文</span>
                <span className="person-altname-val">{entity.name_sa}</span>
              </div>
            )}
            {entity.name_pi && (
              <div className="person-altname-row">
                <span className="person-altname-lang">巴利</span>
                <span className="person-altname-val">{entity.name_pi}</span>
              </div>
            )}
            {entity.name_bo && (
              <div className="person-altname-row">
                <span className="person-altname-lang">藏文</span>
                <span className="person-altname-val">{entity.name_bo}</span>
              </div>
            )}
            {entity.name_en && (
              <div className="person-altname-row">
                <span className="person-altname-lang">英文</span>
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

        {/* 外部链接 */}
        {wikidataQid && (
          <div className="person-extlinks">
            <a
              href={`https://www.wikidata.org/wiki/${wikidataQid}`}
              target="_blank"
              rel="noopener noreferrer"
              className="person-extlink"
            >
              <LinkOutlined style={{ marginRight: 4 }} />
              Wikidata {wikidataQid}
            </a>
          </div>
        )}

        {/* 在知识图谱中查看 */}
        <div className="person-kg-link">
          <Button
            icon={<ApartmentOutlined />}
            onClick={() => navigate(`/kg?id=${entity.id}`)}
            className="person-kg-btn"
          >
            在知识图谱中查看
          </Button>
        </div>
      </div>

      {/* ── 关系面板 ── */}
      {sortedPredicates.length > 0 && (
        <div className="person-card person-relations-card">
          <h2 className="person-section-title">关系网络</h2>
          {sortedPredicates.map((predicate) => {
            const rels = relationsByPredicate[predicate];
            return (
              <div key={predicate} className="person-rel-group">
                <div className="person-rel-group-head">
                  <span className="person-rel-label">
                    {PREDICATE_LABELS[predicate] || predicate}
                  </span>
                  <span className="person-rel-count">{rels.length}</span>
                </div>
                <div className="person-rel-items">
                  {rels.map((rel) => {
                    const tMeta = TYPE_LABELS[rel.target_type] || {
                      label: rel.target_type,
                      className: "kg-type-tag",
                    };
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
                          className={tMeta.className}
                          style={{ fontSize: 9, lineHeight: "16px", padding: "0 4px" }}
                        >
                          {tMeta.label}
                        </span>
                        <span className="person-rel-name">{rel.target_name}</span>
                        {rel.source && (
                          <Tooltip title={`关系出处：${rel.source}`}>
                            <span className="person-rel-source">
                              据 {prettifySource(rel.source)}
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
                暂无关系数据
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
