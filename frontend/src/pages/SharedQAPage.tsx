import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Spin, Button, Result } from "antd";
import { RobotOutlined, MessageOutlined, ShareAltOutlined } from "@ant-design/icons";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { getSharedQA, type SharedQA } from "../api/client";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export default function SharedQAPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SharedQA | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getSharedQA(id)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(() => setError("not_found"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <Result
        status="404"
        title="未找到此分享"
        subTitle="链接可能已失效或被删除"
        extra={
          <Button type="primary" onClick={() => navigate("/chat")}>
            去 AI 问答
          </Button>
        }
      />
    );
  }

  const previewText = data.answer.slice(0, 140).replace(/\n/g, " ");
  const ogTitle = `${data.question.slice(0, 60)} — 佛津 AI 佛典问答`;

  return (
    <div style={{ maxWidth: 780, margin: "0 auto", padding: "32px 20px 80px" }}>
      <Helmet>
        <title>{ogTitle}</title>
        <meta name="description" content={previewText} />
        <meta property="og:title" content={ogTitle} />
        <meta property="og:description" content={previewText} />
        <meta property="og:type" content="article" />
        <meta property="og:url" content={`https://fojin.app/share/qa/${data.id}`} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={ogTitle} />
        <meta name="twitter:description" content={previewText} />
      </Helmet>

      <div style={{ marginBottom: 28 }}>
        <Link
          to="/"
          style={{
            fontSize: 24,
            fontWeight: 700,
            color: "var(--fj-accent, #8b2500)",
            letterSpacing: 3,
            textDecoration: "none",
            fontFamily: '"Noto Serif SC", serif',
          }}
        >
          佛津 · FoJin
        </Link>
        <div style={{ fontSize: 12, color: "var(--fj-ink-muted, #9a8e7a)", marginTop: 4 }}>
          AI 佛典问答 · 引据原典 · {formatDate(data.created_at)}
        </div>
      </div>

      <div style={{ marginBottom: 32 }}>
        <div
          style={{
            display: "inline-block",
            fontSize: 12,
            color: "#fff",
            background: "var(--fj-accent, #8b2500)",
            padding: "3px 12px",
            marginBottom: 12,
            letterSpacing: 2,
          }}
        >
          问
        </div>
        <h1
          style={{
            fontSize: 22,
            lineHeight: 1.6,
            margin: 0,
            color: "var(--fj-ink, #2b2318)",
            borderLeft: "3px solid var(--fj-accent, #8b2500)",
            paddingLeft: 16,
            fontFamily: '"Noto Serif SC", serif',
          }}
        >
          {data.question}
        </h1>
      </div>

      <div style={{ marginBottom: 32 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
            color: "#fff",
            background: "var(--fj-gold, #b08d57)",
            padding: "3px 12px",
            marginBottom: 12,
            letterSpacing: 2,
          }}
        >
          <RobotOutlined /> 答
        </div>
        <div
          className="chat-markdown"
          style={{
            fontSize: 16,
            lineHeight: 1.9,
            color: "var(--fj-ink-light, #5c4f3d)",
            fontFamily: '"Noto Serif SC", serif',
          }}
        >
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{data.answer}</Markdown>
        </div>
      </div>

      {data.sources && data.sources.length > 0 && (
        <div
          style={{
            background: "var(--fj-bg-alt, #f0ebe2)",
            border: "1px solid var(--fj-border, #d9d0c1)",
            padding: "16px 20px",
            marginBottom: 32,
          }}
        >
          <div
            style={{
              fontSize: 12,
              color: "var(--fj-ink-muted, #9a8e7a)",
              marginBottom: 10,
              letterSpacing: 2,
            }}
          >
            引据原典
          </div>
          {data.sources
            .filter((s) => s.title_zh)
            .slice(0, 5)
            .map((s, i) => (
              <div
                key={i}
                style={{
                  fontSize: 14,
                  color: "var(--fj-ink-light, #5c4f3d)",
                  lineHeight: 1.8,
                  marginBottom: 4,
                }}
              >
                <span style={{ color: "var(--fj-gold, #b08d57)", marginRight: 6 }}>▸</span>
                {s.text_id > 0 ? (
                  <Link
                    to={`/texts/${s.text_id}/read?juan=${s.juan_num}`}
                    style={{ color: "var(--fj-ink-light, #5c4f3d)" }}
                  >
                    《{s.title_zh}》{s.juan_num > 0 ? `第${s.juan_num}卷` : ""}
                  </Link>
                ) : (
                  <span>
                    《{s.title_zh}》{s.juan_num > 0 ? `第${s.juan_num}卷` : ""}
                  </span>
                )}
              </div>
            ))}
        </div>
      )}

      <div
        style={{
          background: "var(--fj-card-bg, rgba(255,255,255,0.6))",
          border: "1px solid var(--fj-border, #d9d0c1)",
          padding: "24px 28px",
          textAlign: "center",
          marginTop: 40,
        }}
      >
        <div
          style={{
            fontSize: 16,
            color: "var(--fj-ink, #2b2318)",
            marginBottom: 14,
            fontWeight: 600,
          }}
        >
          想问自己的佛学问题？
        </div>
        <div style={{ fontSize: 13, color: "var(--fj-ink-muted, #9a8e7a)", marginBottom: 18 }}>
          佛津 AI 佛典问答 — 每一个回答都引据原典,汇聚 CBETA · SuttaCentral 等 600+ 数据源
        </div>
        <Button
          type="primary"
          size="large"
          icon={<MessageOutlined />}
          onClick={() => navigate("/chat")}
          style={{
            background: "var(--fj-accent, #8b2500)",
            borderColor: "var(--fj-accent, #8b2500)",
          }}
        >
          打开 AI 问答
        </Button>
      </div>

      <div
        style={{
          marginTop: 24,
          textAlign: "center",
          fontSize: 12,
          color: "var(--fj-ink-muted, #9a8e7a)",
        }}
      >
        <ShareAltOutlined /> 已被浏览 {data.view_count} 次
      </div>
    </div>
  );
}
