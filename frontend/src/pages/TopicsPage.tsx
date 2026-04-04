import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Empty } from "antd";
import { SearchOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { TOPICS, type Topic } from "../data/topics";
import "../styles/sources.css";
import "../styles/topics.css";
import { useEffect } from "react";

function TopicCard({ topic }: { topic: Topic }) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="topic-card">
      <div className="topic-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="topic-card-title-row">
          <span className="topic-card-icon">{topic.icon}</span>
          <h3 className="topic-card-name">{topic.name}</h3>
          <span className="topic-card-count">{topic.texts.length} 部经典</span>
        </div>
        <p className="topic-card-desc">{topic.description}</p>
        <span className="topic-card-toggle">
          {expanded ? "收起 \u25B2" : "展开查看 \u25BC"}
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
              onClick={() => navigate(`/search?q=${encodeURIComponent(topic.name.replace(/系经典|经论|典籍|精选/g, ""))}`)}
            >
              <SearchOutlined /> 在佛津搜索相关经典
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TopicsPage() {
  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const totalTexts = TOPICS.reduce((sum, t) => sum + t.texts.length, 0);

  return (
    <div className="sources-page">
      <Helmet>
        <title>经典专题 — 佛津 FoJin</title>
        <meta
          name="description"
          content="按主题浏览佛教经典：般若系、净土五经、法华系、禅宗典籍、律藏、阿含经、唯识经论、华严系。"
        />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">经典专题</h1>
        <p className="sources-desc">
          {TOPICS.length} 个专题 · {totalTexts} 部经典 · 按主题浏览佛教核心典籍
        </p>
      </div>

      {TOPICS.length === 0 ? (
        <Empty description="暂无专题" style={{ marginTop: 60 }} />
      ) : (
        <div className="topic-grid">
          {TOPICS.map((topic) => (
            <TopicCard key={topic.id} topic={topic} />
          ))}
        </div>
      )}

      {showTop && (
        <button
          className="sources-back-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="回到顶部"
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
