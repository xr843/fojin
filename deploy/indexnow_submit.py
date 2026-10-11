#!/usr/bin/env python3
"""把 sitemap 里的新网址通过 IndexNow 推给 Bing（及 Yandex/Seznam/Naver 等共享该协议的引擎）。

为什么：近 30 天 Bing 带来的访问（bing + cn.bing ≈ 89）已经超过 Google（43），
而 ChatGPT 搜索等 AI 检索也用 Bing 的索引。sitemap 只能等爬虫来读；IndexNow
是主动告诉搜索引擎「这些网址新出现/变了」，不需要站长后台账号——只要站点根目录
放着与 key 同名的 key 文件（frontend/public/<KEY>.txt）证明网址归属。

只推「上次推过之后新出现的网址」：已推集合记在 --state 文件里（每行一个网址），
首次运行（无 state）推全部。推送成功（HTTP 200/202）的批次才写回 state，
失败的下次部署自动重试。

范围：静态页 + 经典页（含 ?lang= 繁体/英文版本）。辞典（55 万词头）与人物页
不推——量大且多为短页，主动推送有被判为灌水的风险，留给爬虫按 sitemap 自己来。

由 deploy.sh 在部署末尾调用，失败只告警不影响部署。手动：
    python3 deploy/indexnow_submit.py --dry-run
    python3 deploy/indexnow_submit.py --state .deploy-state/indexnow-submitted.txt
"""

# 宿主机是 Python 3.6（deploy.sh 在宿主机上跑）：不要用 `from __future__ import annotations`、
# list[str] 之类的内置泛型注解，也不要用 3.7+ 的 API。

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "fojin.app"
BASE = f"https://{HOST}"
KEY = "cb6991010688c547e7260ab42234337d"
KEY_LOCATION = f"{BASE}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
# 只推这几类 sitemap（按 <loc> 文件名前缀匹配）。
SITEMAP_PREFIXES = ("sitemap-static", "sitemap-texts-")
BATCH = 10_000  # IndexNow 单次请求上限
# Cloudflare 会 403 Python 默认 UA。
UA = "Mozilla/5.0 (compatible; fojin-indexnow/1.0; +https://fojin.app)"

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def urls_in_urlset(xml):
    """<loc> 加上每条的 hreflang 替代网址（繁体/英文版本是独立 URL），按出现顺序去重。"""
    root = ET.fromstring(xml)
    seen = {}
    for url in root.findall("sm:url", NS):
        loc = url.findtext("sm:loc", default="", namespaces=NS).strip()
        if loc:
            seen.setdefault(loc)
        for alt in url.findall("xhtml:link", NS):
            href = (alt.get("href") or "").strip()
            if href:
                seen.setdefault(href)
    return list(seen)


def collect(base):
    index = ET.fromstring(fetch(f"{base}/sitemap.xml"))
    out = {}
    for loc in index.findall("sm:sitemap/sm:loc", NS):
        url = (loc.text or "").strip()
        name = url.rsplit("/", 1)[-1]
        if not name.startswith(SITEMAP_PREFIXES):
            continue
        for u in urls_in_urlset(fetch(url)):
            out.setdefault(u)
    # 只推本站网址（IndexNow 要求 urlList 与 host 同域）。
    return [u for u in out if u.startswith(f"{BASE}/") or u == BASE]


def submit(urls):
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", type=Path, help="已推网址记录文件；不给则每次都推全部")
    ap.add_argument("--base", default=BASE, help="读取 sitemap 的站点根（默认生产）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不推送")
    args = ap.parse_args()

    # key 文件必须先在线，否则 IndexNow 会以 403 拒绝整批。
    try:
        served = fetch(KEY_LOCATION).decode().strip()
    except Exception as e:  # 任何失败都等价于「key 未上线」
        print(f"indexnow: key 文件不可达（{e}），跳过", file=sys.stderr)
        return 1
    if served != KEY:
        print("indexnow: key 文件内容不符，跳过", file=sys.stderr)
        return 1

    urls = collect(args.base)
    done = set()
    if args.state and args.state.exists():
        done = set(args.state.read_text().split())
    new = [u for u in urls if u not in done]
    print(f"indexnow: sitemap {len(urls)} 个网址，已推 {len(done)}，本次新增 {len(new)}")
    if args.dry_run or not new:
        return 0

    ok = 0
    for i in range(0, len(new), BATCH):
        chunk = new[i : i + BATCH]
        status = submit(chunk)
        print(f"indexnow: 批次 {i // BATCH + 1}（{len(chunk)} 个）→ HTTP {status}")
        if status not in (200, 202):
            break
        done.update(chunk)
        ok += len(chunk)
        if args.state:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text("\n".join(sorted(done)) + "\n")
    print(f"indexnow: 成功推送 {ok}/{len(new)}")
    return 0 if ok == len(new) else 1


if __name__ == "__main__":
    sys.exit(main())
