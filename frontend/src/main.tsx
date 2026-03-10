import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import App from "./App";
import "./styles/global.css";

// Dify AI 助手：从环境变量注入配置并加载 embed 脚本
(() => {
  const token = import.meta.env.VITE_DIFY_APP_TOKEN;
  const baseUrl = import.meta.env.VITE_DIFY_BASE_URL;
  if (!token || !baseUrl) return; // Dify not configured — skip silently
  (window as any).difyChatbotConfig = { token, baseUrl };
  const s = document.createElement("script");
  s.src = `${baseUrl}/embed.min.js`;
  s.async = true;
  document.body.appendChild(s);
})();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </HelmetProvider>
  </React.StrictMode>
);
