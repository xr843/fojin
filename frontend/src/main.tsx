// MUST be imported before any antd usage. antd v5's static methods
// (message.*, notification.*, Modal.confirm/info/...) internally rely on the
// legacy ReactDOM.render, which React 19 removed — so on React 19 they
// silently do nothing: no toast, no confirm dialog. This patch calls antd's
// unstableSetRender to bridge them to React 19's createRoot. Without it,
// registration feedback, logout confirmation, and ~80 other feedback call
// sites across the app render nothing. See the react group bump (165f3f2,
// 2026-07-03) that introduced React 19.
import "@ant-design/v5-patch-for-react-19";
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import App from "./App";
import "./i18n";
import "./styles/global.css";
import "./umami";

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
