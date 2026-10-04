import { useState } from "react";
import { Link } from "react-router";
import { Spin } from "antd";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { searchContent, submitFeedback } from "../api/client";
import { sanitizeHighlight } from "../utils/sanitize";
import { buildReaderUrl } from "../utils/sourceUrls";
import { similarQuery, similarQueryChars, snippetOf, SIMILAR_QUERY_MIN, type SelectionContext } from "./ReaderSelectionExtras.types";

const SIMILAR_SHOW = 6;

function track(event: string, data: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(event, data);
}

/** 「全藏出处」：选中这句话在其它经论里出现在哪（注疏引文、异译、论典转引）。 */
export function SimilarPassages({ text, context }: { text: string; context: SelectionContext }) {
  const { t } = useTranslation();
  const q = similarQuery(text);
  const enabled = similarQueryChars(q) >= SIMILAR_QUERY_MIN;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reader-similar", q],
    queryFn: () => searchContent({ q, size: SIMILAR_SHOW + 4, phrase: true }),
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  if (!enabled) {
    return <div className="reader-dict-popover-empty">{t("reader.canonrefs.too_short")}</div>;
  }
  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 12 }}>
        <Spin size="small" />
      </div>
    );
  }
  if (isError || !data) {
    return <div className="reader-dict-popover-empty">{t("reader.canonrefs.error")}</div>;
  }
  const others = data.results.filter((h) => h.text_id !== context.textId).slice(0, SIMILAR_SHOW);
  if (!others.length) {
    return <div className="reader-dict-popover-empty">{t("reader.canonrefs.empty")}</div>;
  }
  return (
    <div className="reader-similar-list">
      {others.map((h) => (
        <Link
          key={`${h.text_id}-${h.juan_num}`}
          className="reader-similar-item"
          to={buildReaderUrl(h.text_id, h.juan_num)}
          onClick={() => track("reader_similar_open", { from: context.textId, to: h.text_id })}
        >
          <div className="reader-similar-title">
            {h.title_zh}
            <span className="reader-similar-meta">
              {h.cbeta_id} · {t("reader.canonrefs.juan", { n: h.juan_num })}
              {h.dynasty ? ` · ${h.dynasty}` : ""}
            </span>
          </div>
          {snippetOf(h.highlight) && (
            <div
              className="reader-similar-snippet"
              dangerouslySetInnerHTML={{ __html: `…${sanitizeHighlight(snippetOf(h.highlight)!)}…` }}
            />
          )}
        </Link>
      ))}
      <Link className="reader-similar-all" to={`/search?q=${encodeURIComponent(q)}`}>
        {t("reader.canonrefs.view_all", { n: data.total })}
      </Link>
    </div>
  );
}

/** 「报错」：把选中的经文、位置与说明打包成一条后台反馈，进管理员信箱。 */
export function ReportErrorForm({
  text,
  context,
  loggedIn,
  onDone,
}: {
  text: string;
  context: SelectionContext;
  loggedIn: boolean;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      submitFeedback({
        content: t("reader.report.template", {
          title: context.title,
          id: context.cbetaId,
          juan: context.juanNum,
          ref: context.lineRef ?? "—",
          text: text.slice(0, 300),
          note: note.trim() || "—",
          url: `${window.location.origin}${buildReaderUrl(context.textId, context.juanNum)}`,
        }),
      }),
    onSuccess: () => track("reader_report_submit", { id: context.textId }),
  });

  if (!loggedIn) {
    return (
      <div className="reader-dict-popover-empty">
        {t("reader.report.login_needed")}{" "}
        <Link
          to="/login"
          onClick={() => {
            try {
              sessionStorage.setItem("fojin.login.returnTo", window.location.pathname + window.location.search);
            } catch {
              /* 隐私模式下 sessionStorage 可能不可用，登录后回首页即可 */
            }
          }}
        >
          {t("reader.report.login")}
        </Link>
      </div>
    );
  }
  if (mutation.isSuccess) {
    return (
      <div className="reader-dict-popover-empty">
        {t("reader.report.thanks")}{" "}
        <button type="button" className="reader-report-link" onClick={onDone}>
          {t("reader.dict.close")}
        </button>
      </div>
    );
  }
  return (
    <div className="reader-report-form">
      <div className="reader-report-where">
        {context.cbetaId} · {t("reader.canonrefs.juan", { n: context.juanNum })}
        {context.lineRef ? ` · ${context.lineRef}` : ""}
      </div>
      <textarea
        className="reader-report-note"
        value={note}
        maxLength={500}
        rows={3}
        placeholder={t("reader.report.placeholder")}
        onChange={(e) => setNote(e.target.value)}
      />
      {mutation.isError && <div className="reader-report-error">{t("reader.report.failed")}</div>}
      <button
        type="button"
        className="reader-report-submit"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? t("reader.report.sending") : t("reader.report.submit")}
      </button>
    </div>
  );
}
