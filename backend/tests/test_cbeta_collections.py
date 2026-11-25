"""按藏归属与补遗编号：导入其余各藏时，经号 → 藏、经号 → XML 文件不能出错。"""

import sys
from pathlib import Path

import pytest

from app.core.xml_parser import FRONT_MATTER_ID_RE, collection_of, find_all_xml_files, is_front_matter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from import_apparatus import juans_safe_for_anchors
from import_catalog import _extract_work_id_from_filename


@pytest.mark.parametrize(
    "cbeta_id,coll",
    [
        ("T0235", "T"),
        ("T0128a", "T"),
        ("X0288", "X"),
        ("JB095", "J"),
        ("JA042", "J"),
        ("GA0023", "GA"),
        ("GB0001", "GB"),
        ("G2241", "G"),
        ("ZWa044", "ZW"),
        ("Ba001", "B"),
        ("TX0001", "TX"),
        ("SC-dn1", None),
        ("", None),
    ],
)
def test_collection_of(cbeta_id, coll):
    # 「G」不能把 GA/GB 算进来，「T」不能把 TX（太虛全書，不收）算进来
    assert collection_of(cbeta_id) == coll


@pytest.mark.parametrize(
    "filename,work",
    [
        ("T08n0235.xml", "T0235"),
        ("J20nB095.xml", "JB095"),
        ("GA025n0023.xml", "GA0023"),
        ("B00na001.xml", "Ba001"),  # 補編附录篇：修前认不出，整篇被跳过
        ("ZW08na044_002.xml", "ZWa044"),
    ],
)
def test_work_id_from_filename(filename, work):
    assert _extract_work_id_from_filename(filename) == work


def test_find_files_for_appendix_numbering(tmp_path):
    for rel in ["ZW/ZW08/ZW08na044.xml", "ZW/ZW08/ZW08n0044.xml", "B/B00/B00na001.xml"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<x/>")
    assert [f.name for f in find_all_xml_files("ZWa044", str(tmp_path))] == ["ZW08na044.xml"]
    assert [f.name for f in find_all_xml_files("ZW0044", str(tmp_path))] == ["ZW08n0044.xml"]
    assert [f.name for f in find_all_xml_files("Ba001", str(tmp_path))] == ["B00na001.xml"]


def test_anchors_only_for_juans_matching_stored_content():
    parsed = {1: "如是我聞", 2: "一時佛在", 3: "新卷"}
    stored = {1: "如是我聞", 2: "一時佛住"}  # 卷 2 库里的正文与这份 XML 不同；卷 3 库里没有
    assert juans_safe_for_anchors(parsed, stored) == {1}


@pytest.mark.parametrize("cbeta_id", ["Ba001", "Ba023", "ZWa044", "GAa001", "GBa001", "Ia001"])
def test_front_matter_ids(cbeta_id):
    assert is_front_matter(cbeta_id)


@pytest.mark.parametrize("cbeta_id", ["B0130", "ZW0044", "GA0023", "I0001", "JA042", "JB095", "T0235", "X0288",
                                      "T0128a", "SC-an1", "GRETIL-x", "", None])
def test_not_front_matter(cbeta_id):
    # 正文经号（含 JA042 这种字母分部、T0128a 这种字母后缀）一律不能被当成附文藏起来
    assert not is_front_matter(cbeta_id)


def test_front_matter_regex_is_postgres_compatible():
    # 站点地图用 Postgres 的 ~ 运算符跑同一个正则：只能用 POSIX 也认的写法
    assert "(?" not in FRONT_MATTER_ID_RE.pattern
