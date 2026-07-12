import { Card, Progress, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  getAlignmentCoverage,
  type AlignmentCoverageItem,
} from "../api/client";

const LANG_COLORS: Record<string, string> = {
  bo: "geekblue", // Tibetan
  pli: "green", // Pali
  san: "volcano", // Sanskrit
  en: "gold",
};

function coverageStatus(pct: number | null): "success" | "active" | "exception" {
  if (pct === null) return "active";
  if (pct >= 100) return "success";
  if (pct < 34) return "exception";
  return "active";
}

export default function AdminAlignmentPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "alignment-coverage"],
    queryFn: () => getAlignmentCoverage(500),
  });

  const columns: ColumnsType<AlignmentCoverageItem> = [
    {
      title: t("admin_align.col.text"),
      dataIndex: "title_zh",
      key: "title_zh",
      render: (title: string, r) => (
        <Link to={`/texts/${r.text_id}/read`}>{title}</Link>
      ),
    },
    {
      title: t("admin_align.col.dynasty"),
      dataIndex: "dynasty",
      key: "dynasty",
      width: 90,
      render: (v: string | null) => v || "—",
    },
    {
      title: t("admin_align.col.coverage"),
      dataIndex: "coverage_pct",
      key: "coverage_pct",
      width: 170,
      defaultSortOrder: "ascend",
      sorter: (a, b) => (a.coverage_pct ?? 101) - (b.coverage_pct ?? 101),
      render: (pct: number | null) =>
        pct === null ? (
          <Tooltip title={t("admin_align.coverage_unknown")}>
            <Typography.Text type="secondary">—</Typography.Text>
          </Tooltip>
        ) : (
          <Progress percent={pct} size="small" status={coverageStatus(pct)} />
        ),
    },
    {
      title: t("admin_align.col.juans"),
      key: "juans",
      width: 110,
      render: (_, r) =>
        r.total_juans > 0 ? `${r.aligned_juans} / ${r.total_juans}` : `${r.aligned_juans} / ?`,
    },
    {
      title: t("admin_align.col.gap"),
      dataIndex: "remaining_juans",
      key: "remaining_juans",
      width: 90,
      sorter: (a, b) => (b.remaining_juans ?? -1) - (a.remaining_juans ?? -1),
      render: (v: number | null) =>
        v === null ? (
          "—"
        ) : v > 0 ? (
          <Typography.Text strong>{v}</Typography.Text>
        ) : (
          <Tag color="success">{t("admin_align.done")}</Tag>
        ),
    },
    {
      title: t("admin_align.col.pairs"),
      dataIndex: "pair_count",
      key: "pair_count",
      width: 90,
      sorter: (a, b) => a.pair_count - b.pair_count,
    },
    {
      title: t("admin_align.col.partners"),
      dataIndex: "partner_langs",
      key: "partner_langs",
      render: (langs: string[]) => (
        <>
          {langs.map((l) => (
            <Tag key={l} color={LANG_COLORS[l] || "default"}>
              {t(`admin_align.lang.${l}`, l)}
            </Tag>
          ))}
        </>
      ),
    },
    {
      title: t("admin_align.col.confidence"),
      dataIndex: "avg_confidence",
      key: "avg_confidence",
      width: 100,
      sorter: (a, b) => (a.avg_confidence ?? 0) - (b.avg_confidence ?? 0),
      render: (v: number | null) => (v === null ? "—" : v.toFixed(2)),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <title>{t("admin_align.page_title")}</title>
      <Card
        title={
          data
            ? t("admin_align.title_with_count", { count: data.total })
            : t("admin_align.title")
        }
        extra={
          <Link to="/admin/alignment/review">
            {t("admin_align.review_link")}
          </Link>
        }
      >
        <Typography.Paragraph type="secondary">
          {t("admin_align.subtitle")}
        </Typography.Paragraph>
        <Table<AlignmentCoverageItem>
          rowKey="text_id"
          size="small"
          loading={isLoading}
          dataSource={data?.items ?? []}
          columns={columns}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          locale={{
            emptyText: isError
              ? t("admin_align.load_error")
              : t("admin_align.empty"),
          }}
        />
      </Card>
    </div>
  );
}
