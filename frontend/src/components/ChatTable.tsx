import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Modal } from "antd";
import { ExpandOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";

/** 行数达到这个数才给「全屏看表」：短表在回答区里本来就看得全。 */
export const EXPAND_MIN_ROWS = 8;

/**
 * 问答回答里的 Markdown 表格。
 *
 * 2026-11-26 读者反馈 80 卷字数表（21 行）「显示不全」：Windows 显示缩放 125%/150%
 * 时浏览器可用高度只剩 590–730px，回答区扣掉顶栏和输入框只有 300–440px，再怎么压行距
 * 也装不下 580px 的表。长表上方给一个按钮，在几乎占满窗口的弹窗里用紧凑行距整张显示。
 */
export default function ChatTable({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLTableElement>(null);
  const [rows, setRows] = useState(0);
  const [open, setOpen] = useState(false);

  // 流式输出时表格逐行长出来：内容一变就重数（行数没变时 React 不会重渲染）。
  useLayoutEffect(() => {
    setRows(ref.current?.rows.length ?? 0);
  }, [children]);

  return (
    <>
      {rows >= EXPAND_MIN_ROWS && (
        <button type="button" className="chat-table-expand" onClick={() => setOpen(true)}>
          <ExpandOutlined aria-hidden /> {t("chat.table_expand")}
        </button>
      )}
      <table ref={ref}>{children}</table>
      {open && (
        <Modal
          open
          title={t("chat.table_full_title")}
          footer={null}
          width="min(96vw, 1200px)"
          style={{ top: 8, paddingBottom: 0 }}
          onCancel={() => setOpen(false)}
          styles={{ body: { maxHeight: "calc(100vh - 80px)", overflow: "auto" } }}
        >
          <div className="chat-markdown chat-table-full">
            <table>{children}</table>
          </div>
        </Modal>
      )}
    </>
  );
}
