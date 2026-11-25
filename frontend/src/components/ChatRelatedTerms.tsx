import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { getRelatedTerms } from "../api/client";
import { localizeHan } from "../utils/hanScript";

/**
 * 问答回答下方的「相关词条」（借鉴如是佛典 AI 问答，2026-11-25）：读者问题里的名相，在中文释义类
 * 辞典里的词条，点开去辞典页看全文。
 *
 * 和回答的引文是两回事，界面上必须分得开：每张卡标「词条」与辞典名，区块标题下注明「辞典释义，
 * 不是经文出处」；回答里的经文出处仍在上面的「参考经文」与引文面板里。数据单独请求，不经过
 * 问答的生成与引文核验，所以不影响回答与引文。没有合适词条就整块不显示。
 */
export default function ChatRelatedTerms({ question }: { question: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { data } = useQuery({
    queryKey: ["chat-related-terms", question],
    queryFn: () => getRelatedTerms(question),
    enabled: question.trim().length > 0,
    staleTime: Infinity,
    retry: false,
  });
  if (!data || data.items.length === 0) return null;

  return (
    <section className="chat-related-terms" aria-label={t("chat.related_terms.title")}>
      <div className="chat-related-terms-head">
        <span className="chat-related-terms-title">{t("chat.related_terms.title")}</span>
        <span className="chat-related-terms-note">{t("chat.related_terms.note")}</span>
      </div>
      <div className="chat-related-terms-grid">
        {data.items.map((c) => (
          <Link
            key={c.id}
            className="chat-related-term"
            to={`/dictionary?q=${encodeURIComponent(c.headword)}&source=${encodeURIComponent(c.source_code)}`}
            data-umami-event="chat_related_term"
            data-umami-event-source={c.source_code}
          >
            <span className="chat-related-term-top">
              <span className="chat-related-term-tag">{t("chat.related_terms.tag")}</span>
              <span className="chat-related-term-head">{localizeHan(c.headword, lang)}</span>
            </span>
            <span className="chat-related-term-excerpt">{localizeHan(c.excerpt, lang)}</span>
            <span className="chat-related-term-source">{localizeHan(c.source_name, lang)}</span>
          </Link>
        ))}
      </div>
      {/* 卡片最多 4 张、只取中文释义辞典；想看某个词在全部辞典里的释义，一点就到辞典页 */}
      <div className="chat-related-terms-more">
        {data.headwords
          .filter((h) => h.dict_count > data.items.filter((c) => c.headword === h.headword).length)
          .map((h) => (
            <Link
              key={h.headword}
              to={`/dictionary?q=${encodeURIComponent(h.headword)}`}
              data-umami-event="chat_related_term_all"
            >
              {t("chat.related_terms.all", { term: localizeHan(h.headword, lang), n: h.dict_count })}
            </Link>
          ))}
      </div>
    </section>
  );
}
