import { useState } from "react";
import { Link } from "react-router";
import { Button, Empty, Input, Pagination, Popconfirm, Spin, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { deleteExcerpt, listExcerpts, updateExcerptNote, type ExcerptItem } from "../api/client";
import { localizeHan } from "../utils/hanScript";
import { excerptReaderUrl } from "../utils/excerptUrl";
import "../styles/excerpts.css";

const PAGE_SIZE = 20;


function ExcerptRow({ item }: { item: ExcerptItem }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.note ?? "");
  const save = useMutation({
    mutationFn: () => updateExcerptNote(item.id, draft.trim() || null),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["excerpts"] });
    },
    onError: () => message.error(t("reader.excerpt.failed")),
  });
  const remove = useMutation({
    mutationFn: () => deleteExcerpt(item.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["excerpts"] }),
  });
  const lang = i18n.language;

  return (
    <li className="excerpt-row">
      <div className="excerpt-row-head">
        <Link to={excerptReaderUrl(item)} className="excerpt-row-title">
          《{localizeHan(item.title_zh, lang)}》
        </Link>
        <span className="excerpt-row-where">
          {t("profile.excerpt_juan", { n: item.juan_num })}
          {item.line_ref ? ` · ${item.line_ref}` : ""} · {new Date(item.created_at).toLocaleDateString(lang)}
        </span>
      </div>
      <blockquote className="excerpt-row-quote">{item.quote}</blockquote>
      {editing ? (
        <div className="excerpt-row-edit">
          <Input.TextArea
            value={draft}
            maxLength={2000}
            autoSize={{ minRows: 2, maxRows: 8 }}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="excerpt-row-actions">
            <Button size="small" type="primary" loading={save.isPending} onClick={() => save.mutate()}>
              {t("profile.excerpt_save_note")}
            </Button>
            <Button size="small" onClick={() => { setEditing(false); setDraft(item.note ?? ""); }}>
              {t("profile.excerpt_cancel")}
            </Button>
          </div>
        </div>
      ) : (
        item.note && <div className="excerpt-row-note">{item.note}</div>
      )}
      {!editing && (
        <div className="excerpt-row-actions">
          <Link to={excerptReaderUrl(item)}>{t("profile.excerpt_open")}</Link>
          <Button type="link" size="small" onClick={() => setEditing(true)}>
            {item.note ? t("profile.excerpt_edit_note") : t("profile.excerpt_add_note")}
          </Button>
          <Popconfirm title={t("profile.excerpt_delete_confirm")} onConfirm={() => remove.mutate()}>
            <Button type="link" size="small" danger loading={remove.isPending}>
              {t("profile.excerpt_delete")}
            </Button>
          </Popconfirm>
        </div>
      )}
    </li>
  );
}

export default function ExcerptsList() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["excerpts", "mine", page],
    queryFn: () => listExcerpts({ page, size: PAGE_SIZE }),
  });
  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <Spin />
      </div>
    );
  }
  if (!data?.items.length) return <Empty description={t("profile.no_excerpts")} />;
  return (
    <>
      <ul className="excerpt-list">
        {data.items.map((item) => (
          <ExcerptRow key={item.id} item={item} />
        ))}
      </ul>
      {data.total > PAGE_SIZE && (
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <Pagination current={page} total={data.total} pageSize={PAGE_SIZE} showSizeChanger={false} onChange={setPage} />
        </div>
      )}
    </>
  );
}
