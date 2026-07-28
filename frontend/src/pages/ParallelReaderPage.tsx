import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Empty,
  InputNumber,
  Result,
  Select,
  Space,
  Spin,
  Typography,
} from "antd";
import { ArrowLeftOutlined, RobotOutlined, SwapOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getJuanAlignment,
  getParallelRead,
  getTextRelations,
  type AiDiffChunkInput,
  type JuanAlignmentResponse,
} from "../api/client";
import AlignmentColumn from "../components/parallel/AlignmentColumn";
import AIDiffPopover from "../components/parallel/AIDiffPopover";
import { buildAlignmentMap } from "../components/parallel/buildAlignmentMap";
import { useSyncScroll, type ColumnRef } from "../components/parallel/useSyncScroll";
import { useSelectedChunks } from "../components/parallel/useSelectedChunks";
import type { ColumnData } from "../components/parallel/types";
import "../styles/parallel.css";

const { Title } = Typography;

export default function ParallelReaderPage() {
  const { t } = useTranslation();
  const { textId } = useParams<{ textId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const baseId = Number(textId);
  const compareId = searchParams.get("compare") ? Number(searchParams.get("compare")) : null;
  const compare2Id = searchParams.get("compare2") ? Number(searchParams.get("compare2")) : null;
  const juan = Number(searchParams.get("juan") || "1");

  const { data: relations } = useQuery({
    queryKey: ["relations", baseId],
    queryFn: () => getTextRelations(baseId),
    enabled: !!baseId,
  });

  const compareIds = [compareId, compare2Id].filter((x): x is number => x !== null);

  // Fetch parallel-read pairs for each compare
  const parallelQueries = useQueries({
    queries: compareIds.map((cid) => ({
      queryKey: ["parallel", baseId, cid, juan],
      queryFn: () => getParallelRead(baseId, cid, juan),
      enabled: !!baseId,
    })),
  });

  // Fetch alignment for base + each compare (for symmetric anchor map)
  const allTextIds = [baseId, ...compareIds];
  const alignmentQueries = useQueries({
    queries: allTextIds.map((tid) => ({
      queryKey: ["juan-alignment", tid, juan],
      queryFn: () => getJuanAlignment(tid, juan),
      enabled: !!tid,
      retry: false,
    })),
  });

  const anyLoading = parallelQueries.some((q) => q.isLoading);
  const anyError = parallelQueries.some((q) => q.isError);

  // Stable string keys so useMemo dep arrays don't include array literals
  const parallelKey = parallelQueries.map((q) => q.data?.text_b?.text_id ?? "").join(",");
  const alignmentKey = alignmentQueries.map((q) => q.data?.text_id ?? "").join(",");

  // Build column data: base text from first parallel query's text_a, compares from text_b of each
  const columns: ColumnData[] = useMemo(() => {
    if (parallelQueries.length === 0) return [];
    const result: ColumnData[] = [];
    const first = parallelQueries[0].data;
    if (first) {
      result.push({
        text: first.text_a,
        alignment: alignmentQueries[0]?.data ?? null,
      });
    }
    parallelQueries.forEach((q, i) => {
      if (q.data) {
        result.push({
          text: q.data.text_b,
          alignment: alignmentQueries[i + 1]?.data ?? null,
        });
      }
    });
    return result;
    // parallelQueries / alignmentQueries identities change per render — drive memo via stable keys
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parallelKey, alignmentKey]);

  const alignmentMap = useMemo(
    () => buildAlignmentMap(alignmentQueries.map((q) => q.data ?? null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [alignmentKey],
  );

  // Refs to each column's scroll container. Entries are (re)written by the
  // inline ref callbacks in the JSX below on every commit; here we only trim
  // stale tail entries when columns shrink (ref writes in effects are fine).
  const scrollRefs = useRef<ColumnRef[]>([]);
  useEffect(() => {
    scrollRefs.current.length = columns.length;
  }, [columns.length]);

  useSyncScroll(scrollRefs, alignmentMap);

  const { selected, toggle, clear } = useSelectedChunks();
  const [showDiff, setShowDiff] = useState(false);
  const selectedKeys = useMemo(
    () => new Set(selected.map((s) => `${s.text_id}:${s.chunk_index}`)),
    [selected],
  );

  const makeChunkClickHandler = (col: ColumnData) => (idx: number, paragraph: string) => {
    const c: AiDiffChunkInput = {
      text_id: col.text.text_id,
      juan_num: col.text.juan_num,
      chunk_index: idx,
      lang: col.text.lang,
      text: paragraph,
    };
    toggle(c);
  };

  const handleCompareChange = (value: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("compare", String(value));
    next.set("juan", String(juan));
    setSearchParams(next);
  };

  const handleCompare2Change = (value: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null) {
      next.delete("compare2");
    } else {
      next.set("compare2", String(value));
    }
    next.set("juan", String(juan));
    setSearchParams(next);
  };

  const handleJuanChange = (value: number | null) => {
    if (value && compareId) {
      const next = new URLSearchParams(searchParams);
      next.set("juan", String(value));
      setSearchParams(next);
    }
  };

  const relationOptions =
    relations?.relations.map((r) => ({
      value: r.text_id,
      label: `${r.title_zh} (${r.translator || t("parallel.option.anonymous")} · ${r.dynasty || ""}) [${r.relation_type}]`,
    })) ?? [];

  return (
    <div className="parallel-container">
      <div className="parallel-header">
        <Button
          type="text"
          aria-label={t("parallel.page.back")}
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(-1)}
        >
          {t("parallel.page.back")}
        </Button>
        <Title level={3} style={{ margin: 0 }}>
          <SwapOutlined /> {t("parallel.page.title")}
        </Title>
      </div>

      <Card size="small" style={{ marginBottom: 16 }} className="parallel-controls">
        <Space wrap>
          <span>{t("parallel.controls.compare_version")}</span>
          <Select
            style={{ minWidth: 260 }}
            placeholder={t("parallel.controls.choose_compare")}
            value={compareId ?? undefined}
            onChange={handleCompareChange}
            options={relationOptions}
          />
          <span>{t("parallel.controls.third_column")}</span>
          <Select
            allowClear
            style={{ minWidth: 260 }}
            placeholder={t("parallel.controls.optional")}
            value={compare2Id ?? undefined}
            onChange={(v) => handleCompare2Change(v ?? null)}
            options={relationOptions.filter((o) => o.value !== compareId)}
          />
          <span>{t("parallel.controls.juan")}</span>
          <InputNumber min={1} value={juan} onChange={handleJuanChange} />
        </Space>
      </Card>

      {!compareId ? (
        <Empty description={t("parallel.status.choose_compare")} />
      ) : anyLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : anyError ? (
        <Result
          status="error"
          title={t("parallel.status.load_failed")}
          subTitle={t("parallel.status.load_failed_desc")}
          extra={
            <Button type="primary" onClick={() => parallelQueries.forEach((q) => q.refetch())}>
              {t("parallel.status.retry")}
            </Button>
          }
        />
      ) : columns.length === 0 ? (
        <Empty description={t("parallel.status.not_found")} />
      ) : (
        <>
          <AlignmentCoverageBanner alignments={alignmentQueries.map((q) => q.data ?? null)} />
          <div className={`parallel-grid-v1 cols-${columns.length}`}>
            {columns.map((col, i) => (
              <AlignmentColumn
                key={col.text.text_id}
                text={col.text}
                alignment={col.alignment}
                scrollRef={(el) => {
                  scrollRefs.current[i] = { textId: col.text.text_id, el };
                }}
                selectedKeys={selectedKeys}
                onChunkClick={makeChunkClickHandler(col)}
              />
            ))}
          </div>
          {selected.length >= 2 && !showDiff && (
            <Button
              type="primary"
              size="large"
              shape="round"
              icon={<RobotOutlined />}
              className="ai-diff-trigger"
              onClick={() => setShowDiff(true)}
            >
              {t("parallel.page.ai_diff_button", { count: selected.length })}
            </Button>
          )}
          {showDiff && selected.length >= 2 && (
            <AIDiffPopover
              chunks={selected}
              onClose={() => {
                setShowDiff(false);
                clear();
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

interface CoverageBannerProps {
  alignments: Array<JuanAlignmentResponse | null>;
}

function AlignmentCoverageBanner({ alignments }: CoverageBannerProps) {
  const { t } = useTranslation();
  // Use the base column (first alignment) for the coverage stat — that's the driver
  const base = alignments[0];
  if (!base || base.total_chunks === 0) return null;
  const pct = Math.round((base.chunks_with_parallels / base.total_chunks) * 100);
  const tone = pct >= 60 ? "#5b8c6b" : pct >= 30 ? "#d48806" : "#999";
  return (
    <div className="parallel-coverage-banner" style={{ borderLeftColor: tone }}>
      <span>{t("parallel.coverage.title")}</span>
      <strong style={{ color: tone }}>
        {t("parallel.coverage.count", {
          matched: base.chunks_with_parallels,
          total: base.total_chunks,
          pct,
        })}
      </strong>
      <span className="parallel-coverage-hint">
        {pct >= 60
          ? t("parallel.coverage.high")
          : pct >= 30
            ? t("parallel.coverage.medium")
            : t("parallel.coverage.low")}
      </span>
    </div>
  );
}
