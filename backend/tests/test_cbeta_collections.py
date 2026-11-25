"""按藏归属与补遗编号：导入其余各藏时，经号 → 藏、经号 → XML 文件不能出错。"""

import sys
from pathlib import Path

import pytest

from app.core.xml_parser import collection_of, find_all_xml_files

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
