/**
 * 后台「模块使用」的分组与漏斗定义（2026-11-24 重排）。
 *
 * 旧看板把 48 个英文事件名按次数平铺：一个人连点就能把一项顶上去（search_facet 44 次只有
 * 4 个访客），「出现」和「点开」混在一起（定位卡出现 592 次、点开 9 次），看不出哪个板块
 * 有人在用。这里按板块分组、成对的「出现→点开」合成一行算转化率；人数太少的折进「其他」。
 *
 * ⚠️ 新加埋点时：在下面对应板块补一行，并在三份 translation.json 补
 * admin_dashboard.module_usage.event.<事件名>（漏斗是 .funnel.<key>）。没登记的事件
 * 不会丢，会出现在「其他」里、显示原始事件名。
 */

export interface ModuleEvent {
  event_name: string;
  count: number;
  users: number;
}

type RowDef =
  | { kind: "single"; event: string }
  | { kind: "funnel"; key: string; from: string; to: string };

interface GroupDef {
  key: string;
  /** 异常类：整组标红，且不因人数少折进「其他」 */
  danger?: boolean;
  rows: RowDef[];
}

const one = (event: string): RowDef => ({ kind: "single", event });
const funnel = (key: string, from: string, to: string): RowDef => ({ kind: "funnel", key, from, to });

export const MODULE_GROUPS: GroupDef[] = [
  {
    key: "chat",
    rows: [
      one("chat"),
      funnel("paste_locate", "paste_locate_show", "paste_locate_click"),
      funnel("citation_preview", "citation_preview_show", "citation_preview_open"),
      funnel("commentary_excerpt", "commentary_excerpt_show", "commentary_excerpt_open"),
      one("citation_panel_open"),
      one("master_select"),
      one("master_link"),
      one("chat_regenerate"),
      one("xiaojin_chat"),
      one("study_memory_continue"),
      one("study_memory_save"),
    ],
  },
  {
    key: "reader",
    rows: [
      one("read"),
      one("read_section"),
      one("reader_select"),
      one("reader_dict_result"),
      one("reader_ask_xiaojin"),
      one("reader_ai_ask"),
      one("reader_ai_toggle"),
      one("reader_vernacular"),
      one("reader_cite_copy"),
      funnel("reader_excerpt", "reader_excerpt_open", "reader_excerpt_save"),
      one("read_sat_out"),
    ],
  },
  {
    key: "search",
    rows: [
      one("search"),
      one("search_facet"),
      one("search_source_show"),
      one("search_ask_ai"),
      one("cbeta-shortcut"),
      one("source_click"),
      one("sources_direct_search"),
    ],
  },
  {
    key: "home",
    rows: [
      one("home_card"),
      one("home_hot_tag"),
      one("home_recent_read"),
      one("home_daily"),
      one("daily_open_source"),
      one("daily_vernacular"),
      one("daily_ask"),
      one("daily_share"),
      funnel("community_invite", "community_invite_shown", "community_invite_dismiss"),
    ],
  },
  {
    key: "fojin_ai",
    rows: [
      one("ask_submit"),
      one("card_ask"),
      one("nav_click"),
      one("copy_install"),
      funnel("trace", "trace_submit", "trace_done"),
      one("trace_example"),
      one("trace_merge"),
      one("trace_ask"),
      one("trace_share"),
    ],
  },
  {
    key: "account",
    rows: [funnel("forgot_password", "forgot_password_open", "forgot_password_submit")],
  },
  {
    key: "errors",
    danger: true,
    rows: [one("chat_stream_error"), one("chat_recovered"), one("trace_error")],
  },
];

/** 只是另一事件的反面、单列没有信息量的事件：不显示 */
const HIDDEN_EVENTS = new Set(["citation_panel_close"]);

/** 人数低于这个数的行折进「其他」（异常组除外）：一两个人的点击不足以说明板块有人用 */
export const MIN_USERS = 3;

export interface UsageRow {
  key: string;
  kind: "single" | "funnel";
  /** i18n key；fallback 是原始事件名 */
  labelKey: string;
  fallback: string;
  users: number;
  count: number;
  toUsers?: number;
  toCount?: number;
  /** 漏斗按人数算的转化率（%），from 人数为 0 时为 null */
  rate?: number | null;
}

export interface UsageGroup {
  key: string;
  danger: boolean;
  rows: UsageRow[];
}

export function eventLabelKey(event: string): string {
  return `admin_dashboard.module_usage.event.${event.replace(/-/g, "_")}`;
}

function singleRow(ev: ModuleEvent): UsageRow {
  return {
    key: ev.event_name,
    kind: "single",
    labelKey: eventLabelKey(ev.event_name),
    fallback: ev.event_name,
    users: ev.users,
    count: ev.count,
  };
}

/** 把后端的平铺事件表排成分组；返回的 other 是人数过少或未登记的行，按人数降序。 */
export function groupModuleEvents(events: ModuleEvent[]): { groups: UsageGroup[]; other: UsageRow[] } {
  const byName = new Map(events.map((e) => [e.event_name, e]));
  const used = new Set<string>();
  const other: UsageRow[] = [];
  const groups: UsageGroup[] = [];

  for (const g of MODULE_GROUPS) {
    const rows: UsageRow[] = [];
    for (const def of g.rows) {
      if (def.kind === "single") {
        const ev = byName.get(def.event);
        used.add(def.event);
        if (!ev) continue;
        const row = singleRow(ev);
        if (!g.danger && row.users < MIN_USERS) other.push(row);
        else rows.push(row);
      } else {
        const from = byName.get(def.from);
        const to = byName.get(def.to);
        used.add(def.from);
        used.add(def.to);
        if (!from) {
          if (to) other.push(singleRow(to));
          continue;
        }
        const row: UsageRow = {
          key: def.key,
          kind: "funnel",
          labelKey: `admin_dashboard.module_usage.funnel.${def.key}`,
          fallback: `${def.from} → ${def.to}`,
          users: from.users,
          count: from.count,
          toUsers: to?.users ?? 0,
          toCount: to?.count ?? 0,
          rate: from.users > 0 ? Math.round(((to?.users ?? 0) / from.users) * 1000) / 10 : null,
        };
        if (!g.danger && row.users < MIN_USERS) other.push(row);
        else rows.push(row);
      }
    }
    if (rows.length > 0) groups.push({ key: g.key, danger: !!g.danger, rows });
  }

  for (const ev of events) {
    if (used.has(ev.event_name) || HIDDEN_EVENTS.has(ev.event_name)) continue;
    other.push(singleRow(ev));
  }
  other.sort((a, b) => b.users - a.users || b.count - a.count);
  return { groups, other };
}
