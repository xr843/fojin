import { useState } from "react";
import { Empty, Spin, Alert, Collapse, Tag, Progress } from "antd";
import { LinkOutlined, BookOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getJuanAlignment } from "../api/client";

interface Props {
  textId: number;
  juanNum: number;
}

const LANG_LABEL: Record<string, string> = {
  lzh: "汉",
  pi: "巴利 · 英译",
  sa: "梵",
  bo: "藏 · 英译",
  en: "英",
};

const LANG_COLOR: Record<string, string> = {
  lzh: "gold",
  pi: "cyan",
  sa: "purple",
  bo: "magenta",
  en: "geekblue",
};

/**
 * Reader 右侧"他藏对读"内联面板（非 modal）。
 *
 * 本组件只渲染内容，不负责容器或关闭按钮 —— 外层 TextReaderPage 的
 * reader-parallel-sidebar wrapper 负责尺寸、header、关闭按钮。这和
 * ReaderAIPanel 是同一个模式，确保两个面板共享容器样式 + 可同时开启 +
 * 可各自拖拽宽度 + 不会 modal 覆盖经文。
 */
export default function ReaderParallelPanel({ textId, juanNum }: Props) {
  const [activeKeys, setActiveKeys] = useState<string[]>([]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["juan-alignment", textId, juanNum],
    queryFn: () => getJuanAlignment(textId, juanNum),
    enabled: textId > 0 && juanNum > 0,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const coveragePct = data && data.total_chunks > 0
    ? Math.round((data.chunks_with_parallels / data.total_chunks) * 100)
    : 0;

  return (
    <div className="reader-parallel-panel">
      {isLoading && (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin />
          <div style={{ marginTop: 12, color: "#888" }}>加载跨藏经对应中…</div>
        </div>
      )}

      {error && (
        <Alert
          type="info"
          showIcon
          message="本卷暂无多语对照数据"
          description="当前仅 MVP 首批经典 + 长阿含/中阿含部分卷打通了跨语对照。覆盖会持续扩展。"
          style={{ margin: 12 }}
        />
      )}

      {data && !isLoading && !error && (
        <>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
              <span style={{ fontSize: 13, color: "#555" }}>本卷对照覆盖率</span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>
                {data.chunks_with_parallels} / {data.total_chunks} 段 ({coveragePct}%)
              </span>
            </div>
            <Progress
              percent={coveragePct}
              size="small"
              showInfo={false}
              strokeColor={coveragePct > 50 ? "#5b8c6b" : coveragePct > 20 ? "#d48806" : "#999"}
            />
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
            {data.entries.length === 0 && (
              <Empty description="本卷没有已对齐的段落" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}

            {data.entries.length > 0 && (
              <Collapse
                activeKey={activeKeys}
                onChange={(keys) => setActiveKeys(Array.isArray(keys) ? keys : [keys])}
                ghost
                items={data.entries.map((entry) => ({
                  key: `chunk-${entry.chunk_index}`,
                  label: (
                    <div style={{ paddingRight: 8 }}>
                      <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>
                        段 #{entry.chunk_index}
                        {" · "}
                        {entry.parallels.length} 条跨藏经对应
                      </div>
                      <div
                        lang="zh-Hans"
                        style={{
                          fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
                          fontSize: 14,
                          lineHeight: 1.7,
                          color: "#222",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {entry.chunk_text}
                      </div>
                    </div>
                  ),
                  children: (
                    <div style={{ paddingLeft: 8, borderLeft: "2px solid #e8e8e8" }}>
                      <div
                        lang="zh-Hans"
                        style={{
                          fontFamily: '"Noto Serif SC", serif',
                          fontSize: 14,
                          lineHeight: 1.9,
                          color: "#333",
                          padding: "8px 12px",
                          background: "#fafafa",
                          borderRadius: 4,
                          marginBottom: 12,
                        }}
                      >
                        {entry.chunk_text}
                      </div>
                      {entry.parallels.map((p, idx) => (
                        <div
                          key={`${p.text_id}-${p.juan_num}-${p.chunk_index}-${idx}`}
                          style={{
                            padding: "10px 12px",
                            marginBottom: 10,
                            borderRadius: 4,
                            background: "#fff",
                            border: "1px solid #e8e8e8",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                            <Tag color={LANG_COLOR[p.lang] || "default"} style={{ margin: 0 }}>
                              {LANG_LABEL[p.lang] || p.lang}
                            </Tag>
                            <span style={{ fontSize: 12, color: "#666" }}>
                              《{p.title || "其他藏经"}》 第 {p.juan_num} 卷
                            </span>
                            <span style={{ fontSize: 11, color: "#999", marginLeft: "auto" }}>
                              置信度 {(p.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div
                            lang={p.lang}
                            style={{
                              fontSize: 13,
                              lineHeight: p.lang === "bo" ? 2.1 : 1.85,
                              color: "#333",
                            }}
                          >
                            {p.chunk_text}
                          </div>
                          {p.original_preview && p.original_lang && (
                            <div
                              lang={p.original_lang}
                              style={{
                                marginTop: 8,
                                padding: "8px 10px",
                                background: "#f6fafd",
                                borderLeft: "3px solid #5b8c6b",
                                fontSize: 12,
                                lineHeight: 1.8,
                                color: "#444",
                              }}
                            >
                              <div style={{ fontSize: 11, color: "#5b8c6b", marginBottom: 4, fontWeight: 500 }}>
                                {p.original_lang === "pi" ? "Pāli 原文（本卷前 500 字）" : "原文（本卷前 500 字）"}
                              </div>
                              {p.original_preview}
                              {p.original_preview.length >= 500 && "…"}
                            </div>
                          )}
                          <div style={{ marginTop: 8, fontSize: 12 }}>
                            <Link
                              to={`/texts/${p.text_id}/read?juan=${p.juan_num}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: "#5b8c6b" }}
                            >
                              <BookOutlined style={{ marginRight: 4 }} />
                              阅读全文 →
                            </Link>
                          </div>
                        </div>
                      ))}
                    </div>
                  ),
                }))}
              />
            )}

            {data.entries.length > 0 && (
              <div style={{ marginTop: 20, padding: 12, background: "#fafafa", borderRadius: 4, fontSize: 12, color: "#666" }}>
                <LinkOutlined style={{ marginRight: 6 }} />
                对齐数据由 FoJin 多语 RAG 管道生成，采用 embedding 粗召回 + LLM 精验证。
                巴利/藏文条目展示的匹配文本为 Sujato / 84000 英译本；Pāli 原文预览取自 text_contents。
                低置信度对应可能需人工审核。
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
