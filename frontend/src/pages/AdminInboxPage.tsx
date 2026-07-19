import { Tabs } from "antd";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import AdminAnnotationsPage from "./AdminAnnotationsPage";
import AdminFeedbacksPage from "./AdminFeedbacksPage";
import AdminSuggestionsPage from "./AdminSuggestionsPage";

/** 待办:三个被动响应型队列(有人提交才需要处理)合成一个入口。
 *  侧边栏角标为 0 时,菜单里整项不显示 —— 见 Layout.tsx。 */
const TAB_PATHS: Record<string, string> = {
  suggestions: "/admin/suggestions",
  feedbacks: "/admin/feedbacks",
  annotations: "/admin/annotations",
};

export default function AdminInboxPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  const activeKey =
    Object.keys(TAB_PATHS).find((k) => location.pathname === TAB_PATHS[k]) ??
    "suggestions";

  return (
    <Tabs
      activeKey={activeKey}
      onChange={(k) => navigate(TAB_PATHS[k])}
      items={[
        { key: "suggestions", label: t("nav.admin_suggestions"), children: <AdminSuggestionsPage /> },
        { key: "feedbacks", label: t("nav.admin_feedbacks"), children: <AdminFeedbacksPage /> },
        { key: "annotations", label: t("nav.admin_annotations"), children: <AdminAnnotationsPage /> },
      ]}
    />
  );
}
