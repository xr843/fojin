// CI gate: `npm audit` for production deps, with a documented per-advisory waiver.
// npm audit has no built-in per-advisory ignore (unlike pip-audit's --ignore-vuln),
// so we parse its JSON and fail on any advisory NOT in the waiver list below.
import { execSync } from "node:child_process";

// Currently empty: every production advisory is fixed upstream, so the gate is a
// plain `npm audit --omit=dev`. The waiver mechanism is kept because npm gives us
// no other way to accept a single advisory — add an entry only with a comment
// stating why it is not exposed here and what release would let us drop it.
//
// Previously waived: GHSA-qwww-vcr4-c8h2 (React Router "RSC Mode CSRF"), dropped
// when react-router 8.3.0 shipped the fix — see the v8 upgrade PR.
const WAIVED = new Set([]);

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
    ? `npm audit: only waived advisories are present (${[...WAIVED].join(", ")}) — OK.`
    : "npm audit: no vulnerabilities — OK.",
);
