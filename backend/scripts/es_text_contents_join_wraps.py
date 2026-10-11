"""Rebuild the ``text_contents`` ES index so CBETA hard line wraps stop breaking phrases.

CBETA text is hard-wrapped (「應無所住而\\n生其心」). ``cjk_content`` is
standard tokenizer + ``cjk_bigram``, and CJKBigramFilter does not pair two
characters whose offsets are not adjacent — so the bigram across a wrap
(「而生」) is never indexed and every ``match_phrase`` spanning a line break
silently misses. Measured 2026-10-11: the Diamond Sūtra (T0235) is absent from
the 120 phrase hits for 应无所住而生其心, the Heart Sūtra (T0251) from 照见五蕴皆空.

The fix is a char_filter that deletes a single line break *between two Han
characters* (paragraph breaks, breaks after punctuation, and Latin-script text
are untouched — the same analyzer indexes Pali/Sanskrit/English content).

Runs inside the backend container (uses ES_HOST / ES_USER / ES_PASSWORD):

    ssh sg-vps 'docker exec -i fojin-backend python - <step>' < backend/scripts/es_text_contents_join_wraps.py

Steps, in order — each is idempotent-ish and prints what it did:
    create    PUT text_contents_v2 = live settings/mapping + the char_filter
    reindex   async _reindex text_contents → text_contents_v2, prints task id
    status    progress of running reindex tasks + doc counts
    compare   phrase-hit comparison old vs v2 (wrapped and unwrapped probes)
    backup    async _reindex text_contents → text_contents_backup_20261011 (old analyzer)
    swap      atomically delete the old index and point alias text_contents → v2
    drop-v2   delete text_contents_v2 (refused once it is live)
    analyze   print both char_filters' tokens on fixed samples (read-only)
After ``swap`` the app keeps using the name ``text_contents`` (now an alias).
Keep the backup until the change has been verified in production.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request

OLD = "text_contents"
NEW = "text_contents_v2"
BACKUP = "text_contents_backup_20261011"

# For the ``content.nopunct`` subfield only: drop every punctuation/whitespace
# run between two Han characters — the same set quote_verifier._STRIP_PUNCT_RE
# strips before its substring test. CBETA's modern punctuation (「如夢、幻、泡、
# 影」) and a user's own commas (「從是西方，過十萬億佛土」 vs the source's
# unpunctuated 從是西方過…) then no longer decide whether ES even returns the
# candidate; PG still makes the verbatim call. ES narrows, PG decides.
HAN_PUNCT_CHAR_FILTER = {
    "type": "pattern_replace",
    "pattern": (
        "(?<=\\p{IsHan})"
        "[\\s,.!?;:\"'()\\[\\]\\-_~`<>*，。！？、；：「」『』“”‘’《》〈〉…—（）【】·•～\\u3000]+"
        "(?=\\p{IsHan})"
    ),
    "replacement": "",
}

HAN_WRAP_CHAR_FILTER = {
    "type": "pattern_replace",
    "pattern": "(?<=\\p{IsHan})[ \\t\\u3000]*\\r?\\n[ \\t\\u3000]*(?=\\p{IsHan})",
    "replacement": "",
}

_host = os.environ["ES_HOST"].rstrip("/")
HOST = _host if _host.startswith("http") else f"http://{_host}"
AUTH = "Basic " + base64.b64encode(f"{os.environ['ES_USER']}:{os.environ['ES_PASSWORD']}".encode()).decode()


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": AUTH},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → {e.code}: {e.read().decode()[:800]}") from e


def exists(index: str) -> bool:
    req = urllib.request.Request(HOST + "/" + index, method="HEAD", headers={"Authorization": AUTH})
    try:
        urllib.request.urlopen(req, timeout=30)
        return True
    except urllib.error.HTTPError:
        return False


def live_definition(index: str) -> tuple[dict, dict]:
    settings = call("GET", f"/{index}/_settings")
    real = next(iter(settings))  # resolves an alias to its concrete index
    idx = settings[real]["settings"]["index"]
    mappings = call("GET", f"/{index}/_mapping")[real]["mappings"]
    return {
        "number_of_shards": idx["number_of_shards"],
        "number_of_replicas": idx["number_of_replicas"],
        "analysis": idx["analysis"],
    }, mappings


def create(name: str, *, join_wraps: bool) -> None:
    if exists(name):
        print(f"{name} already exists — skipping create")
        return
    settings, mappings = live_definition(OLD)
    if join_wraps:
        analysis = settings["analysis"]
        char_filters = analysis.setdefault("char_filter", {})
        char_filters["cbeta_join_han_wraps"] = HAN_WRAP_CHAR_FILTER
        char_filters["cbeta_strip_han_punct"] = HAN_PUNCT_CHAR_FILTER
        analysis["analyzer"]["cjk_content"]["char_filter"] = ["cbeta_join_han_wraps"]
        analysis["analyzer"]["cjk_nopunct"] = {
            **analysis["analyzer"]["cjk_content"],
            "char_filter": ["cbeta_strip_han_punct"],
        }
        mappings["properties"]["content"]["fields"] = {"nopunct": {"type": "text", "analyzer": "cjk_nopunct"}}
    call("PUT", f"/{name}", {"settings": settings, "mappings": mappings})
    print(f"created {name} (join_wraps={join_wraps})")


def reindex(dest: str) -> None:
    r = call("POST", "/_reindex?wait_for_completion=false&refresh=true", {"source": {"index": OLD}, "dest": {"index": dest}})
    print("reindex task:", r.get("task"))


def status() -> None:
    tasks = call("GET", "/_tasks?actions=*reindex&detailed=true")
    for node in tasks.get("nodes", {}).values():
        for tid, t in node.get("tasks", {}).items():
            st = t.get("status", {})
            print(tid, t.get("description", "")[:80], f"{st.get('created', 0) + st.get('updated', 0)}/{st.get('total')}")
    for row in call("GET", "/_cat/indices/text_contents*?format=json&h=index,docs.count,store.size,health"):
        print(row)


def _phrase_hits(index: str, q: str) -> list[str]:
    body = {
        "query": {"bool": {"must": [{"match_phrase": {"content": {"query": q, "analyzer": "cjk_content"}}}]}},
        "size": 400,
        "_source": ["cbeta_id"],
    }
    r = call("POST", f"/{index}/_search", body)
    return [h["_source"].get("cbeta_id") for h in r["hits"]["hits"]]


def compare() -> None:
    probes = [
        # (phrase, a text that is known to contain it across a hard wrap)
        ("应无所住而生其心", "T0235"),
        ("照见五蕴皆空", "T0251"),
        ("一切有为法如梦幻泡影", "T0235"),
        ("色不异空空不异色", "T0251"),
        ("诸恶莫作众善奉行", "T0001"),
        # unwrapped / Latin controls: v2 must not lose hits
        ("若人欲了知三世一切佛", None),
        ("心佛及众生是三无差别", None),
        ("Blessed One", None),
        ("evaṃ me sutaṃ", None),
    ]
    regress = 0
    for q, want in probes:
        old, new = _phrase_hits(OLD, q), _phrase_hits(NEW, q)
        lost = set(old) - set(new)
        regress += bool(lost)
        flag = ""
        if want:
            flag = f"  {want}: old={want in old} new={want in new}"
        print(f"{q[:14]:14} old={len(old):4} new={len(new):4} lost={sorted(lost)[:5]}{flag}")
    print("regressions:", regress)


def analyze() -> None:
    """Show both char_filters' tokens on a few fixed samples (read-only)."""
    samples = [
        "應無所住而\n生其心",
        "如夢、幻、泡、影，\n如露亦如電",
        "從是西方，過十萬億佛土",
        "何以故？\n「一切有為法",
        "the Blessed\nOne, said",
    ]
    filters = [{"type": "icu_transform", "id": "Traditional-Simplified"}, "cjk_bigram", "lowercase"]
    for name, cf in (("wraps", HAN_WRAP_CHAR_FILTER), ("nopunct", HAN_PUNCT_CHAR_FILTER)):
        for text in samples:
            body = {"tokenizer": "standard", "char_filter": [cf], "filter": filters, "text": text}
            tokens = [t["token"] for t in call("POST", f"/{OLD}/_analyze", body)["tokens"]]
            print(f"{name:8} {text!r:32} {tokens}")


def drop_new() -> None:
    """Delete text_contents_v2 — refused once it is live behind the alias."""
    aliases = call("GET", "/_alias")
    if OLD in aliases.get(NEW, {}).get("aliases", {}):
        raise SystemExit(f"{NEW} is live behind alias {OLD} — refusing to delete")
    if exists(NEW):
        call("DELETE", f"/{NEW}")
        print(f"deleted {NEW}")


def swap() -> None:
    if not exists(NEW):
        raise SystemExit(f"{NEW} missing")
    if not exists(BACKUP):
        raise SystemExit(f"{BACKUP} missing — run `backup` first and wait for it to finish")
    old_n = call("GET", f"/{OLD}/_count")["count"]
    new_n = call("GET", f"/{NEW}/_count")["count"]
    bak_n = call("GET", f"/{BACKUP}/_count")["count"]
    if not (old_n == new_n == bak_n):
        raise SystemExit(f"doc counts differ: old={old_n} new={new_n} backup={bak_n}")
    call(
        "POST",
        "/_aliases",
        {"actions": [{"remove_index": {"index": OLD}}, {"add": {"index": NEW, "alias": OLD, "is_write_index": True}}]},
    )
    print(f"swapped: {OLD} is now an alias → {NEW} ({new_n} docs); backup kept as {BACKUP}")


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else "status"
    if step == "create":
        create(NEW, join_wraps=True)
    elif step == "reindex":
        reindex(NEW)
    elif step == "backup":
        create(BACKUP, join_wraps=False)
        reindex(BACKUP)
    elif step == "status":
        status()
    elif step == "compare":
        compare()
    elif step == "swap":
        swap()
    elif step == "analyze":
        analyze()
    elif step == "drop-v2":
        drop_new()
    else:
        raise SystemExit(f"unknown step {step}")


if __name__ == "__main__":
    main()
