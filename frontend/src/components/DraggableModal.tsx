import { useCallback, useRef, useState, type ReactNode } from "react";
import { Modal } from "antd";
import "../styles/draggable-modal.css";

/**
 * antd's Modal is fixed where it lands and fixed in size. This adds both —
 * without pulling in react-draggable / react-rnd for a single dialog (two new
 * deps, more bundle, more dependency-audit surface):
 *
 *  - drag:   pointer events on the title bar, translated onto the modalRender
 *            wrapper. Pointer capture keeps the drag alive once the cursor
 *            leaves the header.
 *  - resize: the browser's own `resize: both` grip on .ant-modal-content
 *            (see draggable-modal.css) — no JS at all.
 *
 * The drag is clamped so the dialog can never be thrown fully off-screen: some
 * of it, and always the title bar you'd grab to bring it back, stays reachable.
 */

/** Keep at least this much of the dialog on screen, in px. */
const KEEP_VISIBLE = 96;

interface Props {
  open: boolean;
  title: ReactNode;
  onCancel: () => void;
  /** Initial width; the user can resize from there. */
  width?: number;
  children: ReactNode;
}

export default function DraggableModal({ open, title, onCancel, width = 880, children }: Props) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const wrapRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ sx: number; sy: number; ox: number; oy: number; rect: DOMRect } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = wrapRef.current;
      if (!el || e.button !== 0) return;
      drag.current = {
        sx: e.clientX,
        sy: e.clientY,
        ox: pos.x,
        oy: pos.y,
        rect: el.getBoundingClientRect(), // includes the current transform
      };
      e.currentTarget.setPointerCapture?.(e.pointerId);
    },
    [pos],
  );

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;

    let x = d.ox + (e.clientX - d.sx);
    let y = d.oy + (e.clientY - d.sy);

    // Where the dialog would sit with no transform at all.
    const baseLeft = d.rect.left - d.ox;
    const baseTop = d.rect.top - d.oy;
    const w = d.rect.width;

    x = Math.min(
      Math.max(x, KEEP_VISIBLE - w - baseLeft),
      window.innerWidth - KEEP_VISIBLE - baseLeft,
    );
    // Never above the viewport: the title bar must stay grabbable.
    y = Math.min(Math.max(y, -baseTop), window.innerHeight - KEEP_VISIBLE - baseTop);

    setPos({ x, y });
  }, []);

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  }, []);

  return (
    <Modal
      className="fj-dm"
      open={open}
      onCancel={onCancel}
      /* Recentre for the next open. Deliberately `afterClose` and not an effect
         on `open`: it fires however the dialog was dismissed — including when the
         parent just flips `open` to false (picking a master does exactly that,
         bypassing onCancel entirely) — and it is a plain callback, so it can't
         trigger the cascading re-render an effect-with-setState would. */
      afterClose={() => setPos({ x: 0, y: 0 })}
      footer={null}
      width={width}
      destroyOnClose
      maskClosable
      title={
        <div
          className="fj-dm-title"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          {title}
        </div>
      }
      /* The wrapper IS the sized, resizable box (see .fj-dm-box). It must be —
         if the sizing lived on .ant-modal-content instead, this wrapper would
         stretch to the full width of .ant-modal and two things would break:
         the dialog would sit left-aligned rather than centred, and the drag
         clamp below would measure the full-width wrapper and let you throw the
         dialog clean off the screen. */
      modalRender={(node) => (
        <div
          ref={wrapRef}
          className="fj-dm-box"
          style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
        >
          {node}
        </div>
      )}
    >
      {children}
    </Modal>
  );
}
