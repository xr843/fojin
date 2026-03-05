import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { ConfigProvider, Spin } from "antd";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import ProtectedRoute from "./components/ProtectedRoute";
import HomePage from "./pages/HomePage";
const SearchPage = lazy(() => import("./pages/SearchPage"));
const TextDetailPage = lazy(() => import("./pages/TextDetailPage"));

const SourcesPage = lazy(() => import("./pages/SourcesPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ReaderPage = lazy(() => import("./pages/ReaderPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ParallelReaderPage = lazy(() => import("./pages/ParallelReaderPage"));
const KnowledgeGraphPage = lazy(() => import("./pages/KnowledgeGraphPage"));
const ManuscriptViewerPage = lazy(() => import("./pages/ManuscriptViewerPage"));
const ChatPage = lazy(() => import("./pages/ChatPage"));
const ExportsPage = lazy(() => import("./pages/ExportsPage"));
const DianjinBrowserPage = lazy(() => import("./pages/DianjinBrowserPage"));
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
            <Route path="/login" element={<LoginPage />} />
            <Route path="/read/:textId" element={<ReaderPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/chat" element={<ChatPage />} />
            </Route>
            <Route path="/parallel/:textId" element={<ParallelReaderPage />} />
            <Route path="/kg" element={<KnowledgeGraphPage />} />
            <Route path="/manuscripts/:textId" element={<ManuscriptViewerPage />} />
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
