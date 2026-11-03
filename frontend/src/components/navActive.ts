/**
 * 顶部导航「当前在哪个板块」：把路由映射到导航项的 path。
 *
 * 此前导航一律同色、没有当前态——在读经页看不出自己在「读经」。
 * 子页面归入它所属的板块：经文页/专题/经典落地页都属于读经，人物页属于知识图谱，
 * 问答分享页属于 AI 问答。首页与不在导航里的页面（/map、/verify…）返回 null。
 */
const SECTIONS: Array<[string, string[]]> = [
  ["/chat", ["/chat", "/share/qa"]],
  ["/read", ["/read", "/texts", "/collections", "/sutras", "/works", "/parallel", "/read-aloud"]],
  ["/dictionary", ["/dictionary"]],
  ["/sources", ["/sources"]],
  ["/kg", ["/kg", "/person"]],
  ["/admin", ["/admin"]],
];

export function activeNavPath(pathname: string): string | null {
  for (const [navPath, prefixes] of SECTIONS) {
    if (prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"))) return navPath;
  }
  return null;
}
