// 给每日经句池补上简体字段 text_hans / title_hans（首页用）。
// 首页不能引 hanScript（OpenCC 约 550KB 会进首屏），所以简体版在这里预先算好写进 JSON。
// 用法：重跑 backend/scripts/build_daily_passages.py 之后，在 frontend/ 下跑 node scripts/daily-hans.mjs
import { readFileSync, writeFileSync } from "node:fs";
import * as OpenCC from "opencc-js";

const FILE = new URL("../src/data/dailyPassages.json", import.meta.url);
const toHans = OpenCC.Converter({ from: "tw", to: "cn" });
const rows = JSON.parse(readFileSync(FILE, "utf-8"));
for (const r of rows) {
  r.text_hans = toHans(r.text);
  r.title_hans = toHans(r.title_zh);
}
writeFileSync(FILE, JSON.stringify(rows, null, 1) + "\n");
console.log(`已补 ${rows.length} 条简体字段`);
