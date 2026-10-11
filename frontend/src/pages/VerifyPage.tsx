import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Helmet } from "react-helmet-async";
import { Alert, Button, Input, Spin, message } from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  LinkOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { isAxiosError } from "axios";
import { verifyCardUrl, verifyClaim, type ClaimSegment, type ClaimVerdict } from "../api/client";
import { currentUILang } from "../i18n";
import { LangAlternates } from "../seo/LangAlternates";
import { langUrl, toSeoLang } from "../seo/langUrl";
import { localizeHan } from "../utils/hanScript";
import "../styles/sources.css";
import "../styles/verify.css";

const MAX_CHARS = 200;

/** In-app path for a reader URL the API returns as absolute (https://fojin.app/texts/…). */
function inAppPath(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return `${u.pathname}${u.search}`;
  } catch {
    return url.startsWith("/") ? url : null;
  }
}

function headline(v: ClaimVerdict, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (v.verdict === "not_sutra") {
    return t("verify.verdict.not_sutra", { cls: t(`verify.class.${v.source_class ?? "unknown"}`) });
  }
  return t(`verify.verdict.${v.verdict}`);
}

function explanation(v: ClaimVerdict, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (v.verdict === "not_sutra") {
    return t("verify.explain.not_sutra", { cls: t(`verify.class.${v.source_class ?? "unknown"}`) });
  }
  return t(`verify.explain.${v.verdict}`);
}

function Segment({ seg, language }: { seg: ClaimSegment; language: string }) {
  const { t } = useTranslation();
  return (
    <li className={`verify-seg ${seg.found ? "is-found" : seg.close ? "is-close" : "is-missing"}`}>
      <div className="verify-seg-text">
        {seg.found ? (
          <CheckCircleFilled aria-hidden />
        ) : seg.close ? (
          <ExclamationCircleFilled aria-hidden />
        ) : (
          <CloseCircleFilled aria-hidden />
        )}
        <span>{seg.text}</span>
      </div>
      {!seg.found && seg.close ? (
        <div className="verify-seg-sources verify-seg-close">
          {t("verify.segment_close")}
          <span className="verify-close-text">「{seg.close.window_normalised}」</span>
          {(() => {
            const c = seg.close;
            const title = `《${localizeHan(c.title_zh ?? c.cbeta_id ?? "", language)}》${t("verify.juan", { n: c.juan_num })}`;
            const path = inAppPath(c.reader_url);
            return path ? (
              <Link to={path} className="verify-source">
                {title}
              </Link>
            ) : (
              <span className="verify-source">{title}</span>
            );
          })()}
        </div>
      ) : seg.found ? (
        <div className="verify-seg-sources">
          {t("verify.segment_found")}
          {seg.sources.map((s) => {
            const title = `《${localizeHan(s.title_zh ?? s.cbeta_id ?? "", language)}》`;
            const path = inAppPath(s.reader_url);
            const label = `${title}${t("verify.juan", { n: s.juan_num })}`;
            return path ? (
              <Link key={`${s.text_id}-${s.juan_num}`} to={path} className="verify-source">
                {label}
              </Link>
            ) : (
              <span key={`${s.text_id}-${s.juan_num}`} className="verify-source">
                {label}
              </span>
            );
          })}
        </div>
      ) : (
        <div className="verify-seg-sources">{t("verify.segment_missing")}</div>
      )}
    </li>
  );
}

export default function VerifyPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Array.from: slice by code point, so a hand-made long link cannot cut an
  // Extension-B character in half (a lone surrogate makes encodeURIComponent throw).
  const q = Array.from((searchParams.get("q") ?? "").trim()).slice(0, MAX_CHARS).join("");
  const [draft, setDraft] = useState(q);
  const [prevQ, setPrevQ] = useState(q);
  if (prevQ !== q) {
    setPrevQ(q);
    setDraft(q);
  }
  const lang = currentUILang(i18n);

  const result = useQuery({
    queryKey: ["verify-claim", q],
    queryFn: () => verifyClaim(q),
    enabled: q.length > 0,
    retry: false,
    staleTime: 60 * 60 * 1000,
  });

  const submit = (text: string) => {
    const value = Array.from(text.trim()).slice(0, MAX_CHARS).join("");
    if (!value) return;
    const params = new URLSearchParams(searchParams);
    params.set("q", value);
    navigate({ search: `?${params.toString()}` });
  };

  const errorText = (() => {
    if (!result.isError) return null;
    const status = isAxiosError(result.error) ? result.error.response?.status : undefined;
    if (status === 422) return t("verify.error_short");
    if (status === 429) return t("verify.error_rate");
    return t("verify.error_generic");
  })();

  const shareUrl = q
    ? `${langUrl("/verify", toSeoLang(lang))}${toSeoLang(lang) === "zh" ? "?" : "&"}q=${encodeURIComponent(q)}`
    : "";
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      message.success(t("verify.copied"));
    } catch {
      message.info(shareUrl);
    }
  };

  const verdict = result.data;
  const examples = [t("verify.example_1"), t("verify.example_2"), t("verify.example_3")];

  return (
    <div className="sources-page verify-page">
      <Helmet>
        <title>{t("verify.page_title")}</title>
        <meta name="description" content={t("verify.page_desc")} />
        {/* Result pages are an unbounded query space — keep them out of the index;
            /verify itself (no q) is the indexable entry, with its own shells. */}
        {q && <meta name="robots" content="noindex, follow" />}
        {q && <meta property="og:image" content={`https://fojin.app${verifyCardUrl(q, lang)}`} />}
      </Helmet>
      <LangAlternates path="/verify" />

      <div className="sources-header">
        <h1 className="sources-title">{t("verify.title")}</h1>
        <p className="sources-desc">{t("verify.subtitle")}</p>
      </div>

      <form
        className="verify-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <Input.TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("verify.placeholder")}
          maxLength={MAX_CHARS}
          showCount
          autoSize={{ minRows: 2, maxRows: 5 }}
          aria-label={t("verify.title")}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              submit(draft);
            }
          }}
        />
        <Button type="primary" htmlType="submit" disabled={!draft.trim()} loading={result.isFetching}>
          {t("verify.submit")}
        </Button>
      </form>

      <div className="verify-examples">
        <span>{t("verify.examples")}</span>
        {examples.map((ex) => (
          <button key={ex} type="button" className="verify-example" onClick={() => submit(ex)}>
            {ex}
          </button>
        ))}
      </div>

      {result.isFetching && !verdict && (
        <div className="verify-loading">
          <Spin />
        </div>
      )}
      {errorText && <Alert type="warning" showIcon message={errorText} className="verify-alert" />}

      {verdict && q && (
        <section className={`verify-result verdict-${verdict.verdict}`} aria-live="polite">
          <div className="verify-badge">{headline(verdict, t)}</div>
          <p className="verify-explain">{explanation(verdict, t)}</p>
          <ul className="verify-segs">
            {verdict.segments.map((seg, i) => (
              <Segment key={`${i}-${seg.text}`} seg={seg} language={i18n.language} />
            ))}
          </ul>

          <figure className="verify-card">
            <img
              src={verifyCardUrl(q, lang)}
              alt={`${t("verify.card_alt")} — ${headline(verdict, t)}`}
              width={1200}
              height={630}
              onError={(e) => {
                // Rate-limited or failed: hide the card rather than show a broken image.
                (e.currentTarget.closest("figure") as HTMLElement | null)?.style.setProperty("display", "none");
              }}
            />
            <figcaption>{t("verify.save_hint")}</figcaption>
          </figure>

          <div className="verify-actions">
            <Button icon={<LinkOutlined />} onClick={copyLink}>
              {t("verify.copy_link")}
            </Button>
            <Button icon={<RobotOutlined />} onClick={() => navigate(`/chat?q=${encodeURIComponent(t("verify.ask_prompt", { q }))}`)}>
              {t("verify.ask_xiaojin")}
            </Button>
          </div>
        </section>
      )}

      <p className="verify-method">{t("verify.method")}</p>
    </div>
  );
}
