"""SuttaCentral 相关内容的两条卫生约束 —— 来自 2026-09-13 复核 #1190 时的发现。

背景：SuttaCentral 创始人要求 FoJin 移除其全部数据（xr843/fojin#1190、
suttacentral/suttacentral#3584）。FoJin 按许可义务办事、不按施压办事：经文与
译文是 CC0（``suttacentral/bilara-data`` 的 ``LICENSE.md``），继续使用并署名。
但复核发现两处和这个立场对不上，所以用测试钉住：

1. **论坛不是 CC0。** ``discourse.suttacentral.net`` 的 ToS §3 把用户帖子授权为
   CC BY-NC-SA 3.0，版权在发帖的个人手里。Discourse 的 RSS ``<description>``
   放的是整个首楼，所以把它当 feed 源 = 近乎全文转载个人帖子（生产实测 256 帖，
   中位 941 字，18% 顶到 2000 字截断），而 /activity 上没有 BY 3.0 §4(a) 要求的
   许可声明。FoJin 对外说的是 "used under SuttaCentral's CC0 dedication" ——
   这句话覆盖不到论坛。
2. **#1189 在 NOTICE 里修掉的「SuttaCentral 译文是 CC BY-SA」** 还留在
   ``backend/docs/alignment-dataset-card.md`` 里 —— 同一个错，换了个文件。
"""

import ast
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FEED_SCRIPT = REPO_ROOT / "backend" / "scripts" / "fetch_academic_feeds.py"


def _feed_registry() -> list[dict]:
    """按 AST 取 FEED_REGISTRY 字面量 —— 不 import 脚本，免得牵出数据库依赖。"""
    tree = ast.parse(FEED_SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "FEED_REGISTRY":
            return ast.literal_eval(node.value)
    raise AssertionError("fetch_academic_feeds.py 里找不到 FEED_REGISTRY")


def test_suttacentral_forum_is_not_a_feed_source():
    """论坛帖是个人作品（CC BY-NC-SA 3.0），且 RSS 给的是整帖 —— 不能当 feed 抓。

    曾在 2026-06-11 以「EBT scholarship community」之名加入过一次；若将来想再加，
    先解决两件事：只存摘要而非整帖、页面带上许可声明。
    """
    registry = _feed_registry()
    assert registry, "FEED_REGISTRY 为空 —— 解析方式可能失效，这条测试就不再守任何东西"
    offenders = [f["name"] for f in registry if "discourse.suttacentral.net" in f["url"]]
    assert not offenders, (
        f"FEED_REGISTRY 又抓起了 SuttaCentral 论坛：{offenders}。论坛帖不是 CC0，"
        "是发帖人按 CC BY-NC-SA 3.0 授权的作品，且 Discourse RSS 的 description 是整帖。"
    )


_SKIP_DIRS = {".git", "node_modules", ".claude", ".venv", "dist", "build", "__pycache__"}
_BY_SA = re.compile(r"BY[- ]SA", re.IGNORECASE)


def test_no_doc_records_suttacentral_as_share_alike():
    """SuttaCentral 的经文与译文都是 CC0。BY-SA 只能作为「此前记错了」的历史说明出现。"""
    offenders = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = Path(dirpath) / name
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                lowered = line.lower()
                if "suttacentral" not in lowered or not _BY_SA.search(line):
                    continue
                if "wrongly" in lowered or "previous" in lowered or "曾" in line:
                    continue
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "以下文档仍把 SuttaCentral 记成 BY-SA（实为 CC0，见 bilara-data/LICENSE.md）：\n" + "\n".join(
        offenders
    )
