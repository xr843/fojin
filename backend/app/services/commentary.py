"""经注对读：一段经文，历代各家怎么注。

数据是 hanzhu-align 产出的「经注对齐」——把「哪一段疏注哪一句经」从汉传注疏
里抽出来。CBETA 只为极少数书做了机器可解析的引经标记，古代注疏里基本是 0；
那份数据把这件事推广开，其中一半（无标记书的自主对齐）此前无人做过。

**数据不在本仓库。** 本仓库是公开的，而对齐数据集尚未公开，所以包以带外方式
部署到 ``/data/commentary/*.json``（该目录已在 .gitignore 内且挂进容器）。没有
包时本模块静默降级为「无数据」，接口照常返回 200 并说明原因——线上少一个功能
好过整个后端起不来。

包里自带经文与注文（CBETA，CC BY-NC-SA 4.0，非营利使用并署名），所以运行时
不需要另一份 CBETA 语料。
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.services.quote_verifier import normalise_for_match

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path("/data/commentary")

# 每次最多返回几家。段级中位 13 家、最多 50 家，全吐给模型既挤占上下文又没人
# 读得完；超出时如实标 truncated，绝不假装这就是全部。
DEFAULT_LIMIT = 8
MAX_LIMIT = 50

# 读者划选的首尾常常只沾到一行的几个字（几乎没人正好停在 CBETA 行末）。
# 这样的边界行不算「他在问这一行」——否则下一句的注家会挤满名额，把他真正
# 划的那句的注家顶出去。实测：不设这道门槛时 44 例里有 1 例被下一句占满。
_CORE_MIN_CHARS = 6

# CBETA 书号 → fojin 的 cbeta_id：T08n0235 → T0235、X24n0461 → X0461。
_WORK_ID = re.compile(r"^([A-Z]+)\d*n(\w+)$")


def to_cbeta_id(work_id: str) -> str | None:
    m = _WORK_ID.match(work_id or "")
    return f"{m.group(1)}{m.group(2)}" if m else None


# 行标 X24n0456_p0455c03 → 0455c03，也就是 text_line_anchors.line_ref 的写法。
# 锚点本身带书号前缀（一段里的注文来自不同的书），而库里按 text_id 分表存，
# 前缀是冗余的。
_LINE_REF = re.compile(r"_p([0-9a-z]+)$")


def line_ref(anchor: str | None) -> str | None:
    """CBETA 行标里的页-栏-行部分，用于反查它落在第几卷。

    对不上就返回 None：宁可退回书级链接，也不要拼一个跳不到的锚点。
    """
    m = _LINE_REF.search(anchor or "")
    return m.group(1) if m else None


@dataclass
class Package:
    """一部经的经注对读包。文本在内存里常驻——单包约 2 MB。"""

    meta: dict
    lines: list[dict]
    comms: dict
    by_line: dict = field(default_factory=dict)
    ids: list[str] = field(default_factory=list)
    pos: dict = field(default_factory=dict)
    text: dict = field(default_factory=dict)
    _flat: str = ""
    _owner: list[str] = field(default_factory=list)
    _len: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Package:
        d = json.loads(path.read_text(encoding="utf-8"))
        pkg = cls(meta=d["meta"], lines=d["base_lines"], comms=d["commentaries"])
        pkg.ids = [ln["id"] for ln in pkg.lines]
        pkg.pos = {x: i for i, x in enumerate(pkg.ids)}
        pkg.text = {ln["id"]: ln["text"] for ln in pkg.lines}
        pkg.by_line = {}
        for n in d["notes"]:
            pkg.by_line.setdefault(n["base_line"], []).append(n)
        # 全经拼接 + 每个字属于哪一行。CBETA 一行才十来个字，稍长的句子必然
        # 跨行，逐行匹配是找不到的。归一化用 quote_verifier 那一份 —— 全站
        # 「同一句经文」只能有一个定义，顺带让简体查询也能命中繁体原文。
        parts = []
        for ln in pkg.lines:
            t = normalise_for_match(ln["text"])
            parts.append(t)
            pkg._owner.extend([ln["id"]] * len(t))
            pkg._len[ln["id"]] = len(t)
        pkg._flat = "".join(parts)
        return pkg

    def find(self, quote: str) -> str | None:
        """含该句的第一行行号。"""
        needle = normalise_for_match(quote)
        if not needle:
            return None
        p = self._flat.find(needle)
        return self._owner[p] if p >= 0 else None

    def locate(self, quote: str) -> tuple[set[str], int, int] | None:
        """读者划选实质覆盖了哪几行 —— (行号集合, 起始下标, 结束下标)。

        ``find`` 只给起点，丢掉了划选的长度。读者划一整段（常有七八行）时，
        只按起点行前后取窗口，会把他没划到的上文也算进来，而上文的注家按
        置信度排序往往排在前面，于是他划 A 段、看到的却是 B 段的注。
        """
        needle = normalise_for_match(quote)
        if not needle:
            return None
        p = self._flat.find(needle)
        if p < 0:
            return None
        covered = Counter(self._owner[p:p + len(needle)])
        core = {
            ln for ln, n in covered.items()
            if n >= min(_CORE_MIN_CHARS, max(1, self._len.get(ln, 1)) // 2)
        }
        if not core:  # 划选比一行还短时，门槛会把唯一那行也筛掉
            core = {self._owner[p]}
        idx = [self.pos[x] for x in core if x in self.pos]
        if not idx:
            return None
        return core, min(idx), max(idx)

    def passage(
        self, core: set[str], i0: int, i1: int, limit: int
    ) -> tuple[list[str], list[dict], int]:
        """(段内各行, 去重后的各家注, 本段总家数)。

        同一部注疏常在段内多行都有锚点（牒文分几处引），按行列会让它重复出现，
        把「有几家注」答成「有几条对齐」。按注疏去重，保留最贴题的那个锚点。

        ``core`` 是读者实际划到的行；窗口仍向两侧各放 ``passage_radius`` 行，
        因为对齐锚点本身有偏移，只认 core 会让一些段一家都取不到。但 core 内的
        注**永远排在**窗口边缘的注之前 —— 边缘只是兜底，不该顶替正题。
        """
        if i0 is None:
            return [], [], 0
        r = self.meta.get("passage_radius", 3)
        span = self.ids[max(0, i0 - r): i1 + r + 1]

        def pick(n: dict) -> tuple[int, float]:
            """同一部书取哪个锚点：先看是不是落在读者划的行上，再看置信度。"""
            return (0 if n["base_line"] in core else 1, -n["score"])

        best: dict[str, dict] = {}
        for bl in span:
            for n in self.by_line.get(bl, ()):
                if n["work"] not in best or pick(n) < pick(best[n["work"]]):
                    best[n["work"]] = n
        order = {"A": 0, "B": 1, "C": 2}
        ranked = sorted(
            best.values(),
            key=lambda n: (
                0 if n["base_line"] in core else 1,
                order.get(self.comms.get(n["work"], {}).get("tier"), 9),
                -n["score"],
            ),
        )
        return span, ranked[:limit], len(ranked)


@lru_cache(maxsize=1)
def packages() -> list[Package]:
    """加载 /data/commentary 下的全部包；缺目录或坏文件都不抛，只记日志。"""
    if not PACKAGE_DIR.is_dir():
        logger.info("commentary: no package dir at %s — feature idle", PACKAGE_DIR)
        return []
    out = []
    for p in sorted(PACKAGE_DIR.glob("*.json")):
        try:
            out.append(Package.load(p))
        except Exception:
            logger.warning("commentary: failed to load %s", p, exc_info=True)
    logger.info("commentary: loaded %d package(s)", len(out))
    return out


def available() -> list[dict]:
    return [
        {
            "base_work": p.meta["base_work"],
            "base_title": p.meta.get("base_title"),
            "commentary_count": p.meta.get("commentary_count"),
            "line_coverage_pct": (
                p.meta["lines_with_notes"] * 100 // p.meta["line_count"]
                if p.meta.get("line_count") else None
            ),
        }
        for p in packages()
    ]
