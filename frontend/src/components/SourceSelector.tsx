import { useState, useMemo } from "react";
import { Input, Select, Checkbox, Button, Tag } from "antd";
import { SearchOutlined, LinkOutlined } from "@ant-design/icons";
import type { DataSource } from "../api/client";
import { localizedSourceName } from "../utils/sourceName";

interface SourceSelectorProps {
  sources: DataSource[];
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
}

function getCategory(s: DataSource): string {
  const n = s.name_zh + (s.name_en || "");
  if (/图书馆|Library/i.test(n)) return "图书馆";
  if (/大学|University|Univ|Institute/i.test(n)) return "高校研究";
  if (/博物馆|Museum/i.test(n)) return "博物馆";
  if (/寺|Temple|Monastery|Order/i.test(n)) return "寺院";
  if (/研究|Academy|Research|Society/i.test(n)) return "研究机构";
  if (/数据|Digital|电子|CBETA|BDRC|Sutra/i.test(n)) return "数字项目";
  return "其他";
}

export default function SourceSelector({ sources, selected, onChange }: SourceSelectorProps) {
  const [search, setSearch] = useState("");
  const [regionFilter, setRegionFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all"); // all / local / external

  const regions = useMemo(() => {
    const set = new Set<string>();
    sources.forEach((s) => set.add(s.region || "其他"));
    const order = ["中国大陆", "中国台湾", "中国香港", "中国澳门", "日本", "韩国", "越南", "泰国", "缅甸", "斯里兰卡", "印度", "尼泊尔", "不丹", "蒙古", "老挝", "柬埔寨", "美国", "加拿大", "英国", "德国", "法国", "荷兰", "比利时", "奥地利", "挪威", "丹麦", "意大利", "西班牙", "捷克", "俄罗斯", "澳大利亚", "国际"];
    return Array.from(set).sort((a, b) => {
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });
  }, [sources]);

  const localCount = useMemo(() => sources.filter((s) => s.access_type === "local").length, [sources]);

  const filtered = useMemo(() => {
    return sources.filter((s) => {
      if (search && !s.name_zh.includes(search) && !(s.name_en || "").toLowerCase().includes(search.toLowerCase())) return false;
      if (regionFilter !== "all" && (s.region || "其他") !== regionFilter) return false;
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
          <span>选择数据源</span>
          <span className="src-panel-hint">
            已选择 {selected.size} / {sources.length} 个数据源
            （{localCount} 个本地，{sources.length - localCount} 个外链）
            {selected.size === 0 && " · 未选择时搜索全部"}
          </span>
        </div>
        <div className="src-panel-filters">
          <Input
            prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
            placeholder="搜索..."
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
              { value: "all", label: "全部地区" },
              ...regions.map((r) => ({ value: r, label: r })),
            ]}
          />
          <Select
            size="small"
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 120 }}
            options={[
              { value: "all", label: "全部类型" },
              { value: "local", label: `本地数据 (${localCount})` },
              { value: "external", label: `外链跳转 (${sources.length - localCount})` },
            ]}
          />
          <Button size="small" onClick={selectAllVisible}>选中当前</Button>
          <Button size="small" onClick={clearAll}>取消全部</Button>
        </div>
      </div>
      <div className="src-panel-list">
        {filtered.length === 0 && (
          <div className="src-panel-empty">无匹配数据源</div>
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
                  本地
                </Tag>
              )}
            </span>
            <span className="src-item-tag">{s.region || "其他"}</span>
            <span className="src-item-tag">{getCategory(s)}</span>
            {s.access_type === "external" && s.base_url && (
              <a
                className="src-item-link"
                href={s.base_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                title="前往原站"
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
