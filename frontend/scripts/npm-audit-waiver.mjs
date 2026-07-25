// CI gate: `npm audit` for production deps, with a documented per-advisory waiver.
// npm audit has no built-in per-advisory ignore (unlike pip-audit's --ignore-vuln),
// so we parse its JSON and fail on any advisory NOT in the waiver list below.
import { execSync } from "node:child_process";

// GHSA-qwww-vcr4-c8h2 — React Router "RSC Mode CSRF" (affects react-router 7.12.0–8.2.0).
// Only exploitable in React Router's RSC / framework mode. FoJin runs LIBRARY mode
// (<BrowserRouter> + ReactDOM.createRoot in src/main.tsx; no react-router.config,
// no @react-router/dev), so the RSC action path does not exist here — not exposed.
// No patched 7.x/8.x is published yet (latest 7.18.1 is still in-range); npm's only
// "fix" downgrades to 7.11.0, which re-introduces GHSA-wrjc-x8rr-h8h6 /
// GHSA-337j-9hxr-rhxg that the v7 upgrade (#1042) fixed. Re-audit and drop this
// waiver once react-router ships a fixed release (>8.2.0 or a 7.x patch).
const WAIVED = new Set(["GHSA-qwww-vcr4-c8h2"]);

let json;
try {
  json = execSync("npm audit --omit=dev --json", { encoding: "utf8" });
} catch (e) {
  // npm audit exits non-zero when vulnerabilities exist; the JSON is still on stdout.
  json = e.stdout;
}

const report = JSON.parse(json);
const vulns = report.vulnerabilities || {};
const unwaived = new Set();
for (const [name, v] of Object.entries(vulns)) {
  for (const via of v.via) {
    if (typeof via !== "object" || !via.url) continue; // string via = transitive dep name
    const id = via.url.split("/").pop();
    if (!WAIVED.has(id)) unwaived.add(`${id} (${via.severity}) via ${name}`);
  }
}

if (unwaived.size) {
  console.error("npm audit: un-waived advisories found:\n  " + [...unwaived].join("\n  "));
  process.exit(1);
}
console.log(
  Object.keys(vulns).length
    ? "npm audit: only the waived advisory (GHSA-qwww-vcr4-c8h2) is present — OK."
    : "npm audit: no vulnerabilities — OK.",
);
