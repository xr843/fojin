import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Button, Drawer, Spin, Switch } from "antd";
import { UnorderedListOutlined } from "@ant-design/icons";
import { isAxiosError } from "axios";
import { getTibetanZhDocument, getTibetanZhIndex } from "../api/tibetanZh";
import TibetanZhNotice from "../components/TibetanZhNotice";
import TibetanZhDocBody, { type TzBodyHandle } from "../components/TibetanZhDocBody";
import { useNarrowViewport } from "../hooks/useNarrowViewport";
import { chunkId, prepareDocument, type TzDoc } from "../utils/tibetanZhDoc";
import "../styles/tibetan-zh.css";

/**
 * 藏译汉稿阅读页（/tibetan-zh/:id）。
 *
 * ⚠️ AI 译稿，未经懂藏文的专家审定：只做展示，不进 AI 问答、不进检索。
 * 正文由后端从 GitHub 转发（大陆读者打不开 raw.githubusercontent.com）。
 */

const ZH_ONLY_KEY = "fojin-tibetan-zh-zh-only";

function readZhOnly(): boolean {
  try {
    return localStorage.getItem(ZH_ONLY_KEY) === "1";
  } catch {
    return false;
  }
}

function TocList({ doc, onJump }: { doc: TzDoc; onJump: (chunk: number) => void }) {
  return (
    <ol className="tz-toc-list">
      {doc.toc.map((e, i) => (
        <li key={`${i}-${e.chunk}`}>
          <a
            href={`#${chunkId(e.chunk)}`}
            onClick={(ev) => {
              ev.preventDefault();
              onJump(e.chunk);
            }}
          >
            {e.title}
          </a>
        </li>
      ))}
    </ol>
  );
}

export default function TibetanZhReaderPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const narrow = useNarrowViewport();
  const [zhOnly, setZhOnly] = useState(readZhOnly);
  const [tocOpen, setTocOpen] = useState(false);
  const bodyRef = useRef<TzBodyHandle>(null);

  const index = useQuery({
    queryKey: ["tibetanZhIndex"],
    queryFn: getTibetanZhIndex,
    staleTime: 10 * 60_000,
  });
  const docQ = useQuery({
    queryKey: ["tibetanZhDoc", id],
    queryFn: () => getTibetanZhDocument(id),
    staleTime: 30 * 60_000,
    retry: (count, err) => !(isAxiosError(err) && err.response?.status === 404) && count < 1,
  });

  const item = index.data?.items.find((x) => x.id === id);
  const doc = useMemo(() => (docQ.data ? prepareDocument(docQ.data) : null), [docQ.data]);
  const title = item?.title ?? docQ.data?.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? id;
  const notFound = isAxiosError(docQ.error) && docQ.error.response?.status === 404;

  const toggleZhOnly = (on: boolean) => {
    setZhOnly(on);
    try {
      localStorage.setItem(ZH_ONLY_KEY, on ? "1" : "0");
    } catch {
      // 隐私模式等写不进去，只影响下次打开时的默认值
    }
  };

  const jumpToChunk = (chunk: number) => {
    setTocOpen(false);
    bodyRef.current?.jumpTo(chunkId(chunk), chunk);
  };

  const links = item
    ? ([
        ["md", item.md, t("tibetanZh.link_md")],
        ["pdf", item.pdf, t("tibetanZh.link_pdf")],
        ["docx", item.docx, t("tibetanZh.link_docx")],
      ] as const).filter(([, href]) => !!href)
    : [];

  return (
    <div className={`tz-reader-page${zhOnly ? " tz-zh-only" : ""}`}>
      <Helmet>
        <title>{t("tibetanZh.reader_page_title", { title, id })}</title>
        <meta name="description" content={t("tibetanZh.page_desc")} />
      </Helmet>

      <nav className="tz-crumbs">
        <Link to="/tibetan-zh">{t("tibetanZh.back_to_list")}</Link>
      </nav>

      <header className="tz-reader-head">
        <h1 className="tz-reader-title">
          《{title}》<span className="tz-reader-id">{id}</span>
        </h1>
        {item && (
          <p className="tz-reader-meta">
            {[item.au && t("tibetanZh.author", { name: item.au }), item.part, item.cat].filter(Boolean).join(" · ")}
          </p>
        )}
        {links.length > 0 && (
          <p className="tz-reader-links">
            {links.map(([k, href, label]) => (
              <a key={k} href={href!} target="_blank" rel="noopener noreferrer">
                {label} ↗
              </a>
            ))}
          </p>
        )}
      </header>

      <TibetanZhNotice rv={item?.rv} />

      {docQ.isLoading ? (
        <div className="tz-state">
          <Spin />
          <p>{t("tibetanZh.loading_doc")}</p>
        </div>
      ) : notFound ? (
        <div className="tz-state">
          <p>{t("tibetanZh.not_found")}</p>
          <Link to="/tibetan-zh">{t("tibetanZh.back_to_list")}</Link>
        </div>
      ) : docQ.isError || !doc ? (
        <div className="tz-state">
          <p>{t("tibetanZh.load_failed")}</p>
          <Button onClick={() => docQ.refetch()}>{t("tibetanZh.retry")}</Button>
        </div>
      ) : (
        <>
          <div className="tz-toolbar">
            {narrow && doc.toc.length > 0 && (
              <Button size="small" icon={<UnorderedListOutlined />} onClick={() => setTocOpen(true)}>
                {t("tibetanZh.toc")}
              </Button>
            )}
            <label className="tz-toggle">
              <Switch size="small" checked={zhOnly} onChange={toggleZhOnly} />
              <span>{t("tibetanZh.zh_only")}</span>
            </label>
          </div>

          <div className="tz-reader">
            {!narrow && doc.toc.length > 0 && (
              <aside className="tz-toc" aria-label={t("tibetanZh.toc")}>
                <div className="tz-toc-title">{t("tibetanZh.toc")}</div>
                <TocList doc={doc} onJump={jumpToChunk} />
              </aside>
            )}
            <TibetanZhDocBody key={id} doc={doc} ref={bodyRef} />
          </div>

          {narrow && (
            <Drawer
              open={tocOpen}
              onClose={() => setTocOpen(false)}
              title={t("tibetanZh.toc")}
              placement="left"
              width={300}
              styles={{ body: { padding: "8px 0" } }}
            >
              <TocList doc={doc} onJump={jumpToChunk} />
            </Drawer>
          )}
        </>
      )}
    </div>
  );
}
