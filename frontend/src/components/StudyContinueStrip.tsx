import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getStudyMemory } from "../api/client";
import { localizeHan } from "../utils/hanScript";
import "../styles/study-memory.css";

const MAX_CHIPS = 3;

/**
 * 新对话空态上的「接着研读」：最近读的经卷、最近问过的主题，一点就接上。
 * 只给登录读者渲染（游客没有记忆）。外层容器先占住一行高度，数据回来不顶动居中的输入框
 * （空态整组靠上下撑高块居中，后出现的内容会让输入框跳，见 ChatPage 卡片占位的注释）。
 */
export default function StudyContinueStrip() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { data } = useQuery({ queryKey: ["studyMemory"], queryFn: getStudyMemory, staleTime: 60_000 });

  const reading = data?.enabled ? data.reading.slice(0, 2) : [];
  const topics = data?.enabled ? data.topics.slice(0, MAX_CHIPS - reading.length) : [];
  const show = reading.length + topics.length > 0;

  return (
    <div className="study-continue" data-testid="study-continue">
      {show && (
        <>
          <span className="study-continue-label">{t("study_memory.continue")}</span>
          {reading.map((r) => (
            <Link
              key={`r${r.text_id}`}
              className="study-continue-chip"
              to={`/texts/${r.text_id}/read?juan=${r.juan_num}`}
              data-umami-event="study_memory_continue"
              data-umami-event-kind="reading"
            >
              《{localizeHan(r.title_zh, lang)}》{t("study_memory.juan", { n: r.juan_num })}
            </Link>
          ))}
          {topics.map((tp) => (
            <Link
              key={`t${tp.session_id}`}
              className="study-continue-chip"
              to={`/chat?s=${tp.session_id}`}
              data-umami-event="study_memory_continue"
              data-umami-event-kind="topic"
            >
              {tp.title}
            </Link>
          ))}
          <Link className="study-continue-manage" to="/profile?tab=memory">
            {t("study_memory.manage")}
          </Link>
        </>
      )}
    </div>
  );
}
