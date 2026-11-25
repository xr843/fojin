// 列出今日经句池在简体、繁体界面下要显示的全部字（与站内同一个 OpenCC 转换），给 build_daily_fonts.py 用。
// 在 frontend/ 目录下运行（要用它的 node_modules）：node scripts/daily_font_chars.mjs > chars.json
import fs from "fs";
import * as OpenCC from "opencc-js";

const pool = JSON.parse(fs.readFileSync("src/data/dailyPassages.json", "utf8"));
const toSimp = OpenCC.Converter({ from: "tw", to: "cn" });
const toTrad = OpenCC.Converter({ from: "cn", to: "tw" });
const simp = new Set();
const trad = new Set();
for (const p of pool) {
  for (const c of toSimp(p.text)) simp.add(c);
  for (const c of toTrad(p.text)) trad.add(c);
}
console.log(JSON.stringify({ simp: [...simp].join(""), trad: [...trad].join("") }));
