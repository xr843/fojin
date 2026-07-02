from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))


def load_script(module_name: str, relative_path: str):
    inserted_helpers_stub = False
    if "elasticsearch" in sys.modules and "elasticsearch.helpers" not in sys.modules:
        helpers_stub = ModuleType("elasticsearch.helpers")

        async def _unused_async_bulk(*args, **kwargs):  # pragma: no cover - not used by these tests
            raise AssertionError("async_bulk should not run in importer discovery tests")

        helpers_stub.async_bulk = _unused_async_bulk
        sys.modules["elasticsearch.helpers"] = helpers_stub
        inserted_helpers_stub = True

    spec = importlib.util.spec_from_file_location(module_name, BACKEND_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted_helpers_stub:
            sys.modules.pop("elasticsearch.helpers", None)
    return module


@pytest.mark.asyncio
async def test_gretil_discovers_buddhist_texts_from_gretil_html_without_duplicates():
    gretil = load_script("import_gretil_for_test", "scripts/archive/imports/import_gretil.py")

    html = """
    <h4 id="RLBuddh">Buddhist</h4>
    <ul>
      <li>Abhidharmasamuccayabhasya
        <a href="gretil/corpustei/sa_abhidharmasamuccayabhASya.xml">TEI-conformant XML</a>
        <a href="gretil/corpustei/transformations/plaintext/sa_abhidharmasamuccayabhASya.txt">
          Plain Transformation (txt)
        </a>
      </li>
      <li>XML-only source
        <a href="gretil/corpustei/sa_xml_only.xml">TEI-conformant XML</a>
      </li>
    </ul>
    <h4 id="RLJaina">Jaina</h4>
    <a href="gretil/corpustei/sa_jaina.xml">TEI-conformant XML</a>
    <h4 id="Bauddha">Buddhist</h4>
    <ul>
      <li>Nagarjuna: Mulamadhyamakakarika
        <a href="/gretil/corpustei/sa_nAgArjuna-mUlamadhyamakakArikA.xml">TEI-conformant XML</a>
        <a href="gretil/corpustei/transformations/plaintext/sa_nAgArjuna-mUlamadhyamakakArikA.txt">
          Plain Transformation (txt)
        </a>
      </li>
    </ul>
    <h4 id="Other">Other</h4>
    <a href="gretil/corpustei/sa_other.xml">TEI-conformant XML</a>
    """
    fetched_urls: list[str] = []
    importer = gretil.GRETILImporter()

    async def fake_get(url: str):
        fetched_urls.append(url)
        return SimpleNamespace(text=html)

    importer.rate_limited_get = fake_get

    texts = await importer.discover_texts()

    assert fetched_urls == ["https://gretil.sub.uni-goettingen.de/gretil.html"]
    urls = {text["url"] for text in texts}
    assert urls == {
        "https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/sa_abhidharmasamuccayabhASya.txt",
        "https://gretil.sub.uni-goettingen.de/gretil/corpustei/sa_xml_only.xml",
        "https://gretil.sub.uni-goettingen.de/gretil/corpustei/transformations/plaintext/sa_nAgArjuna-mUlamadhyamakakArikA.txt",
    }
    assert len(texts) == len({Path(text["filename"]).stem for text in texts})
    assert {text["category"] for text in texts} == {"Buddhism"}


@pytest.mark.asyncio
async def test_84000_fallback_raw_url_uses_master_branch_when_download_url_missing():
    downloader = load_script("download_84000_data_for_test", "scripts/archive/fetch/download_84000_data.py")

    class FakeResponse:
        status_code = 200

        def json(self):
            return [
                {"name": "toh1.xml", "download_url": None, "size": 12},
                {"name": "README.md", "download_url": None, "size": 4},
            ]

    class FakeClient:
        async def get(self, url: str):
            return FakeResponse()

    files = await downloader.list_xml_files(FakeClient(), "translations/kangyur/translations")

    assert files == [
        {
            "name": "toh1.xml",
            "download_url": (
                "https://raw.githubusercontent.com/84000/data-tei/master/"
                "translations/kangyur/translations/toh1.xml"
            ),
            "size": 12,
        }
    ]
