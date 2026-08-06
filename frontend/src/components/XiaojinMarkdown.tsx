import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 小津气泡里的 markdown 渲染 —— 单独成文件是为了**懒加载边界**：
 * react-markdown/remark/micromark 打在一个 152K 的共享 chunk 里，而首页是唯一
 * 静态导入的路由，直接 import 会把这 152K 压进首屏。XiaojinPet 用 React.lazy
 * 引它，并在用户提问的一刻预取——首字要等好几秒，chunk 在这段等待里就下完了。
 *
 * ⚠️ 别从 ChatPage.tsx 里 import 任何东西（哪怕只是一个 helper）：那会把整个
 * ChatPage 模块拖进首页 chunk，懒加载就白做了。下面的 tightenLists 是照抄
 * ChatPage 同名函数的有意复制。
 *
 * 与 /chat 的差异（有意为之）：
 * - 不接 fojin-citation:// 协议。引文核对 UI 在 /chat，气泡里那些链接会被
 *   react-markdown 的 defaultUrlTransform 归零，退化成纯文本，正是想要的。
 * - 因此也不需要 rehype-sanitize：没有 rehype-raw，原始 HTML 根本不会进树。
 * - 标题一律降为粗体：272px 宽的气泡放不下 h1/h2 的字号阶梯。
 */

/** 把松散的有序列表收紧（编号独占一行、项间空行）。照抄 ChatPage 的同名函数。 */
function tightenLists(md: string): string {
  return md
    .replace(/^(\d+\.)\s*\n\n+/gm, "$1 ")
    .replace(/\n\n+(?=\d+\.\s)/g, "\n");
}

const COMPONENTS: Components = {
  // 气泡只有 272px 宽，标题的字号阶梯放不下，统一降成一行粗体。
  h1: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  h2: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  h3: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  h4: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  h5: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  h6: ({ children }) => <p className="xiaojin-md-h">{children}</p>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  // 窄气泡里表格必须能横向滚，否则撑破布局。
  table: ({ children }) => (
    <div className="xiaojin-md-table">
      <table>{children}</table>
    </div>
  ),
};

export default function XiaojinMarkdown({ content }: { content: string }) {
  return (
    <div className="xiaojin-md">
      <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {tightenLists(content)}
      </Markdown>
    </div>
  );
}
