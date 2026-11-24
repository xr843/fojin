"""生成「今日经句」用的农历月表：frontend/src/data/lunarMonths.json。

为什么不用浏览器自带的 Intl 农历（zh-u-ca-chinese）：它在朔日落在北京时间午夜附近时算错
一天——2026-11-24 实测 ICU 77 把 2027 年春节算成 2 月 7 日、2030 年算成 2 月 2 日，权威
万年历分别是 2 月 6 日、2 月 3 日（wannianli.tianqi.com）；而 lunardate（基于香港天文台
数据的传统农历表）两处都对，2026–2030 共 1,826 天里与 ICU 只在这两个月份有分歧。

输出：每个农历月的起始公历日期 + 月序 + 是否闰月，前端按天数推算当日农历。
用法：uvx --with lunardate python backend/scripts/build_lunar_months.py
"""

import datetime as dt
import json
import pathlib

from lunardate import LunarDate

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend/src/data/lunarMonths.json"
START, END = dt.date(2025, 12, 1), dt.date(2031, 1, 1)


def main() -> None:
    months = []
    d = START
    while d < END:
        lu = LunarDate.from_solar_date(d.year, d.month, d.day)
        if lu.day == 1:
            months.append({"start": d.isoformat(), "month": lu.month, "leap": bool(lu.isLeapMonth)})
        d += dt.timedelta(days=1)
    OUT.write_text(json.dumps({"until": END.isoformat(), "months": months}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(months)} 个农历月 → {OUT}")


if __name__ == "__main__":
    main()
