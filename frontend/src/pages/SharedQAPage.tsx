import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Spin, Button, Result } from "antd";
import { RobotOutlined, MessageOutlined, ShareAltOutlined } from "@ant-design/icons";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { useTranslation } from "react-i18next";
import { getSharedQA, type SharedQA } from "../api/client";

function dateLocale(language: string): string {
  if (language.startsWith("zh-Hant")) return "zh-Hant";
  if (language.startsWith("en")) return "en-US";
  return "zh-CN";
}

function formatDate(iso: string, language: string): string {
  return new Intl.DateTimeFormat(dateLocale(language), {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(iso));
}

export default function SharedQAPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<SharedQA | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [prevId, setPrevId] = useState(id);
  if (prevId !== id) {
    setPrevId(id);
    setLoading(true);
  }

  useEffect(() => {
    if (!id) return;
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
        title={t("sharedQA.notFoundTitle")}
        subTitle={t("sharedQA.notFoundSubtitle")}
        extra={
          <Button type="primary" onClick={() => navigate("/chat")}>
            {t("sharedQA.goToChat")}
          </Button>
        }
      />
    );
  }

  const previewText = data.answer.slice(0, 140).replace(/\n/g, " ");
  const ogTitle = t("sharedQA.ogTitle", { question: data.question.slice(0, 60) });

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
          {t("shareCard.brand")}
        </Link>
        <div style={{ fontSize: 12, color: "var(--fj-ink-muted, #9a8e7a)", marginTop: 4 }}>
          {t("shareCard.subtitle")} · {formatDate(data.created_at, i18n.language)}
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
          {t("shareCard.questionLabel")}
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
          <RobotOutlined /> {t("shareCard.answerLabel")}
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
            {t("shareCard.sourcesTitle")}
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
                    《{s.title_zh}》{s.juan_num > 0 ? t("shareCard.fascicle", { n: s.juan_num }) : ""}
                  </Link>
                ) : (
                  <span>
                    《{s.title_zh}》{s.juan_num > 0 ? t("shareCard.fascicle", { n: s.juan_num }) : ""}
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
          {t("sharedQA.askOwnQuestion")}
        </div>
        <div style={{ fontSize: 13, color: "var(--fj-ink-muted, #9a8e7a)", marginBottom: 18 }}>
          {t("sharedQA.ctaDescription")}
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
          {t("sharedQA.openChat")}
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
        <ShareAltOutlined /> {t("sharedQA.viewed", { count: data.view_count })}
      </div>
    </div>
  );
}
