import { Typography, Button, Divider, Tooltip } from "antd";
import {
  BookOutlined,
  ReadOutlined,
  ArrowRightOutlined,
  ArrowLeftOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { EntityRelationItem } from "../api/client";

const TYPE_META: Record<string, { labelKey: string; className: string }> = {
  person:    { labelKey: "geo.type_person", className: "kg-type-tag kg-type-tag--person" },
  text:      { labelKey: "geo.type_text", className: "kg-type-tag kg-type-tag--text" },
  monastery: { labelKey: "geo.type_temple", className: "kg-type-tag kg-type-tag--monastery" },
  school:    { labelKey: "geo.type_school", className: "kg-type-tag kg-type-tag--school" },
  place:     { labelKey: "geo.type_place", className: "kg-type-tag kg-type-tag--place" },
  concept:   { labelKey: "geo.type_concept", className: "kg-type-tag kg-type-tag--concept" },
  dynasty:   { labelKey: "geo.type_dynasty", className: "kg-type-tag kg-type-tag--dynasty" },
};

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

/* 属性键 → i18n key 映射 */
const PROPERTY_LABEL_KEYS: Record<string, string> = {
  role: "entity.prop_role",
  dynasty: "entity.prop_dynasty",
  period: "entity.prop_period",
  birth: "entity.prop_birth",
  death: "entity.prop_death",
  birthplace: "entity.prop_birthplace",
  school: "entity.prop_school",
  tradition: "entity.prop_tradition",
  title: "entity.prop_title",
  aka: "entity.prop_aka",
  dates: "entity.prop_dates",
  region: "entity.prop_region",
  location: "entity.prop_location",
  founded: "entity.prop_founded",
  founder: "entity.prop_founder",
  language: "entity.prop_language",
  author: "entity.prop_author",
  translator: "entity.prop_translator",
  year_start: "entity.prop_year_start",
  year_end: "entity.prop_year_end",
};

/* Relation-source provenance labels. A relation's `source` records where
   the assertion came from — an authoritative catalogue, auto-extracted
   metadata, or hand-seeded data. Surfacing it lets a scholar judge how
   much to trust an edge instead of taking every relation at face value. */
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

interface Entity {
  id: number;
  entity_type: string;
  name_zh: string;
  name_sa?: string | null;
  name_pi?: string | null;
  name_bo?: string | null;
  name_en?: string | null;
  description?: string | null;
  properties?: Record<string, unknown> | null;
  text_id?: number | null;
  external_ids?: Record<string, string> | null;
  relations?: EntityRelationItem[];
}

interface EntityCardProps {
  entity: Entity;
  onEntityClick?: (entityId: number) => void;
}

export default function EntityCard({ entity, onEntityClick }: EntityCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const meta = TYPE_META[entity.entity_type];
  const metaLabel = meta ? t(meta.labelKey) : entity.entity_type;
  const metaClassName = meta?.className ?? "kg-type-tag";

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
            color: "var(--fj-ink)",
          }}
        >
          {entity.name_zh}
        </span>
        <span className={metaClassName} style={{ marginLeft: 8 }}>
          {metaLabel}
        </span>
      </div>

      {/* Description */}
      {entity.description && (
        <Typography.Paragraph
          style={{ color: "var(--fj-ink-muted)", fontSize: 13, marginBottom: 10, lineHeight: 1.6 }}
        >
          {entity.description}
        </Typography.Paragraph>
      )}

      {/* Cross-module jumps: read the linked text, or look the term up
          in the Buddhist dictionary — so the graph isn't a dead end. */}
      {entity.text_id && (
        <Button
          type="link"
          size="small"
          icon={<BookOutlined />}
          style={{ padding: 0, marginBottom: 10, color: "var(--fj-highlight)", fontSize: 12 }}
          onClick={() => navigate(`/texts/${entity.text_id}`)}
        >
          {t("entity.view_linked_text")}
        </Button>
      )}
      {entity.entity_type === "concept" && (
        <Button
          type="link"
          size="small"
          icon={<ReadOutlined />}
          style={{ padding: 0, marginBottom: 10, color: "var(--fj-highlight)", fontSize: 12 }}
          onClick={() =>
            navigate(`/dict/${encodeURIComponent(entity.name_zh)}`)
          }
        >
          {t("entity.view_dict")}
        </Button>
      )}
      {entity.entity_type === "person" && (
        <Button
          type="link"
          size="small"
          icon={<UserOutlined />}
          style={{ padding: 0, marginBottom: 10, color: "var(--fj-highlight)", fontSize: 12 }}
          onClick={() => navigate(`/person/${entity.id}`)}
        >
          {t("entity.person_page")}
        </Button>
      )}

      {/* Multi-language names */}
      <div style={{ marginBottom: 10 }}>
        {entity.name_sa && (
          <div style={{ fontSize: 12, color: "var(--fj-ink-light)", marginBottom: 2 }}>
            <span style={{ color: "var(--fj-ink-muted)", display: "inline-block", width: 48 }}>{t("lang.sa")}</span>
            {entity.name_sa}
          </div>
        )}
        {entity.name_pi && (
          <div style={{ fontSize: 12, color: "var(--fj-ink-light)", marginBottom: 2 }}>
            <span style={{ color: "var(--fj-ink-muted)", display: "inline-block", width: 48 }}>{t("lang.pi")}</span>
            {entity.name_pi}
          </div>
        )}
        {entity.name_bo && (
          <div style={{ fontSize: 12, color: "var(--fj-ink-light)", marginBottom: 2 }}>
            <span style={{ color: "var(--fj-ink-muted)", display: "inline-block", width: 48 }}>{t("lang.bo")}</span>
            {entity.name_bo}
          </div>
        )}
        {entity.name_en && (
          <div style={{ fontSize: 12, color: "var(--fj-ink-light)", marginBottom: 2 }}>
            <span style={{ color: "var(--fj-ink-muted)", display: "inline-block", width: 48 }}>{t("lang.en")}</span>
            {entity.name_en}
          </div>
        )}
      </div>

      {/* Properties with Chinese labels */}
      {entity.properties && Object.keys(entity.properties).length > 0 && (
        <div
          style={{
            background: "var(--fj-surface-alt)",
            border: "1px solid var(--fj-bg-alt)",
            borderRadius: 6,
            padding: "8px 10px",
            marginBottom: 10,
          }}
        >
          {Object.entries(entity.properties)
            .filter(([key]) => key in PROPERTY_LABEL_KEYS)
            .filter(([key]) => !["latitude", "longitude", "geo_source", "province", "city", "district"].includes(key) && !key.startsWith("wikidata:"))
            .map(([key, value]) => (
            <div
              key={key}
              style={{ fontSize: 12, color: "var(--fj-ink-light)", marginBottom: 2 }}
            >
              <span style={{ color: "var(--fj-ink-muted)", display: "inline-block", width: 48 }}>
                {PROPERTY_LABEL_KEYS[key] ? t(PROPERTY_LABEL_KEYS[key]) : key}
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
              style={{ fontSize: 11, color: "var(--fj-ink-muted)", marginBottom: 2 }}
            >
              <span style={{ textTransform: "uppercase", marginRight: 4 }}>
                {key}:
              </span>
              {typeof value === "string" && value.startsWith("http") ? (
                <a
                  href={value}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "var(--fj-highlight)" }}
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
            style={{ margin: "10px 0 8px", borderColor: "var(--fj-bg-alt)" }}
          />
          <div
            style={{
              fontFamily: '"Noto Serif SC", serif',
              fontSize: 13,
              fontWeight: 600,
              color: "var(--fj-ink)",
              marginBottom: 8,
            }}
          >
            {t("kg.relations_label")}
          </div>
          {Object.entries(relationsByPredicate).map(([predicate, rels]) => {
            return (
              <div key={predicate} style={{ marginBottom: 10 }}>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--fj-ink-muted)",
                    marginBottom: 4,
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  {PREDICATE_LABEL_KEYS[predicate] ? t(PREDICATE_LABEL_KEYS[predicate]) : predicate}
                  <span
                    style={{
                      background: "var(--fj-bg-alt)",
                      borderRadius: 8,
                      padding: "0 5px",
                      fontSize: 10,
                      color: "var(--fj-ink-muted)",
                    }}
                  >
                    {rels.length}
                  </span>
                </div>
                {rels.map((rel) => {
                  const targetMeta = TYPE_META[rel.target_type];
                  const targetLabel = targetMeta ? t(targetMeta.labelKey) : rel.target_type;
                  const targetClassName = targetMeta?.className ?? "kg-type-tag";
                  return (
                    <div
                      key={`${rel.predicate}-${rel.target_id}-${rel.direction}`}
                      style={{
                        padding: "3px 0",
                        cursor: onEntityClick ? "pointer" : undefined,
                        fontSize: 12,
                        color: "var(--fj-ink-light)",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      onClick={() => onEntityClick?.(rel.target_id)}
                      onMouseEnter={(e) => {
                        if (onEntityClick)
                          (e.currentTarget as HTMLElement).style.color = "var(--fj-accent)";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.color = "var(--fj-ink-light)";
                      }}
                    >
                      {rel.direction === "outgoing" ? (
                        <ArrowRightOutlined
                          style={{ color: "var(--fj-border)", fontSize: 9 }}
                        />
                      ) : (
                        <ArrowLeftOutlined
                          style={{ color: "var(--fj-border)", fontSize: 9 }}
                        />
                      )}
                      <span className={targetClassName} style={{ fontSize: 9, lineHeight: "16px", padding: "0 4px" }}>
                        {targetLabel}
                      </span>
                      <span>{rel.target_name}</span>
                      {rel.source && (
                        <Tooltip title={t("entity.relation_source_tooltip", { source: rel.source })}>
                          <span
                            style={{
                              fontSize: 10,
                              color: "var(--fj-ink-muted)",
                              marginLeft: "auto",
                              flexShrink: 0,
                            }}
                          >
                            {t("entity.source_according_to", { name: prettifySource(t, rel.source) })}
                          </span>
                        </Tooltip>
                      )}
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
