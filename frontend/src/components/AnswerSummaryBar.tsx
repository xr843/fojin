import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DownOutlined, RightOutlined } from "@ant-design/icons";
import type { ChatMessageItem } from "../api/client";
import ReasoningExcerpt from "./ReasoningExcerpt";
import { distinctSourceTextCount } from "../utils/answerCitations";
import { formatResponseSeconds } from "../utils/responseTiming";
import "../styles/chat-citation-panel.css";

/**
 * 回答上方的一行摘要：「检索 8 部经典 · 核验 7 条引文 · 用时 26 秒」，有思考文本时
 * 可展开看思考过程。每一段都只在数据真实存在时出现：
 *  - 经典部数 = 本条回答 sources 里不同 text_id 的个数（sources 随消息持久化，刷新后仍在）；
 *  - 核验条数 = trust_status.quote_checked_count，>0 才显示（0 由答案下方信任行负责说明）；
 *  - 用时 = totalMs，刻意不持久化 —— 刷新后的历史回答没有这一段，不显示 0；
 *  - 思考过程 = reasoningFinal，同样只在本次会话生成的回答上有。
 * 三段都没有、也没有思考文本时整条不渲染。
 */
export default function AnswerSummaryBar({ m, isStreaming }: { m: ChatMessageItem; isStreaming: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (isStreaming) return null;

  const parts: string[] = [];
  const texts = distinctSourceTextCount(m.sources);
  if (texts > 0) parts.push(t("chat.summary.texts", { n: texts }));
  const checked = m.trust_status?.quote_checked_count;
  if (checked != null && checked > 0) parts.push(t("chat.summary.quotes_checked", { n: checked }));
  if (m.totalMs != null) parts.push(t("chat.summary.elapsed", { n: formatResponseSeconds(m.totalMs) }));
  const reasoning = m.reasoningFinal?.trim() ? m.reasoningFinal : null;

  if (parts.length === 0 && !reasoning) return null;
  const line = parts.join(" · ");

  if (!reasoning) {
    return (
      <div className="chat-answer-summary">
        <span className="chat-answer-summary-line">{line}</span>
      </div>
    );
  }

  return (
    <div className="chat-answer-summary">
      <button
        type="button"
        className="chat-answer-summary-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <DownOutlined /> : <RightOutlined />}
        <span className="chat-answer-summary-line">{line || t("chat.summary.reasoning_only")}</span>
        <span className="chat-answer-summary-hint">
          {open ? t("chat.summary.hide_reasoning") : t("chat.summary.show_reasoning")}
        </span>
      </button>
      {open && <ReasoningExcerpt text={reasoning} settled />}
    </div>
  );
}
