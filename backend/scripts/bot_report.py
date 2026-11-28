#!/usr/bin/env python3
"""爬虫日报：把宿主 nginx 日志里某一天的请求按爬虫公司 / 类型汇总，写成 data/bot-stats/<日期>.json。

宿主机 cron 每天 04:40 跑（nginx 日志约 03:40 轮转），统计前一天（北京时间自然日）：
    sudo -n python3 /home/admin/fojin/backend/scripts/bot_report.py            # 昨天
    sudo -n python3 /home/admin/fojin/backend/scripts/bot_report.py 2026-11-27 # 指定日期

只看自报名字的爬虫（User-Agent 里写明的）；伪装成普通浏览器的隐身爬虫在这里归「普通浏览器/未自报」，
要靠网站统计里的有效访问 / 自动化标签区分（见 frontend/src/analyticsSignals.ts）。
只存计数和路径，不存 IP。只用标准库（宿主 python 较旧）。
2026-11-28 首次实测（7 小时）：SEO 工具 1,941、SpiceHarvester 1,554、KeenableBot 1,127、Bing 530、Google 204、
OpenAI 15、Anthropic 11。
"""

import collections
import datetime
import glob
import gzip
import json
import os
import re
import sys

LOG_DIR = "/var/log/nginx"
OUT_DIR = "/home/admin/fojin/data/bot-stats"

# (显示名, 类型, 匹配 UA 的正则)；按顺序匹配，先到先得
FAMILIES = [
    ("OpenAI", "AI", r"GPTBot|ChatGPT-User|OAI-SearchBot"),
    ("Anthropic", "AI", r"ClaudeBot|Claude-User|Claude-SearchBot|anthropic-ai"),
    ("Perplexity", "AI", r"PerplexityBot|Perplexity-User"),
    ("字节跳动", "AI", r"Bytespider|TikTokSpider"),
    ("Meta", "AI", r"meta-externalagent|meta-externalfetcher|FacebookBot"),
    ("Common Crawl", "AI", r"CCBot"),
    ("Amazon", "AI", r"Amazonbot"),
    ("Apple", "AI", r"Applebot"),
    ("ElevenLabs", "AI", r"ElevenlabsCrawler"),
    ("Microsoft AI", "AI", r"AzureAI-SearchBot|bingbot-ai"),
    ("Google", "搜索引擎", r"Googlebot|Google-Extended|GoogleOther|Storebot-Google|Google-InspectionTool"),
    ("Microsoft/Bing", "搜索引擎", r"bingbot|BingPreview"),
    ("百度", "搜索引擎", r"Baiduspider"),
    ("搜狗/360/神马", "搜索引擎", r"Sogou|360Spider|YisouSpider"),
    ("Yandex", "搜索引擎", r"YandexBot"),
    ("DuckDuckGo", "搜索引擎", r"DuckDuckBot"),
    ("SEO 工具", "SEO 工具", r"AhrefsBot|SemrushBot|MJ12bot|DotBot|PetalBot|DataForSeoBot|BLEXBot|SERanking|serpstatbot"),
    ("社交预览", "社交预览", r"facebookexternalhit|Twitterbot|TelegramBot|WhatsApp|Slackbot|Discordbot|LinkedInBot"),
]
GENERIC = re.compile(
    r"([\w.-]*(?:bot|spider|crawl|prober|harvester|python-requests|python-httpx|curl|wget|go-http|axios|scrapy|headless|okhttp|java/)[\w./-]*)",
    re.I,
)
LINE = re.compile(r'\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)" "[^"]*"\s*$')


def classify(ua):
    for name, kind, pat in FAMILIES:
        if re.search(pat, ua, re.I):
            return name, kind
    g = GENERIC.search(ua)
    if g:
        token = re.sub(r"[/;)].*$", "", g.group(1))[:40]
        return "其他自报：" + token, "其他自报爬虫"
    return "普通浏览器/未自报", "普通浏览器/未自报"


def norm_path(path):
    path = path.split("?", 1)[0]
    path = re.sub(r"/\d+", "/N", path)
    return re.sub(r"^/dict/.+", "/dict/*", path)


def main():
    if len(sys.argv) > 1:
        day = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        day = datetime.date.today() - datetime.timedelta(days=1)
    stamp = day.strftime("%d/%b/%Y")
    files = sorted(glob.glob(os.path.join(LOG_DIR, "access.log*")))
    by_name = collections.Counter()
    kinds = {}
    paths = collections.defaultdict(collections.Counter)
    status = collections.defaultdict(collections.Counter)
    total = 0
    for f in files:
        opener = gzip.open if f.endswith(".gz") else open
        try:
            with opener(f, "rt", errors="replace") as fh:
                for line in fh:
                    if stamp not in line:
                        continue
                    m = LINE.search(line)
                    if not m or m.group(1) != stamp:
                        continue
                    name, kind = classify(m.group(5))
                    total += 1
                    by_name[name] += 1
                    kinds[name] = kind
                    paths[kind][norm_path(m.group(3))] += 1
                    status[kind][m.group(4)[0] + "xx"] += 1
        except OSError:
            continue
    by_kind = collections.Counter()
    for name, n in by_name.items():
        by_kind[kinds[name]] += n
    out = {
        "date": day.isoformat(),
        "total_requests": total,
        "by_kind": dict(by_kind.most_common()),
        "by_crawler": [{"name": n, "kind": kinds[n], "requests": c} for n, c in by_name.most_common(40)],
        "top_paths": {k: paths[k].most_common(10) for k in by_kind},
        "status": {k: dict(v) for k, v in status.items()},
        "note": "nginx 回源请求（Cloudflare 缓存命中的不在内）；不含 IP",
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    dest = os.path.join(OUT_DIR, day.isoformat() + ".json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    os.chmod(dest, 0o644)
    print(dest, total, dict(by_kind.most_common()))


if __name__ == "__main__":
    main()
