import { Typography, Button, Divider } from "antd";
import {
  BookOutlined,
  ArrowRightOutlined,
  ArrowLeftOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import type { EntityRelationItem } from "../api/client";

const TYPE_LABELS: Record<string, { label: string; className: string }> = {
  person:    { label: "人物", className: "kg-type-tag kg-type-tag--person" },
  text:      { label: "典籍", className: "kg-type-tag kg-type-tag--text" },
  monastery: { label: "寺院", className: "kg-type-tag kg-type-tag--monastery" },
  school:    { label: "宗派", className: "kg-type-tag kg-type-tag--school" },
  place:     { label: "地点", className: "kg-type-tag kg-type-tag--place" },
  concept:   { label: "概念", className: "kg-type-tag kg-type-tag--concept" },
  dynasty:   { label: "朝代", className: "kg-type-tag kg-type-tag--dynasty" },
};

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

/* 属性键中英映射 */
const PROPERTY_LABELS: Record<string, string> = {
  role: "角色",
  dynasty: "朝代",
  period: "时期",
  birth: "出生",
  death: "去世",
  birthplace: "出生地",
  school: "宗派",
  tradition: "传承",
  title: "称号",
  aka: "别名",
  dates: "年代",
  region: "地区",
  location: "位置",
  founded: "创建",
  founder: "创始人",
  language: "语言",
  author: "作者",
  translator: "译者",
};

interface Entity {
  id: number;
  entity_type: string;
  name_zh: string;
  name_sa?: string | null;
  name_pi?: string | null;
  name_bo?: string | null;
  name_en?: string | null;
  description?: string | null;
  properties?: Record<string, any> | null;
  text_id?: number | null;
  external_ids?: Record<string, string> | null;
  relations?: EntityRelationItem[];
}

interface EntityCardProps {
  entity: Entity;
  onEntityClick?: (entityId: number) => void;
}

export default function EntityCard({ entity, onEntityClick }: EntityCardProps) {
  const navigate = useNavigate();
  const meta = TYPE_LABELS[entity.entity_type] || {
    label: entity.entity_type,
    className: "kg-type-tag",
  };

  // Group relations by predicate
  const relationsByPredicate: Record<string, EntityRelationItem[]> = {};
  if (entity.relations) {
    for (const rel of entity.relations) {
      if (!relationsByPredicate[rel.predicate]) {
        relationsByPredicate[rel.predicate] = [];
      }
      relationsByPredicate[rel.predicate].push(rel);
    }
  }

  return (
    <div style={{ padding: 16 }}>
      {/* Name + type tag */}
      <div style={{ marginBottom: 8 }}>
        <span
          style={{
            fontFamily: '"Noto Serif SC", serif',
            fontSize: 18,
            fontWeight: 600,
            color: "#2b2318",
          }}
        >
          {entity.name_zh}
        </span>
        <span className={meta.className} style={{ marginLeft: 8 }}>
          {meta.label}
        </span>
      </div>

      {/* Description */}
      {entity.description && (
        <Typography.Paragraph
          style={{ color: "#7a6e5c", fontSize: 13, marginBottom: 10, lineHeight: 1.6 }}
        >
          {entity.description}
        </Typography.Paragraph>
      )}

      {/* Link to text */}
      {entity.text_id && (
        <Button
          type="link"
          size="small"
          icon={<BookOutlined />}
          style={{ padding: 0, marginBottom: 10, color: "#8b2500", fontSize: 12 }}
          onClick={() => navigate(`/texts/${entity.text_id}`)}
        >
          查看关联经文
        </Button>
      )}

      {/* Multi-language names */}
      <div style={{ marginBottom: 10 }}>
        {entity.name_sa && (
          <div style={{ fontSize: 12, color: "#5c4f3d", marginBottom: 2 }}>
            <span style={{ color: "#9a8e7a", display: "inline-block", width: 48 }}>梵文</span>
            {entity.name_sa}
          </div>
        )}
        {entity.name_pi && (
          <div style={{ fontSize: 12, color: "#5c4f3d", marginBottom: 2 }}>
            <span style={{ color: "#9a8e7a", display: "inline-block", width: 48 }}>巴利文</span>
            {entity.name_pi}
          </div>
        )}
        {entity.name_bo && (
          <div style={{ fontSize: 12, color: "#5c4f3d", marginBottom: 2 }}>
            <span style={{ color: "#9a8e7a", display: "inline-block", width: 48 }}>藏文</span>
            {entity.name_bo}
          </div>
        )}
        {entity.name_en && (
          <div style={{ fontSize: 12, color: "#5c4f3d", marginBottom: 2 }}>
            <span style={{ color: "#9a8e7a", display: "inline-block", width: 48 }}>英文</span>
            {entity.name_en}
          </div>
        )}
      </div>

      {/* Properties with Chinese labels */}
      {entity.properties && Object.keys(entity.properties).length > 0 && (
        <div
          style={{
            background: "#faf8f5",
            border: "1px solid #f0ebe2",
            borderRadius: 6,
            padding: "8px 10px",
            marginBottom: 10,
          }}
        >
          {Object.entries(entity.properties).map(([key, value]) => (
            <div
              key={key}
              style={{ fontSize: 12, color: "#5c4f3d", marginBottom: 2 }}
            >
              <span style={{ color: "#9a8e7a", display: "inline-block", width: 48 }}>
                {PROPERTY_LABELS[key] || key}
              </span>
              {String(value)}
            </div>
          ))}
        </div>
      )}

      {/* External IDs */}
      {entity.external_ids && Object.keys(entity.external_ids).length > 0 && (
        <div style={{ marginBottom: 10 }}>
          {Object.entries(entity.external_ids).map(([key, value]) => (
            <div
              key={`ext-${key}`}
              style={{ fontSize: 11, color: "#9a8e7a", marginBottom: 2 }}
            >
              <span style={{ textTransform: "uppercase", marginRight: 4 }}>
                {key}:
              </span>
              {typeof value === "string" && value.startsWith("http") ? (
                <a
                  href={value}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "#8b2500" }}
                >
                  {value}
                </a>
              ) : (
                String(value)
              )}
            </div>
          ))}
        </div>
      )}

      {/* Relations grouped by predicate */}
      {Object.keys(relationsByPredicate).length > 0 && (
        <>
          <Divider
            style={{ margin: "10px 0 8px", borderColor: "#f0ebe2" }}
          />
          <div
            style={{
              fontFamily: '"Noto Serif SC", serif',
              fontSize: 13,
              fontWeight: 600,
              color: "#2b2318",
              marginBottom: 8,
            }}
          >
            关系
          </div>
          {Object.entries(relationsByPredicate).map(([predicate, rels]) => {
            return (
              <div key={predicate} style={{ marginBottom: 10 }}>
                <div
                  style={{
                    fontSize: 12,
                    color: "#9a8e7a",
                    marginBottom: 4,
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  {PREDICATE_LABELS[predicate] || predicate}
                  <span
                    style={{
                      background: "#f0ebe2",
                      borderRadius: 8,
                      padding: "0 5px",
                      fontSize: 10,
                      color: "#7a6e5c",
                    }}
                  >
                    {rels.length}
                  </span>
                </div>
                {rels.map((rel) => {
                  const targetMeta = TYPE_LABELS[rel.target_type] || {
                    label: rel.target_type,
                    className: "kg-type-tag",
                  };
                  return (
                    <div
                      key={`${rel.predicate}-${rel.target_id}-${rel.direction}`}
                      style={{
                        padding: "3px 0",
                        cursor: onEntityClick ? "pointer" : undefined,
                        fontSize: 12,
                        color: "#5c4f3d",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      onClick={() => onEntityClick?.(rel.target_id)}
                      onMouseEnter={(e) => {
                        if (onEntityClick)
                          (e.currentTarget as HTMLElement).style.color = "#8b2500";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.color = "#5c4f3d";
                      }}
                    >
                      {rel.direction === "outgoing" ? (
                        <ArrowRightOutlined
                          style={{ color: "#d9d0c1", fontSize: 9 }}
                        />
                      ) : (
                        <ArrowLeftOutlined
                          style={{ color: "#d9d0c1", fontSize: 9 }}
                        />
                      )}
                      <span className={targetMeta.className} style={{ fontSize: 9, lineHeight: "16px", padding: "0 4px" }}>
                        {targetMeta.label}
                      </span>
                      <span>{rel.target_name}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
