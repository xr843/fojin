import { Helmet } from "react-helmet-async";

const DIFY_BASE_URL = import.meta.env.VITE_DIFY_BASE_URL || "";
const DIFY_APP_TOKEN = import.meta.env.VITE_DIFY_APP_TOKEN || "";

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
          maxWidth: 1200,
          margin: "0 auto",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <iframe
          src={`${DIFY_BASE_URL}/chatbot/${DIFY_APP_TOKEN}`}
          style={{ width: "100%", height: "100%", border: "none" }}
          allow="microphone"
          title="AI 佛典问答"
        />
      </div>
    </>
  );
}
