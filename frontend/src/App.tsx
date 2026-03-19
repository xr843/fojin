import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { ConfigProvider, Spin } from "antd";
import { useTranslation } from "react-i18next";
import zhCN from "antd/locale/zh_CN";
import jaJP from "antd/locale/ja_JP";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import RouteErrorBoundary from "./components/RouteErrorBoundary";
import ProtectedRoute from "./components/ProtectedRoute";

const antdLocales: Record<string, typeof zhCN> = { zh: zhCN, ja: jaJP };
import HomePage from "./pages/HomePage";
const SearchPage = lazy(() => import("./pages/SearchPage"));
const TextDetailPage = lazy(() => import("./pages/TextDetailPage"));
const TextReaderPage = lazy(() => import("./pages/TextReaderPage"));

const SourcesPage = lazy(() => import("./pages/SourcesPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ParallelReaderPage = lazy(() => import("./pages/ParallelReaderPage"));
const KnowledgeGraphPage = lazy(() => import("./pages/KnowledgeGraphPage"));
const ManuscriptViewerPage = lazy(() => import("./pages/ManuscriptViewerPage"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const ExportsPage = lazy(() => import("./pages/ExportsPage"));
const CollectionsPage = lazy(() => import("./pages/CollectionsPage"));
const AdminSuggestionsPage = lazy(() => import("./pages/AdminSuggestionsPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

function Loading() {
  return (
    <div style={{ textAlign: "center", padding: 80 }}>
      <Spin size="large" />
    </div>
  );
}

function App() {
  const { i18n } = useTranslation();
  const antLocale = antdLocales[i18n.language] || zhCN;
  return (
    <ConfigProvider
      locale={antLocale}
    >
      <ErrorBoundary>
        <Suspense fallback={<Loading />}>
          <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/texts/:id" element={<TextDetailPage />} />
            <Route path="/texts/:id/read" element={<TextReaderPage />} />
            <Route path="/sources" element={<SourcesPage />} />
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/chat" element={<RouteErrorBoundary><ChatPage /></RouteErrorBoundary>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/profile" element={<ProfilePage />} />
            </Route>
            <Route element={<ProtectedRoute requiredRole="admin" />}>
              <Route path="/admin/suggestions" element={<AdminSuggestionsPage />} />
            </Route>
            <Route path="/parallel/:textId" element={<ParallelReaderPage />} />
            <Route path="/kg" element={<RouteErrorBoundary><KnowledgeGraphPage /></RouteErrorBoundary>} />
            <Route path="/manuscripts/:textId" element={<RouteErrorBoundary><ManuscriptViewerPage /></RouteErrorBoundary>} />
            <Route path="/exports" element={<ExportsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </ConfigProvider>
  );
}

export default App;
