import { useState } from "react";
import { useNavigate } from "react-router";
import { Helmet } from "react-helmet-async";
import { Empty } from "antd";
import { SearchOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { getLocalizedTopics, type Topic } from "../data/topics";
import "../styles/sources.css";
import "../styles/topics.css";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

function TopicCard({ topic }: { topic: Topic }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="topic-card">
      <div className="topic-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="topic-card-title-row">
          <span className="topic-card-icon">{topic.icon}</span>
          <h3 className="topic-card-name">{topic.name}</h3>
          <span className="topic-card-count">{t("topics.card.text_count", { count: topic.texts.length })}</span>
        </div>
        <p className="topic-card-desc">{topic.description}</p>
        <span className="topic-card-toggle">
          {expanded ? t("topics.card.collapse") : t("topics.card.expand")}
        </span>
      </div>

      {expanded && (
        <div className="topic-card-body">
          <div className="topic-text-list">
            {topic.texts.map((text) => (
              <div
                key={text.title}
                className={`topic-text-item${text.textId ? " topic-text-clickable" : ""}`}
                onClick={text.textId ? () => navigate(`/texts/${text.textId}`) : undefined}
              >
                <div className="topic-text-title">{text.title}</div>
                <div className="topic-text-desc">{text.description}</div>
              </div>
            ))}
          </div>
          <div className="topic-card-actions">
            <button
              className="source-btn source-btn-search"
              onClick={() => navigate(`/search?q=${encodeURIComponent(topic.searchQuery)}`)}
            >
              <SearchOutlined /> {t("topics.card.search_related")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TopicsPage() {
  const { t, i18n } = useTranslation();
  const [showTop, setShowTop] = useState(false);
  const topics = getLocalizedTopics(i18n.language);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const totalTexts = topics.reduce((sum, t) => sum + t.texts.length, 0);

  return (
    <div className="sources-page">
      <Helmet>
        <title>{t("topics.page.title")}</title>
        <meta
          name="description"
          content={t("topics.page.description")}
        />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">{t("topics.page.heading")}</h1>
        <p className="sources-desc">
          {t("topics.page.summary", { topics: topics.length, texts: totalTexts })}
        </p>
      </div>

      {topics.length === 0 ? (
        <Empty description={t("topics.page.empty")} style={{ marginTop: 60 }} />
      ) : (
        <div className="topic-grid">
          {topics.map((topic) => (
            <TopicCard key={topic.id} topic={topic} />
          ))}
        </div>
      )}

      {showTop && (
        <button
          className="sources-back-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label={t("topics.page.back_to_top")}
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
