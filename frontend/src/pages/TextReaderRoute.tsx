import { useLocation } from "react-router";
import TextReaderPage from "./TextReaderPage";

/**
 * 阅读器路由外壳：按 pathname + search 给阅读器加 key。
 *
 * 阅读器的卷号是惰性 state，只在首次挂载时读 `?juan=` / `?highlight_chunk=`。
 * 从阅读器里跳到另一部经（全藏出处、相关经典、异译本……）时 React Router
 * 复用同一个组件实例，于是沿用上一部经的卷号——点「四分律 第21卷」却停在
 * 第1卷。阅读器自己从不改写 URL（换卷只改 state），所以 URL 变了就一定是
 * 一次新的导航，整体重挂载是安全且正确的。
 */
export default function TextReaderRoute() {
  const { pathname, search } = useLocation();
  return <TextReaderPage key={pathname + search} />;
}
