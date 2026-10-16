import { useMemo } from "react";
import { Button, Dropdown, Tooltip, message } from "antd";
import type { MenuProps } from "antd";
import {
  ClockCircleOutlined,
  CopyOutlined,
  DislikeFilled,
  DislikeOutlined,
  LikeFilled,
  LikeOutlined,
  RedoOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { ChatMessageItem } from "../api/client";
import type { ChatModelOption } from "../api/chatModels";
import { formatResponseSeconds } from "../utils/responseTiming";

export interface MessageActionsProps {
  m: ChatMessageItem;
  /** 复制的文本：助手回答是去掉 [追问] 行之后的正文，用户消息是原文。 */
  copyText: string;
  /** 是不是对话里的最后一条：只有它能重新生成，它的操作栏也常显。 */
  isLast: boolean;
  /** 失败哨兵：只给重试，不给分享/反馈/重新生成，也不显示耗时。 */
  failed: boolean;
  sending: boolean;
  loggedIn: boolean;
  /** 「换模型重答」可选的模型；少于两个可用时不显示该按钮。由页面取一次传下来。 */
  models?: ChatModelOption[];
  onShare: (m: ChatMessageItem) => void;
  onRetry: (m: ChatMessageItem) => void;
  /** modelId 有值 = 只这一次用该模型重答；不改输入框里选的默认模型。 */
  onRegenerate: (m: ChatMessageItem, modelId?: string) => void;
  onFeedback: (m: ChatMessageItem, dir: "up" | "down") => void;
}


/**
 * 每条消息下方的操作栏。
 *
 * 显隐交给 CSS（global.css .chat-msg-actions）：桌面悬停整行才显示，最后一条助手
 * 回答常显（is-pinned），触屏设备（hover: none）一律常显，键盘聚焦进来时也显示。
 * 用 opacity 而不是不渲染：不渲染会让悬停时整行高度跳动，而且读屏与键盘用户要能
 * 一直够得到这些按钮。
 */
export default function MessageActions({
  m, copyText, isLast, failed, sending, loggedIn, models, onShare, onRetry, onRegenerate, onFeedback,
}: MessageActionsProps) {
  const { t } = useTranslation();
  const isAssistant = m.role === "assistant";
  const canRegenerate = isAssistant && isLast && !failed;

  const usable = useMemo(() => (models ?? []).filter((x) => x.available), [models]);

  const menu: MenuProps = useMemo(() => ({
    items: [{
      type: "group" as const,
      label: t("chat.regenerate_with_model"),
      children: usable.map((x) => ({ key: x.id, label: x.label })),
    }],
    onClick: ({ key }) => onRegenerate(m, key),
  }), [usable, t, onRegenerate, m]);

  const pinned = isAssistant && isLast;

  return (
    <div
      className={`chat-msg-actions${pinned ? " is-pinned" : ""}`}
      role="toolbar"
      aria-label={t("chat.message_actions")}
    >
      {/* 响应耗时。只对本次会话生成的回答显示：totalMs 的有无就是那个判据，
          历史消息读回来时为空。失败的回答不显示。 */}
      {isAssistant && m.totalMs != null && !failed && (
        <Tooltip title={t("chat.timing.tooltip")}>
          <span className="chat-msg-timing">
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            {m.firstTokenMs != null && (
              <>{t("chat.timing.first_token", { n: formatResponseSeconds(m.firstTokenMs) })}
                {" · "}</>
            )}
            {t("chat.timing.total", { n: formatResponseSeconds(m.totalMs) })}
          </span>
        </Tooltip>
      )}
      <Tooltip title={t("chat.copy")}>
        <Button
          type="text" size="small" icon={<CopyOutlined />}
          aria-label={t("chat.copy")}
          onClick={() => {
            navigator.clipboard.writeText(copyText);
            message.success(t("chat.copied"));
            // Behavioural quality signal: copying an answer = found it useful.
            if (isAssistant && typeof umami !== "undefined") umami.track("chat_copy");
          }}
        />
      </Tooltip>
      {isAssistant && !failed && (
        <Tooltip title={t("chat.share_card_tooltip")}>
          <Button
            type="text" size="small" icon={<ShareAltOutlined />}
            aria-label={t("chat.share_card_tooltip")}
            onClick={() => onShare(m)}
          />
        </Tooltip>
      )}
      {/* 反馈要等真实的 chat_messages.id 换掉 Date.now() 占位符（≥ ~1.7e12）之后才给：
          流式但尚未落库的窗口里点下去会 PUT 到一个不存在的 id、静默 404。 */}
      {isAssistant && loggedIn && m.id < 1e12 && (
        <>
          <Tooltip title={t("chat.feedback_helpful")}>
            <Button
              type="text" size="small"
              icon={m.feedback === "up" ? <LikeFilled /> : <LikeOutlined />}
              aria-label={t("chat.feedback_helpful")}
              aria-pressed={m.feedback === "up"}
              className={m.feedback === "up" ? "is-active-up" : undefined}
              onClick={() => onFeedback(m, "up")}
            />
          </Tooltip>
          <Tooltip title={t("chat.feedback_not_helpful")}>
            <Button
              type="text" size="small"
              icon={m.feedback === "down" ? <DislikeFilled /> : <DislikeOutlined />}
              aria-label={t("chat.feedback_not_helpful")}
              aria-pressed={m.feedback === "down"}
              className={m.feedback === "down" ? "is-active-down" : undefined}
              onClick={() => onFeedback(m, "down")}
            />
          </Tooltip>
        </>
      )}
      {isAssistant && failed && (
        <Tooltip title={t("chat.retry")}>
          <Button
            type="text" size="small" icon={<ReloadOutlined />}
            aria-label={t("chat.retry")}
            onClick={() => onRetry(m)}
          />
        </Tooltip>
      )}
      {/* 「重新生成」只给最后一条成功的回答。图标用 Redo 而不是 Reload：Reload
          是失败重试的图标，测试按 .anticon-reload 找它，两者不能撞。 */}
      {canRegenerate && (
        <Tooltip title={t("chat.regenerate")}>
          <Button
            type="text" size="small" icon={<RedoOutlined />}
            aria-label={t("chat.regenerate")}
            disabled={sending}
            onClick={() => onRegenerate(m)}
          />
        </Tooltip>
      )}
      {/* 换模型重答：只有一个可用模型时没有「别的」可换，不显示。 */}
      {canRegenerate && usable.length > 1 && (
        <Dropdown menu={menu} trigger={["click"]} disabled={sending} placement="bottomLeft">
          <Tooltip title={t("chat.regenerate_with_model")}>
            <Button
              type="text" size="small" icon={<SwapOutlined />}
              aria-label={t("chat.regenerate_with_model")}
              aria-haspopup="menu"
              disabled={sending}
              className="chat-msg-switch-model"
            />
          </Tooltip>
        </Dropdown>
      )}
    </div>
  );
}
