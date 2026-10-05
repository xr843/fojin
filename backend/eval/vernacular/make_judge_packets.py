"""把 sample.jsonl + out.jsonl 做成盲评包：每句三份译文乱序标为 甲/乙/丙，
映射单独存 key.json，裁判看不到臂别。

    python make_judge_packets.py sample.jsonl out.jsonl outdir/ 4
"""

import json
import random
import sys
from pathlib import Path

LABELS = ["甲", "乙", "丙"]


def main(sample_path: str, out_path: str, outdir: str, n_packets: int) -> None:
    samples = [json.loads(x) for x in Path(sample_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    outs: dict[tuple[str, str], dict] = {}
    for x in Path(out_path).read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            outs[(r["id"], r["arm"])] = r
    rng = random.Random(42)
    key: dict[str, dict[str, str]] = {}
    items = []
    for s in samples:
        arms = ["A", "B", "C"]
        rng.shuffle(arms)
        key[s["id"]] = dict(zip(LABELS, arms, strict=True))
        items.append({
            "id": s["id"],
            "经名": f"《{s['title']}》{s['translator'] or ''}",
            "前文": s["before"],
            "选文": s["sentence"],
            "后文": s["after"],
            "译文": {lab: outs.get((s["id"], arm), {}).get("translation", "") or "（空）" for lab, arm in zip(LABELS, arms, strict=True)},
        })
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    per = -(-len(items) // n_packets)
    for i in range(n_packets):
        chunk = items[i * per:(i + 1) * per]
        (out / f"packet{i + 1}.json").write_text(json.dumps(chunk, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))
