import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Typography, Card, Button, Space, Select, Tag, Spin } from "antd";
import {
  DownloadOutlined,
  FileTextOutlined,
  ApartmentOutlined,
  ShareAltOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import api from "../api/client";

const { Title, Paragraph, Text } = Typography;

interface ExportStats {
  texts: number;
  kg_entities: number;
  kg_relations: number;
}

const ENTITY_TYPE_OPTIONS = [
  { value: "person", labelKey: "geo.type_person" },
  { value: "text", labelKey: "geo.type_text" },
  { value: "monastery", labelKey: "geo.type_temple" },
  { value: "school", labelKey: "geo.type_school" },
  { value: "place", labelKey: "geo.type_place" },
  { value: "concept", labelKey: "geo.type_concept" },
  { value: "dynasty", labelKey: "geo.type_dynasty" },
];

const DYNASTY_FILTER_OPTIONS = [
  { value: "东汉", labelKey: "exports.dynasty.easternHan" }, // i18n-exempt
  { value: "三国", labelKey: "exports.dynasty.threeKingdoms" }, // i18n-exempt
  { value: "西晋", labelKey: "exports.dynasty.westernJin" }, // i18n-exempt
  { value: "东晋", labelKey: "exports.dynasty.easternJin" }, // i18n-exempt
  { value: "南北朝", labelKey: "exports.dynasty.northernSouthern" }, // i18n-exempt
  { value: "隋", labelKey: "exports.dynasty.sui" }, // i18n-exempt
  { value: "唐", labelKey: "exports.dynasty.tang" }, // i18n-exempt
  { value: "宋", labelKey: "exports.dynasty.song" }, // i18n-exempt
  { value: "元", labelKey: "exports.dynasty.yuan" }, // i18n-exempt
  { value: "明", labelKey: "exports.dynasty.ming" }, // i18n-exempt
  { value: "清", labelKey: "exports.dynasty.qing" }, // i18n-exempt
];

const CATEGORY_FILTER_OPTIONS = [
  { value: "阿含部", labelKey: "exports.category.agama" }, // i18n-exempt
  { value: "般若部", labelKey: "exports.category.prajna" }, // i18n-exempt
  { value: "华严部", labelKey: "exports.category.huayan" }, // i18n-exempt
  { value: "法华部", labelKey: "exports.category.lotus" }, // i18n-exempt
  { value: "密教部", labelKey: "exports.category.esoteric" }, // i18n-exempt
  { value: "律部", labelKey: "exports.category.vinaya" }, // i18n-exempt
  { value: "论集部", labelKey: "exports.category.treatises" }, // i18n-exempt
];

function buildUrl(base: string, params: Record<string, string>) {
  const qs = Object.entries(params)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&");
  return qs ? `${base}?${qs}` : base;
}

export default function ExportsPage() {
  const { t } = useTranslation();
  const [dynasty, setDynasty] = useState("");
  const [category, setCategory] = useState("");
  const [entityType, setEntityType] = useState("");

  const { data: stats, isLoading } = useQuery<ExportStats>({
    queryKey: ["exportStats"],
    queryFn: async () => (await api.get("/exports/stats")).data,
  });

  const csvUrl = buildUrl("/api/exports/metadata.csv", { dynasty, category });
  const kgJsonUrl = buildUrl("/api/exports/kg.json", { entity_type: entityType });
  const kgJsonLdUrl = buildUrl("/api/exports/kg.jsonld", { entity_type: entityType });

  return (
    <div style={{ maxWidth: 800, margin: "24px auto" }}>
      <Title level={3}>
        <DownloadOutlined /> {t("exports.title")}
      </Title>
      <Paragraph type="secondary">
        {t("exports.description")}
      </Paragraph>

      {isLoading ? (
        <Spin style={{ display: "block", margin: "24px auto" }} />
      ) : stats ? (
        <Card size="small" style={{ marginBottom: 24 }}>
          <Space size="large">
            <span>
              {t("exports.stats.texts")} <Tag color="blue">{t("exports.count.records", { n: stats.texts.toLocaleString() })}</Tag>
            </span>
            <span>
              {t("exports.stats.entities")} <Tag color="green">{t("exports.count.items", { n: stats.kg_entities.toLocaleString() })}</Tag>
            </span>
            <span>
              {t("exports.stats.relations")} <Tag color="orange">{t("exports.count.records", { n: stats.kg_relations.toLocaleString() })}</Tag>
            </span>
          </Space>
        </Card>
      ) : null}

      {/* CSV Export */}
      <Card style={{ marginBottom: 16 }}>
        <Space align="start" size="large">
          <div style={{ color: "#1a1a2e" }}>
            <FileTextOutlined style={{ fontSize: 24 }} />
          </div>
          <div style={{ flex: 1 }}>
            <Text strong style={{ fontSize: 16 }}>
              {t("exports.csvTitle")}
            </Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 8px" }}>
              {t("exports.csvDescription")}
            </Paragraph>
            <Space wrap style={{ marginBottom: 8 }}>
              <Select
                style={{ width: 120 }}
                placeholder={t("exports.dynastyPlaceholder")}
                allowClear
                value={dynasty || undefined}
                onChange={(v) => setDynasty(v || "")}
                options={DYNASTY_FILTER_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
              />
              <Select
                style={{ width: 120 }}
                placeholder={t("exports.categoryPlaceholder")}
                allowClear
                value={category || undefined}
                onChange={(v) => setCategory(v || "")}
                options={CATEGORY_FILTER_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
              />
            </Space>
            <br />
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              href={csvUrl}
              download="fojin_metadata.csv"
            >
              {t("exports.downloadCsv")}
            </Button>
          </div>
        </Space>
      </Card>

      {/* KG JSON Export */}
      <Card style={{ marginBottom: 16 }}>
        <Space align="start" size="large">
          <div style={{ color: "#1a1a2e" }}>
            <ApartmentOutlined style={{ fontSize: 24 }} />
          </div>
          <div style={{ flex: 1 }}>
            <Text strong style={{ fontSize: 16 }}>
              {t("exports.kgJsonTitle")}
            </Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 8px" }}>
              {t("exports.kgJsonDescription")}
            </Paragraph>
            <Space style={{ marginBottom: 8 }}>
              <Select
                style={{ width: 140 }}
                placeholder={t("exports.entityTypePlaceholder")}
                allowClear
                value={entityType || undefined}
                onChange={(v) => setEntityType(v || "")}
                options={ENTITY_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
              />
            </Space>
            <br />
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              href={kgJsonUrl}
              download="fojin_kg.json"
            >
              {t("exports.downloadJson")}
            </Button>
          </div>
        </Space>
      </Card>

      {/* KG JSON-LD Export */}
      <Card style={{ marginBottom: 16 }}>
        <Space align="start" size="large">
          <div style={{ color: "#1a1a2e" }}>
            <ShareAltOutlined style={{ fontSize: 24 }} />
          </div>
          <div style={{ flex: 1 }}>
            <Text strong style={{ fontSize: 16 }}>
              {t("exports.kgJsonLdTitle")}
            </Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 8px" }}>
              {t("exports.kgJsonLdDescription")}
            </Paragraph>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              href={kgJsonLdUrl}
              download="fojin_kg.jsonld"
            >
              {t("exports.downloadJsonLd")}
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  );
}
