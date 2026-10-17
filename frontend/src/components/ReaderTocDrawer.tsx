import { useEffect, useRef } from "react";
import { Drawer } from "antd";
import { useTranslation } from "react-i18next";

/** public/cbeta-toc/<经号>.json 的一条：[层级, 标题, 卷, 行号]。 */
export type TocEntry = [number, string, number, string];

interface Props {
  open: boolean;
  onClose: () => void;
  toc: TocEntry[];
  currentJuan: number;
  onJump: (juan: number, lineRef: string) => void;
  /** 窄屏从底部弹出，宽屏从左侧（CBETA Online 的目次也在左栏）。 */
  placement: "left" | "bottom";
}

/** 品 / 分 / 会 目次（来自 CBETA 的 cb:mulu）。点一条 → 跳到那一卷、那一行。 */
export default function ReaderTocDrawer({ open, onClose, toc, currentJuan, onJump, placement }: Props) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);

  // 打开时把当前卷的第一条滚进视野：长目次（如《一切經音義》上千条）不必从头翻。
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLElement>(".reader-toc-item.is-current")?.scrollIntoView({ block: "center" });
    });
    return () => cancelAnimationFrame(id);
  }, [open, currentJuan]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t("reader.toc.title")}
      placement={placement}
      width={placement === "left" ? 320 : undefined}
      height={placement === "bottom" ? "70vh" : undefined}
      styles={{ body: { padding: "8px 0" } }}
      destroyOnHidden
    >
      <div ref={listRef} className="reader-toc-list" role="list">
        {toc.map(([level, title, juan, ref], i) => {
          const current = juan === currentJuan;
          return (
            <button
              key={`${i}-${ref}`}
              type="button"
              role="listitem"
              className={`reader-toc-item${current ? " is-current" : ""}`}
              style={{ paddingInlineStart: 16 + Math.min(level - 1, 4) * 16 }}
              onClick={() => onJump(juan, ref)}
            >
              <span className={`reader-toc-title level-${Math.min(level, 3)}`}>{title}</span>
              <span className="reader-toc-juan">{t("reader.toc.juan", { n: juan })}</span>
            </button>
          );
        })}
      </div>
    </Drawer>
  );
}
