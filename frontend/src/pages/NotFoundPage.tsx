import { useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { Input } from "antd";
import { DatabaseOutlined, FileTextOutlined, HomeOutlined, RobotOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import "../styles/notfound.css";

/**
 * 404。曾是 antd `<Result status="404">` 的默认插画（蓝问号、蓝裤子小人、绿仙人掌），
 * 与全站暖米色 / 朱砂 / 水墨山水完全不搭，唯一出口是「返回首页」。
 *
 * 视觉只用站里已有的东西：首页那张 18KB 的水墨山水（landscape-bg.webp，nginx
 * 已给它长缓存）、--fj-cinnabar 朱砂、Noto Serif SC。标题没有用毛笔体 —— 站上的
 * Ma Shan Zheng 是按字裁剪的子集（只含「佛津」「小典问答」几个字，见 fonts.css），
 * 「此路不通」会逐字掉回宋体、一半毛笔一半宋体；为它再裁一份字体就是新增资源。
 *
 * nginx 对未知路由一律 try_files 回 index.html、状态码 200（软 404），而 index.html
 * 写死了 robots "index, follow"。见 useNoindex。
 */

/**
 * 把 index.html 那条 robots 就地改成 noindex，离开时还原。
 *
 * 不用 Helmet 再加一条：Helmet 只管带 data-rh 的标签，不会替换模板里那条，head 里
 * 就并存「index, follow」与「noindex」两条（2026-10-10 生产实测）。也不能删模板里那条：
 * 后端 seo.py 的 _inject_meta 是用正则**替换**它来给阅读页注入 "noindex, follow" 的，
 * 删了阅读页的 noindex 就静默失效。
 */
function useNoindex() {
  useEffect(() => {
    const existing = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previous = existing?.getAttribute("content") ?? null;
    const meta = existing ?? document.head.appendChild(document.createElement("meta"));
    const created = !existing;
    meta.setAttribute("name", "robots");
    meta.setAttribute("content", "noindex");
    return () => {
      if (created) meta.remove();
      else if (previous !== null) meta.setAttribute("content", previous);
    };
  }, []);
}

export default function NotFoundPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  useNoindex();

  const onSearch = (value: string) => {
    const q = value.trim();
    if (!q) return;
    navigate(`/search?q=${encodeURIComponent(q)}`);
  };

  const exits = [
    { to: "/", icon: <HomeOutlined />, label: t("notfound.back") },
    { to: "/chat", icon: <RobotOutlined />, label: t("nav.chat") },
    { to: "/dictionary", icon: <FileTextOutlined />, label: t("nav.dictionary") },
    { to: "/sources", icon: <DatabaseOutlined />, label: t("nav.sources") },
  ];

  return (
    <div className="nf-page">
      <Helmet>
        <title>{`${t("notfound.doc_title")} - ${t("app.name")}`}</title>
      </Helmet>
      <div className="nf-bg" aria-hidden="true">
        <img src="/landscape-bg.webp" alt="" decoding="async" />
      </div>
      <div className="nf-inner">
        <div className="nf-seal" aria-hidden="true">{t("notfound.title")}</div>
        <h1 className="nf-heading">{t("notfound.heading")}</h1>
        <p className="nf-desc">{t("notfound.subtitle")}</p>
        <div className="nf-search" role="search">
          <Input.Search
            type="search"
            size="large"
            allowClear
            aria-label={t("notfound.search_label")}
            placeholder={t("notfound.search_placeholder")}
            enterButton={t("nav.search")}
            onSearch={onSearch}
          />
        </div>
        <nav className="nf-links" aria-label={t("notfound.links_label")}>
          <div className="nf-links-label">{t("notfound.links_label")}</div>
          <ul>
            {exits.map((e) => (
              <li key={e.to}>
                <Link to={e.to} className="nf-link">
                  {e.icon}
                  <span>{e.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  );
}
