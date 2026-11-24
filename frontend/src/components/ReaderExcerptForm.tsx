import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { createExcerpt } from "../api/client";
import type { SelectionContext } from "./ReaderSelectionExtras.types";

/** 阅读页划词浮层里的「摘录」：把选中的经文存进个人摘录，可附一句笔记。只有本人可见、不经审核。 */
export function ReaderExcerptForm({
  text,
  context,
  endLineRef,
  loggedIn,
  onDone,
}: {
  text: string;
  context: SelectionContext;
  endLineRef?: string | null;
  loggedIn: boolean;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      createExcerpt({
        text_id: context.textId,
        juan_num: context.juanNum,
        line_ref: context.lineRef,
        end_line_ref: endLineRef ?? null,
        quote: text.slice(0, 500),
        note: note.trim() || null,
      }),
    onSuccess: () => {
      if (typeof umami !== "undefined") {
        umami.track("reader_excerpt_save", { id: context.textId, note: note.trim() ? 1 : 0 });
      }
      queryClient.invalidateQueries({ queryKey: ["excerpts"] });
    },
  });

  if (!loggedIn) {
    return (
      <div className="reader-dict-popover-empty">
        {t("reader.excerpt.login_needed")}{" "}
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
        {t("reader.excerpt.saved")}{" "}
        <Link to="/profile?tab=excerpts" onClick={onDone}>
          {t("reader.excerpt.view_all")}
        </Link>
      </div>
    );
  }
  return (
    <div className="reader-report-form">
      <div className="reader-report-where">
        {context.cbetaId} · {t("reader.canonrefs.juan", { n: context.juanNum })}
        {context.lineRef ? ` · ${context.lineRef}` : ""} · {t("reader.excerpt.private")}
      </div>
      <textarea
        className="reader-report-note"
        value={note}
        maxLength={2000}
        rows={2}
        placeholder={t("reader.excerpt.placeholder")}
        onChange={(e) => setNote(e.target.value)}
      />
      {mutation.isError && <div className="reader-report-error">{t("reader.excerpt.failed")}</div>}
      <button
        type="button"
        className="reader-report-submit"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? t("reader.excerpt.saving") : t("reader.excerpt.save")}
      </button>
    </div>
  );
}

export default ReaderExcerptForm;
