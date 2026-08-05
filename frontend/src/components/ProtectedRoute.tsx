import { Navigate, Outlet, useLocation } from "react-router";
import { useAuthStore } from "../stores/authStore";

export default function ProtectedRoute({ requiredRole }: { requiredRole?: string }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (!user) {
    // 记下他本来要去哪儿，LoginPage 的 consumeReturnTo() 会消费掉。
    // 用 sessionStorage 而不是 location.state：OAuth 要经第三方往返，state 必然
    // 丢失 —— LoginPage 顶上那段注释记的就是这件事。
    //
    // 写在 render 里而不是 useEffect 里是必需的：本组件返回的 <Navigate> 会在它
    // 自己的 effect 里就把路由换掉，而子组件的 effect 先于父组件跑，放进
    // useEffect 就来不及了。这个写入幂等，StrictMode 双渲染重复执行无副作用。
    try {
      sessionStorage.setItem("fojin.login.returnTo", location.pathname + location.search);
    } catch { /* ignore */ }
    return <Navigate to="/login" replace />;
  }

  // 角色不够不是「没登录」，送回首页且不写 returnTo —— 登录完再把他弹回一个
  // 依然进不去的页面，只是让他把同一堵墙撞第二次。
  if (requiredRole && user.role !== requiredRole) return <Navigate to="/" replace />;
  return <Outlet />;
}
