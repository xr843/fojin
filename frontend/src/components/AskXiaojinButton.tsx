import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { MessageOutlined } from "@ant-design/icons";

interface AskXiaojinButtonProps {
  /** CSS selector or ref for the container to listen for text selection */
  containerRef: React.RefObject<HTMLElement | null>;
  /** Source label, e.g. "心经第1卷" */
  source: string;
}

const MAX_CONTEXT_LENGTH = 500;

export default function AskXiaojinButton({ containerRef, source }: AskXiaojinButtonProps) {
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const selectedTextRef = useRef("");
  const buttonRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const updatePosition = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.toString().trim()) {
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    // Check that the selection is within our container
    const anchorNode = selection.anchorNode;
    if (!anchorNode || !container.contains(anchorNode)) return;

    const text = selection.toString().trim();
    if (!text) return;

    selectedTextRef.current = text.slice(0, MAX_CONTEXT_LENGTH);

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    // Position above the selection, centered horizontally
    const top = rect.top - containerRect.top - 40;
    const left = Math.max(
      0,
      Math.min(
        rect.left - containerRect.left + rect.width / 2 - 55,
        containerRect.width - 110,
      ),
    );

    setPosition({ top, left });
    setVisible(true);
  }, [containerRef]);

  const hideButton = useCallback(() => {
    hideTimerRef.current = setTimeout(() => {
      setVisible(false);
      selectedTextRef.current = "";
    }, 200);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleMouseUp = () => {
      // Small delay to let selection finalize
      setTimeout(updatePosition, 10);
    };

    const handleTouchEnd = () => {
      setTimeout(updatePosition, 300);
    };

    const handleMouseDown = (e: MouseEvent) => {
      // If clicking on the button itself, don't hide
      if (buttonRef.current?.contains(e.target as Node)) return;
      setVisible(false);
    };

    const handleSelectionChange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        hideButton();
      }
    };

    container.addEventListener("mouseup", handleMouseUp);
    container.addEventListener("touchend", handleTouchEnd);
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("selectionchange", handleSelectionChange);

    return () => {
      container.removeEventListener("mouseup", handleMouseUp);
      container.removeEventListener("touchend", handleTouchEnd);
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("selectionchange", handleSelectionChange);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [containerRef, updatePosition, hideButton]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const context = selectedTextRef.current;
    if (!context) return;

    const params = new URLSearchParams({
      q: "这段经文是什么意思？",
      context,
      source,
    });

    setVisible(false);
    navigate(`/chat?${params.toString()}`);
  }, [navigate, source]);

  if (!visible) return null;

  return (
    <div
      ref={buttonRef}
      className="ask-xiaojin-btn"
      style={{ top: position.top, left: position.left }}
      onMouseDown={(e) => {
        // Prevent selection from being cleared
        e.preventDefault();
        e.stopPropagation();
        if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      }}
      onClick={handleClick}
    >
      <MessageOutlined style={{ fontSize: 13, marginRight: 4 }} />
      问问小津
    </div>
  );
}
