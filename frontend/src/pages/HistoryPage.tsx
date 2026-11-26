import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AutoComplete, Button, Drawer, Empty, Segmented, Spin, Tooltip } from "antd";
import { MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { localizeHan, scriptForLanguage } from "../utils/hanScript";
import { BANDS, TIMELINE_END, TIMELINE_START, dynastyAt } from "../data/historyDynasties";
import {
  aliveAt,
  fixZhuAfterSimplify,
  formatYears,
  layoutLanes,
  personSpan,
  SCHOOL_KEY,
  translationRiver,
  type HistoryData,
  type HistoryPerson,
  type PersonSpan,
} from "../utils/historyTimeline";
import TOURS_DATA from "../data/historyTours.json";
import { useEffectiveTheme } from "../hooks/useTheme";
import { useNarrowViewport } from "../hooks/useNarrowViewport";
import type { MapEdge, MapPoint } from "../components/history/HistoryMap";
import "../styles/history.css";

// 地图（maplibre 约 800KB）单独分包：长卷先出来，地图随后
const HistoryMap = lazy(() => import("../components/history/HistoryMap"));

/** 导览路线。step.p：上一站（师）在本路线里的序号，缺省为前一站——传承分叉时（临济下分黄龙、杨岐）画成树；
 *  gap：中间隔了几代（道邃→羲寂），连线画虚线。g：分组（禅宗五条归在一起）。 */
interface TourStep {
  id: string;
  y: number;
  t: string;
  /** 该站地点 [经度, 纬度, 地名]（DILA 地名库），说不准的不标 */
  pl?: [number, number, string];
  p?: number;
  gap?: boolean;
}
interface HistoryTour {
  id: string;
  g?: string;
  title: string;
  intro: string;
  steps: TourStep[];
}
// JSON 推断不出元组类型，按约定断言（historyTours.json 的格式见文件头 _note）
const TOURS = TOURS_DATA.tours as unknown as HistoryTour[];

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
  const L = useCallback((s: string) => fixZhuAfterSimplify(localizeHan(s, lang)), [lang]);
  const [params, setParams] = useSearchParams();
  const { data, isLoading, isError } = useQuery({ queryKey: ["history-people"], queryFn: fetchHistory, staleTime: Infinity });

  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [onlyTr, setOnlyTr] = useState(false);
  const [search, setSearch] = useState("");
  const selectedId = params.get("p");
  // 默认按宗派分泳道；?v=time 按年代混排
  const byYear = params.get("v") === "time";
  // 导览：?tour=chan&s=2（第 3 站）
  const tour = TOURS.find((x) => x.id === params.get("tour")) ?? null;
  const stepIdx = tour ? Math.min(Math.max(0, Number(params.get("s")) || 0), tour.steps.length - 1) : 0;
  const step = tour ? tour.steps[stepIdx] : null;
  const yParam = Number(params.get("y"));
  const cursor = params.get("y") && Number.isFinite(yParam) ? yParam : null;
  const scrollRef = useRef<HTMLDivElement>(null);
  // 窄于 1200px：地图默认收起、人物卡盖在长卷上
  const narrow = useNarrowViewport("(max-width: 1199px)");

  const px = ZOOMS[zoom];
  const byId = useMemo(() => new Map((data?.people ?? []).map((p) => [p.id, p])), [data]);
  const spans = useMemo(() => new Map((data?.people ?? []).map((p) => [p.id, personSpan(p)])), [data]);
  const shown = useMemo(() => (data?.people ?? []).filter((p) => !onlyTr || p.tr), [data, onlyTr]);

  const { items: placed, lanes, rows } = useMemo(() => {
    const labelFn = (p: HistoryPerson) => {
      const s = spans.get(p.id);
      const barPx = s ? (s.end - s.start) * px : 0;
      const labelPx = p.n.length * CHAR_PX + 10;
      return barPx >= labelPx ? 0 : labelPx;
    };
    return layoutLanes(shown, px, labelFn, byYear ? null : (p) => p.sc);
  }, [shown, px, spans, byYear]);

  const river = useMemo(() => translationRiver(data?.people ?? [], TIMELINE_START, TIMELINE_END, 10), [data]);
  const riverMax = Math.max(1, ...river);

  const selected = selectedId ? byId.get(selectedId) ?? null : null;
  const related = useMemo(() => new Set(selected ? [...selected.te, ...selected.st] : []), [selected]);

  const xOf = (year: number) => PAD + (year - TIMELINE_START) * px;
  // 人物卡开着时右边多留一块，最右端的人（印光、虚云）才能滚到卡片左边
  const width = PAD * 2 + (TIMELINE_END - TIMELINE_START) * px + (selected ? 480 : 0);
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

  // 深链 / 搜索选中 / 导览换站：这个人不在视野里就滚过去。右侧人物卡会挡住约 460px，横向可见区要扣掉；
  // 分宗派泳道后人可能在很下面，纵向也要判断（11-26 实测：?p=智顗 停在最上面的译经泳道）。
  const placedById = useMemo(() => new Map(placed.map((x) => [x.person.id, x])), [placed]);
  const ensureVisible = useCallback(
    (id: string, coveredRight: boolean) => {
      const pl = placedById.get(id);
      const el = scrollRef.current;
      if (!pl || !el) return;
      const covered = coveredRight ? Math.min(460, el.clientWidth * 0.5) : 0;
      const left = xOf(pl.span.start);
      const right = Math.min(xOf(pl.span.end), left + 200);
      const hVisible = left >= el.scrollLeft && right <= el.scrollLeft + el.clientWidth - covered;
      const rowTop = TOP + pl.row * ROW_H;
      const vVisible = rowTop >= el.scrollTop + TOP && rowTop + ROW_H <= el.scrollTop + el.clientHeight;
      if (hVisible && vVisible) return;
      el.scrollTo({
        left: hVisible ? el.scrollLeft : Math.max(0, left - (el.clientWidth - covered) / 3),
        top: vVisible ? el.scrollTop : Math.max(0, rowTop - TOP - 3 * ROW_H),
      });
    },
    // xOf 只依赖 px
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [placedById, px],
  );
  useEffect(() => {
    // 宽屏时页面右侧给人物卡让位（history-page--card），长卷不被挡；窄屏人物卡盖在上面，要扣掉
    if (selectedId) ensureVisible(selectedId, narrow);
  }, [selectedId, ensureVisible, narrow]);
  useEffect(() => {
    if (step && !selectedId) ensureVisible(step.id, false);
    // 只在换站时滚；关掉人物卡不要把视野拽回来
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step?.id, placedById]);

  const startTour = useCallback(
    (id: string | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete("p");
          next.delete("s");
          if (id) {
            next.set("tour", id);
            next.delete("y");
          } else next.delete("tour");
          return next;
        },
        { replace: true },
      );
      if (id) track("history_tour", { id });
    },
    [setParams],
  );
  const goStep = useCallback(
    (k: number) => {
      if (!tour) return;
      const s2 = Math.min(Math.max(0, k), tour.steps.length - 1);
      setParam("s", String(s2));
      track("history_tour_step", { id: tour.id, s: s2 });
    },
    [tour, setParam],
  );
  // 导览中左右方向键换站（焦点在输入框时不抢）
  useEffect(() => {
    if (!tour) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "ArrowRight") goStep(stepIdx + 1);
      else if (e.key === "ArrowLeft") goStep(stepIdx - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tour, stepIdx, goStep]);
  const tourOrder = useMemo(() => new Map((tour?.steps ?? []).map((x, i) => [x.id, i])), [tour]);


  // 首次打开：没指定人也没指定年时，停在东晉—唐（佛教史最密的一段）
  const initialScrolled = useRef(false);
  useEffect(() => {
    if (initialScrolled.current || !data || !scrollRef.current) return;
    initialScrolled.current = true;
    // 有人物或导览时由上面的 ensureVisible 负责定位，这里不能再把视野拽回 520 年
    if (!selectedId && !tour) scrollToYear(cursor ?? 520);
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

  // ---- 地图：随导览 / 选中的人 / 游标年份变 ----
  const dark = useEffectiveTheme() === "dark";
  const [mapOpen, setMapOpen] = useState<boolean | null>(null);
  const showMap = mapOpen ?? !narrow;
  const mapModel = useMemo((): { points: MapPoint[]; edges: MapEdge[]; focus: Array<[number, number]>; caption: string } => {
    const people = data?.people ?? [];
    const ll = (v: { 0: number; 1: number }) => [v[0], v[1]] as [number, number];
    if (tour) {
      const pts: MapPoint[] = [];
      const edges: MapEdge[] = [];
      tour.steps.forEach((st, i) => {
        if (!st.pl) return;
        const who = byId.get(st.id);
        pts.push({ id: `t${i}`, lon: st.pl[0], lat: st.pl[1], label: `${L(who?.n ?? "")} · ${L(st.pl[2])}`, kind: i === stepIdx ? "current" : "tour", n: i + 1, person: st.id });
        // 连到最近一个有地点的上游（师）
        let p = st.p ?? i - 1;
        while (p >= 0 && !tour.steps[p]?.pl) p = tour.steps[p]?.p ?? p - 1;
        const par = p >= 0 ? tour.steps[p] : null;
        if (i > 0 && par?.pl) edges.push({ from: ll(par.pl), to: ll(st.pl), gap: st.gap });
      });
      const cur = tour.steps[stepIdx]?.pl;
      return {
        points: pts,
        edges,
        focus: stepIdx === 0 || !cur ? pts.map((x) => [x.lon, x.lat] as [number, number]) : [ll(cur)],
        caption: t("history.map_tour"),
      };
    }
    if (selected) {
      const pts: MapPoint[] = [];
      const edges: MapEdge[] = [];
      if (selected.o) pts.push({ id: "o", lon: selected.o[0], lat: selected.o[1], label: `${L(selected.n)} · ${t("history.map_origin")} ${L(selected.o[2])}`, kind: "focus", person: selected.id });
      if (selected.bu) pts.push({ id: "bu", lon: selected.bu[0], lat: selected.bu[1], label: `${t("history.map_burial")} ${L(selected.bu[2])}`, kind: "burial", person: selected.id });
      for (const rid of [...selected.te, ...selected.st]) {
        const r = byId.get(rid);
        if (!r?.o) continue;
        pts.push({ id: `r${rid}`, lon: r.o[0], lat: r.o[1], label: L(r.n), kind: "related", person: rid });
        if (selected.o) edges.push({ from: ll(r.o), to: ll(selected.o) });
      }
      return { points: pts, edges, focus: pts.map((x) => [x.lon, x.lat] as [number, number]), caption: t("history.map_person") };
    }
    if (cursor !== null) {
      const pts: MapPoint[] = alive
        .filter((p) => p.o)
        .map((p) => ({ id: p.id, lon: p.o![0], lat: p.o![1], label: L(p.n), kind: "alive" as const, person: p.id }));
      return { points: pts, edges: [], focus: pts.length > 1 ? pts.map((x) => [x.lon, x.lat] as [number, number]) : [], caption: t("history.map_alive", { y: cursor }) };
    }
    return {
      points: people.filter((p) => shown.includes(p) && p.o).map((p) => ({ id: p.id, lon: p.o![0], lat: p.o![1], label: L(p.n), kind: "base" as const, person: p.id })),
      edges: [],
      focus: [],
      caption: t("history.map_base"),
    };
  }, [data, tour, stepIdx, selected, cursor, alive, shown, byId, L, t]);

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
    <div className={`history-page${selected && !narrow ? " history-page--card" : ""}`}>
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
          value={byYear ? "time" : "school"}
          onChange={(v) => {
            setParam("v", v === "time" ? "time" : null);
            track("history_view", { view: String(v) });
          }}
          options={[
            { label: t("history.view_by_school"), value: "school" },
            { label: t("history.view_by_year"), value: "time" },
          ]}
        />
        <Segmented
          value={onlyTr ? "tr" : "all"}
          onChange={(v) => setOnlyTr(v === "tr")}
          options={[
            { label: t("history.filter_all"), value: "all" },
            { label: t("history.filter_translators"), value: "tr" },
          ]}
        />
        <Button size="small" onClick={() => { setMapOpen(!showMap); track("history_map_toggle", { open: String(!showMap) }); }}>
          {showMap ? t("history.map_hide") : t("history.map_show")}
        </Button>
        <span className="history-zoom">
          <Tooltip title={t("history.zoom_out")}>
            <Button size="small" icon={<MinusOutlined />} aria-label={t("history.zoom_out")} disabled={zoom === 0} onClick={() => setZoom((z) => Math.max(0, z - 1))} />
          </Tooltip>
          <Tooltip title={t("history.zoom_in")}>
            <Button size="small" icon={<PlusOutlined />} aria-label={t("history.zoom_in")} disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom((z) => Math.min(ZOOMS.length - 1, z + 1))} />
          </Tooltip>
        </span>
      </div>

      <div className="history-tours" role="group" aria-label={t("history.tours")}>
        <span className="history-tours-k">{t("history.tours")}</span>
        {TOURS.map((x, i) => {
          const chip = (
            <button
              key={x.id}
              type="button"
              className={`history-chip${tour?.id === x.id ? " history-chip--on" : ""}`}
              aria-pressed={tour?.id === x.id}
              onClick={() => startTour(tour?.id === x.id ? null : x.id)}
            >
              {L(x.title)}
            </button>
          );
          if (!x.g) return chip;
          if (TOURS[i - 1]?.g === x.g) return null;
          // 同组的路线收在一个框里，前面写组名
          return (
            <span key={`g-${x.g}`} className="history-tours-group">
              <span className="history-tours-gname">{L(x.g)}</span>
              {TOURS.filter((y) => y.g === x.g).map((y) => (
                <button
                  key={y.id}
                  type="button"
                  className={`history-chip${tour?.id === y.id ? " history-chip--on" : ""}`}
                  aria-pressed={tour?.id === y.id}
                  onClick={() => startTour(tour?.id === y.id ? null : y.id)}
                >
                  {L(y.title)}
                </button>
              ))}
            </span>
          );
        })}
      </div>

      {tour && step ? (
        <div className="history-tour-panel" role="status">
          <div className="history-tour-head">
            <strong>{L(tour.g ? `${tour.g} · ${tour.title}` : tour.title)}</strong>
            <span className="history-tour-intro">{L(tour.intro)}</span>
            <button type="button" className="history-chip history-chip--clear" onClick={() => startTour(null)}>
              {t("history.tour_exit")}
            </button>
          </div>
          <div className="history-tour-step">
            <span className="history-tour-count">{t("history.tour_step", { k: stepIdx + 1, n: tour.steps.length })}</span>
            <button type="button" className="history-tour-name" onClick={() => openPerson(step.id, "tour")}>
              {L(byId.get(step.id)?.n ?? "")}
            </button>
            <span className="history-tour-years">{byId.get(step.id) ? formatYears(byId.get(step.id)!, t("history.approx")) : ""}</span>
            <span className="history-tour-text">{L(step.t)}</span>
            <span className="history-tour-nav">
              <Button size="small" disabled={stepIdx === 0} onClick={() => goStep(stepIdx - 1)}>
                {t("history.tour_prev")}
              </Button>
              <Button size="small" type="primary" disabled={stepIdx === tour.steps.length - 1} onClick={() => goStep(stepIdx + 1)}>
                {t("history.tour_next")}
              </Button>
            </span>
          </div>
        </div>
      ) : (
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
      )}

      {isLoading ? (
        <div className="history-loading"><Spin /></div>
      ) : isError || !data ? (
        <Empty description={t("history.load_error")} />
      ) : (
        <div className={`history-main${showMap ? " history-main--map" : ""}`}>
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
            {lanes.map((l, i) => (
              <div
                key={l.key}
                className={`history-lane${i % 2 ? " history-lane--alt" : ""}`}
                style={{ top: TOP + l.firstRow * ROW_H, height: l.rows * ROW_H, width }}
              >
                <span className="history-lane-label">
                  {t(`history.school.${SCHOOL_KEY[l.key] ?? "other"}`)}
                  <small>{l.count}</small>
                </span>
              </div>
            ))}
            {cursor !== null && <div className="history-cursor" style={{ left: xOf(cursor), height }} />}
            {tour && !selected && <TourPath steps={tour.steps} current={step?.id ?? ""} placedById={placedById} xOf={xOf} width={width} height={height} />}
            {selected && (
              <LineageLines
                selectedId={selected.id}
                related={[...selected.te.map((id) => [id, "te"] as const), ...selected.st.map((id) => [id, "st"] as const)]}
                placedById={placedById}
                xOf={xOf}
                width={width}
                height={height}
              />
            )}
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
                !selected && tour && !tourOrder.has(p.id) ? "is-dim" : "",
                !selected && tour && tourOrder.has(p.id) ? "is-tour" : "",
                !selected && step?.id === p.id ? "is-tour-current" : "",
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
                  {!selected && tourOrder.has(p.id) && <span className="history-tour-num">{(tourOrder.get(p.id) ?? 0) + 1}</span>}
                  <span className={inside ? "history-bar-name" : "history-bar-name history-bar-name--out"} style={inside ? undefined : { left: w + 4 }}>
                    {L(p.n)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        {showMap && (
          <aside className="history-map" aria-label={t("history.map_title")}>
            <div className="history-map-caption">{mapModel.caption}</div>
            <Suspense fallback={<div className="history-loading"><Spin /></div>}>
              <HistoryMap
                points={mapModel.points}
                edges={mapModel.edges}
                focus={mapModel.focus}
                dark={dark}
                traditional={scriptForLanguage(lang) === "traditional"}
                onPick={(id) => openPerson(id, "map")}
                attribution={t("history.map_attribution")}
              />
            </Suspense>
          </aside>
        )}
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
        // 不加遮罩：卡片开着时长卷仍可见、可点（看师承连线、换人）
        mask={false}
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
        {[L(p.dy), years || t("history.years_unknown"), role, t(`history.school.${SCHOOL_KEY[p.sc] ?? "other"}`)].filter(Boolean).join(" · ")}
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

/** 选中一个人时，把他和师、弟子的条子连起来：师在上游用实线，弟子用虚线。 */
function LineageLines({
  selectedId,
  related,
  placedById,
  xOf,
  width,
  height,
}: {
  selectedId: string;
  related: ReadonlyArray<readonly [string, "te" | "st"]>;
  placedById: Map<string, { span: PersonSpan; row: number }>;
  xOf: (year: number) => number;
  width: number;
  height: number;
}) {
  const me = placedById.get(selectedId);
  if (!me) return null;
  const y = (row: number) => TOP + row * ROW_H + 9;
  const x1 = xOf(me.span.start) + 6;
  const y1 = y(me.row);
  return (
    <svg className="history-lineage" width={width} height={height} aria-hidden>
      {related.map(([id, kind]) => {
        const o = placedById.get(id);
        if (!o) return null;
        const x2 = Math.min(Math.max(x1, xOf(o.span.start) + 6), xOf(o.span.end) - 6);
        const y2 = y(o.row);
        const mid = (y1 + y2) / 2;
        return (
          <path
            key={id}
            d={`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`}
            className={kind === "te" ? "history-lineage-te" : "history-lineage-st"}
          />
        );
      })}
    </svg>
  );
}

/** 导览：按师承把路线上的人连起来——每站连到它的上一站（step.p，缺省为前一站），分叉时自然成树；隔代的画虚线。 */
function TourPath({
  steps,
  current,
  placedById,
  xOf,
  width,
  height,
}: {
  steps: TourStep[];
  current: string;
  placedById: Map<string, { span: PersonSpan; row: number }>;
  xOf: (year: number) => number;
  width: number;
  height: number;
}) {
  const pt = (id: string) => {
    const pl = placedById.get(id);
    return pl ? { x: xOf(pl.span.start) + 8, y: TOP + pl.row * ROW_H + 9 } : null;
  };
  const edges = steps.flatMap((st, i) => {
    if (i === 0) return [];
    const parent = steps[st.p ?? i - 1];
    const a = parent ? pt(parent.id) : null;
    const b = pt(st.id);
    return a && b ? [{ key: `${i}`, a, b, gap: !!st.gap }] : [];
  });
  const cur = pt(current);
  return (
    <svg className="history-lineage history-tour-path" width={width} height={height} aria-hidden>
      {edges.map(({ key, a, b, gap }) => (
        <path key={key} d={`M ${a.x} ${a.y} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y}`} className={gap ? "history-tour-gap" : undefined} />
      ))}
      {cur && <circle cx={cur.x} cy={cur.y} r={13} />}
    </svg>
  );
}
