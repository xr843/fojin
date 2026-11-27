"""/history（中国佛教史长卷）的分享卡片：按 ?p= / ?e= / ?r= / ?tour= 注入 title、description、og:*。

此前 /history 走 SPA 通用壳，分享任何一个人、一件大事，微信 / Telegram 卡片都显示首页文案。
数据都取前端容器里的静态文件（与页面同源，不另存一份）：
- history-people.json：人物（DILA 人名规范库）；
- history-share.json：大事、导览的标题字段（vite 构建时由 src/data 生成，见 vite.config.ts）；
- history-translations.json：译经长河（开元录）。
带参数的页 noindex（同一页面换参数，算不上独立内容）；不带参数的总页可收录。
"""

from __future__ import annotations

import logging
import re
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from opencc import OpenCC

from app.api.seo import _escape_meta_value, _fetch_index_html, _inject_meta, public_base_url
from app.services.seo_lang import LANG_SHELL_SUFFIX, SeoLang, html_lang, resolve_lang

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seo"])

_DATA_TTL = 3600
_data_cache: dict[str, tuple[float, dict]] = {}
_t2s = OpenCC("t2s")

# 繁转简后「著」（撰著）被转成「着」的校正——与前端 utils/hanScript.ts localizeProse 同一组规则（只取有把握的几条）
_ZHU_FIX = [
    (re.compile(r"着(?=[《〈])"), "著"),
    (re.compile(r"着(语|述|作)"), r"著\1"),
    (re.compile(r"(杂|遗|新|编|辑|撰|论|名|合|原|另)着"), r"\1著"),
    (re.compile(r"无着(?=菩萨|论师|造|所造)"), "无著"),
    (re.compile(r"(^|[。，；：、）\s])着有(?![、，。；者])"), r"\1著有"),
]

_COPY: dict[str, dict[str, str]] = {
    "zh": {
        "base": "中国佛教史长卷",
        "tail": " — 佛津 FoJin",
        "desc": "从东汉到民国，三百多位译经师、高僧与居士排成一条时间轴；大事逐条附大藏经原文，点名字看僧传原文。",
        "event": "公元 {y} 年 · {s}",
        "river": "{a}–{b} 年译出的经",
        "river_desc": "《开元释教录》记下这十年译出 {n} 部：{titles}。",
        "tour": "{t} · 导览",
    },
    "zh-Hant": {
        "base": "中國佛教史長卷",
        "tail": " — 佛津 FoJin",
        "desc": "從東漢到民國，三百多位譯經師、高僧與居士排成一條時間軸；大事逐條附大藏經原文，點名字看僧傳原文。",
        "event": "公元 {y} 年 · {s}",
        "river": "{a}–{b} 年譯出的經",
        "river_desc": "《開元釋教錄》記下這十年譯出 {n} 部：{titles}。",
        "tour": "{t} · 導覽",
    },
    "en": {
        "base": "Timeline of Chinese Buddhism",
        "tail": " — FoJin",
        "desc": (
            "From the Han to the Republic: 300+ translators, monks, nuns and lay Buddhists on one timeline, "
            "with key events quoted from the canon."
        ),
        "event": "{y} CE · {s}",
        "river": "Texts translated {a}–{b}",
        "river_desc": "The Kaiyuan Catalogue dates {n} texts to this decade: {titles}.",
        "tour": "{t} · guided tour",
    },
}


def _local(s: str, lang: SeoLang) -> str:
    """数据是繁体；简体界面转简并校正「著」。"""
    if lang != "zh" or not s:
        return s
    out = _t2s.convert(s)
    for pat, rep in _ZHU_FIX:
        out = pat.sub(rep, out)
    return out


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


async def _data(name: str) -> dict:
    now = time.monotonic()
    hit = _data_cache.get(name)
    if hit and now - hit[0] < _DATA_TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"http://frontend/{name}")
        resp.raise_for_status()
        data = resp.json()
    _data_cache[name] = (now, data)
    return data


def _years(p: dict) -> str:
    def one(v):
        if not v:
            return "?"
        return str(v[0]) if v[0] == v[1] else f"约{v[0]}"

    if not p.get("b") and not p.get("d"):
        return ""
    return f"{one(p.get('b'))}–{one(p.get('d'))}"


async def history_meta(params: dict[str, str], lang: SeoLang) -> tuple[str, str, str]:
    """返回 (标题, 描述, 规范化的查询串)；参数无效时退回总页。"""
    c = _COPY[lang]
    base = c["base"]
    try:
        if params.get("p"):
            pid = params["p"]
            people = (await _data("history-people.json")).get("people", [])
            p = next((x for x in people if x.get("id") == pid), None)
            if p:
                yrs = _years(p)
                name = _local(p.get("n", ""), lang)
                title = f"{name}（{yrs}）· {base}" if yrs else f"{name} · {base}"
                head = " · ".join(x for x in (_local(p.get("dy", ""), lang), yrs) if x)
                desc = _clip(f"{head}。{_local(p.get('bio', ''), lang)}", 150)
                return title, desc, f"p={pid}"
        if params.get("e"):
            eid = params["e"]
            ev = (await _data("history-share.json")).get("events", {}).get(eid)
            if ev:
                title = c["event"].format(y=ev["y"], s=_local(ev["s"], lang)) + f" · {base}"
                quote = _local(ev.get("q", "").split("｜")[0], lang)
                desc = _clip(f"{_local(ev.get('t', ''), lang)}「{quote}」", 150)
                return title, desc, f"e={eid}"
        if params.get("r", "").lstrip("-").isdigit():
            a = int(params["r"]) // 10 * 10
            items = [x for x in (await _data("history-translations.json")).get("items", []) if a <= x["y"] < a + 10]
            if items:
                titles = "、".join(f"《{_local(x['t'], lang)}》" for x in items[:5])
                title = c["river"].format(a=a, b=a + 9) + f" · {base}"
                return title, _clip(c["river_desc"].format(n=len(items), titles=titles), 150), f"r={a}"
        if params.get("tour"):
            tid = params["tour"]
            tour = (await _data("history-share.json")).get("tours", {}).get(tid)
            if tour:
                title = c["tour"].format(t=_local(tour["title"], lang)) + f" · {base}"
                return title, _clip(_local(tour.get("intro", ""), lang), 150), f"tour={tid}"
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("history share meta fell back to the base page: %s", e)
    return base, c["desc"], ""


@router.get("/history", response_class=HTMLResponse, include_in_schema=False)
async def history_seo_html(request: Request):
    lang = resolve_lang(request)
    c = _COPY[lang]
    title, desc, query = await history_meta(dict(request.query_params), lang)
    base_url = public_base_url(request)
    canonical = f"{base_url}/history" + (f"?{query}" if query else "")
    robots = "noindex, follow" if query else "index, follow"
    full_title = title + c["tail"]
    try:
        html = await _fetch_index_html(LANG_SHELL_SUFFIX[lang])
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch frontend index.html for /history: %s", e)
        return HTMLResponse(
            f'<!doctype html><html lang="{html_lang(lang)}"><head><title>{_escape_meta_value(full_title)}</title>'
            f'<meta name="description" content="{_escape_meta_value(desc)}" /></head><body></body></html>'
        )
    return HTMLResponse(_inject_meta(html, full_title, desc, canonical, robots=robots, lang=lang))
