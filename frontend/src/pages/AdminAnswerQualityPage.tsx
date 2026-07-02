import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  getAnswerReviewStats,
  getAnswerQualityQueue,
  submitAnswerReview,
  type AnswerQueueItem,
  type AnswerReviewStats,
  type ScoreDistribution,
} from "../api/client";

const REASON_LABELS: Record<string, string> = {
  downvoted: "被踩",
  abnormal: "异常短答",
  no_citation: "未引经",
  weak_evidence: "召回证据弱",
};

const REASON_COLORS: Record<string, string> = {
  downvoted: "red",
  abnormal: "purple",
  no_citation: "orange",
  weak_evidence: "gold",
};

// Mirrors backend WEAK_EVIDENCE_THRESHOLD (answer_quality.py) — keep in sync if
// the backend threshold is recalibrated. Display-only (reds weak sources).
const WEAK_SCORE = 0.37;

const CATEGORY_OPTIONS = [
  { value: "recall", label: "召回弱/不全" },
  { value: "hallucination", label: "幻觉" },
  { value: "prompt", label: "表达/提示词" },
  { value: "data", label: "语料缺失" },
  { value: "other", label: "其他" },
];

export default function AdminAnswerQualityPage() {
  const [items, setItems] = useState<AnswerQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [dist, setDist] = useState<ScoreDistribution | null>(null);
  const [reviewStats, setReviewStats] = useState<AnswerReviewStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [windowDays, setWindowDays] = useState(90);
  const [minSuspicion, setMinSuspicion] = useState(0);
  const [reasonFilters, setReasonFilters] = useState<string[]>([]);
  const [verdicts, setVerdicts] = useState<
    Record<number, { category?: string; note?: string }>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [res, stats] = await Promise.all([
        getAnswerQualityQueue({
          window: windowDays,
          min_suspicion: minSuspicion,
          category: reasonFilters.length ? reasonFilters.join(",") : undefined,
          limit: 50,
        }),
        getAnswerReviewStats(),
      ]);
      setItems(res.items);
      setTotal(res.total_unreviewed);
      setDist(res.score_distribution);
      setReviewStats(stats);
    } catch {
      message.error("加载差答案队列失败");
    } finally {
      setLoading(false);
    }
  }, [minSuspicion, reasonFilters, windowDays]);

  useEffect(() => {
    void load();
  }, [load]);

  const review = useCallback(
    async (item: AnswerQueueItem, verdict: "good" | "bad") => {
      const extra = verdicts[item.message_id] || {};
      if (verdict === "bad" && !extra.category) {
        message.warning("标为 bad 时请先选择失败类型");
        return;
      }
      try {
        const res = await submitAnswerReview({
          message_id: item.message_id,
          verdict,
          failure_category: verdict === "bad" ? extra.category : undefined,
          note: extra.note,
        });
        setItems((prev) => prev.filter((i) => i.message_id !== item.message_id));
        setTotal(res.remaining_unreviewed);
        void getAnswerReviewStats()
          .then(setReviewStats)
          .catch(() => undefined);
        message.success(verdict === "good" ? "已标记 good" : "已标记 bad");
      } catch {
        message.error("提交失败");
      }
    },
    [verdicts],
  );

  const columns: ColumnsType<AnswerQueueItem> = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 160,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "问题",
      dataIndex: "question",
      ellipsis: true,
      render: (q: string) =>
        q || <Typography.Text type="secondary">（无）</Typography.Text>,
    },
    {
      title: "原因",
      dataIndex: "reason_tags",
      width: 220,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {tags.map((t) => (
            <Tag key={t} color={REASON_COLORS[t] || "default"}>
              {REASON_LABELS[t] || t}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "可疑度",
      dataIndex: "suspicion_score",
      width: 90,
      sorter: (a, b) => a.suspicion_score - b.suspicion_score,
      defaultSortOrder: "descend",
      render: (s: number) => s.toFixed(1),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>差答案队列</Typography.Title>
      <Space style={{ marginBottom: 16 }} wrap>
        <Typography.Text strong>未复核 {total} 条</Typography.Text>
        {reviewStats && (
          <>
            <Typography.Text type="secondary">
              已复核 {reviewStats.reviewed_total} 条
            </Typography.Text>
            <Typography.Text type="secondary">good {reviewStats.good}</Typography.Text>
            <Typography.Text type="secondary">bad {reviewStats.bad}</Typography.Text>
          </>
        )}
        {dist && (
          <Typography.Text type="secondary">
            召回分布 p10 {dist.p10 ?? "—"} / p50 {dist.p50 ?? "—"} / p90{" "}
            {dist.p90 ?? "—"}
          </Typography.Text>
        )}
        <Space size={6}>
          <Typography.Text type="secondary">时间窗口</Typography.Text>
          <Select
            style={{ width: 96 }}
            value={windowDays}
            onChange={setWindowDays}
            options={[
              { value: 30, label: "30 天" },
              { value: 90, label: "90 天" },
              { value: 180, label: "180 天" },
              { value: 365, label: "365 天" },
            ]}
          />
        </Space>
        <Space size={6}>
          <Typography.Text type="secondary">最低可疑度</Typography.Text>
          <InputNumber
            min={0}
            max={20}
            step={0.5}
            precision={1}
            style={{ width: 88 }}
            value={minSuspicion}
            onChange={(v) => setMinSuspicion(typeof v === "number" ? v : 0)}
          />
        </Space>
        <Select
          mode="multiple"
          allowClear
          placeholder="按原因筛选"
          style={{ minWidth: 220 }}
          value={reasonFilters}
          onChange={(v: string[]) => setReasonFilters(v)}
          options={Object.entries(REASON_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
        />
        <Button onClick={() => void load()}>刷新</Button>
      </Space>

      <Table<AnswerQueueItem>
        rowKey="message_id"
        loading={loading}
        columns={columns}
        dataSource={items}
        locale={{ emptyText: "队列已清空" }}
        expandable={{
          expandedRowRender: (item) => (
            <Card size="small" bordered={false}>
              <Typography.Paragraph>
                <Typography.Text strong>问：</Typography.Text>
                {item.question || "（无）"}
              </Typography.Paragraph>
              <Typography.Paragraph>
                <Typography.Text strong>答：</Typography.Text>
                <span style={{ whiteSpace: "pre-wrap" }}>{item.answer}</span>
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                当前反馈：{item.feedback ?? "无"}
              </Typography.Paragraph>
              <Typography.Text strong>召回片段：</Typography.Text>
              {item.sources.length === 0 ? (
                <Typography.Paragraph type="secondary">
                  （未引经）
                </Typography.Paragraph>
              ) : (
                <ul>
                  {item.sources.map((s, i) => (
                    <li
                      key={i}
                      style={{ color: (s.score ?? 1) < WEAK_SCORE ? "#cf1322" : undefined }}
                    >
                      {s.title_zh}（卷{s.juan_num}，score {s.score ?? "—"}）：
                      {s.chunk_text.slice(0, 80)}
                    </li>
                  ))}
                </ul>
              )}
              <Space direction="vertical" style={{ width: "100%", marginTop: 12 }}>
                <Space wrap>
                  <Select
                    placeholder="失败类型（bad 必填）"
                    style={{ width: 180 }}
                    options={CATEGORY_OPTIONS}
                    value={verdicts[item.message_id]?.category}
                    onChange={(v) =>
                      setVerdicts((p) => ({
                        ...p,
                        [item.message_id]: { ...p[item.message_id], category: v },
                      }))
                    }
                  />
                  <Button onClick={() => void review(item, "good")}>标 good</Button>
                  <Button danger onClick={() => void review(item, "bad")}>
                    标 bad
                  </Button>
                </Space>
                <Input.TextArea
                  placeholder="笔记（可选）"
                  rows={2}
                  value={verdicts[item.message_id]?.note}
                  onChange={(e) =>
                    setVerdicts((p) => ({
                      ...p,
                      [item.message_id]: {
                        ...p[item.message_id],
                        note: e.target.value,
                      },
                    }))
                  }
                />
              </Space>
            </Card>
          ),
        }}
      />
    </div>
  );
}
