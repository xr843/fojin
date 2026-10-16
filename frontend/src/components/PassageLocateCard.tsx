import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AimOutlined } from "@ant-design/icons";
import type { ChatRetrieval, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";
import { localizeHan } from "../utils/hanScript";
import { locateInfoFrom, snippetOf } from "../utils/passageLocate";

/**
 * 「原文定位」卡片：用户在 /chat 贴了一段经文（约占全部提问的 19%），后端
 * passage_locator 在全藏里找到了逐字包含它的那一块 —— 这张卡片把位置直接告诉读者，
 * 一键在抽屉里打开那段原文。
 *
 * 措辞纪律（eval/paste_locate/GATE.md 修订 2/3）：语料里逐字出现 ≠ 原始出处。佛典
 * 大量引用外典，也互相引用；所以这里只说「见于」，不说「出自」，同一段文字见于多部
 * 典籍时写「另有至多 N 部」（计数只要求各小句同在一卷、不保证连续，故为上限），并始终带一行说明。
 *
 * 数据来源两处，合并成一份：
 *   - 流式中：retrieved 事件的 located（检索完成就到，模型作答前卡片就出现）
 *   - 流结束 / 刷新后：sources 里 located=true 的那一条（随消息入库）
 * 两处字段同义；sources 优先（它是入库的那份），见 utils/passageLocate。
 */

// 展示埋点去重：一条回答只记一次。key 用 retrieval（流式中）或 sources 数组（历史读回）
// 的对象身份 —— 消息 id 在流中途会被 message_id 换掉、气泡随 key 重挂载，按 id 去重会
// 重复计数；而 patchLive 只展开消息对象、retrieval 引用不变。
const shownKeys = new WeakSet<object>();

interface Props {
  sources: ChatSource[] | null | undefined;
  retrieval?: ChatRetrieval | null;
  /** 打开抽屉。quote = 命中的窗口，抽屉据此高亮那一句。 */
  onOpen: (source: ChatSource, quote?: string) => void;
}

export default function PassageLocateCard({ sources, retrieval, onOpen }: Props) {
  const { t, i18n } = useTranslation();
  const info = useMemo(() => locateInfoFrom(sources, retrieval), [sources, retrieval]);

  useEffect(() => {
    if (!info) return;
    const key: object | null | undefined = retrieval ?? sources;
    if (!key || shownKeys.has(key)) return;
    shownKeys.add(key);
    if (typeof umami !== "undefined") {
      umami.track("paste_locate_show", { text_id: info.textId, texts: info.texts, phase: retrieval ? "live" : "history" });
    }
  }, [info, retrieval, sources]);

  if (!info) return null;

  const title = localizeHan(info.title, i18n.language);
  const others = info.texts > 1 ? info.texts - 1 : 0;

  const handleOpen = () => {
    if (typeof umami !== "undefined") {
      umami.track("paste_locate_click", { text_id: info.textId, texts: info.texts });
    }
    onOpen(
      {
        text_id: info.textId as TextId,
        juan_num: info.juanNum,
        chunk_index: info.chunkIndex ?? undefined,
        chunk_text: "",
        score: 1,
        title_zh: info.title,
      },
      info.window || undefined,
    );
  };

  // 样式在 global.css（.chat-locate-*）：颜色全用主题 token，深浅色自动跟随。
  return (
    <div className="chat-locate-card" data-testid="passage-locate-card">
      <div className="chat-locate-label">
        <AimOutlined aria-hidden />
        <span>{t("chat.locate.label")}</span>
      </div>
      <div>
        {t("chat.locate.found_in", { title, n: info.juanNum })}
        {others > 0 && (
          <span data-testid="passage-locate-also">
            {t("chat.locate.sep")}
            {t("chat.locate.also_in", { n: others })}
          </span>
        )}
      </div>
      {info.window && (
        <div className="chat-locate-snippet">{t("chat.locate.snippet", { text: snippetOf(info.window) })}</div>
      )}
      <div className="chat-locate-foot">
        <button type="button" className="chat-locate-open" onClick={handleOpen} data-testid="passage-locate-open">
          {t("chat.locate.open")}
        </button>
        <span className="chat-locate-note">{t("chat.locate.note")}</span>
      </div>
    </div>
  );
}
