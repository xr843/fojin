import { useState, useMemo } from "react";
import { Input, Select, Checkbox, Button, Tag } from "antd";
import { SearchOutlined, LinkOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { DataSource } from "../api/client";
import { localizedSourceName } from "../utils/sourceName";

interface SourceSelectorProps {
  sources: DataSource[];
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
}

// Returns a category CODE; display sites translate it via
// t(`sources.category_${code}`). The regexes match raw data names.
function getCategory(s: DataSource): string {
  const n = s.name_zh + (s.name_en || "");
  if (/图书馆|Library/i.test(n)) return "library";
  if (/大学|University|Univ|Institute/i.test(n)) return "academic";
  if (/博物馆|Museum/i.test(n)) return "museum";
  if (/寺|Temple|Monastery|Order/i.test(n)) return "temple";
  if (/研究|Academy|Research|Society/i.test(n)) return "research";
  if (/数据|Digital|电子|CBETA|BDRC|Sutra/i.test(n)) return "digital";
  return "other";
}

export default function SourceSelector({ sources, selected, onChange }: SourceSelectorProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [regionFilter, setRegionFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all"); // all / local / external

  const regions = useMemo(() => {
    const set = new Set<string>();
    sources.forEach((s) => set.add(s.region || "其他")); // i18n-exempt
    const order = ["中国大陆", "中国台湾", "中国香港", "中国澳门", "日本", "韩国", "越南", "泰国", "缅甸", "斯里兰卡", "印度", "尼泊尔", "不丹", "蒙古", "老挝", "柬埔寨", "美国", "加拿大", "英国", "德国", "法国", "荷兰", "比利时", "奥地利", "挪威", "丹麦", "意大利", "西班牙", "捷克", "俄罗斯", "澳大利亚", "国际"]; // i18n-exempt
    return Array.from(set).sort((a, b) => {
      if (a === "其他") return 1; // i18n-exempt
      if (b === "其他") return -1; // i18n-exempt
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });
  }, [sources]);

  const localCount = useMemo(() => sources.filter((s) => s.access_type === "local").length, [sources]);

  const filtered = useMemo(() => {
    return sources.filter((s) => {
      if (search && !s.name_zh.includes(search) && !(s.name_en || "").toLowerCase().includes(search.toLowerCase())) return false;
      if (regionFilter !== "all" && (s.region || "其他") !== regionFilter) return false; // i18n-exempt
      if (typeFilter === "local" && s.access_type !== "local") return false;
      if (typeFilter === "external" && s.access_type !== "external") return false;
      return true;
    });
  }, [sources, search, regionFilter, typeFilter]);

  const selectAllVisible = () => {
    const next = new Set(selected);
    filtered.forEach((s) => next.add(s.code));
    onChange(next);
  };

  const clearAll = () => onChange(new Set());

  return (
    <div className="src-panel">
      <div className="src-panel-header">
        <div className="src-panel-title">
          <span>{t("sources.selector_title")}</span>
          <span className="src-panel-hint">
            {t("sources.selector_hint", {
              selected: selected.size,
              total: sources.length,
              local: localCount,
              external: sources.length - localCount,
            })}
            {selected.size === 0 && ` · ${t("sources.selector_none_hint")}`}
          </span>
        </div>
        <div className="src-panel-filters">
          <Input
            prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
            placeholder={t("sources.selector_search_placeholder")}
            allowClear
            size="small"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 160 }}
          />
          <Select
            size="small"
            value={regionFilter}
            onChange={setRegionFilter}
            style={{ width: 120 }}
            options={[
              { value: "all", label: t("sources.selector_all_regions") },
              ...regions.map((r) => ({ value: r, label: t(`region.${r}`, r) })),
            ]}
          />
          <Select
            size="small"
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 120 }}
            options={[
              { value: "all", label: t("sources.selector_all_types") },
              { value: "local", label: t("sources.selector_local_n", { n: localCount }) },
              { value: "external", label: t("sources.selector_external_n", { n: sources.length - localCount }) },
            ]}
          />
          <Button size="small" onClick={selectAllVisible}>{t("sources.selector_select_visible")}</Button>
          <Button size="small" onClick={clearAll}>{t("sources.selector_clear_all")}</Button>
        </div>
      </div>
      <div className="src-panel-list">
        {filtered.length === 0 && (
          <div className="src-panel-empty">{t("sources.no_match")}</div>
        )}
        {filtered.map((s) => (
          <label key={s.code} className="src-panel-item">
            <Checkbox
              checked={selected.has(s.code)}
              onChange={() => {
                const next = new Set(selected);
                if (next.has(s.code)) next.delete(s.code);
                else next.add(s.code);
                onChange(next);
              }}
            />
            <span className="src-item-name">
              {localizedSourceName(s)}
              {s.access_type === "local" && (
                <Tag color="green" style={{ marginLeft: 6, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                  {t("sources.selector_local_tag")}
                </Tag>
              )}
            </span>
            <span className="src-item-tag">{t(`region.${s.region || "其他"}`, s.region || "其他")}</span>
            <span className="src-item-tag">{t(`sources.category_${getCategory(s)}`)}</span>
            {s.access_type === "external" && s.base_url && (
              <a
                className="src-item-link"
                href={s.base_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                title={t("sources.selector_goto_site")}
              >
                <LinkOutlined />
              </a>
            )}
          </label>
        ))}
      </div>
    </div>
  );
}
