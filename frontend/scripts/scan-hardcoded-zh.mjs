#!/usr/bin/env node
/**
 * Scan src/ for hardcoded Chinese strings that should go through i18n t().
 *
 * Why: the en/zh-Hant locales only work when every user-visible string is a
 * translation key. Hardcoded Chinese silently renders as-is in all locales —
 * issue #657 was reported by an English user who hit exactly this on the
 * search page. This scanner is the regression gate so the next page never
 * ships untranslated.
 *
 * Ratchet mode: scripts/i18n-baseline.json records the known per-file count
 * of pre-existing violations (the "debt inventory"). CI fails only when a
 * file EXCEEDS its baseline — paying debt down is allowed without ceremony,
 * adding new debt is not. After fixing a page, run with --update to lower
 * the baseline so it can't regress.
 *
 * Exemptions:
 *   - anything inside a t(...) call (keys like region.中国 are legitimate)
 *   - comments, import paths, type space (AST-level, automatic)
 *   - test files (*.test.*, src/test/)
 *   - a line ending with  // i18n-exempt  (internal data values, e.g. the
 *     normalizeRegion comparison literals that never render directly)
 *
 * Usage:
 *   node scripts/scan-hardcoded-zh.mjs            # report all violations
 *   node scripts/scan-hardcoded-zh.mjs --check    # ratchet vs baseline (CI)
 *   node scripts/scan-hardcoded-zh.mjs --update   # rewrite baseline
 */
import ts from "typescript";
import { readFileSync, writeFileSync, readdirSync, statSync } from "fs";
import { join, relative, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const BASELINE_PATH = join(ROOT, "scripts", "i18n-baseline.json");
const CJK = /[㐀-䶿一-鿿豈-﫿]/;

const mode = process.argv.includes("--update")
  ? "update"
  : process.argv.includes("--check")
  ? "check"
  : "report";

function* walkFiles(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === "test" || name === "__mocks__") continue;
      yield* walkFiles(p);
    } else if (/\.(tsx|ts)$/.test(name) && !/\.(test|spec)\.|\.d\.ts$/.test(name)) {
      yield p;
    }
  }
}

/** Is this node (or an ancestor, via the stack) inside a t(...) / i18n.t(...) call? */
function insideT(stack) {
  for (const node of stack) {
    if (ts.isCallExpression(node)) {
      const ex = node.expression;
      const name = ts.isIdentifier(ex)
        ? ex.text
        : ts.isPropertyAccessExpression(ex)
        ? ex.name.text
        : null;
      if (name === "t") return true;
      // console.* / umami.track / logger noise is not user-visible UI
      if (ts.isPropertyAccessExpression(ex) && ts.isIdentifier(ex.expression)) {
        if (["console", "umami", "logger"].includes(ex.expression.text)) return true;
      }
    }
  }
  return false;
}

function scanFile(path) {
  const text = readFileSync(path, "utf8");
  const lines = text.split("\n");
  const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const violations = [];

  const report = (node, raw) => {
    const value = raw.trim();
    if (!CJK.test(value)) return;
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
    if (/\/\/\s*i18n-exempt/.test(lines[line] ?? "")) return;
    violations.push({ line: line + 1, text: value.slice(0, 60) });
  };

  const stack = [];
  const visit = (node) => {
    stack.push(node);
    if (ts.isJsxText(node)) {
      report(node, node.text);
    } else if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
      CJK.test(node.text)
    ) {
      const parent = node.parent;
      const exempt =
        insideT(stack) ||
        ts.isImportDeclaration(parent) ||
        // object property NAMES (keys) are code, values are not
        (ts.isPropertyAssignment(parent) && parent.name === node) ||
        // case "中文": / === "中国" comparisons are data plumbing, not UI...
        // ...except they often SHOULD be keys — flag them, allow i18n-exempt
        false;
      if (!exempt) report(node, node.text);
    } else if (ts.isTemplateExpression(node) && !insideT(stack)) {
      const raw = [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join("");
      if (CJK.test(raw)) report(node, raw);
    }
    ts.forEachChild(node, visit);
    stack.pop();
  };
  visit(sf);
  return violations;
}

const results = {};
let total = 0;
for (const file of walkFiles(SRC)) {
  const v = scanFile(file);
  if (v.length > 0) {
    results[relative(ROOT, file)] = v;
    total += v.length;
  }
}

const counts = Object.fromEntries(
  Object.entries(results)
    .map(([f, v]) => [f, v.length])
    .sort((a, b) => b[1] - a[1])
);

if (mode === "update") {
  writeFileSync(BASELINE_PATH, JSON.stringify(counts, null, 2) + "\n");
  console.log(`Baseline updated: ${Object.keys(counts).length} files, ${total} hardcoded strings.`);
  process.exit(0);
}

if (mode === "report") {
  for (const [file, v] of Object.entries(results)) {
    console.log(`\n${file} (${v.length})`);
    for (const { line, text } of v) console.log(`  ${line}: ${text}`);
  }
  console.log(`\nTotal: ${total} hardcoded strings in ${Object.keys(counts).length} files.`);
  process.exit(0);
}

// --check: ratchet against baseline
let baseline = {};
try {
  baseline = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
} catch {
  console.error(`No baseline at ${BASELINE_PATH}. Run with --update first.`);
  process.exit(1);
}

let failed = false;
for (const [file, count] of Object.entries(counts)) {
  const allowed = baseline[file] ?? 0;
  if (count > allowed) {
    failed = true;
    console.error(`✗ ${file}: ${count} hardcoded Chinese strings (baseline ${allowed})`);
    for (const { line, text } of results[file]) console.error(`    ${line}: ${text}`);
  }
}

if (failed) {
  console.error(
    "\nNew hardcoded Chinese detected. Move strings into t() keys (all three locales)," +
      "\nor append  // i18n-exempt  for non-UI data values." +
      "\nIf you intentionally reduced debt elsewhere, run: npm run i18n:scan -- --update"
  );
  process.exit(1);
}

const improved = Object.entries(baseline).filter(([f, n]) => (counts[f] ?? 0) < n);
if (improved.length > 0) {
  console.log("Debt reduced (consider updating baseline with --update):");
  for (const [f, n] of improved) console.log(`  ${f}: ${n} → ${counts[f] ?? 0}`);
}
console.log(`✓ i18n ratchet OK: ${total} known hardcoded strings (baseline holds).`);
