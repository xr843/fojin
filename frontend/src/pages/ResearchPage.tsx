import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Helmet } from "react-helmet-async";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApartmentOutlined, FileTextOutlined, ReadOutlined, SendOutlined } from "@ant-design/icons";
import { runResearch, type ResearchReport, type ResearchStep, type ChatSource } from "../api/client";
import { useAuthStore } from "../stores/authStore";
import "../styles/research.css";

const TOOL_ICON: Record<string, ReactNode> = {
  corpus: <ReadOutlined />,
  dictionary: <FileTextOutlined />,
  entity: <ApartmentOutlined />,
};

function StepRow({ step }: { step: ResearchStep }) {
  const { t } = useTranslation();
  return (
    <li className="rp-step">
      <span className="rp-step-icon">{TOOL_ICON[step.tool] ?? <ReadOutlined />}</span>
      <span className="rp-step-query">{step.query}</span>
      {step.aspect && <span className="rp-step-aspect">{step.aspect}</span>}
      <span className="rp-step-count">{t("research.n_sources", { n: step.num_sources })}</span>
    </li>
  );
}

function SourceRow({ src }: { src: ChatSource }) {
  const { t } = useTranslation();
  const label = src.title_zh ? `《${src.title_zh}》${t("research.juan_n", { n: src.juan_num })}` : `#${src.text_id}`;
  return (
    <li className="rp-source">
      <Link className="rp-source-link" to={`/texts/${src.text_id}/read?juan=${src.juan_num}`}>
        {label}
      </Link>
      {src.urn && <code className="rp-urn" title={t("research.urn_hint")}>{src.urn}</code>}
    </li>
  );
}

export default function ResearchPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [question, setQuestion] = useState("");

  const mutation = useMutation<ResearchReport, Error, string>({
    // 3 steps already yields ~10 cited sources; 4 pushes total latency toward
    // the ~100s upstream (Cloudflare) ceiling, so keep the default at 3.
    mutationFn: (q: string) => runResearch(q, 3),
  });

  const submit = () => {
    const q = question.trim();
    if (q.length >= 2 && !mutation.isPending) mutation.mutate(q);
  };

  const report = mutation.data;

  return (
    <div className="research-page">
      <Helmet>
        {/* 品牌后缀用 app.name（短名）而非 app.title：后者是首页专用的完整主张句，
            拼进来会变成「研究助手 — 佛津 FoJin — 佛经 AI 问答，每句引用可点开核对原文」。
            DictionaryPage 等页面用的就是 app.name，这里跟齐。 */}
        <title>{t("research.title")} — {t("app.name")}</title>
      </Helmet>

      <header className="rp-header">
        <h1>{t("research.title")}</h1>
        <p className="rp-intro">{t("research.intro")}</p>
      </header>

      {!user ? (
        <div className="rp-login">
          <p>{t("research.login_required")}</p>
          <Link className="rp-login-btn" to="/login">{t("auth.login")}</Link>
        </div>
      ) : (
        <>
          <div className="rp-input-row">
            <textarea
              className="rp-input"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
              }}
              placeholder={t("research.placeholder")}
              rows={3}
              maxLength={500}
              aria-label={t("research.title")}
            />
            <button className="rp-submit" onClick={submit} disabled={mutation.isPending || question.trim().length < 2}>
              <SendOutlined /> {mutation.isPending ? t("research.thinking") : t("research.button")}
            </button>
          </div>

          {mutation.isPending && (
            <div className="rp-loading">{t("research.thinking_detail")}</div>
          )}
          {mutation.isError && (
            <div className="rp-error">{t("research.error")}</div>
          )}

          {report && !mutation.isPending && (
            <div className="rp-report">
              {report.plan.length > 0 && (
                <section className="rp-section">
                  <h2>{t("research.plan_title")}</h2>
                  <ol className="rp-plan">
                    {report.plan.map((s, i) => <StepRow key={i} step={s} />)}
                  </ol>
                </section>
              )}

              <section className="rp-section">
                <h2>{t("research.answer_title")}</h2>
                <div className="rp-answer">
                  <Markdown remarkPlugins={[remarkGfm]}>{report.answer}</Markdown>
                </div>
                {report.trust_status && (
                  <div className="rp-trust">{t(`chat.trust.${report.trust_status.state}`)}</div>
                )}
              </section>

              {report.sources.length > 0 && (
                <section className="rp-section">
                  <h2>{t("research.sources_title", { n: report.sources.length })}</h2>
                  <ul className="rp-sources">
                    {report.sources.map((s, i) => <SourceRow key={i} src={s} />)}
                  </ul>
                </section>
              )}

              {report.references.length > 0 && (
                <section className="rp-section">
                  <h2>{t("research.references_title")}</h2>
                  <ul className="rp-references">
                    {report.references.map((r, i) => (
                      <li key={i} className="rp-reference">
                        <span className="rp-ref-kind">{t(`research.ref_${r.kind}`)}</span>
                        <button
                          className="rp-ref-term"
                          onClick={() => navigate(`/dictionary?q=${encodeURIComponent(r.term)}`)}
                        >
                          {r.term}
                        </button>
                        {r.detail && <span className="rp-ref-detail">{r.detail}</span>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
