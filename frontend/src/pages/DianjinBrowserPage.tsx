import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Input, Select, Tag, Empty, Spin, Badge } from "antd";
import {
  SearchOutlined, LinkOutlined, BookOutlined,
  CheckCircleOutlined, CloseCircleOutlined, DatabaseOutlined, VerticalAlignTopOutlined,
} from "@ant-design/icons";
import {
  getDianjinHealth,
  getDianjinDatasources,
  getDianjinRegionLabels,
  getDianjinInstitutions,
  type DianjinDatasource,
  type DianjinDatasourcePage,
  type DianjinHealthStatus,
  type DianjinInstitution,
} from "../api/dianjin";
import "../styles/sources.css";

/* 地区排序权重 */
const REGION_ORDER = [
  "中国大陆", "中国台湾", "中国香港", "中国澳门",
  "日本", "韩国", "越南",
  "美国", "加拿大", "英国", "德国", "法国", "俄罗斯", "澳大利亚",
];

export default function DianjinBrowserPage() {
  const [search, setSearch] = useState("");
  const [regionFilter, setRegionFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("all");
  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const { data: health } = useQuery<DianjinHealthStatus>({
    queryKey: ["dianjinHealth"],
    queryFn: getDianjinHealth,
    staleTime: 60_000,
  });

  // 一次拉取两页凑齐全部 180 个数据源（典津 max size=100）
  const { data: page1, isLoading: l1 } = useQuery<DianjinDatasourcePage>({
    queryKey: ["dianjinDS", 1],
    queryFn: () => getDianjinDatasources(1, 100),
    staleTime: 300_000,
  });
  const { data: page2, isLoading: l2 } = useQuery<DianjinDatasourcePage>({
    queryKey: ["dianjinDS", 2],
    queryFn: () => getDianjinDatasources(2, 100),
    staleTime: 300_000,
    enabled: (page1?.total_pages ?? 0) > 1,
  });

  const allDatasources = useMemo(() => {
    const items = [...(page1?.items || []), ...(page2?.items || [])];
    return items;
  }, [page1, page2]);

  // 地区标签映射
  const { data: regionLabels } = useQuery<Record<string, string>>({
    queryKey: ["dianjinRegionLabels"],
    queryFn: getDianjinRegionLabels,
    staleTime: 300_000,
  });

  // 机构列表（含 countryRegion）
  const { data: institutions } = useQuery<DianjinInstitution[]>({
    queryKey: ["dianjinInstitutions"],
    queryFn: getDianjinInstitutions,
    staleTime: 300_000,
  });

  // institutionCode → 中文地区名
  const instToRegion = useMemo(() => {
    const map: Record<string, string> = {};
    if (institutions && regionLabels) {
      for (const inst of institutions) {
        map[inst.code] = regionLabels[inst.countryRegion] || inst.countryRegion || "其他";
      }
    }
    return map;
  }, [institutions, regionLabels]);

  const getRegion = (ds: DianjinDatasource) => instToRegion[ds.institution_code] || "其他";

  // 可用的地区和标签列表
  const regions = useMemo(() => {
    const set = new Set<string>();
    allDatasources.forEach((s) => set.add(getRegion(s)));
    return Array.from(set).sort((a, b) => {
      const ia = REGION_ORDER.indexOf(a);
      const ib = REGION_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
  }, [allDatasources, instToRegion]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    allDatasources.forEach((s) => s.tags?.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [allDatasources]);

  // 筛选
  const filtered = useMemo(() => {
    return allDatasources.filter((s) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.name.toLowerCase().includes(q) &&
          !s.code.toLowerCase().includes(q) &&
          !s.description.toLowerCase().includes(q)
        )
          return false;
      }
      if (regionFilter !== "all" && getRegion(s) !== regionFilter) return false;
      if (tagFilter !== "all" && !s.tags?.includes(tagFilter)) return false;
      return true;
    });
  }, [allDatasources, search, regionFilter, tagFilter, instToRegion]);

  // 按地区分组
  const grouped = useMemo(() => {
    const map: Record<string, DianjinDatasource[]> = {};
    for (const s of filtered) {
      const r = getRegion(s);
      if (!map[r]) map[r] = [];
      map[r].push(s);
    }
    return Object.entries(map).sort(([a], [b]) => {
      const ia = REGION_ORDER.indexOf(a);
      const ib = REGION_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
  }, [filtered, instToRegion]);

  const isLoading = l1 || l2;
  const totalRecords = allDatasources.reduce((sum, s) => sum + s.record_count, 0);

  return (
    <div className="sources-page">
      <div className="sources-header">
        <h1 className="sources-title">典津跨平台古籍资源</h1>
        <p className="sources-desc">
          典津平台 (guji.cckb.cn) 聚合 {regions.length} 个国家/地区、
          {page1?.total || 0} 个数据源、{totalRecords.toLocaleString()} 条古籍记录
          {" · "}
          {health?.public_api ? (
            <Badge status="success" text="在线" />
          ) : (
            <Badge status="error" text="离线" />
          )}
        </p>
      </div>

      {/* 工具栏 */}
      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder="搜索数据源名称、代码..."
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260 }}
        />
        <Select
          value={regionFilter}
          onChange={setRegionFilter}
          style={{ width: 160 }}
          options={[
            { value: "all", label: `全部地区 (${regions.length})` },
            ...regions.map((r) => ({ value: r, label: r })),
          ]}
        />
        {allTags.length > 0 && (
          <Select
            value={tagFilter}
            onChange={setTagFilter}
            style={{ width: 160 }}
            options={[
              { value: "all", label: `全部标签 (${allTags.length})` },
              ...allTags.map((t) => ({ value: t, label: t })),
            ]}
          />
        )}

        <div className="sources-try-search">
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#9a8e7a" }}>
            {health?.public_api ? (
              <Tag icon={<CheckCircleOutlined />} color="success">公开 API</Tag>
            ) : (
              <Tag icon={<CloseCircleOutlined />} color="error">公开 API</Tag>
            )}
            {health?.configured ? (
              health?.search_api ? (
                <Tag icon={<CheckCircleOutlined />} color="success">搜索 API</Tag>
              ) : (
                <Tag icon={<CloseCircleOutlined />} color="warning">搜索 API</Tag>
              )
            ) : (
              <Tag color="default">搜索未配置</Tag>
            )}
          </div>
        </div>
      </div>

      <div className="sources-stats-bar">
        当前显示 <strong>{filtered.length}</strong> / {page1?.total || 0} 个数据源
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : filtered.length === 0 ? (
        <Empty description="无匹配数据源" style={{ marginTop: 60 }} />
      ) : (
        <div className="sources-groups">
          {grouped.map(([region, items]) => (
            <div key={region} className="sources-group">
              <div className="sources-group-header">
                <span className="sources-group-name">{region}</span>
                <span className="sources-group-count">{items.length}</span>
              </div>
              <div className="sources-grid">
                {items.map((s) => (
                  <div key={s.id} className="source-card">
                    <div className="source-card-top">
                      <span className="source-card-icon">
                        <DatabaseOutlined />
                      </span>
                      <div className="source-card-titles">
                        <span className="source-card-name">{s.name}</span>
                        <span className="source-card-name-en">{s.institution_code}</span>
                      </div>
                      <div className="source-card-badges">
                        <Tag
                          color="blue"
                          style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}
                        >
                          <BookOutlined /> {s.record_count.toLocaleString()}
                        </Tag>
                      </div>
                    </div>

                    {s.description && (
                      <p className="source-card-desc">{s.description}</p>
                    )}

                    <div className="source-card-langs">
                      {s.category && <span className="source-lang-tag">{s.category}</span>}
                      {s.tags?.map((t) => (
                        <span key={t} className="source-lang-tag">{t}</span>
                      ))}
                    </div>

                    <div className="source-card-actions">
                      <a
                        href={`https://guji.cckb.cn/search?datasources=${s.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="source-btn source-btn-search"
                      >
                        <LinkOutlined /> 在典津搜索
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {showTop && (
        <button
          className="sources-back-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="回到顶部"
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
