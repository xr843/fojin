import { useState } from "react";
import { Drawer, Empty, Spin, Alert, Collapse, Tag, Progress } from "antd";
import { GlobalOutlined, LinkOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { getJuanAlignment } from "../api/client";

interface Props {
  textId: number;
  juanNum: number;
  textTitle: string;
  open: boolean;
  onClose: () => void;
}

const LANG_LABEL: Record<string, string> = {
  lzh: "汉",
  pi: "巴利",
  sa: "梵",
  bo: "藏",
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
 * Reader 右侧"他藏对读"抽屉：展示当前卷所有有跨藏经对应的段落。
 *
 * 数据来自 /api/alignment/texts/{text_id}/juans/{juan_num}，每个条目包含：
 *   - 本源段落 (chunk_text)
 *   - N 条跨藏经 parallel (with lang + title + confidence)
 *
 * MVP 经典 (心经/金刚经/念处经/转法轮经/法句经/维摩诘经) 打开后会显示
 * 实际对应段落，其他经典显示 "暂无跨藏经对照数据"。
 */
export default function ReaderParallelDrawer({
  textId,
  juanNum,
  textTitle,
  open,
  onClose,
}: Props) {
  const [activeKeys, setActiveKeys] = useState<string[]>([]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["juan-alignment", textId, juanNum],
    queryFn: () => getJuanAlignment(textId, juanNum),
    enabled: open && textId > 0 && juanNum > 0,
    staleTime: 5 * 60 * 1000,
    retry: false,  // alignment 404 is expected for non-MVP texts
  });

  const coveragePct = data && data.total_chunks > 0
    ? Math.round((data.chunks_with_parallels / data.total_chunks) * 100)
    : 0;

  return (
    <Drawer
      title={
        <span>
          <GlobalOutlined style={{ marginRight: 8 }} />
          他藏对读 · 《{textTitle}》第 {juanNum} 卷
        </span>
      }
      placement="right"
      width={560}
      open={open}
      onClose={onClose}
      styles={{ body: { padding: "12px 16px" } }}
    >
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
          message="本卷暂无跨藏经对照数据"
          description="当前只有 MVP 首批 5 部佛典（心经、念处经、转法轮经、法句经、维摩诘经）打通了汉巴/汉藏段落对照。未来会陆续扩展。"
          style={{ marginBottom: 16 }}
        />
      )}

      {data && !isLoading && !error && (
        <>
          <div style={{ marginBottom: 16 }}>
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
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
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
              对齐数据由 FoJin 跨藏经 RAG 对读管道生成，采用 embedding 粗召回 + LLM 精验证。
              低置信度的对应可能需要人工审核。
            </div>
          )}
        </>
      )}
    </Drawer>
  );
}
