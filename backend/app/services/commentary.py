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

# 「注疏怎么讲这几句」片段（excerpts）：
# 插值段（前一个对齐点 → 后一个对齐点之间的注文）里必须逐字出现贴文所在论文行的
# 某个 4 字片段，才算这家确实牒到了这几句——挡住对齐点稀疏处跨品错位的情况。
# 2026-11-05 实测：人工判对上的 26 条留 25、错位 1 条被挡；5 字只留 22。
EXCERPT_QUOTE_GRAM = 4
# 插值段中位 1,196 字（光记）、P90 4,069 字，整段给读者等于让他自己翻卷。
# 从首个牒引所在行起截约这么多字，断在句号处。
EXCERPT_CHARS = 500
_SENTENCE_END = "。"

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
    # 反向：注疏书号 → [(该注在自己书里的行标, note)]，按行标排序。
    # 正查问「这句经谁注过」，反查问「这段注在解释哪一句」——读注疏的人问的是
    # 后者，而 by_line 只按经文行建索引，答不了。数据本来就双向（每条对齐两端
    # 都带行号），缺的只是这个索引。
    by_anchor: dict = field(default_factory=dict)
    ids: list[str] = field(default_factory=list)
    pos: dict = field(default_factory=dict)
    text: dict = field(default_factory=dict)
    _flat: str = ""
    _owner: list[str] = field(default_factory=list)
    _len: dict = field(default_factory=dict)
    # 注疏全文（可选，schema ≥ 2 的包才有）：work → 逐行 [行标, 原文]。
    # 只有带全文的注疏才能给「怎么讲这几句」的片段。
    comm_lines: dict = field(default_factory=dict)
    # work → (行标 → 行序, 归一化全书拼接, 每个归一化字符属于第几行, 每行在拼接里的起点)
    _comm_idx: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Package:
        d = json.loads(path.read_text(encoding="utf-8"))
        pkg = cls(meta=d["meta"], lines=d["base_lines"], comms=d["commentaries"])
        pkg.ids = [ln["id"] for ln in pkg.lines]
        pkg.pos = {x: i for i, x in enumerate(pkg.ids)}
        pkg.text = {ln["id"]: ln["text"] for ln in pkg.lines}
        pkg.by_line = {}
        pkg.by_anchor = {}
        for n in d["notes"]:
            pkg.by_line.setdefault(n["base_line"], []).append(n)
            if ref := line_ref(n["anchor"]):
                pkg.by_anchor.setdefault(n["work"], []).append((ref, n))
        for rows in pkg.by_anchor.values():
            rows.sort(key=lambda r: r[0])
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
        for work, rows in (d.get("commentary_lines") or {}).items():
            pkg.comm_lines[work] = rows
            ref_pos, flat, owner, starts = {}, [], [], []
            n = 0
            for k, (ref, txt) in enumerate(rows):
                ref_pos[ref] = k
                starts.append(n)
                t = normalise_for_match(txt)
                flat.append(t)
                owner.extend([k] * len(t))
                n += len(t)
            starts.append(n)
            pkg._comm_idx[work] = (ref_pos, "".join(flat), owner, starts)
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

    def excerpts(self, i0: int, i1: int) -> list[dict]:
        """各家注疏讲第 i0–i1 行论文的那一段原文（只对带全文的注疏）。

        对齐点只覆盖约 12% 的论文行，直接命中很少（俱舍实测 8.5%）。但注疏是顺着论
        一句句往下讲的——对齐点按注疏行序排后论文行号 100% 单调——所以取「i0 之前
        最后一个对齐点」到「i1 之后第一个对齐点」之间的注文，必然包住讲这几句的那段。
        再在里面找首个逐字牒引（EXCERPT_QUOTE_GRAM 字），从那一行起截取。找不到牒引
        就不给这家：宁缺，不给讲别处的注。

        按注疏行序给出；每条带行标区间与锚点，调用方据此链回原书。
        """
        if not self._comm_idx or i0 is None:
            return []
        base = "".join(normalise_for_match(self.text.get(self.ids[k], "")) for k in range(i0, i1 + 1))
        k = EXCERPT_QUOTE_GRAM
        grams = list(dict.fromkeys(base[j:j + k] for j in range(max(0, len(base) - k + 1))))
        if not grams:
            return []
        out = []
        for work, (ref_pos, flat, owner, starts) in self._comm_idx.items():
            prev = nxt = None
            for _ref, n in self.by_anchor.get(work, ()):
                p = self.pos.get(n["base_line"])
                if p is None or (r := line_ref(n["anchor"])) not in ref_pos:
                    continue
                if p <= i0:
                    prev = r
                elif p > i1:
                    nxt = r
                    break
            rows = self.comm_lines[work]
            c0 = ref_pos[prev] if prev else 0
            c1 = ref_pos[nxt] if nxt else len(rows)
            lo, hi = starts[c0], starts[c1]
            hits = [h for g in grams if (h := flat.find(g, lo, hi)) >= 0]
            if not hits:
                continue
            first = owner[min(hits)]
            # 起点对齐到「这处牒文」的开头，而不是命中行的行首。在「上一行＋命中行」里、
            # 命中位置之前找：
            #   1. 最后一处牒文起点——「論「……」」或「「……」者」。牒文常用「至」缩略
            #      （「謂前生至為同類因」者），4 字匹配会落在后面的解释上，只看句号会把
            #      牒文本身切掉；
            #   2. 没有牒文标志就从最后一个句号之后起（行首常是上一句的尾巴）；
            #   3. 都没有就从命中行行首起。
            last = first
            line_from = rows[first][0]
            prev_line = rows[first - 1][1] if first > c0 else ""
            win = prev_line + rows[first][1]
            cut = len(prev_line) + _raw_offset(rows[first][1], min(hits) - starts[first])
            start = _quote_start(win, cut)
            if start is None:
                j = win.rfind(_SENTENCE_END, 0, cut)
                start = j + 1 if j >= 0 else len(prev_line)
            while start < cut and win[start] in "」』":
                start += 1
            if start < len(prev_line):
                line_from = rows[first - 1][0]
            head = win[start:]
            text = head
            for li in range(first + 1, c1):
                if len(text) >= EXCERPT_CHARS:
                    break
                text += rows[li][1]
                last = li
            more = last + 1 < c1 or len(text) > EXCERPT_CHARS
            if len(text) > EXCERPT_CHARS:
                cut = text.rfind(_SENTENCE_END, int(EXCERPT_CHARS * 0.6), EXCERPT_CHARS + 80)
                text = text[: cut + 1] if cut >= 0 else text[:EXCERPT_CHARS]
            meta = self.comms.get(work) or {}
            out.append({
                "work": work,
                "title": meta.get("title"),
                "tier": meta.get("tier"),
                "text": text,
                "line_from": line_from,
                "line_to": rows[last][0],
                "anchor": f"{work}_p{line_from}",
                "truncated": more,
            })
        return out

    def source(self, work: str, ref_from: str, ref_to: str, limit: int) -> list[dict]:
        """一段注文（注疏自己的行标区间）在解释论的哪几句。

        行标形如 ``0334b14``：页四位补零、栏 a/b/c、行两位，所以字符串比较就是
        行序，不必解析。区间两端都含——读者看到的那一块注文，首尾两行的牒文
        同样是他在读的。

        按论文行去重：一部注疏常把同一句论的牒文分成几处（先牒后释、或科判里
        再牒一次），逐锚点列出来会让「这块注讲了几句论」答成「这块注有几个锚
        点」。同一句留置信度最高的那处。

        结果按论文行序，不按置信度——读者要的是「这块注依次讲了哪几句」，那是
        一条顺着读下去的线，按分数排会打乱它。

        逐条扫而不用二分：单部注疏最多一千多条，查一次的代价远小于一次 DB 往返，
        换来的是这段逻辑一眼能看懂。
        """
        best: dict[str, dict] = {}
        for ref, n in self.by_anchor.get(work, ()):
            if ref < ref_from or ref > ref_to:
                continue
            cur = best.get(n["base_line"])
            if cur is None or n["score"] > cur["score"]:
                best[n["base_line"]] = n
        ordered = sorted(best.values(), key=lambda n: self.pos.get(n["base_line"], 1 << 30))
        return ordered[:limit]


def _raw_offset(raw: str, norm_off: int) -> int:
    """归一化文本里的第 norm_off 个字，对应原文行里的第几个字符（标点在归一化时被去掉）。"""
    n = 0
    for i, ch in enumerate(raw):
        if n >= norm_off:
            return i
        n += len(normalise_for_match(ch))
    return len(raw)


_QUOTE_OPEN = re.compile(r"論?「")


def _quote_start(win: str, cut: int) -> int | None:
    """win[:cut] 里最后一处牒文的起点：「論「」，或后面紧跟「者」的「「…」」。"""
    best = None
    for m in _QUOTE_OPEN.finditer(win, 0, cut):
        if m.group().startswith("論"):
            best = m.start()
            continue
        close = win.find("」", m.end(), m.end() + 60)
        if close >= 0 and win[close + 1:close + 2] == "者":
            best = m.start()
    return best


def available_commentaries() -> list[dict]:
    """能反查的注疏清单（fojin 书号 + 它注的是哪一部）。

    只列有锚点的——包里的 ``commentaries`` 段是书目，而没有锚点的书反查必然空手，
    列出来等于给一个点了没反应的入口。
    """
    out = []
    for pkg in packages():
        for work, rows in pkg.by_anchor.items():
            meta = pkg.comms.get(work) or {}
            out.append({
                "cbeta_id": to_cbeta_id(work),
                "work": work,
                "title": meta.get("title"),
                "tier": meta.get("tier"),
                "anchors": len(rows),
                "base_work": pkg.meta.get("base_work"),
                "base_title": pkg.meta.get("base_title"),
            })
    return out


def find_commentary(cbeta_id: str) -> list[tuple[Package, str]]:
    """fojin 书号 → 装着这部注疏的包和它在包里的全号。

    抽屉手里只有 fojin 的 ``cbeta_id``（``T1821``），包里写的是 CBETA 全号
    （``T41n1821``，带册号）。同一部注疏可能出现在多个包里（它注了不止一部经），
    所以返回列表而不是单值。
    """
    if not cbeta_id:
        return []
    return [
        (pkg, work)
        for pkg in packages()
        for work in pkg.by_anchor
        if to_cbeta_id(work) == cbeta_id
    ]


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
            # 能给「注疏怎么讲这几句」片段（包里带注疏全文）
            "excerpts": bool(p.comm_lines),
            "line_coverage_pct": (
                p.meta["lines_with_notes"] * 100 // p.meta["line_count"]
                if p.meta.get("line_count") else None
            ),
        }
        for p in packages()
    ]
