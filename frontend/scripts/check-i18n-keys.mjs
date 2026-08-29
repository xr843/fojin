#!/usr/bin/env node
/**
 * Fail on `t("some.key")` where the key does not exist in the zh locale.
 *
 * The ratchet next door (scan-hardcoded-zh.mjs) catches Chinese text that never
 * went through i18n. This catches the opposite mistake: a key that went through
 * i18n and has nowhere to land. i18next renders a missing key as the key
 * itself, so the page shows a literal `common.cancel` — visible to every user,
 * invisible to typecheck, lint, and any test that does not assert on that exact
 * string. One shipped to production on 2026-08-29 (the Popconfirm cancel button
 * in ProfilePage) and was only caught by looking at the rendered page.
 *
 * zh is the reference locale: it is bundled synchronously in i18n.ts and is the
 * fallbackLng, so a key missing there is missing everywhere. Keys present in zh
 * but absent from another locale fall back to zh — degraded, not broken, and
 * out of scope here.
 *
 * Only string-literal keys are checked. `t(\`a.${b}\`)` and `t(someVar)` are
 * invisible to any static check and are left alone. A second argument makes the
 * call safe regardless — i18next treats it as the default value — so those are
 * skipped too.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = "src";
const LOCALE = "public/locales/zh/translation.json";

const known = new Set(Object.keys(JSON.parse(readFileSync(LOCALE, "utf8"))));

// t("key")            → checked
// t("key", "default") → skipped, the default renders
// t("key", { n: 1 })  → checked; interpolation options are not a default value
const CALL = /\bt\(\s*"([A-Za-z][\w.-]*)"\s*(,\s*(.))?/g;

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) yield p;
  }
}

const bad = [];
for (const file of walk(SRC)) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    for (const m of line.matchAll(CALL)) {
      const [, key, secondArg, firstChar] = m;
      if (secondArg && firstChar === '"') continue; // has a default value
      if (!known.has(key)) bad.push({ file, line: i + 1, key });
    }
  });
}

if (bad.length) {
  console.error(`✗ ${bad.length} translation key(s) used but not defined in ${LOCALE}:\n`);
  for (const b of bad) console.error(`  ${b.file}:${b.line}  t("${b.key}")`);
  console.error("\ni18next renders a missing key as the key itself — users would see the raw string.");
  console.error("Add the key to all three locales, or use an existing one.");
  process.exit(1);
}
console.log(`✓ i18n keys OK: every t("...") literal in ${SRC}/ exists in ${LOCALE}.`);
