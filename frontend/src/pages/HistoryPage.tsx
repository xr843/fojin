import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AutoComplete, Button, Drawer, Empty, Segmented, Spin, Tooltip } from "antd";
import { MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { localizeHan } from "../utils/hanScript";
import { BANDS, TIMELINE_END, TIMELINE_START, dynastyAt } from "../data/historyDynasties";
import {
  aliveAt,
  formatYears,
  packRows,
  personSpan,
  translationRiver,
  type HistoryData,
  type HistoryPerson,
  type PersonSpan,
} from "../utils/historyTimeline";
import "../styles/history.css";

const ZOOMS = [1, 1.5, 2.2, 3.2, 4.6, 6.5];
const DEFAULT_ZOOM = 2;
const AXIS_H = 26;
const BAND_H = 22;
const RIVER_H = 44;
const ROW_H = 24;
const TOP = AXIS_H + BAND_H * 2 + RIVER_H + 10;
const PAD = 24;
const CHAR_PX = 13;

function track(name: string, data?: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(name, data);
}

async function fetchHistory(): Promise<HistoryData> {
  const r = await fetch("/history-people.json");
  if (!r.ok) throw new Error(`history data ${r.status}`);
  return r.json();
}

/**
 * 中国佛教史长卷：从东汉到民国，核心人物的一生排成一条时间轴（借鉴「江山时序」的拖时间轴读史）。
 * 点名字看生平、师承、僧传本传原文与藏内著译；点时间轴看那一年谁在世。
 * 数据：DILA 人名规范库（CC BY-SA 3.0），见 backend/scripts/build_history_timeline.py。
 */
export default function HistoryPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const L = useCallback((s: string) => localizeHan(s, lang), [lang]);
  const [params, setParams] = useSearchParams();
  const { data, isLoading, isError } = useQuery({ queryKey: ["history-people"], queryFn: fetchHistory, staleTime: Infinity });

  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [onlyTr, setOnlyTr] = useState(false);
  const [search, setSearch] = useState("");
  const selectedId = params.get("p");
  const yParam = Number(params.get("y"));
  const cursor = params.get("y") && Number.isFinite(yParam) ? yParam : null;
  const scrollRef = useRef<HTMLDivElement>(null);

  const px = ZOOMS[zoom];
  const byId = useMemo(() => new Map((data?.people ?? []).map((p) => [p.id, p])), [data]);
  const spans = useMemo(() => new Map((data?.people ?? []).map((p) => [p.id, personSpan(p)])), [data]);
  const shown = useMemo(() => (data?.people ?? []).filter((p) => !onlyTr || p.tr), [data, onlyTr]);

  const { placed, rows } = useMemo(() => {
    return packRows(shown, px, (p) => {
      const s = spans.get(p.id);
      const barPx = s ? (s.end - s.start) * px : 0;
      const labelPx = p.n.length * CHAR_PX + 10;
      return barPx >= labelPx ? 0 : labelPx;
    });
  }, [shown, px, spans]);

  const river = useMemo(() => translationRiver(data?.people ?? [], TIMELINE_START, TIMELINE_END, 10), [data]);
  const riverMax = Math.max(1, ...river);

  const selected = selectedId ? byId.get(selectedId) ?? null : null;
  const related = useMemo(() => new Set(selected ? [...selected.te, ...selected.st] : []), [selected]);

  const xOf = (year: number) => PAD + (year - TIMELINE_START) * px;
  const width = PAD * 2 + (TIMELINE_END - TIMELINE_START) * px;
  const height = TOP + rows * ROW_H + 16;

  const setParam = useCallback(
    (key: string, value: string | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value === null) next.delete(key);
          else next.set(key, value);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const scrollToYear = useCallback(
    (year: number, top?: number) => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ left: Math.max(0, xOf(year) - el.clientWidth / 2), top: top ?? el.scrollTop });
    },
    // xOf 只依赖 px
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [px],
  );

  const openPerson = useCallback(
    (id: string, via: string) => {
      setParam("p", id);
      track("history_open_person", { id, via });
    },
    [setParam],
  );

  // 深链 / 搜索选中：把这个人滚到视野中间
  const placedById = useMemo(() => new Map(placed.map((x) => [x.person.id, x])), [placed]);
  useEffect(() => {
    if (!selectedId) return;
    const pl = placedById.get(selectedId);
    if (!pl) return;
    const el = scrollRef.current;
    const rowTop = TOP + pl.row * ROW_H;
    const visible = el && el.scrollLeft < xOf(pl.span.start) && xOf(pl.span.end) < el.scrollLeft + el.clientWidth;
    if (!visible) scrollToYear((pl.span.start + pl.span.end) / 2, Math.max(0, rowTop - 120));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, placedById]);

  // 首次打开：没指定人也没指定年时，停在东晉—唐（佛教史最密的一段）
  const initialScrolled = useRef(false);
  useEffect(() => {
    if (initialScrolled.current || !data || !scrollRef.current) return;
    initialScrolled.current = true;
    if (!selectedId) scrollToYear(cursor ?? 520);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const onCanvasClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest(".history-bar")) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const year = Math.round((e.clientX - rect.left - PAD) / px + TIMELINE_START);
    if (year < TIMELINE_START || year > TIMELINE_END) return;
    setParam("y", String(year));
    track("history_cursor", { year });
  };

  const alive = useMemo(
    () => (cursor === null ? [] : shown.filter((p) => aliveAt(spans.get(p.id) ?? null, cursor))),
    [cursor, shown, spans],
  );

  const options = useMemo(() => {
    const q = search.trim();
    if (!q || !data) return [];
    const hits = data.people.filter((p) =>
      [p.n, p.dn, ...p.alt].some((n) => n.includes(q) || L(n).includes(q) || localizeHan(n, "zh-Hant").includes(q)),
    );
    return hits.slice(0, 20).map((p) => ({
      value: p.id,
      label: `${L(p.n)} · ${L(p.dy)} ${formatYears(p, t("history.approx"))}`,
    }));
  }, [search, data, L, t]);

  const ticks = useMemo(() => {
    const step = px >= 4 ? 25 : px >= 2 ? 50 : 100;
    const out: number[] = [];
    for (let y = Math.ceil(TIMELINE_START / step) * step; y <= TIMELINE_END; y += step) out.push(y);
    return out;
  }, [px]);

  const kindNote = (s: PersonSpan | null | undefined) =>
    s && s.kind !== "full" ? t(`history.kind_${s.kind}`) : null;

  return (
    <div className="history-page">
      <Helmet>
        <title>{`${t("history.title")} - ${t("app.name")}`}</title>
        <meta name="description" content={t("history.meta_desc")} />
      </Helmet>

      <header className="history-head">
        <div>
          <h1 className="history-title">{t("history.title")}</h1>
          <p className="history-sub">{t("history.subtitle", { n: data?.people.length ?? 300 })}</p>
        </div>
        <nav className="history-views" aria-label={t("history.views")}>
          <span className="history-view history-view--on">{t("history.view_timeline")}</span>
          <Link className="history-view" to="/kg">
            {t("history.view_graph")}
          </Link>
        </nav>
      </header>

      <div className="history-tools">
        <AutoComplete
          className="history-search"
          options={options}
          value={search}
          onChange={setSearch}
          onSelect={(id: string) => {
            setSearch("");
            openPerson(id, "search");
          }}
          placeholder={t("history.search_placeholder")}
          aria-label={t("history.search_placeholder")}
          allowClear
        />
        <Segmented
          value={onlyTr ? "tr" : "all"}
          onChange={(v) => setOnlyTr(v === "tr")}
          options={[
            { label: t("history.filter_all"), value: "all" },
            { label: t("history.filter_translators"), value: "tr" },
          ]}
        />
        <span className="history-zoom">
          <Tooltip title={t("history.zoom_out")}>
            <Button size="small" icon={<MinusOutlined />} aria-label={t("history.zoom_out")} disabled={zoom === 0} onClick={() => setZoom((z) => Math.max(0, z - 1))} />
          </Tooltip>
          <Tooltip title={t("history.zoom_in")}>
            <Button size="small" icon={<PlusOutlined />} aria-label={t("history.zoom_in")} disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom((z) => Math.min(ZOOMS.length - 1, z + 1))} />
          </Tooltip>
        </span>
      </div>

      <div className="history-cursor-bar" role="status">
        {cursor === null ? (
          <span className="history-hint">{t("history.cursor_prompt")}</span>
        ) : (
          <>
            <strong>{t("history.cursor", { y: cursor, d: L(dynastyAt(cursor)?.name ?? ""), n: alive.length })}</strong>
            <button type="button" className="history-chip history-chip--clear" onClick={() => setParam("y", null)} aria-label={t("history.clear_cursor")}>
              ×
            </button>
            <span className="history-alive">
              {alive.length === 0
                ? t("history.cursor_none")
                : alive.slice(0, 40).map((p) => (
                    <button key={p.id} type="button" className="history-chip" onClick={() => openPerson(p.id, "cursor")}>
                      {L(p.n)}
                    </button>
                  ))}
            </span>
          </>
        )}
      </div>

      {isLoading ? (
        <div className="history-loading"><Spin /></div>
      ) : isError || !data ? (
        <Empty description={t("history.load_error")} />
      ) : (
        <div className="history-scroll" ref={scrollRef}>
          <div className="history-canvas" style={{ width, height }} onClick={onCanvasClick}>
            {ticks.map((y) => (
              <div key={y} className="history-tick" style={{ left: xOf(y) }} />
            ))}
            {/* 刻度、朝代、译经长河：纵向滚动时吸顶，横向跟着长卷走 */}
            <div className="history-header" style={{ width, height: TOP - 6 }}>
              {ticks.map((y) => (
                <span key={y} className="history-tick-label" style={{ left: xOf(y) }}>
                  {y}
                </span>
              ))}
              {BANDS.map((b) => (
                <div
                  key={`${b.name}-${b.from}`}
                  className={`history-band history-band--${b.row}`}
                  style={{ left: xOf(b.from), width: (b.to - b.from) * px, top: AXIS_H + b.row * BAND_H }}
                  title={`${L(b.name)} ${b.from}–${b.to}`}
                >
                  {(b.to - b.from) * px > L(b.name).length * 12 + 6 ? L(b.name) : ""}
                </div>
              ))}
              <div className="history-river" style={{ top: AXIS_H + BAND_H * 2 + 4, height: RIVER_H }} title={t("history.river_hint")}>
                <span className="history-river-label">{t("history.river")}</span>
                {river.map((v, i) =>
                  v > 0 ? (
                    <i
                      key={i}
                      style={{ left: xOf(TIMELINE_START + i * 10), width: Math.max(1, 10 * px - 1), height: Math.max(1, (v / riverMax) * (RIVER_H - 4)) }}
                    />
                  ) : null,
                )}
              </div>
            </div>
            {cursor !== null && <div className="history-cursor" style={{ left: xOf(cursor), height }} />}
            {placed.map(({ person: p, span, row }) => {
              const left = xOf(span.start);
              const w = Math.max(3, (span.end - span.start) * px);
              const inside = w >= p.n.length * CHAR_PX + 10;
              const cls = [
                "history-bar",
                `history-bar--${span.kind}`,
                p.tr ? "history-bar--tr" : p.monk ? "history-bar--monk" : "history-bar--lay",
                selectedId === p.id ? "is-selected" : "",
                related.has(p.id) ? "is-related" : "",
                selected && selectedId !== p.id && !related.has(p.id) ? "is-dim" : "",
              ].join(" ");
              return (
                <button
                  key={p.id}
                  type="button"
                  className={cls}
                  style={{ left, top: TOP + row * ROW_H, width: w }}
                  title={`${L(p.n)} ${formatYears(p, t("history.approx")) || t("history.years_unknown")} · ${L(p.dy)}`}
                  onClick={() => openPerson(p.id, "bar")}
                >
                  <span className={inside ? "history-bar-name" : "history-bar-name history-bar-name--out"} style={inside ? undefined : { left: w + 4 }}>
                    {L(p.n)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <p className="history-legend">
        <span><i className="history-swatch history-bar--tr" />{t("history.legend_translator")}</span>
        <span><i className="history-swatch history-bar--monk" />{t("history.legend_monk")}</span>
        <span><i className="history-swatch history-bar--lay" />{t("history.legend_lay")}</span>
        <span><i className="history-swatch history-swatch--approx" />{t("history.legend_approx")}</span>
      </p>
      <p className="history-attrib">
        {t("history.attribution_before")}
        <a href="https://authority.dila.edu.tw/person/" target="_blank" rel="noopener noreferrer">
          {t("history.attribution_source")}
        </a>
        {t("history.attribution_after")}
        <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 3.0</a>
        {t("history.attribution_end")}
      </p>

      <Drawer
        open={!!selected}
        onClose={() => setParam("p", null)}
        width="min(440px, 100vw)"
        title={selected ? L(selected.n) : ""}
        destroyOnHidden
      >
        {selected && (
          <PersonCard
            p={selected}
            span={spans.get(selected.id) ?? null}
            byId={byId}
            L={L}
            kindNote={kindNote(spans.get(selected.id))}
            onOpen={(id) => openPerson(id, "lineage")}
          />
        )}
      </Drawer>
    </div>
  );
}

function PersonCard({
  p,
  span,
  byId,
  L,
  kindNote,
  onOpen,
}: {
  p: HistoryPerson;
  span: PersonSpan | null;
  byId: Map<string, HistoryPerson>;
  L: (s: string) => string;
  kindNote: string | null;
  onOpen: (id: string) => void;
}) {
  const { t } = useTranslation();
  const years = formatYears(p, t("history.approx"));
  const role = p.tr ? t("history.legend_translator") : p.monk ? t("history.legend_monk") : t("history.legend_lay");
  const people = (ids: string[]) =>
    ids
      .map((id) => byId.get(id))
      .filter((x): x is HistoryPerson => !!x)
      .map((x) => (
        <button key={x.id} type="button" className="history-chip" onClick={() => onOpen(x.id)}>
          {L(x.n)}
        </button>
      ));
  return (
    <div className="history-card">
      <p className="history-card-meta">
        {[L(p.dy), years || t("history.years_unknown"), role].filter(Boolean).join(" · ")}
        {span && span.kind !== "full" && kindNote && <span className="history-card-note">{kindNote}</span>}
      </p>
      {(p.dn !== p.n || p.alt.length > 0) && (
        <p className="history-card-alt">
          {t("history.alt_names")}
          {[p.dn !== p.n ? p.dn : null, ...p.alt].filter(Boolean).slice(0, 6).map((n) => L(n as string)).join("、")}
        </p>
      )}
      {p.bio && <p className="history-card-bio">{L(p.bio)}</p>}

      {(p.te.length > 0 || p.st.length > 0) && (
        <section>
          {p.te.length > 0 && (
            <div className="history-card-row">
              <span className="history-card-k">{t("history.teachers")}</span>
              {people(p.te)}
            </div>
          )}
          {p.st.length > 0 && (
            <div className="history-card-row">
              <span className="history-card-k">{t("history.students")}</span>
              {people(p.st)}
            </div>
          )}
        </section>
      )}

      {(p.bios.length > 0 || p.men.length > 0) && (
        <section>
          <h4>{p.bios.length > 0 ? t("history.bios") : t("history.mentions")}</h4>
          <ul className="history-card-links">
            {(p.bios.length > 0 ? p.bios : p.men).map((b) => (
              <li key={b.u}>
                <Link to={b.u} onClick={() => track("history_link", { kind: p.bios.length ? "bio" : "mention" })}>
                  {L(b.t)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {p.works.length > 0 && (
        <section>
          <h4>{t("history.works")}</h4>
          <ul className="history-card-links history-card-links--works">
            {p.works.map((w) => (
              <li key={w.u}>
                <Link to={w.u} onClick={() => track("history_link", { kind: "work" })}>
                  {L(w.t)}
                </Link>
                <span className="history-card-cid">{w.c}</span>
              </li>
            ))}
          </ul>
          {p.wn > p.works.length && <p className="history-card-more">{t("history.works_more", { n: p.wn, m: p.works.length })}</p>}
        </section>
      )}

      <p className="history-card-src">
        {t("history.bio_source")}
        <a href={`https://authority.dila.edu.tw/person/search.php?aid=${p.id}`} target="_blank" rel="noopener noreferrer">
          {t("history.dila_link")}
        </a>
      </p>
    </div>
  );
}
