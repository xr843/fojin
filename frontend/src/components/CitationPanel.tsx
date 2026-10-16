import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Button, Tooltip } from "antd";
import { BookOutlined, CheckCircleFilled, CloseOutlined } from "@ant-design/icons";
import type { ChatMessageItem, ChatSource } from "../api/client";
import { distinctSourceFascicles, extractAnswerCitations, type AnswerCitation } from "../utils/answerCitations";
import { localizeHan } from "../utils/hanScript";
import { quoteCheckDetail } from "../utils/trustDetail";
import { trustStatusColor, trustStatusLabelKey } from "../utils/trustDisplay";

interface Props {
  /** 当前选中的回答；null = 还没有回答。 */
  message: ChatMessageItem | null;
  isLatest: boolean;
  /** 选中的是正在生成的那条：引文要等流结束（sources 到达）才列得出来。 */
  pending: boolean;
  onOpenCitation: (c: AnswerCitation) => void;
  onOpenSource: (s: ChatSource) => void;
  /** 右上角 ×：关掉整列（与原文对照视图里 CitationDrawer 的 × 同语义）。 */
  onClose: () => void;
  onShowLatest: () => void;
}

/**
 * 引文列表视图：一条回答里的每一处 【《经名》第N卷】，点开即原文对照。
 *
 * 核验状态的诚实边界 —— 只显示系统真实算过的东西：
 *  - 顶部一行是整篇聚合的 trust_status（与答案下方那行同源同文案）；
 *  - 逐条「已逐字核验」只在后端 trust_status.checked_quotes 里列出了**这一句**时才出现
 *    （那张表就是 quote_checked_count 数的那几句，失败的引文早被降级成转述、不会在表里）；
 *  - 其余条目不打任何标记 —— 不打绿勾，也不打「未核验」，因为前端不知道。
 */
export default function CitationPanel({
  message, isLatest, pending, onOpenCitation, onOpenSource, onClose, onShowLatest,
}: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const citations = useMemo(
    () =>
      message
        ? extractAnswerCitations(message.content, message.sources, lang, message.trust_status?.checked_quotes)
        : [],
    [message, lang],
  );
  const sources = useMemo(() => distinctSourceFascicles(message?.sources), [message]);

  const trust = message?.trust_status;
  const trustKey = trustStatusLabelKey(trust);
  const quoteDetail = quoteCheckDetail(trust);

  return (
    <>
      <div className="chat-citation-panel-header">
        <span className="chat-citation-panel-title">
          <BookOutlined /> {t("chat.cpanel.title")}
        </span>
        <Tooltip title={t("chat.cpanel.close")}>
          <Button
            type="text"
            size="small"
            className="chat-cpanel-close"
            icon={<CloseOutlined />}
            aria-label={t("chat.cpanel.close")}
            onClick={onClose}
          />
        </Tooltip>
      </div>
      <div className="chat-cpanel-body">
        {!isLatest && (
          <div className="chat-cpanel-scope">
            <span>{t("chat.cpanel.viewing_earlier")}</span>
            <button type="button" className="chat-cpanel-link" onClick={onShowLatest}>
              {t("chat.cpanel.show_latest")}
            </button>
          </div>
        )}
        {pending ? (
          <p className="chat-cpanel-empty">{t("chat.cpanel.pending")}</p>
        ) : (
          <>
            {trustKey && (
              <div className="chat-cpanel-trust" style={{ color: trustStatusColor(trust) }}>
                {t(trustKey)}
                {quoteDetail && (
                  <span className="chat-cpanel-trust-detail">
                    {" · "}
                    {quoteDetail.key === "chat.trust.quotes_checked"
                      ? t(quoteDetail.key, { n: quoteDetail.count })
                      : t(quoteDetail.key)}
                  </span>
                )}
              </div>
            )}
            <h3 className="chat-cpanel-heading">{t("chat.cpanel.citations_heading", { n: citations.length })}</h3>
            {citations.length === 0 ? (
              <p className="chat-cpanel-empty">{t("chat.cpanel.no_citations")}</p>
            ) : (
              <ol className="chat-cpanel-list">
                {citations.map((c) => (
                  <li key={c.key}>
                    <button type="button" className="chat-cpanel-item" onClick={() => onOpenCitation(c)}>
                      <span className="chat-cpanel-item-title">
                        {t("reader.citation.title_with_juan", {
                          title: localizeHan(c.target.titleZh, lang),
                          n: c.target.juanNum,
                        })}
                      </span>
                      {c.target.quote && (
                        <span className="chat-cpanel-item-quote">
                          {t("chat.cpanel.quote", { q: c.target.quote })}
                        </span>
                      )}
                      {c.verbatimChecked && (
                        <span className="chat-cpanel-badge">
                          <CheckCircleFilled /> {t("chat.cpanel.verbatim_checked")}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {sources.length > 0 && (
              <>
                <h3 className="chat-cpanel-heading">{t("chat.reference_sources")}</h3>
                <div className="chat-cpanel-sources">
                  {sources.map((s) => (
                    <button
                      key={`${s.text_id}:${s.juan_num}`}
                      type="button"
                      className="chat-cpanel-source"
                      onClick={() => onOpenSource(s)}
                    >
                      {t("reader.citation.title_with_juan", {
                        title: localizeHan(s.title_zh ?? "", lang),
                        n: s.juan_num,
                      })}
                    </button>
                  ))}
                </div>
              </>
            )}
            {citations.some((c) => c.verbatimChecked) && (
              <p className="chat-cpanel-note">{t("chat.cpanel.badge_note")}</p>
            )}
          </>
        )}
      </div>
    </>
  );
}
