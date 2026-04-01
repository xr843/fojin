import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Helmet } from "react-helmet-async";
import { Input, Select, Tag, Empty, Spin, Form, Button, message } from "antd";
import {
  SearchOutlined, LinkOutlined, GlobalOutlined,
  ApiOutlined, FileImageOutlined, ReadOutlined,
  SendOutlined, VerticalAlignTopOutlined,
} from "@ant-design/icons";
import { getSources, submitSourceSuggestion, type DataSource } from "../api/client";
import {
  buildSearchUrlWithFallback,
  getLangName,
  normalizeLangCode,
} from "../utils/sourceUrls";
import "../styles/sources.css";

function getChannelLabel(channelType: string): string {
  if (channelType === "git") return "Git";
  if (channelType === "bulk_dump") return "批量";
  if (channelType === "api") return "API";
  return channelType;
}

export default function SourcesPage() {
  const [search, setSearch] = useState("");
  const [regionFilter, setRegionFilter] = useState("all");
  const [langFilter, setLangFilter] = useState("all");
  const [fieldFilter, setFieldFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("default");
  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const { data: sources, isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: getSources,
  });

  // 提取可用筛选项
  const regionOrder = ["中国大陆", "中国台湾", "中国香港", "中国澳门", "日本", "韩国", "越南", "泰国", "缅甸", "斯里兰卡", "印度", "尼泊尔", "不丹", "蒙古", "老挝", "柬埔寨", "美国", "加拿大", "英国", "德国", "法国", "荷兰", "比利时", "奥地利", "挪威", "丹麦", "意大利", "西班牙", "捷克", "俄罗斯", "澳大利亚", "国际"];
  const regions = useMemo(() => {
    if (!sources) return [];
    const set = new Set<string>();
    sources.forEach((s) => set.add(s.region || "其他"));
    return Array.from(set).sort((a, b) => {
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      const ia = regionOrder.indexOf(a);
      const ib = regionOrder.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });
  }, [sources]);

  const langOrder = ["zh", "lzh", "sa", "pi", "bo", "en", "ja", "ko"];
  const languages = useMemo(() => {
    if (!sources) return [];
    // 按中文名去重（如 xto/txb 都映射为"吐火罗语"，只保留一个代表代码）
    const nameToCode = new Map<string, string>();
    const allCodes = new Set<string>();
    sources.forEach((s) => {
      if (s.languages) s.languages.split(",").forEach((l) => {
        const code = normalizeLangCode(l.trim());
        allCodes.add(code);
        const name = getLangName(code);
        if (!nameToCode.has(name)) nameToCode.set(name, code);
      });
    });
    return Array.from(nameToCode.values()).sort((a, b) => {
      const order = (c: string) => c === "mul" ? 999 : langOrder.indexOf(c) === -1 ? 99 : langOrder.indexOf(c);
      return order(a) - order(b);
    });
  }, [sources]);

  const FIELD_NAMES: Record<string, string> = {
    han: "汉传佛教", theravada: "南传佛教", tibetan: "藏传佛教",
    dunhuang: "敦煌学", art: "佛教艺术",
    dictionary: "辞典工具", dh: "数字人文",
  };
  const fieldOrder = ["han", "theravada", "tibetan", "dictionary", "dh", "dunhuang", "art"];
  const researchFields = useMemo(() => {
    if (!sources) return [];
    const set = new Set<string>();
    sources.forEach((s) => {
      if (s.research_fields) s.research_fields.split(",").forEach((f) => {
        const key = f.trim();
        if (key in FIELD_NAMES) set.add(key);
      });
    });
    return Array.from(set).sort((a, b) => {
      const ia = fieldOrder.indexOf(a);
      const ib = fieldOrder.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
  }, [sources]);

  // 筛选
  const filtered = useMemo(() => {
    if (!sources) return [];
    const result = sources.filter((s) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.name_zh.toLowerCase().includes(q) &&
          !(s.name_en || "").toLowerCase().includes(q) &&
          !(s.description || "").toLowerCase().includes(q) &&
          !s.code.toLowerCase().includes(q)
        )
          return false;
      }
      if (regionFilter !== "all" && (s.region || "其他") !== regionFilter) return false;
      if (langFilter !== "all") {
        const langs = (s.languages || "").split(",").map((l) => l.trim());
        const filterName = getLangName(langFilter);
        if (!langs.some((l) => getLangName(l) === filterName)) return false;
      }
      if (fieldFilter !== "all") {
        const fields = (s.research_fields || "").split(",").map((f) => f.trim());
        if (!fields.includes(fieldFilter)) return false;
      }
      return true;
    });
    if (sortBy === "region") {
      result.sort((a, b) => (a.region || "").localeCompare(b.region || "", "zh"));
    } else if (sortBy === "count") {
      result.sort((a, b) => (b.distributions?.length || 0) - (a.distributions?.length || 0));
    } else if (sortBy === "name") {
      result.sort((a, b) => a.name_zh.localeCompare(b.name_zh, "zh"));
    }
    // sortBy === "default": keep backend sort_order
    return result;
  }, [sources, search, regionFilter, langFilter, fieldFilter, sortBy]);

  // 按地区分组
  const grouped = useMemo(() => {
    const map: Record<string, DataSource[]> = {};
    for (const s of filtered) {
      const r = s.region || "其他";
      if (!map[r]) map[r] = [];
      map[r].push(s);
    }
    // 排序：中国大陆第一，中国台湾第二，其他最后
    return Object.entries(map).sort(([a], [b]) => {
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      const ia = regionOrder.indexOf(a);
      const ib = regionOrder.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });
  }, [filtered]);

  const localCount = useMemo(() => (sources || []).filter((s) => s.has_local_fulltext).length, [sources]);
  const remoteCount = useMemo(() => (sources || []).filter((s) => s.has_remote_fulltext).length, [sources]);
  const directSearchCount = useMemo(
    () => (sources || []).filter((s) => s.supports_search).length,
    [sources],
  );
  const iiifCount = useMemo(() => (sources || []).filter((s) => s.supports_iiif).length, [sources]);
  const apiCount = useMemo(() => (sources || []).filter((s) => s.supports_api).length, [sources]);

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="sources-page">
      <Helmet>
        <title>数据源导航 | 佛津</title>
        <meta name="description" content={`聚合全球 ${sources?.length || 40}+ 佛教数字资源，覆盖图书馆、大学、研究机构、数字项目等。`} />
        <link rel="canonical" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="x-default" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="zh" href="https://fojin.app/sources" />
      </Helmet>
      <div className="sources-header">
        <h1 className="sources-title">数据源导航</h1>
        <p className="sources-desc">
          聚合全球 {sources?.length || 0} 个佛教数字资源：
          {directSearchCount} 可搜索 · {localCount} 已入库全文 · {remoteCount} 外站全文 · {iiifCount} 影像 · {apiCount} API
        </p>
      </div>

      <div className="sources-trust">
        <div className="sources-trust-items">
          <div className="sources-trust-item">
            <div className="sources-trust-title">来源可溯</div>
            <div className="sources-trust-desc">所有数据均来自 CBETA、BDRC、SAT、SuttaCentral 等学术机构公开发布的数字资源，每条记录保留原始来源标识与链接。</div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">定期同步</div>
            <div className="sources-trust-desc">通过 Git、API、批量导入等渠道与上游数据源保持同步，确保收录内容反映最新发布状态。</div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">自动去重</div>
            <div className="sources-trust-desc">跨数据源自动识别同一典籍的不同收录，合并为统一记录，保留各源的独立编号与访问链接。</div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">覆盖广泛</div>
            <div className="sources-trust-desc">涵盖 {regions.length} 个国家和地区、{languages.length} 种语言，覆盖汉传、藏传、南传、梵文等多种佛教传统。</div>
          </div>
        </div>
      </div>

      {/* 搜索与过滤栏 */}
      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder="搜索数据源名称、描述..."
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260 }}
        />
        <Select
          value={regionFilter}
          onChange={setRegionFilter}
          style={{ width: 140 }}
          options={[
            { value: "all", label: `全部地区 (${regions.length})` },
            ...regions.map((r) => ({ value: r, label: r })),
          ]}
        />
        <Select
          value={langFilter}
          onChange={setLangFilter}
          style={{ width: 140 }}
          options={[
            { value: "all", label: `全部语种 (${languages.length})` },
            ...languages.map((l) => ({ value: l, label: getLangName(l) })),
          ]}
        />
        <Select
          value={fieldFilter}
          onChange={setFieldFilter}
          style={{ width: 150 }}
          options={[
            { value: "all", label: `研究领域 (${researchFields.length})` },
            ...researchFields.map((f) => ({ value: f, label: FIELD_NAMES[f] || f })),
          ]}
        />
        <Select
          value={sortBy}
          onChange={setSortBy}
          style={{ width: 120 }}
          options={[
            { value: "default", label: "默认排序" },
            { value: "name", label: "按名称" },
            { value: "region", label: "按地区" },
            { value: "count", label: "按收录数" },
          ]}
        />

        {/* 试搜功能 */}
        <div className="sources-try-search">
          <Input.Search
            placeholder="输入关键词试搜"
            size="small"
            allowClear
            onSearch={(v) => setSearchQuery(v)}
            style={{ width: 200 }}
          />
        </div>
      </div>

      <div className="sources-stats-bar">
        当前显示 <strong>{filtered.length}</strong> / {sources?.length || 0} 个数据源
      </div>

      {filtered.length === 0 ? (
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
                {items.map((s) => {
                  const langs = [...new Map(
                    (s.languages || "").split(",").map((l) => l.trim()).filter(Boolean)
                      .map((l) => [getLangName(l), l] as const)
                  ).values()]
                    .sort((a, b) => {
                      const ia = langOrder.indexOf(a);
                      const ib = langOrder.indexOf(b);
                      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
                    });
                  const distributions = (s.distributions || [])
                    .filter((d) => d.is_active)
                    .slice(0, 5);
                  const searchUrl = searchQuery
                    ? buildSearchUrlWithFallback(s.code, s.base_url, searchQuery)
                    : null;

                  return (
                    <div key={s.code} className="source-card">
                      <div className="source-card-top">
                        <span className="source-card-icon">
                          <GlobalOutlined />
                        </span>
                        <div className="source-card-titles">
                          <span className="source-card-name">{s.name_zh}</span>
                          {s.name_en && (
                            <span className="source-card-name-en">{s.name_en}</span>
                          )}
                        </div>
                        <div className="source-card-badges">
                          {s.has_local_fulltext && (
                            <Tag color="green" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
                              <ReadOutlined /> 已入库
                            </Tag>
                          )}
                          {s.has_remote_fulltext && !s.has_local_fulltext && (
                            <Tag color="cyan" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
                              <ReadOutlined /> 外站全文
                            </Tag>
                          )}
                          {s.supports_search && (
                            <Tag color="blue" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
                              <SearchOutlined /> 可搜索
                            </Tag>
                          )}
                          {s.supports_iiif && (
                            <Tag color="purple" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
                              <FileImageOutlined /> 影像
                            </Tag>
                          )}
                          {s.supports_api && (
                            <Tag color="orange" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
                              <ApiOutlined /> API
                            </Tag>
                          )}
                        </div>
                      </div>

                      {s.description && (
                        <p className="source-card-desc">{s.description}</p>
                      )}

                      {distributions.length > 0 && (
                        <div className="source-card-dists">
                          <div className="source-card-dists-title">官方分发端</div>
                          <div className="source-card-dists-list">
                            {distributions.map((d) => (
                              <a
                                key={d.code}
                                href={d.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className={`source-dist-link${d.is_primary_ingest ? " is-primary" : ""}`}
                                title={d.license_note || d.name}
                              >
                                <span className="source-dist-name">{d.name}</span>
                                <span className="source-dist-meta">
                                  {getChannelLabel(d.channel_type)}
                                  {d.format ? ` · ${d.format}` : ""}
                                </span>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="source-card-langs">
                        {langs.map((l) => (
                          <span key={l} className="source-lang-tag">{getLangName(l)}</span>
                        ))}
                      </div>

                      <div className="source-card-actions">
                        {s.base_url && (
                          <a
                            href={s.base_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="source-btn"
                          >
                            <GlobalOutlined /> 访问网站
                          </a>
                        )}
                        {searchUrl && (
                          <a
                            href={searchUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="source-btn source-btn-search"
                          >
                            <LinkOutlined /> 搜索「{searchQuery}」
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 推荐数据源 */}
      <SuggestSourceSection />

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

function SuggestSourceSection() {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (values: { name: string; url: string; description?: string }) => {
    setSubmitting(true);
    try {
      await submitSourceSuggestion(values);
      setSubmitted(true);
      form.resetFields();
    } catch {
      message.error("提交失败，请稍后再试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="sources-suggest">
      <div className="sources-suggest-header">
        <h2 className="sources-suggest-title">推荐数据源</h2>
        <p className="sources-suggest-desc">
          如果您知道尚未收录的佛教数字资源网站，欢迎推荐给我们
        </p>
      </div>
      {submitted ? (
        <div className="sources-suggest-success">
          感谢您的推荐！我们会尽快查阅。
        </div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          className="sources-suggest-form"
        >
          <div className="sources-suggest-row">
            <Form.Item
              name="name"
              label="网站名称"
              rules={[{ required: true, message: "请输入网站名称" }]}
              style={{ flex: 1 }}
            >
              <Input placeholder="例：CBETA 在线阅读" />
            </Form.Item>
            <Form.Item
              name="url"
              label="网站 URL"
              rules={[
                { required: true, message: "请输入网站地址" },
                { type: "url", message: "请输入有效的网址" },
              ]}
              style={{ flex: 1 }}
            >
              <Input placeholder="https://..." />
            </Form.Item>
          </div>
          <Form.Item name="description" label="简要说明">
            <Input.TextArea
              rows={3}
              placeholder="简要描述该网站收录的内容、语种、特色等（选填）"
              maxLength={2000}
              showCount
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={submitting}
              icon={<SendOutlined />}
              className="sources-suggest-btn"
            >
              提交推荐
            </Button>
          </Form.Item>
        </Form>
      )}
    </div>
  );
}
