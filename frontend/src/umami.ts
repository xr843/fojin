// Self-hosters opt in by setting both VITE_UMAMI_URL and VITE_UMAMI_WEBSITE_ID
// at build time. Missing either one means no script is injected — no phone-home.
const url = import.meta.env.VITE_UMAMI_URL;
const websiteId = import.meta.env.VITE_UMAMI_WEBSITE_ID;

// Free text a visitor typed must not land in the analytics database. Umami
// records the whole URL, and /chat?q=<the question>, a passage pasted into
// search, or a citation's ?quote= carry exactly that (found 2026-11-22). Values
// of these params longer than this are dropped before sending; short ones —
// search terms, dictionary words — stay, as do utm_* and every other param.
const FREE_TEXT_PARAMS = ["q", "quote"];

const FREE_TEXT_MAX_CHARS = 20;

// Only these hosts report. A copy of the built bundle carries the website id, and
// lobster-ai.net ran one (2026-04/05) that sent 142 events into fojin's stats;
// local dev (localhost) added more. Umami's data-domains stops both at the source.
export const TRACKED_DOMAINS = "fojin.app,www.fojin.app";

export function scrubTrackedUrl(raw: string): string {
  if (!raw) return raw;
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return raw;
  }
  let changed = false;
  for (const name of FREE_TEXT_PARAMS) {
    const v = u.searchParams.get(name);
    if (v !== null && Array.from(v).length > FREE_TEXT_MAX_CHARS) {
      u.searchParams.delete(name);
      changed = true;
    }
  }
  return changed ? u.toString() : raw;
}

type UmamiPayload = { url?: string; referrer?: string; [key: string]: unknown };

/** Umami's data-before-send hook (called by name on window). */
function beforeSend(_type: string, payload: UmamiPayload): UmamiPayload {
  if (typeof payload.url === "string") payload.url = scrubTrackedUrl(payload.url);
  if (typeof payload.referrer === "string") payload.referrer = scrubTrackedUrl(payload.referrer);
  return payload;
}

if (url && websiteId) {
  (window as unknown as Record<string, unknown>).fojinUmamiBeforeSend = beforeSend;
  const script = document.createElement("script");
  script.defer = true;
  script.src = url;
  script.dataset.websiteId = websiteId;
  script.dataset.beforeSend = "fojinUmamiBeforeSend";
  script.dataset.domains = TRACKED_DOMAINS;
  document.head.appendChild(script);
}
