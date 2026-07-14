import { useCallback, useEffect, useState } from "react";
import {
  Alert,
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
import { useTranslation } from "react-i18next";
import { formatAdminDate } from "./adminI18n";

const REASON_LABEL_KEYS: Record<string, string> = {
  downvoted: "admin_aq.reason.downvoted",
  abnormal: "admin_aq.reason.abnormal",
  no_citation: "admin_aq.reason.no_citation",
  weak_evidence: "admin_aq.reason.weak_evidence",
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

const CATEGORY_OPTION_KEYS = [
  { value: "recall", labelKey: "admin_aq.category.recall" },
  { value: "hallucination", labelKey: "admin_aq.category.hallucination" },
  { value: "prompt", labelKey: "admin_aq.category.prompt" },
  { value: "data", labelKey: "admin_aq.category.data" },
  { value: "other", labelKey: "admin_aq.category.other" },
];

const WINDOW_DAY_OPTIONS = [30, 90, 180, 365];

export default function AdminAnswerQualityPage() {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<AnswerQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [dist, setDist] = useState<ScoreDistribution | null>(null);
  const [reviewStats, setReviewStats] = useState<AnswerReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [windowDays, setWindowDays] = useState(30);
  const [minSuspicion, setMinSuspicion] = useState(0);
  const [reasonFilters, setReasonFilters] = useState<string[]>([]);
  const [verdicts, setVerdicts] = useState<
    Record<number, { category?: string; note?: string }>
  >({});

  const load = useCallback(() => {
    return Promise.all([
      getAnswerQualityQueue({
        window: windowDays,
        min_suspicion: minSuspicion,
        category: reasonFilters.length ? reasonFilters.join(",") : undefined,
        limit: 50,
      }),
      getAnswerReviewStats(),
    ])
      .then(([res, stats]) => {
        setItems(res.items);
        setTotal(res.total_unreviewed);
        setDist(res.score_distribution);
        setReviewStats(stats);
        setLoadError(false);
      })
      .catch(() => {
        // 失败必须显性化:此前只弹 toast、把 total 留在初始 0,于是 500 和
        // 「队列真的空」长得一模一样 —— 715 条积压就是这样被当成空队列的。
        setLoadError(true);
        setItems([]);
        message.error(t("admin_aq.load_error"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [minSuspicion, reasonFilters, t, windowDays]);

  // Spinner state for param changes is adjusted during render; the fetch
  // effect below only sets state from promise callbacks.
  const queryKey = `${windowDays}|${minSuspicion}|${reasonFilters.join(",")}`;
  const [prevQueryKey, setPrevQueryKey] = useState(queryKey);
  if (prevQueryKey !== queryKey) {
    setPrevQueryKey(queryKey);
    setLoading(true);
  }

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(() => {
    setLoading(true);
    void load();
  }, [load]);

  const review = useCallback(
    async (item: AnswerQueueItem, verdict: "good" | "bad") => {
      const extra = verdicts[item.message_id] || {};
      if (verdict === "bad" && !extra.category) {
        message.warning(t("admin_aq.bad_requires_category"));
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
        message.success(
          t(
            verdict === "good"
              ? "admin_aq.review_good_success"
              : "admin_aq.review_bad_success",
          ),
        );
      } catch {
        message.error(t("admin_aq.submit_error"));
      }
    },
    [t, verdicts],
  );

  const columns: ColumnsType<AnswerQueueItem> = [
    {
      title: t("admin_aq.column.time"),
      dataIndex: "created_at",
      width: 160,
      render: (v: string) => formatAdminDate(v, i18n.language),
    },
    {
      title: t("admin_aq.column.question"),
      dataIndex: "question",
      ellipsis: true,
      render: (q: string) =>
        q || (
          <Typography.Text type="secondary">
            {t("admin_aq.empty_value")}
          </Typography.Text>
        ),
    },
    {
      title: t("admin_aq.column.reason"),
      dataIndex: "reason_tags",
      width: 220,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {tags.map((tag) => (
            <Tag key={tag} color={REASON_COLORS[tag] || "default"}>
              {REASON_LABEL_KEYS[tag] ? t(REASON_LABEL_KEYS[tag]) : tag}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t("admin_aq.column.suspicion"),
      dataIndex: "suspicion_score",
      width: 90,
      sorter: (a, b) => a.suspicion_score - b.suspicion_score,
      defaultSortOrder: "descend",
      render: (s: number) => s.toFixed(1),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>{t("nav.admin_answer_quality")}</Typography.Title>
      {loadError && (
        <Alert
          role="alert"
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("admin_aq.load_error")}
          action={
            <Button
              size="small"
              onClick={() => {
                setLoading(true);
                void load();
              }}
            >
              {t("common.retry")}
            </Button>
          }
        />
      )}
      <Space style={{ marginBottom: 16 }} wrap>
        {!loadError && (
          <Typography.Text strong>
            {t("admin_aq.unreviewed_total", { count: total })}
          </Typography.Text>
        )}
        {reviewStats && (
          <>
            <Typography.Text type="secondary">
              {t("admin_aq.reviewed_total", {
                count: reviewStats.reviewed_total,
              })}
            </Typography.Text>
            <Typography.Text type="secondary">good {reviewStats.good}</Typography.Text>
            <Typography.Text type="secondary">bad {reviewStats.bad}</Typography.Text>
          </>
        )}
        {dist && (
          <Typography.Text type="secondary">
            {t("admin_aq.score_distribution", {
              p10: dist.p10 ?? "—",
              p50: dist.p50 ?? "—",
              p90: dist.p90 ?? "—",
            })}
          </Typography.Text>
        )}
        <Space size={6}>
          <Typography.Text type="secondary">
            {t("admin_aq.window_label")}
          </Typography.Text>
          <Select
            style={{ width: 96 }}
            value={windowDays}
            onChange={setWindowDays}
            options={WINDOW_DAY_OPTIONS.map((value) => ({
              value,
              label: t("admin_aq.days", { count: value }),
            }))}
          />
        </Space>
        <Space size={6}>
          <Typography.Text type="secondary">
            {t("admin_aq.min_suspicion_label")}
          </Typography.Text>
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
          placeholder={t("admin_aq.reason_filter_placeholder")}
          style={{ minWidth: 220 }}
          value={reasonFilters}
          onChange={(v: string[]) => setReasonFilters(v)}
          options={Object.entries(REASON_LABEL_KEYS).map(([value, labelKey]) => ({
            value,
            label: t(labelKey),
          }))}
        />
        <Button onClick={() => refresh()}>{t("admin_aq.refresh")}</Button>
      </Space>

      <Table<AnswerQueueItem>
        rowKey="message_id"
        loading={loading}
        columns={columns}
        dataSource={items}
        locale={{ emptyText: loadError ? t("admin_aq.load_error") : t("admin_aq.queue_empty") }}
        expandable={{
          expandedRowRender: (item) => (
            <Card size="small" bordered={false}>
              <Typography.Paragraph>
                <Typography.Text strong>{t("admin_aq.detail.question_label")}</Typography.Text>
                {item.question || t("admin_aq.empty_value")}
              </Typography.Paragraph>
              <Typography.Paragraph>
                <Typography.Text strong>{t("admin_aq.detail.answer_label")}</Typography.Text>
                <span style={{ whiteSpace: "pre-wrap" }}>{item.answer}</span>
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                {t("admin_aq.detail.current_feedback", {
                  feedback: item.feedback ?? t("admin_aq.empty_value"),
                })}
              </Typography.Paragraph>
              <Typography.Text strong>{t("admin_aq.detail.sources_label")}</Typography.Text>
              {item.sources.length === 0 ? (
                <Typography.Paragraph type="secondary">
                  {t("admin_aq.detail.no_sources")}
                </Typography.Paragraph>
              ) : (
                <ul>
                  {item.sources.map((s, i) => (
                    <li
                      key={i}
                      style={{ color: (s.score ?? 1) < WEAK_SCORE ? "#cf1322" : undefined }}
                    >
                      {t("admin_aq.detail.source_meta", {
                        title: s.title_zh,
                        juan: s.juan_num,
                        score: s.score ?? "—",
                      })}
                      {s.chunk_text.slice(0, 80)}
                    </li>
                  ))}
                </ul>
              )}
              <Space direction="vertical" style={{ width: "100%", marginTop: 12 }}>
                <Space wrap>
                  <Select
                    placeholder={t("admin_aq.failure_category_placeholder")}
                    style={{ width: 180 }}
                    options={CATEGORY_OPTION_KEYS.map(({ value, labelKey }) => ({
                      value,
                      label: t(labelKey),
                    }))}
                    value={verdicts[item.message_id]?.category}
                    onChange={(v) =>
                      setVerdicts((p) => ({
                        ...p,
                        [item.message_id]: { ...p[item.message_id], category: v },
                      }))
                    }
                  />
                  <Button onClick={() => void review(item, "good")}>
                    {t("admin_aq.action.mark_good")}
                  </Button>
                  <Button danger onClick={() => void review(item, "bad")}>
                    {t("admin_aq.action.mark_bad")}
                  </Button>
                </Space>
                <Input.TextArea
                  placeholder={t("admin_aq.note_placeholder")}
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
