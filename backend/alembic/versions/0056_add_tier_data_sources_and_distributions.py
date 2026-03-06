"""add three-tier Buddhist resource data sources and distributions

Organize global Buddhist digital resources into three tiers:
  Tier 1: Directly downloadable, structured data (dictionaries, parallel corpora, catalogs)
  Tier 2: Requires more parsing work (TEI/RDF, Tibetan corpora, Sanskrit texts)
  Tier 3: Image/manuscript sources requiring OCR or manual processing

Revision ID: 0056
Revises: 0055
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── New data sources not yet in the database ──────────────────────────

NEW_SOURCES = [
    # Tier 1
    {
        "code": "dila-authority",
        "name_zh": "DILA 佛学规范资料库",
        "name_en": "DILA Buddhist Studies Authority Database",
        "base_url": "https://authority.dila.edu.tw/",
        "description": "DILA 佛学人名、地名、寺院、时间规范资料库，提供 JSON API 与批量下载。Tier 1 资源。",
        "access_type": "external",
        "region": "台湾",
        "languages": "zh,sa,pi,bo",
        "supports_search": True,
        "supports_api": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "is_active": True,
    },
    {
        "code": "cdsl-ap90",
        "name_zh": "Apte 梵英辞典",
        "name_en": "Apte Practical Sanskrit-English Dictionary",
        "base_url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/AP90Scan/2020/web/webtc/indexcaller.php",
        "description": "Apte 实用梵英辞典 (1890)，Cologne CDSL 收录，提供 XML 批量下载。Tier 1 资源。",
        "access_type": "external",
        "region": "德国",
        "languages": "sa,en",
        "supports_search": True,
        "supports_api": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "is_active": True,
    },
    {
        "code": "cdsl-pw",
        "name_zh": "Böhtlingk 梵德辞典",
        "name_en": "Böhtlingk Sanskrit-Wörterbuch (PW)",
        "base_url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/PWScan/2020/web/webtc/indexcaller.php",
        "description": "Böhtlingk & Roth 梵文大辞典（Petersburg Wörterbuch），Cologne CDSL 收录。Tier 1 资源。",
        "access_type": "external",
        "region": "德国",
        "languages": "sa,de",
        "supports_search": True,
        "supports_api": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "is_active": True,
    },
    {
        "code": "cdsl-wilson",
        "name_zh": "Wilson 梵英辞典",
        "name_en": "Wilson Sanskrit-English Dictionary",
        "base_url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/WILScan/2020/web/webtc/indexcaller.php",
        "description": "H.H. Wilson 梵英辞典 (1832)，Cologne CDSL 收录。Tier 1 资源。",
        "access_type": "external",
        "region": "德国",
        "languages": "sa,en",
        "supports_search": True,
        "supports_api": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "is_active": True,
    },
    # Tier 2
    {
        "code": "esukhia-derge",
        "name_zh": "Esukhia 德格丹珠尔",
        "name_en": "Esukhia Derge Tengyur",
        "base_url": "https://github.com/Esukhia/derge-tengyur",
        "description": "Esukhia 德格版《丹珠尔》藏文文本 GitHub 开源项目，经校对的 Unicode 藏文。Tier 2 资源。",
        "access_type": "external",
        "region": "国际",
        "languages": "bo",
        "supports_search": False,
        "supports_api": False,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "is_active": True,
    },
    {
        "code": "esukhia-kangyur",
        "name_zh": "Esukhia 德格甘珠尔",
        "name_en": "Esukhia Derge Kangyur",
        "base_url": "https://github.com/Esukhia/derge-kangyur",
        "description": "Esukhia 德格版《甘珠尔》藏文文本 GitHub 开源项目。Tier 2 资源。",
        "access_type": "external",
        "region": "国际",
        "languages": "bo",
        "supports_search": False,
        "supports_api": False,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "is_active": True,
    },
    {
        "code": "buddhanexus-data",
        "name_zh": "BuddhaNexus 平行语料",
        "name_en": "BuddhaNexus Parallel Corpus Data",
        "base_url": "https://github.com/BuddhaNexus/segmented-sanskrit",
        "description": "BuddhaNexus 分段梵藏巴利平行语料 GitHub 数据，适合比较语言学研究。Tier 2 资源。",
        "access_type": "external",
        "region": "德国",
        "languages": "sa,bo,pi,lzh",
        "supports_search": False,
        "supports_api": False,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "is_active": True,
    },
]

# ── Source distributions (download channels) for Tier 1 & 2 ──────────

SOURCE_DISTRIBUTIONS = [
    # ── Tier 1: DILA Authority DB ──
    {
        "source_code": "dila-authority",
        "code": "dila-authority-person-api",
        "name": "DILA Person Authority API",
        "channel_type": "api",
        "url": "https://authority.dila.edu.tw/person/",
        "format": "json",
        "license_note": "DILA 佛学人名规范资料库 API，CC BY-NC-SA 3.0 TW。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "dila-authority",
        "code": "dila-authority-place-api",
        "name": "DILA Place Authority API",
        "channel_type": "api",
        "url": "https://authority.dila.edu.tw/place/",
        "format": "json",
        "license_note": "DILA 佛学地名规范资料库 API。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    {
        "source_code": "dila-authority",
        "code": "dila-authority-time-api",
        "name": "DILA Time Authority API",
        "channel_type": "api",
        "url": "https://authority.dila.edu.tw/time/",
        "format": "json",
        "license_note": "DILA 佛学时间规范资料库 API。",
        "is_primary_ingest": False,
        "priority": 30,
        "is_active": True,
    },
    # ── Tier 1: DPD (Digital Pali Dictionary) ──
    {
        "source_code": "dpd-dict",
        "code": "dpd-sqlite-release",
        "name": "DPD SQLite Release",
        "channel_type": "bulk_dump",
        "url": "https://github.com/digitalpalidictionary/digitalpalidictionary/releases",
        "format": "sqlite",
        "license_note": "DPD 提供 SQLite 完整辞典下载，CC BY-NC 4.0。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "dpd-dict",
        "code": "dpd-github",
        "name": "DPD GitHub Source",
        "channel_type": "git",
        "url": "https://github.com/digitalpalidictionary/digitalpalidictionary",
        "format": "sqlite/tsv",
        "license_note": "DPD 源代码与数据仓库。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    # ── Tier 1: Cologne CDSL additional dictionaries ──
    {
        "source_code": "cdsl-cologne",
        "code": "cdsl-xml-github",
        "name": "CDSL XML Data GitHub",
        "channel_type": "git",
        "url": "https://github.com/sanskrit-lexicon/csl-orig",
        "format": "xml",
        "license_note": "Cologne CDSL 全部辞典 XML 源数据 GitHub 仓库。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "cdsl-ap90",
        "code": "cdsl-ap90-xml",
        "name": "Apte XML Data",
        "channel_type": "bulk_dump",
        "url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/AP90Scan/2020/downloads/ap90xml.zip",
        "format": "xml",
        "license_note": "Apte 梵英辞典 XML 批量下载。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "cdsl-pw",
        "code": "cdsl-pw-xml",
        "name": "PW XML Data",
        "channel_type": "bulk_dump",
        "url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/PWScan/2020/downloads/pwxml.zip",
        "format": "xml",
        "license_note": "Böhtlingk 梵德辞典 XML 批量下载。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "cdsl-wilson",
        "code": "cdsl-wilson-xml",
        "name": "Wilson XML Data",
        "channel_type": "bulk_dump",
        "url": "https://www.sanskrit-lexicon.uni-koeln.de/scans/WILScan/2020/downloads/wilxml.zip",
        "format": "xml",
        "license_note": "Wilson 梵英辞典 XML 批量下载。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: SuttaCentral bilara-data (already has distribution, add API) ──
    {
        "source_code": "suttacentral",
        "code": "suttacentral-api",
        "name": "SuttaCentral API",
        "channel_type": "api",
        "url": "https://suttacentral.net/api/v0/",
        "format": "json",
        "license_note": "SuttaCentral REST API，CC0 公共领域。",
        "is_primary_ingest": False,
        "priority": 30,
        "is_active": True,
    },
    # ── Tier 1: Kanseki Repository ──
    {
        "source_code": "kanseki-repo",
        "code": "kanripo-github-org",
        "name": "Kanripo GitHub Organization",
        "channel_type": "git",
        "url": "https://github.com/kanripo",
        "format": "txt/xml",
        "license_note": "Kanripo 汉文典籍 GitHub 组织，含数千部经典。CC BY-SA。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: BDK English Tripitaka ──
    {
        "source_code": "bdk-tripitaka",
        "code": "bdk-pdf-download",
        "name": "BDK PDF Downloads",
        "channel_type": "bulk_dump",
        "url": "https://www.bdkamerica.org/tripitaka-list/",
        "format": "pdf",
        "license_note": "BDK 英译大藏经 PDF 免费下载（需注册），可 OCR 提取文本。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: DILA Glossaries (additional dictionaries) ──
    {
        "source_code": "dila-glossaries",
        "code": "dila-glossaries-tei-download",
        "name": "DILA Glossaries TEI Download",
        "channel_type": "bulk_dump",
        "url": "https://glossaries.dila.edu.tw/data/",
        "format": "tei/xml",
        "license_note": "DILA 佛学辞典 TEI P5 XML 批量下载。已导入 DFB/Soothill/Hopkins。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: 84000 (already has distributions, add glossary) ──
    {
        "source_code": "84000",
        "code": "84000-glossary",
        "name": "84000 Glossary",
        "channel_type": "git",
        "url": "https://github.com/84000/data-tei",
        "format": "tei/xml",
        "license_note": "84000 术语表包含在 data-tei 仓库内，可提取藏梵英多语术语。",
        "is_primary_ingest": False,
        "priority": 40,
        "is_active": True,
    },
    # ── Tier 2: ACIP Tibetan ──
    {
        "source_code": "acip",
        "code": "acip-texts-archive",
        "name": "ACIP Text Archive",
        "channel_type": "bulk_dump",
        "url": "https://www.asianclassics.org/",
        "format": "txt",
        "license_note": "ACIP 藏文文本数据库，需要 Wylie 转写处理。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: Esukhia Derge Tengyur & Kangyur ──
    {
        "source_code": "esukhia-derge",
        "code": "esukhia-derge-tengyur-github",
        "name": "Esukhia Derge Tengyur GitHub",
        "channel_type": "git",
        "url": "https://github.com/Esukhia/derge-tengyur",
        "format": "txt",
        "license_note": "Esukhia 德格丹珠尔校对藏文文本，CC0 公共领域。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "esukhia-kangyur",
        "code": "esukhia-derge-kangyur-github",
        "name": "Esukhia Derge Kangyur GitHub",
        "channel_type": "git",
        "url": "https://github.com/Esukhia/derge-kangyur",
        "format": "txt",
        "license_note": "Esukhia 德格甘珠尔校对藏文文本，CC0 公共领域。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: Gandhari.org ──
    {
        "source_code": "gandhari",
        "code": "gandhari-catalog-api",
        "name": "Gandhari.org Catalog",
        "channel_type": "api",
        "url": "https://gandhari.org/catalog",
        "format": "html",
        "license_note": "犍陀罗语文本目录与文献库，需爬取 HTML 结构化。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: GRETIL Sanskrit ──
    {
        "source_code": "gretil",
        "code": "gretil-github-mirror",
        "name": "GRETIL GitHub Mirror",
        "channel_type": "git",
        "url": "https://github.com/gretil-corpus/gretil-corpus-tei-2024",
        "format": "tei/xml",
        "license_note": "GRETIL 梵文文本 TEI 格式 GitHub 镜像，公共领域。推荐主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: OpenPecha ──
    {
        "source_code": "openpecha",
        "code": "openpecha-github-org",
        "name": "OpenPecha GitHub Organization",
        "channel_type": "git",
        "url": "https://github.com/OpenPecha",
        "format": "opf",
        "license_note": "OpenPecha 藏文文本 GitHub 组织，OPF 格式。CC0。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "openpecha",
        "code": "openpecha-catalog",
        "name": "OpenPecha Catalog",
        "channel_type": "git",
        "url": "https://github.com/OpenPecha/openpecha-catalog",
        "format": "csv",
        "license_note": "OpenPecha 目录数据，可用于批量发现文本。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    # ── Tier 2: BuddhaNexus ──
    {
        "source_code": "buddhanexus-data",
        "code": "buddhanexus-segmented-sanskrit",
        "name": "BuddhaNexus Segmented Sanskrit",
        "channel_type": "git",
        "url": "https://github.com/BuddhaNexus/segmented-sanskrit",
        "format": "json",
        "license_note": "BuddhaNexus 分段梵文数据。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "buddhanexus-data",
        "code": "buddhanexus-segmented-pali",
        "name": "BuddhaNexus Segmented Pali",
        "channel_type": "git",
        "url": "https://github.com/BuddhaNexus/segmented-pali",
        "format": "json",
        "license_note": "BuddhaNexus 分段巴利文数据。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    # ── Tier 2: SARIT Sanskrit ──
    {
        "source_code": "sarit",
        "code": "sarit-github",
        "name": "SARIT GitHub Repository",
        "channel_type": "git",
        "url": "https://github.com/sarit/sarit-corpus",
        "format": "tei/xml",
        "license_note": "SARIT 梵文 TEI 文本语料库，CC BY-SA。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 2: DCS Sanskrit ──
    {
        "source_code": "dcs-sanskrit",
        "code": "dcs-conllu-github",
        "name": "DCS CoNLL-U GitHub",
        "channel_type": "git",
        "url": "https://github.com/OliverHellworthy/dcs",
        "format": "conllu",
        "license_note": "Digital Corpus of Sanskrit 形态分析数据 CoNLL-U 格式。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 3: IDP Dunhuang ──
    {
        "source_code": "idp",
        "code": "idp-iiif-manifest",
        "name": "IDP IIIF Manifests",
        "channel_type": "api",
        "url": "https://idp.bl.uk/",
        "format": "iiif/json",
        "license_note": "国际敦煌项目 IIIF 图像接口，图像高清但需 OCR 提取文本。Tier 3。",
        "is_primary_ingest": False,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 3: BDRC Tibetan ──
    {
        "source_code": "bdrc",
        "code": "bdrc-iiif-presentation",
        "name": "BDRC IIIF Presentation API",
        "channel_type": "api",
        "url": "https://iiifpres.bdrc.io/",
        "format": "iiif/json",
        "license_note": "BDRC IIIF 藏文写本图像 API。图像源需 OCR。Tier 3。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    {
        "source_code": "bdrc",
        "code": "bdrc-linked-data",
        "name": "BDRC Linked Data",
        "channel_type": "api",
        "url": "https://ldspdi.bdrc.io/",
        "format": "rdf/json-ld",
        "license_note": "BDRC 关联数据 SPARQL 端点，适合元数据与知识图谱导入。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 3: Berlin Turfan ──
    {
        "source_code": "berlin-turfan",
        "code": "berlin-turfan-titus",
        "name": "TITUS Turfan Texts",
        "channel_type": "bulk_dump",
        "url": "https://titus.uni-frankfurt.de/indexe.htm",
        "format": "html",
        "license_note": "TITUS 吐鲁番文献数字化，包含部分转录文本。需解析 HTML。Tier 3。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    # ── Tier 1: Rangjung Yeshe (already imported, add distribution) ──
    {
        "source_code": "rangjung-yeshe",
        "code": "rangjung-yeshe-github",
        "name": "Tibetan Dictionary GitHub CSV",
        "channel_type": "git",
        "url": "https://github.com/christiansteinert/tibetan-dictionary",
        "format": "csv",
        "license_note": "christiansteinert 藏英辞典 GitHub 仓库，含 Rangjung Yeshe 数据。已导入。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: PTS PED (already imported, add distribution) ──
    {
        "source_code": "pts-ped",
        "code": "pts-ped-github",
        "name": "PTS PED GitHub Data",
        "channel_type": "git",
        "url": "https://github.com/vpnry/ptsped",
        "format": "tsv",
        "license_note": "PTS 巴英辞典 GitHub 结构化数据。已导入。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: NTI Reader (already imported, add distribution) ──
    {
        "source_code": "nti-reader",
        "code": "nti-reader-github",
        "name": "NTI Reader GitHub",
        "channel_type": "git",
        "url": "https://github.com/alexamies/chinesenotes.com",
        "format": "tsv",
        "license_note": "NTI Reader 中英佛学辞典 GitHub 数据。已导入。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    # ── Tier 1: DILA dictionaries (already imported, add distributions) ──
    {
        "source_code": "dila-dfb",
        "code": "dila-dfb-tei-download",
        "name": "DFB TEI P5 XML Download",
        "channel_type": "bulk_dump",
        "url": "https://glossaries.dila.edu.tw/data/dingfubao.dila.tei.p5.xml.zip",
        "format": "tei/xml",
        "license_note": "丁福保佛学大辞典 TEI P5 XML，CC BY-SA 2.5 TW。已导入 31,366 条。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "dila-soothill",
        "code": "dila-soothill-tei-download",
        "name": "Soothill TEI P5 XML Download",
        "channel_type": "bulk_dump",
        "url": "https://glossaries.dila.edu.tw/data/soothill-hodous.ddbc.tei.p5.xml.zip",
        "format": "tei/xml",
        "license_note": "Soothill 中英佛学辞典 TEI P5 XML，CC。已导入 16,792 条。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "dila-hopkins",
        "code": "dila-hopkins-tei-download",
        "name": "Hopkins TEI P5 XML Download",
        "channel_type": "bulk_dump",
        "url": "https://glossaries.dila.edu.tw/data/hopkins.dila.tei.p5.xml.zip",
        "format": "tei/xml",
        "license_note": "Hopkins 藏梵英辞典 TEI P5 XML。已导入 18,441 条。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
]

# Track all new source codes for downgrade
_NEW_SOURCE_CODES = [s["code"] for s in NEW_SOURCES]
_NEW_DIST_CODES = [d["code"] for d in SOURCE_DISTRIBUTIONS]


def _upsert_source(conn, source: dict) -> None:
    existing = conn.execute(
        sa_text("SELECT id FROM data_sources WHERE code = :code"),
        {"code": source["code"]},
    ).scalar()

    params = {
        "code": source["code"],
        "name_zh": source["name_zh"],
        "name_en": source["name_en"],
        "base_url": source["base_url"],
        "description": source["description"],
        "access_type": source["access_type"],
        "region": source["region"],
        "languages": source["languages"],
        "supports_search": source["supports_search"],
        "supports_fulltext": source.get("supports_fulltext", False),
        "has_local_fulltext": source.get("has_local_fulltext", False),
        "has_remote_fulltext": source.get("has_remote_fulltext", False),
        "supports_iiif": source.get("supports_iiif", False),
        "supports_api": source.get("supports_api", False),
        "is_active": source["is_active"],
    }

    if existing:
        conn.execute(
            sa_text("""
                UPDATE data_sources SET
                    name_zh = :name_zh, name_en = :name_en,
                    base_url = :base_url, description = :description,
                    access_type = :access_type, region = :region,
                    languages = :languages,
                    supports_search = :supports_search,
                    supports_fulltext = :supports_fulltext,
                    has_local_fulltext = :has_local_fulltext,
                    has_remote_fulltext = :has_remote_fulltext,
                    supports_iiif = :supports_iiif,
                    supports_api = :supports_api,
                    is_active = :is_active
                WHERE code = :code
            """),
            params,
        )
    else:
        conn.execute(
            sa_text("""
                INSERT INTO data_sources (
                    code, name_zh, name_en, base_url, api_url, description,
                    access_type, region, languages,
                    supports_search, supports_fulltext,
                    has_local_fulltext, has_remote_fulltext,
                    supports_iiif, supports_api, is_active
                ) VALUES (
                    :code, :name_zh, :name_en, :base_url, NULL, :description,
                    :access_type, :region, :languages,
                    :supports_search, :supports_fulltext,
                    :has_local_fulltext, :has_remote_fulltext,
                    :supports_iiif, :supports_api, :is_active
                )
            """),
            params,
        )


def _insert_distribution(conn, item: dict) -> None:
    source_id = conn.execute(
        sa_text("SELECT id FROM data_sources WHERE code = :code"),
        {"code": item["source_code"]},
    ).scalar()
    if source_id is None:
        return

    existing = conn.execute(
        sa_text("SELECT id FROM source_distributions WHERE code = :code"),
        {"code": item["code"]},
    ).scalar()
    if existing:
        conn.execute(
            sa_text("""
                UPDATE source_distributions SET
                    source_id = :source_id, name = :name,
                    channel_type = :channel_type, url = :url,
                    format = :format, license_note = :license_note,
                    is_primary_ingest = :is_primary_ingest,
                    priority = :priority, is_active = :is_active
                WHERE code = :code
            """),
            {
                "source_id": source_id,
                "code": item["code"],
                "name": item["name"],
                "channel_type": item["channel_type"],
                "url": item["url"],
                "format": item["format"],
                "license_note": item["license_note"],
                "is_primary_ingest": item["is_primary_ingest"],
                "priority": item["priority"],
                "is_active": item["is_active"],
            },
        )
        return

    conn.execute(
        sa_text("""
            INSERT INTO source_distributions (
                source_id, code, name, channel_type, url, format,
                license_note, is_primary_ingest, priority, is_active
            ) VALUES (
                :source_id, :code, :name, :channel_type, :url, :format,
                :license_note, :is_primary_ingest, :priority, :is_active
            )
        """),
        {
            "source_id": source_id,
            "code": item["code"],
            "name": item["name"],
            "channel_type": item["channel_type"],
            "url": item["url"],
            "format": item["format"],
            "license_note": item["license_note"],
            "is_primary_ingest": item["is_primary_ingest"],
            "priority": item["priority"],
            "is_active": item["is_active"],
        },
    )


def upgrade() -> None:
    conn = op.get_bind()

    # Insert new sources first
    for source in NEW_SOURCES:
        _upsert_source(conn, source)

    # Then insert distributions (which reference sources)
    for item in SOURCE_DISTRIBUTIONS:
        _insert_distribution(conn, item)


def downgrade() -> None:
    conn = op.get_bind()

    # Remove distributions
    for code in _NEW_DIST_CODES:
        conn.execute(
            sa_text("DELETE FROM source_distributions WHERE code = :code"),
            {"code": code},
        )

    # Remove new sources (only those we added)
    for code in _NEW_SOURCE_CODES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": code},
        )
