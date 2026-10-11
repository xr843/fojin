"""Score /api/verify/claim on a deployment against the discovery and held-out sets.

    python backend/eval/verify_claim/run_against.py https://fojin.app [--only heldout|discovery]

Talks to the public API only (no DB/ES access needed); paced under the
10/min/IP rate limit, so a full run takes ~7 minutes. Metrics:

- top1: first source of the answer (verbatim source, or the near-miss text) is
  one of the item's accepted cbeta ids.
- verdict: sutra items answered sutra (or variant with source_class sutra);
  school items answered not_sutra/variant with source_class school.
- discovery fakes must be absent; spliced (real head + invented tail) partial.

The held-out set was written before the ranking was tuned — report it as is.
"""

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "fojin-verify-eval/1.0"}
PACE_S = 6.5


def claim(base: str, q: str) -> dict:
    url = f"{base.rstrip('/')}/api/verify/claim?q={urllib.parse.quote(q)}"
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30)
                continue
            return {"error": e.code}
    return {"error": "429x3"}


def first_source(resp: dict) -> tuple[str | None, str | None]:
    for seg in resp.get("segments", []):
        if seg.get("found") and seg.get("sources"):
            s = seg["sources"][0]
            return s.get("cbeta_id"), s.get("canon_class")
        if seg.get("close"):
            return seg["close"].get("cbeta_id"), seg["close"].get("canon_class")
    return None, None


def verdict_ok(resp: dict, want_class: str) -> bool:
    v, cls = resp.get("verdict"), resp.get("source_class")
    if want_class == "sutra":
        return v == "sutra" or (v == "variant" and cls == "sutra")
    return v in ("not_sutra", "variant") and cls == want_class


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--only", choices=["heldout", "discovery"])
    args = ap.parse_args()
    report: dict = {"base": args.base, "ran_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    if args.only in (None, "heldout"):
        items = json.loads((HERE / "heldout.json").read_text())["items"]
        rows = []
        for it in items:
            r = claim(args.base, it["q"])
            cbeta, _cls = first_source(r)
            rows.append({**it, "verdict": r.get("verdict"), "source_class": r.get("source_class"),
                         "top1": cbeta, "top1_ok": cbeta in it["accept"], "verdict_ok": verdict_ok(r, it["class"])})
            print(f"{'OK ' if rows[-1]['top1_ok'] else 'MISS'} {'v' if rows[-1]['verdict_ok'] else 'x'} "
                  f"{r.get('verdict')}/{r.get('source_class')} top1={cbeta} {it['q'][:16]}", flush=True)
            time.sleep(PACE_S)
        report["heldout"] = {
            "n": len(rows),
            "top1": sum(r["top1_ok"] for r in rows),
            "verdict": sum(r["verdict_ok"] for r in rows),
            "rows": rows,
        }

    if args.only in (None, "discovery"):
        d = json.loads((HERE / "discovery.json").read_text())
        out = {"famous": [], "fake": [], "spliced": []}
        for it in d["famous"]:
            r = claim(args.base, it["q"])
            cbeta, _ = first_source(r)
            out["famous"].append({"q": it["q"], "top1": cbeta, "top1_ok": cbeta in it["accept"], "verdict": r.get("verdict")})
            time.sleep(PACE_S)
        for q in d["fake"]:
            r = claim(args.base, q)
            out["fake"].append({"q": q, "verdict": r.get("verdict"), "ok": r.get("verdict") == "absent"})
            time.sleep(PACE_S)
        for q in d["spliced"]:
            r = claim(args.base, q)
            out["spliced"].append({"q": q, "verdict": r.get("verdict"), "ok": r.get("verdict") == "partial"})
            time.sleep(PACE_S)
        report["discovery"] = {
            "famous_top1": sum(x["top1_ok"] for x in out["famous"]),
            "famous_n": len(out["famous"]),
            "fake_absent": sum(x["ok"] for x in out["fake"]),
            "fake_n": len(out["fake"]),
            "spliced_partial": sum(x["ok"] for x in out["spliced"]),
            "spliced_n": len(out["spliced"]),
            "rows": out,
        }

    summary = {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in report.items() if isinstance(v, dict)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    out_path = HERE / f"report-{time.strftime('%Y%m%d-%H%M')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
