import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCommentaryCorpus, getCommentaryExcerpts } from "../api/client";
import { localizeHan } from "../utils/hanScript";

/**
 * 「注疏怎么讲这几句」——贴原文定位卡片里的一个展开区。
 *
 * 用户在 /chat 贴了一段论（俱舍研读者为主），这里把光记、宝疏等讲这几句的**原文
 * 片段**直接给出来，由读者自己判断。不经模型改写、不做「谁说的」判断：2026-11-02
 * 评测过让模型按体例规则判归属，没有改善还引入新错，所以只给原文。
 *
 * 只在定位到「有片段数据的论」时出现（corpus 里 excerpts=true 的那几部，判定在本地
 * 做，不为每次定位都打一次注定落空的请求）；点开才去取片段。
 */

// 展示埋点去重：同一段贴文只记一次（气泡会随 message_id 重挂载）。
const shown = new Set<string>();

/** 绝对阅读链接 → 站内路径，新标签页打开时不跨域、不丢语言参数。 */
function toPath(url: string): string {
  try {
    const u = new URL(url);
    return `${u.pathname}${u.search}${u.hash}`;
  } catch {
    return url;
  }
}

interface Props {
  /** 定位到的那部论的 fojin text_id */
  textId: number;
  /** 命中的原文窗口（≤200 字），用它去取片段 */
  quote: string;
}

export default function CommentaryExcerpts({ textId, quote }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);

  const { data: corpus } = useQuery({
    queryKey: ["commentary-corpus"],
    queryFn: getCommentaryCorpus,
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });
  const available = !!corpus?.sutras?.some((s) => s.text_id === textId && s.excerpts);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["commentary-excerpts", quote],
    queryFn: () => getCommentaryExcerpts(quote),
    enabled: open && available,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });

  useEffect(() => {
    if (!available || shown.has(quote)) return;
    shown.add(quote);
    if (typeof umami !== "undefined") umami.track("commentary_excerpt_show", { text_id: textId });
  }, [available, quote, textId]);

  if (!available || !quote) return null;

  const toggle = () => {
    if (!open && typeof umami !== "undefined") umami.track("commentary_excerpt_open", { text_id: textId });
    setOpen((v) => !v);
  };

  const items = data?.excerpts ?? [];

  return (
    <div className="chat-comm" data-testid="commentary-excerpts">
      <button
        type="button"
        className="chat-locate-open"
        aria-expanded={open}
        onClick={toggle}
        data-testid="commentary-excerpts-toggle"
      >
        {open ? t("chat.locate.comm_hide") : t("chat.locate.comm_button")}
      </button>
      {open && (
        <div className="chat-comm-body">
          {isLoading ? (
            <div className="chat-comm-state">{t("chat.locate.comm_loading")}</div>
          ) : isError ? (
            <div className="chat-comm-state">{t("chat.locate.comm_failed")}</div>
          ) : items.length === 0 ? (
            <div className="chat-comm-state">{t("chat.locate.comm_none")}</div>
          ) : (
            <>
              {items.map((e) => (
                <section key={e.work} className="chat-comm-item">
                  <div className="chat-comm-head">
                    <strong>《{localizeHan(e.title ?? e.work, i18n.language)}》</strong>
                    <span className="chat-comm-ref">{e.line_from}–{e.line_to}</span>
                    {e.reader_url && (
                      <a
                        className="chat-comm-read"
                        href={toPath(e.reader_url)}
                        target="_blank"
                        rel="noopener"
                        onClick={() => {
                          if (typeof umami !== "undefined") umami.track("commentary_excerpt_read", { work: e.work });
                        }}
                      >
                        {t("chat.locate.comm_open_reader")}
                      </a>
                    )}
                  </div>
                  <p className="chat-comm-text">
                    {e.text}
                    {e.truncated && <span className="chat-comm-more">{t("chat.locate.comm_more")}</span>}
                  </p>
                </section>
              ))}
              <div className="chat-locate-note">{t("chat.locate.comm_note")}</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
