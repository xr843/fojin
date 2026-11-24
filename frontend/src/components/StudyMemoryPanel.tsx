import { useState } from "react";
import { Link } from "react-router";
import { Button, Empty, Input, Spin, Switch, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getStudyMemory, saveStudyMemory } from "../api/client";
import { localizeHan } from "../utils/hanScript";
import "../styles/study-memory.css";

/**
 * 个人中心「研读记忆」：小津记得什么（与交给模型的是同一份）、读者自己写的回答偏好、总开关。
 * 透明可控是前提——记忆只用来理解提问、调整讲解，不会被当作经文引用（见后端 services/study_memory.py）。
 */
export default function StudyMemoryPanel() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({ queryKey: ["studyMemory"], queryFn: getStudyMemory });
  // null = 没改过，显示已存的偏好；改过才是草稿（不用 effect 同步服务器值）
  const [draft, setDraft] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: { enabled: boolean; notes: string | null }) => saveStudyMemory(body),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["studyMemory"], fresh);
      setDraft(null);
      message.success(t("study_memory.saved"));
    },
    onError: () => message.error(t("study_memory.save_failed")),
  });

  if (isLoading) return <Spin />;
  if (isError || !data) return <Empty description={t("study_memory.load_failed")} />;

  const notes = draft ?? data.notes ?? "";
  const cleanNotes = notes.trim() || null;
  const dirty = cleanNotes !== (data.notes ?? null);
  const nothing = data.reading.length === 0 && data.topics.length === 0 && data.excerpts.length === 0;

  return (
    <div className="study-memory">
      <p className="study-memory-intro">
        {t(data.used_in_answers ? "study_memory.intro" : "study_memory.intro_records_only")}
      </p>

      <div className="study-memory-switch">
        <Switch
          checked={data.enabled}
          loading={save.isPending}
          onChange={(on) => save.mutate({ enabled: on, notes: data.notes })}
          aria-label={t("study_memory.switch")}
        />
        <span>
          {data.enabled
            ? t(data.used_in_answers ? "study_memory.on" : "study_memory.on_records_only")
            : t(data.used_in_answers ? "study_memory.off" : "study_memory.off_records_only")}
        </span>
      </div>

      {/* 偏好只有在记忆进入作答时才有用：没进之前不收，免得读者以为写了就生效 */}
      {data.used_in_answers && (
        <section className="study-memory-section">
          <h4>{t("study_memory.notes_title")}</h4>
          <p className="study-memory-hint">{t("study_memory.notes_hint")}</p>
          <Input.TextArea
            value={notes}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={data.max_notes_chars}
            showCount
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder={t("study_memory.notes_placeholder")}
            aria-label={t("study_memory.notes_title")}
          />
          <Button
            type="primary"
            size="small"
            style={{ marginTop: 8 }}
            disabled={!dirty}
            loading={save.isPending}
            data-umami-event="study_memory_save"
            onClick={() => save.mutate({ enabled: data.enabled, notes: cleanNotes })}
          >
            {t("study_memory.save")}
          </Button>
        </section>
      )}

      {data.enabled && (
        <section className="study-memory-section">
          <h4>{t("study_memory.remembers_title")}</h4>
          {nothing ? (
            <p className="study-memory-hint">{t("study_memory.empty")}</p>
          ) : (
            <dl className="study-memory-list">
              {data.reading.length > 0 && (
                <>
                  <dt>{t("study_memory.reading")}</dt>
                  {data.reading.map((r) => (
                    <dd key={`r${r.text_id}`}>
                      <Link to={`/texts/${r.text_id}/read?juan=${r.juan_num}`}>
                        《{localizeHan(r.title_zh, lang)}》{t("study_memory.juan", { n: r.juan_num })}
                      </Link>
                    </dd>
                  ))}
                </>
              )}
              {data.topics.length > 0 && (
                <>
                  <dt>{t("study_memory.topics")}</dt>
                  {data.topics.map((tp) => (
                    <dd key={`t${tp.session_id}`}>
                      <Link to={`/chat?s=${tp.session_id}`}>{tp.title}</Link>
                    </dd>
                  ))}
                </>
              )}
              {data.excerpts.length > 0 && (
                <>
                  <dt>{t("study_memory.excerpts")}</dt>
                  {data.excerpts.map((e, i) => (
                    <dd key={`e${i}`}>
                      《{localizeHan(e.title_zh, lang)}》「{localizeHan(e.quote, lang)}」
                    </dd>
                  ))}
                </>
              )}
            </dl>
          )}
          <p className="study-memory-hint">{t("study_memory.window_note")}</p>
        </section>
      )}
    </div>
  );
}
