// 给每日经句池与节日经句补上简体字段 text_hans / title_hans、节日名繁体 name_hant（首页用）。
// 首页不能引 hanScript（OpenCC 约 550KB 会进首屏），所以简体版在这里预先算好写进 JSON。
// 用法：重跑 backend/scripts/build_daily_passages.py 之后，在 frontend/ 下跑 node scripts/daily-hans.mjs
import { readFileSync, writeFileSync } from "node:fs";
import * as OpenCC from "opencc-js";

const toHans = OpenCC.Converter({ from: "tw", to: "cn" });
const toHant = OpenCC.Converter({ from: "cn", to: "tw" });
for (const name of ["dailyPassages.json", "dailyFestivals.json"]) {
  const file = new URL(`../src/data/${name}`, import.meta.url);
  const rows = JSON.parse(readFileSync(file, "utf-8"));
  for (const r of rows) {
    r.text_hans = toHans(r.text);
    r.title_hans = toHans(r.title_zh);
    // 节日名在候选表里写简体，繁体界面要用（首页同样不能现转）
    if (r.name) r.name_hant = toHant(r.name);
  }
  writeFileSync(file, JSON.stringify(rows, null, 1) + "\n");
  console.log(`${name}：已补 ${rows.length} 条繁简字段`);
}
