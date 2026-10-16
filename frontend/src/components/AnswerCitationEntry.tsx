import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { BookOutlined, RightOutlined } from "@ant-design/icons";
import type { ChatMessageItem } from "../api/client";
import { citedFascicleCount } from "../utils/answerCitations";
import { quoteCheckDetail } from "../utils/trustDetail";
import { trustStatusColor, trustStatusLabelKey } from "../utils/trustDisplay";
import "../styles/chat-citation-panel.css";

interface Props {
  m: ChatMessageItem;
  isStreaming: boolean;
  /** 打开右侧引文面板并显示**这条**回答的引文。 */
  onOpen: (m: ChatMessageItem) => void;
}

/**
 * 回答下方的一行：引文面板入口胶囊 + 聚合信任状态。
 *
 * 胶囊上的数字只来自现有数据，口径：
 *  - 「N 处出处」= 正文里显式【《经名》第N卷】按（经, 卷）去重后的个数（citedFascicleCount）。
 *    不用面板行数：面板一行是（出处, 引句）对，且会为「核验过但没挂在内联链接上」的引句补行，
 *    拿它当「引文数」会把同一处出处数多次。
 *  - 「已逐字核验 M 条」= trust_status.quote_checked_count（逐句计，单位是引句不是出处，
 *    所以 1 处出处下核验 3 条是正常的，两个数字刻意用不同的量词）。
 *  - 没有显式引文、只有检索到的参考经文时不出胶囊：面板内容与下方「参考经文」芯片行重复。
 * 流式中不显示：sources / trust_status 要等流结束才到。
 *
 * 信任行：胶囊出现后，原来那行「引用已校验 · 已逐字核验 N 条引文」里的核验数由胶囊承担，
 * 不再重复；信任状态本身（引用已校验 / 部分引文未逐字核实 …）胶囊不表达，仍留在胶囊右侧。
 * 没有胶囊（无引文也无参考经文）时信任行原样显示。
 */
export default function AnswerCitationEntry({ m, isStreaming, onOpen }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const fascicles = useMemo(
    () => (isStreaming ? 0 : citedFascicleCount(m.content, m.sources, lang)),
    [isStreaming, m.content, m.sources, lang],
  );
  if (isStreaming) return null;

  const trust = m.trust_status;
  const trustKey = trustStatusLabelKey(trust);
  const detail = quoteCheckDetail(trust);
  const checked = trust?.quote_checked_count ?? 0;

  let label: string | null = null;
  let checkedInChip = false;
  if (fascicles > 0) {
    label = t("chat.cpanel.entry_citations", { n: fascicles });
    if (checked > 0) {
      label += ` · ${t("chat.cpanel.entry_checked", { n: checked })}`;
      checkedInChip = true;
    }
  }
  // 只有参考经文、没有显式引文时不出胶囊：面板此时只会列出参考经文，与回答下方已有的
  // 「参考经文」芯片行一字不差，胶囊只是重复入口（芯片本身可点开原文）。

  const trustLine = trustKey ? (
    <span className="chat-answer-trust-label" style={{ color: trustStatusColor(trust) }}>
      {t(trustKey)}
      {detail && !(checkedInChip && detail.key === "chat.trust.quotes_checked") && (
        <span style={{ color: "var(--fj-ink-muted)" }}>
          {" · "}
          {detail.key === "chat.trust.quotes_checked" ? t(detail.key, { n: detail.count }) : t(detail.key)}
        </span>
      )}
    </span>
  ) : null;

  if (!label) {
    return trustLine ? <div className="chat-answer-trust">{trustLine}</div> : null;
  }

  return (
    <div className="chat-answer-trust chat-cpanel-entry-row">
      <button
        type="button"
        className="chat-cpanel-entry"
        title={t("chat.cpanel.entry_hint")}
        onClick={() => onOpen(m)}
      >
        <BookOutlined />
        <span className="chat-cpanel-entry-label">{label}</span>
        <RightOutlined className="chat-cpanel-entry-arrow" />
      </button>
      {trustLine}
    </div>
  );
}
