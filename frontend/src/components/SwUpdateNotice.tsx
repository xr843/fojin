import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { isUpdateReady, onUpdateReady } from "../utils/swUpdate";

/**
 * 佛津有新版本时：页面底部一行提示（可点刷新）；读者在站内换页时顺手整页刷新到新版。
 * 不自动刷新当前页——读者可能正在问答框里打字。见 utils/swUpdate.ts。
 */
export default function SwUpdateNotice() {
  const { t } = useTranslation();
  const [ready, setReady] = useState(isUpdateReady);
  const [dismissed, setDismissed] = useState(false);
  const location = useLocation();
  const firstPath = useRef(location.pathname);

  useEffect(() => onUpdateReady(() => setReady(true)), []);

  // 有新版时，站内换页就整页加载新版（换页本来就离开了当前输入，不丢东西）
  useEffect(() => {
    if (ready && location.pathname !== firstPath.current) window.location.reload();
    firstPath.current = location.pathname;
  }, [ready, location.pathname]);

  if (!ready || dismissed) return null;
  return (
    <div className="sw-update-notice" role="status">
      <span>{t("app.update_ready")}</span>
      <button type="button" className="sw-update-reload" onClick={() => window.location.reload()}>
        {t("app.update_reload")}
      </button>
      <button type="button" className="sw-update-close" aria-label={t("app.update_dismiss")} onClick={() => setDismissed(true)}>
        ×
      </button>
    </div>
  );
}
