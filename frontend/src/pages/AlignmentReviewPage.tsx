import { Button, Card, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  getAlignmentCandidates,
  reviewAlignmentCandidate,
  type AlignmentCandidate,
} from "../api/client";

const LANG_COLORS: Record<string, string> = {
  bo: "geekblue", // Tibetan
  pli: "green", // Pali
  san: "volcano", // Sanskrit
  en: "gold",
  zh: "magenta",
  lzh: "magenta", // literary Chinese
};

const SOURCE_COLORS: Record<string, string> = {
  "knn-bootstrap": "blue",
  "anchor-expansion": "purple",
};

const QUERY_KEY = ["admin", "alignment-candidates"] as const;

export default function AlignmentReviewPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => getAlignmentCandidates(50),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) =>
      reviewAlignmentCandidate(id, accept),
    onSuccess: (_updated, { id, accept }) => {
      // Drop the reviewed row locally so the reviewer keeps their place.
      queryClient.setQueryData<AlignmentCandidate[]>(QUERY_KEY, (prev) =>
        (prev ?? []).filter((c) => c.id !== id),
      );
      message.success(
        accept
          ? t("admin_align_review.accepted")
          : t("admin_align_review.rejected"),
      );
    },
    onError: () => {
      message.error(t("admin_align_review.review_error"));
    },
  });

  const langTag = (lang: string) => (
    <Tag color={LANG_COLORS[lang] || "default"}>
      {t(`admin_align.lang.${lang}`, lang)}
    </Tag>
  );

  const sideCell = (
    id: number,
    title: string | null,
    juan: number,
    lang: string,
  ) => (
    <Space direction="vertical" size={0}>
      <Link to={`/texts/${id}/read?juan=${juan}`}>
        {title || t("admin_align_review.text_id", { id })}
      </Link>
      <Space size={4}>
        <Typography.Text type="secondary">
          {t("admin_align_review.juan", { n: juan })}
        </Typography.Text>
        {langTag(lang)}
      </Space>
    </Space>
  );

  const columns: ColumnsType<AlignmentCandidate> = [
    {
      title: t("admin_align_review.col.side_a"),
      key: "side_a",
      render: (_, r) =>
        sideCell(r.text_a_id, r.text_a_title, r.text_a_juan_num, r.text_a_lang),
    },
    {
      title: t("admin_align_review.col.side_b"),
      key: "side_b",
      render: (_, r) =>
        sideCell(r.text_b_id, r.text_b_title, r.text_b_juan_num, r.text_b_lang),
    },
    {
      title: t("admin_align_review.col.similarity"),
      dataIndex: "similarity",
      key: "similarity",
      width: 110,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: t("admin_align_review.col.source"),
      dataIndex: "source",
      key: "source",
      width: 130,
      render: (v: string) => (
        <Tag color={SOURCE_COLORS[v] || "default"}>
          {t(`admin_align_review.source.${v}`, v)}
        </Tag>
      ),
    },
    {
      title: t("admin_align_review.col.actions"),
      key: "actions",
      width: 280,
      render: (_, r) => {
        const busy =
          reviewMutation.isPending && reviewMutation.variables?.id === r.id;
        return (
          <Space>
            <Link
              to={`/parallel/${r.text_a_id}?compare=${r.text_b_id}&juan=${r.text_a_juan_num}`}
            >
              {t("admin_align_review.open_parallel")}
            </Link>
            <Button
              type="primary"
              size="small"
              loading={busy}
              onClick={() =>
                reviewMutation.mutate({ id: r.id, accept: true })
              }
            >
              {t("admin_align_review.accept")}
            </Button>
            <Popconfirm
              title={t("admin_align_review.reject_confirm")}
              okText={t("admin_align_review.reject")}
              cancelText={t("admin_align_review.cancel")}
              okButtonProps={{ danger: true }}
              onConfirm={() =>
                reviewMutation.mutate({ id: r.id, accept: false })
              }
            >
              <Button danger size="small" loading={busy}>
                {t("admin_align_review.reject")}
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Card
      title={
        data
          ? t("admin_align_review.title_with_count", { n: data.length })
          : t("admin_align_review.title")
      }
    >
      <Typography.Paragraph type="secondary">
        {t("admin_align_review.subtitle")}
      </Typography.Paragraph>
      <Table<AlignmentCandidate>
        rowKey="id"
        size="small"
        loading={isLoading}
        dataSource={data ?? []}
        columns={columns}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        locale={{
          emptyText: isError
            ? t("admin_align_review.load_error")
            : t("admin_align_review.empty"),
        }}
      />
    </Card>
  );
}
