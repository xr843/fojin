import { Helmet } from "react-helmet-async";
import { RobotOutlined, GithubOutlined } from "@ant-design/icons";

export default function ChatPage() {
  return (
    <>
      <Helmet>
        <title>小津 AI 佛典问答 — 佛津 FoJin</title>
      </Helmet>
      <div
        style={{
          width: "100%",
          height: "calc(100vh - 120px)",
          maxWidth: 800,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          fontFamily: '"Noto Serif SC", serif',
        }}
      >
        <RobotOutlined
          style={{ fontSize: 64, color: "var(--fj-accent)", marginBottom: 24 }}
        />
        <h2
          style={{
            color: "var(--fj-ink)",
            fontSize: 28,
            fontWeight: 400,
            marginBottom: 12,
          }}
        >
          小津 AI 问答
        </h2>
        <p
          style={{
            color: "var(--fj-ink-muted)",
            fontSize: 16,
            lineHeight: 1.8,
            maxWidth: 480,
            marginBottom: 32,
          }}
        >
          基于 38 部核心佛典、约 1100 万字经文的 RAG 智能问答系统，
          支持自然语言提问，每条回答均附原文引用。
        </p>
        <div
          style={{
            background: "rgba(217,208,193,0.3)",
            borderRadius: 8,
            padding: "16px 32px",
            color: "var(--fj-ink-muted)",
            fontSize: 14,
          }}
        >
          功能开发中，即将上线，敬请期待
        </div>
        <a
          href="https://github.com/xr843/fojin"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            marginTop: 24,
            color: "var(--fj-accent)",
            fontSize: 14,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <GithubOutlined /> 关注项目进展
        </a>
      </div>
    </>
  );
}
