import { useEffect, useRef } from "react";

/**
 * A green glowing circle that follows the mouse cursor.
 * Uses requestAnimationFrame for smooth animation.
 * Hidden on touch devices.
 */
export default function CursorGlow() {
  const dotRef = useRef<HTMLDivElement>(null);
  const pos = useRef({ x: -100, y: -100 });
  const rendered = useRef({ x: -100, y: -100 });
  const raf = useRef<number>(0);

  useEffect(() => {
    // Skip on touch-only devices
    if (window.matchMedia("(pointer: coarse)").matches) return;

    const onMove = (e: MouseEvent) => {
      pos.current = { x: e.clientX, y: e.clientY };
    };

    const animate = () => {
      const dx = pos.current.x - rendered.current.x;
      const dy = pos.current.y - rendered.current.y;
      // Smooth lerp (0.15 = responsive but not jittery)
      rendered.current.x += dx * 0.15;
      rendered.current.y += dy * 0.15;

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
  }, []);

  return (
    <div
      ref={dotRef}
      aria-hidden="true"
      style={{
        position: "fixed",
        top: -10,
        left: -10,
        width: 20,
        height: 20,
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(76,175,80,0.7) 0%, rgba(76,175,80,0) 70%)",
        pointerEvents: "none",
        zIndex: 9999,
        willChange: "transform",
        mixBlendMode: "screen",
      }}
    />
  );
}
