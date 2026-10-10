import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * 触屏（无悬停能力或粗指针）没有鼠标可跟。光点会永远停在初始的 top/left -6px，
 * 在手机每一页左上角露出半颗绿点（2026-10 生产 390×844 实测）。所以这类设备上
 * 整个组件不渲染，而不只是不挂 mousemove。
 */
function isTouchOnly(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: none)").matches || window.matchMedia("(pointer: coarse)").matches;
}

/**
 * A green glowing circle that follows the mouse cursor.
 * Uses requestAnimationFrame for smooth animation.
 * Not rendered at all on touch devices.
 */
export default function CursorGlow() {
  const [touchOnly] = useState(isTouchOnly);
  const dotRef = useRef<HTMLDivElement>(null);
  const pos = useRef({ x: -100, y: -100 });
  const rendered = useRef({ x: -100, y: -100 });
  const raf = useRef<number>(0);

  useEffect(() => {
    if (touchOnly) return;

    const onMove = (e: MouseEvent) => {
      pos.current = { x: e.clientX, y: e.clientY };
    };

    const animate = () => {
      const dx = pos.current.x - rendered.current.x;
      const dy = pos.current.y - rendered.current.y;
      rendered.current.x += dx * 0.35;
      rendered.current.y += dy * 0.35;

      if (dotRef.current) {
        dotRef.current.style.transform = `translate(${rendered.current.x}px, ${rendered.current.y}px)`;
      }
      raf.current = requestAnimationFrame(animate);
    };

    window.addEventListener("mousemove", onMove);
    raf.current = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf.current);
    };
  }, [touchOnly]);

  if (touchOnly) return null;

  return createPortal(
    <div
      ref={dotRef}
      aria-hidden="true"
      style={{
        position: "fixed",
        top: -6,
        left: -6,
        width: 12,
        height: 12,
        borderRadius: "50%",
        background: "#2e7d32",
        boxShadow: "0 0 8px 2px rgba(46,125,50,0.5)",
        pointerEvents: "none",
        zIndex: 9999,
        willChange: "transform",
      }}
    />,
    document.body,
  );
}
