import { memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type CSSProperties, type Ref } from "react";
import Markdown, { type Components } from "react-markdown";
import { useTranslation } from "react-i18next";
import { MARKDOWN_REMARK_PLUGINS } from "../utils/markdownPlugins";
import rehypeTibetanInline from "../utils/rehypeTibetanInline";
import { chunkId, hasTibetan, noteId, parseTzHref, refId, type TzDoc } from "../utils/tibetanZhDoc";

/**
 * 藏译汉稿正文：按块按需渲染。
 *
 * 每块先放一个按估计高度占位的空 <section>，进入视口附近（上下 1200px）才交给
 * react-markdown 渲染，渲染过的不再卸载（读过的部分 Ctrl+F 仍可找到、来回滚动不跳）。
 * 2.5 MB 的 T-2978 打开时只渲染开头几块。跳转（目录、校注、跳回）先强制渲染目标块，
 * 等它进入 DOM 再滚过去；上方占位块随后渲染造成的高度变化由浏览器的滚动锚定抵消。
 */

export interface TzBodyHandle {
  jumpTo(elementId: string, chunk: number): void;
}

interface Props {
  doc: TzDoc;
  ref?: Ref<TzBodyHandle>;
}

type HastLike = { type?: string; value?: string; children?: HastLike[] };
function hastText(node: HastLike | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(hastText).join("");
}

const REHYPE_PLUGINS = [rehypeTibetanInline];

const ChunkView = memo(function ChunkView({ text, components }: { text: string; components: Components }) {
  return (
    <Markdown remarkPlugins={MARKDOWN_REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={components}>
      {text}
    </Markdown>
  );
});

const canObserve = typeof window !== "undefined" && "IntersectionObserver" in window;

export default function TibetanZhDocBody({ doc, ref }: Props) {
  const { t } = useTranslation();
  // 没有 IntersectionObserver（测试环境、极老的浏览器）就全部渲染
  const [rendered, setRendered] = useState<Set<number>>(() =>
    canObserve ? new Set([0, 1]) : new Set(doc.chunks.map((c) => c.index)),
  );
  const pending = useRef<string | null>(null);
  const lastRef = useRef<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const renderChunks = useCallback((idx: number[]) => {
    setRendered((prev) => {
      if (idx.every((i) => prev.has(i))) return prev;
      const next = new Set(prev);
      idx.forEach((i) => next.add(i));
      return next;
    });
  }, []);

  // 一块一个任务地渲染：藏文排版很重（T-2978 实测，三块一起渲染一次占主线程 0.5–0.9 s），
  // 排成队、每块之间让出主线程，滚动和点击才不会卡住。
  const queue = useRef<number[]>([]);
  const pumpTimer = useRef<number | null>(null);
  const enqueue = useCallback(
    (idx: number[]) => {
      for (const i of idx) if (!queue.current.includes(i)) queue.current.push(i);
      if (pumpTimer.current !== null || queue.current.length === 0) return;
      const step = () => {
        pumpTimer.current = null;
        const i = queue.current.shift();
        if (i === undefined) return;
        renderChunks([i]);
        if (queue.current.length) pumpTimer.current = window.setTimeout(step, 0);
      };
      pumpTimer.current = window.setTimeout(step, 0);
    },
    [renderChunks],
  );
  useEffect(
    () => () => {
      if (pumpTimer.current !== null) window.clearTimeout(pumpTimer.current);
    },
    [],
  );

  // 视口附近的块才渲染
  useEffect(() => {
    if (!canObserve || !containerRef.current) return;
    const io = new IntersectionObserver(
      (entries) => {
        const hit: number[] = [];
        for (const e of entries) {
          if (e.isIntersecting) {
            hit.push(Number((e.target as HTMLElement).dataset.tzChunk));
            io.unobserve(e.target);
          }
        }
        if (hit.length) enqueue(hit.sort((a, b) => a - b));
      },
      { rootMargin: "1200px 0px" },
    );
    containerRef.current.querySelectorAll<HTMLElement>("section[data-tz-chunk]").forEach((el) => {
      if (el.dataset.tzRendered !== "1") io.observe(el);
    });
    return () => io.disconnect();
  }, [doc, enqueue]);

  const flashed = useRef(false);
  const scrollToPending = useCallback(() => {
    const id = pending.current;
    if (!id) return false;
    const el = document.getElementById(id);
    if (!el) return false;
    el.scrollIntoView({ block: "start" });
    if (!flashed.current && !id.startsWith("tz-chunk-")) {
      flashed.current = true;
      el.classList.remove("tz-flash");
      void el.offsetWidth; // 重新触发动画
      el.classList.add("tz-flash");
    }
    return true;
  }, []);

  // 目标块渲染进 DOM 后滚过去；相邻块随后陆续渲染、上方高度会变，每次都把目标重新对准，
  // 安静 400ms 后才放手。
  useEffect(() => {
    if (!pending.current || !scrollToPending()) return;
    const timer = window.setTimeout(() => {
      pending.current = null;
    }, 400);
    return () => window.clearTimeout(timer);
  }, [rendered, scrollToPending]);

  const jumpTo = useCallback(
    (elementId: string, chunk: number) => {
      pending.current = elementId;
      flashed.current = false;
      const neighbours = [chunk + 1, chunk - 1].filter((i) => i >= 0 && i < doc.chunks.length && !rendered.has(i));
      if (rendered.has(chunk)) {
        scrollToPending();
        window.setTimeout(() => {
          pending.current = null;
        }, 400);
      } else {
        renderChunks([chunk]); // 目标块立刻渲染，邻块排队
      }
      enqueue(neighbours);
    },
    [doc.chunks.length, rendered, renderChunks, enqueue, scrollToPending],
  );

  useImperativeHandle(ref, () => ({ jumpTo }), [jumpTo]);

  // 下面的回调经 ref 拿最新的 jumpTo，好让 components 保持稳定、已渲染的块不必重渲
  const jumpRef = useRef(jumpTo);
  useEffect(() => {
    jumpRef.current = jumpTo;
  }, [jumpTo]);

  const components = useMemo<Components>(() => {
    const go = (id: string | undefined) => {
      if (!id) return;
      const chunk = doc.anchorChunk.get(id);
      if (chunk !== undefined) jumpRef.current(id, chunk);
    };
    return {
      a: ({ href, children }) => {
        const tz = parseTzHref(href);
        if (tz?.kind === "ref") {
          const id = refId(tz.section, tz.n, tz.k);
          return (
            <a
              id={id}
              className="tz-noteref"
              href={`#${noteId(tz.section, tz.n)}`}
              onClick={(e) => {
                e.preventDefault();
                lastRef.current = id;
                go(noteId(tz.section, tz.n));
              }}
            >
              {children}
            </a>
          );
        }
        if (tz?.kind === "back") {
          const nid = noteId(tz.section, tz.n);
          return (
            <a
              id={nid}
              className="tz-noteback"
              href="#"
              title={t("tibetanZh.back_to_text")}
              aria-label={t("tibetanZh.back_to_text")}
              onClick={(e) => {
                e.preventDefault();
                const last = lastRef.current;
                const back = last && last.startsWith(`tz-ref-${tz.section}-${tz.n}-`) ? last : doc.firstRefOf.get(nid);
                go(back);
              }}
            >
              ↩
            </a>
          );
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        );
      },
      blockquote: ({ node, children }) =>
        hasTibetan(hastText(node as HastLike)) ? (
          <blockquote lang="bo" className="tz-bo">
            {children}
          </blockquote>
        ) : (
          <blockquote>{children}</blockquote>
        ),
      table: ({ children }) => (
        <div className="tz-table">
          <table>{children}</table>
        </div>
      ),
    };
  }, [doc, t]);

  return (
    <div className="tz-md" ref={containerRef}>
      {doc.chunks.map((c) => {
        const on = rendered.has(c.index);
        return (
          <section
            key={c.index}
            id={chunkId(c.index)}
            data-tz-chunk={c.index}
            data-tz-rendered={on ? "1" : "0"}
            className="tz-chunk"
            style={
              on
                ? undefined
                : ({ "--tz-est": `${c.estHeight}px`, "--tz-est-zh": `${c.estHeightZhOnly}px` } as CSSProperties)
            }
          >
            {on && <ChunkView text={c.text} components={components} />}
          </section>
        );
      })}
    </div>
  );
}
