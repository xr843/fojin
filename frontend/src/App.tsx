import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { ConfigProvider, Spin } from "antd";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import RouteErrorBoundary from "./components/RouteErrorBoundary";
import ProtectedRoute from "./components/ProtectedRoute";
import HomePage from "./pages/HomePage";
const SearchPage = lazy(() => import("./pages/SearchPage"));
const TextDetailPage = lazy(() => import("./pages/TextDetailPage"));

const SourcesPage = lazy(() => import("./pages/SourcesPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ParallelReaderPage = lazy(() => import("./pages/ParallelReaderPage"));
const KnowledgeGraphPage = lazy(() => import("./pages/KnowledgeGraphPage"));
const ManuscriptViewerPage = lazy(() => import("./pages/ManuscriptViewerPage"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const ExportsPage = lazy(() => import("./pages/ExportsPage"));
const CollectionsPage = lazy(() => import("./pages/CollectionsPage"));
const DianjinBrowserPage = lazy(() => import("./pages/DianjinBrowserPage"));
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
  return (
    <ConfigProvider>
      <ErrorBoundary>
        <Suspense fallback={<Loading />}>
          <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/texts/:id" element={<TextDetailPage />} />
            <Route path="/sources" element={<SourcesPage />} />
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/chat" element={<RouteErrorBoundary><ChatPage /></RouteErrorBoundary>} />
            </Route>
            <Route element={<ProtectedRoute requiredRole="admin" />}>
              <Route path="/admin/suggestions" element={<AdminSuggestionsPage />} />
            </Route>
            <Route path="/parallel/:textId" element={<ParallelReaderPage />} />
            <Route path="/kg" element={<RouteErrorBoundary><KnowledgeGraphPage /></RouteErrorBoundary>} />
            <Route path="/manuscripts/:textId" element={<RouteErrorBoundary><ManuscriptViewerPage /></RouteErrorBoundary>} />
            <Route path="/exports" element={<ExportsPage />} />
            <Route path="/dianjin" element={<DianjinBrowserPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </ConfigProvider>
  );
}

export default App;
