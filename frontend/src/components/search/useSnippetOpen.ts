import { useCallback } from "react";
import type { MouseEvent } from "react";
import { useNavigate } from "react-router";

/**
 * 点检索片段 → 打开阅读器并定位到这段原文（读者反馈 2026-11-28：点片段没反应）。
 * 片段整块可点，但读者在上面划选文字（要复制）时不跳走；Ctrl/⌘ 点照浏览器习惯开新标签。
 * 键盘与读屏仍走卡片里的「阅读」链接，片段本身不另设 Tab 停靠点。
 */
export function useSnippetOpen() {
  const navigate = useNavigate();
  return useCallback(
    (url: string) => (e: MouseEvent) => {
      if (window.getSelection()?.toString()) return;
      if (e.metaKey || e.ctrlKey) {
        window.open(url, "_blank", "noopener");
        return;
      }
      navigate(url);
    },
    [navigate],
  );
}
