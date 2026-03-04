"""deduplicate sources, deactivate dead, fix data quality

Comprehensive audit (2026-03-04) of 333 active sources:

PHASE 1 — DELETE 13 duplicate sources (keeping better entry):
  sat-utokyo → sat, suttacentral-org → suttacentral, cbeta-org → cbeta,
  tbrc-bdrc → bdrc, polyglotta → oslo-polyglotta, dharmanexus → buddhanexus,
  dharma-dictionary → ddb, sinhala-tripitaka → tipitaka-lk,
  gandhari-texts-sydney → gandhari, washington-gandhari → gandhari,
  stein-collection → idp, cscd-myanmar → myanmar-tipitaka,
  titus → gretil (not Buddhist-specific)

PHASE 2 — DEACTIVATE 10 confirmed dead/unreachable sources:
  mahayana-texts, xuanzang-project, zhonghua-dazangjing, myanmar-digital-lib,
  read-workbench, cass-guji, diga-bochum, korean-tripitaka-db,
  vietnamese-nikaaya, snu-kyujanggak

PHASE 3 — Fix data quality:
  - 2 wrong regions: gandhari→美国, adarsha-pechamaker→美国
  - 3 wrong languages: bdrc→bo,sa,lzh,en; laos-palm-leaf→lo,pi;
    oslo-polyglotta→sa,bo,pi,lzh,en
  - 3 URL corrections: mitra-ai, numata-center, rkts

Revision ID: 0044
Revises: 0043
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── PHASE 1: Duplicate sources to delete ──
DELETE_CODES = [
    "sat-utokyo",           # dup of sat
    "suttacentral-org",     # dup of suttacentral
    "cbeta-org",            # dup of cbeta
    "tbrc-bdrc",            # dup of bdrc
    "polyglotta",           # dup of oslo-polyglotta
    "dharmanexus",          # dup of buddhanexus
    "dharma-dictionary",    # dup of ddb
    "sinhala-tripitaka",    # dup of tipitaka-lk
    "gandhari-texts-sydney",# dup of gandhari
    "washington-gandhari",  # dup of gandhari
    "stein-collection",     # dup of idp
    "cscd-myanmar",         # dup of myanmar-tipitaka
    "titus",                # overlaps gretil, not Buddhist-specific
]

# For downgrade: (code, name_zh, name_en, base_url, region, languages,
#   has_local_fulltext, has_remote_fulltext, supports_search, supports_iiif,
#   supports_api, access_type, description)
DELETED_RECORDS = [
    ("sat-utokyo", "东京大学 SAT 大藏经", "SAT Daizōkyō Text Database",
     "https://21dzk.l.u-tokyo.ac.jp/SAT/", "日本", "lzh,ja",
     False, False, True, False, False, "external",
     "日本地区佛教数字资源"),
    ("suttacentral-org", "SuttaCentral 早期佛典", "SuttaCentral Early Buddhist Texts",
     "https://suttacentral.net/", "澳大利亚", "pi,en,lzh",
     False, True, True, False, True, "external",
     "国际地区佛教数字资源"),
    ("cbeta-org", "CBETA 中华电子佛典", "Chinese Buddhist Electronic Text Assn",
     "https://www.cbeta.org/", "中国台湾", "lzh",
     True, False, True, False, False, "external",
     "国际地区佛教数字资源"),
    ("tbrc-bdrc", "佛教数字资源中心 BDRC", "Buddhist Digital Resource Center",
     "https://www.bdrc.io/", "美国", "bo,sa,en",
     False, False, True, False, True, "external",
     "国际地区佛教数字资源"),
    ("polyglotta", "多语种佛典图书馆", "Bibliotheca Polyglotta",
     "https://www2.hf.uio.no/polyglotta", "挪威", "sa,bo,lzh,pi,en",
     False, False, False, False, False, "external",
     "奥斯陆大学多语种平行文本，含佛教经典多语对照"),
    ("dharmanexus", "法典知识图谱", "DharmaNexus Knowledge Graph",
     "https://dharmamitra.org/nexus", "国际", "sa,pi,bo,lzh,en",
     False, False, False, False, False, "external",
     "基于AI的佛教概念知识图谱与经典交叉引用平台"),
    ("dharma-dictionary", "法语辞典 (Dharma Dictionary)", "Dharma Dictionary",
     "https://rywiki.tsadra.org/", "美国", "bo,en",
     False, False, False, False, False, "external",
     "Erik Pema Kunsang 藏英佛学术语辞典"),
    ("sinhala-tripitaka", "僧伽罗语三藏电子版", "Sinhala Tipitaka Online",
     "https://tipitaka.lk/", "斯里兰卡", "si,pi",
     False, False, False, False, False, "external",
     "斯里兰卡巴利三藏僧伽罗语翻译全文在线版"),
    ("gandhari-texts-sydney", "悉尼犍陀罗语文本", "Gandhari.org Texts (Sydney)",
     "https://gandhari.org", "澳大利亚", "pgd",
     False, False, True, False, False, "external",
     "悉尼犍陀罗语佛教文本数据库与词典"),
    ("washington-gandhari", "华盛顿大学犍陀罗研究", "Univ Washington Gandhāran Studies",
     "https://gandhari.org/", "美国", "en,sa,lzh",
     False, False, True, False, False, "external",
     "华盛顿大学犍陀罗语研究组，运营 gandhari.org 犍陀罗语文本数据库"),
    ("stein-collection", "斯坦因敦煌收集品", "Stein Collection",
     "https://www.bl.uk/collection-guides/stein-collection", "英国", "en,sa,pi",
     False, False, False, False, False, "external",
     "大英图书馆斯坦因敦煌收集品导览与数字化资源（通过 IDP 访问实际影像）"),
    ("cscd-myanmar", "缅甸第六次结集", "Chaṭṭha Saṅgāyana CD",
     "https://www.tipitaka.org", "缅甸", "pi,my",
     False, False, False, False, False, "external",
     "缅甸第六次佛教结集巴利三藏电子版"),
    ("titus", "TITUS 印欧语文本库",
     "Thesaurus Indogermanischer Text- und Sprachmaterialien",
     "https://titus.uni-frankfurt.de/", "德国", "sa,pi,xto,txb,sog,kho",
     False, False, False, False, False, "external",
     "法兰克福大学印欧语系文本数据库，含梵/巴利/吐火罗佛教文本"),
]

# ── PHASE 2: Dead/unreachable sources to deactivate ──
DEACTIVATE_CODES = [
    "mahayana-texts",       # dead URL
    "xuanzang-project",     # dead URL
    "zhonghua-dazangjing",  # dead URL
    "myanmar-digital-lib",  # dead URL
    "read-workbench",       # dead URL
    "cass-guji",            # dead URL
    "diga-bochum",          # dead URL
    "korean-tripitaka-db",  # dead URL
    "vietnamese-nikaaya",   # dead URL
    "snu-kyujanggak",       # dead URL
]

# ── PHASE 3: Data quality fixes ──
REGION_FIXES = {
    "gandhari": "美国",
    "adarsha-pechamaker": "美国",
}
REGION_ORIGINALS = {
    "gandhari": "印度",
    "adarsha-pechamaker": "中国大陆",
}

LANGUAGE_FIXES = {
    "bdrc": "bo,sa,lzh,en",
    "laos-palm-leaf": "lo,pi",
    "oslo-polyglotta": "sa,bo,pi,lzh,en",
}
LANGUAGE_ORIGINALS = {
    "bdrc": "lzh",
    "laos-palm-leaf": "lzh",
    "oslo-polyglotta": "lzh",
}

URL_FIXES = {
    "mitra-ai": "https://dharmamitra.org/",
    "numata-center": "https://www.bdkamerica.org/",
    "rkts": "https://www.rkts.org/",
}
URL_ORIGINALS = {
    "mitra-ai": "https://mitra-t.org/",
    "numata-center": "https://www.numatacenter.com/",
    "rkts": "https://www.istb.univie.ac.at/kanjur/rktsneu/sub/index.php",
}


def _escape(s: str) -> str:
    """Escape single quotes for SQL."""
    return s.replace("'", "''")


def upgrade() -> None:
    # Phase 1: Delete 13 duplicate sources
    del_str = ", ".join(f"'{c}'" for c in DELETE_CODES)
    op.execute(f"DELETE FROM data_sources WHERE code IN ({del_str})")

    # Phase 2: Deactivate 10 dead sources
    deact_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = false "
        f"WHERE code IN ({deact_str})"
    )

    # Phase 3a: Fix regions
    for code, region in REGION_FIXES.items():
        op.execute(
            f"UPDATE data_sources SET region = '{region}' "
            f"WHERE code = '{code}'"
        )

    # Phase 3b: Fix languages
    for code, langs in LANGUAGE_FIXES.items():
        op.execute(
            f"UPDATE data_sources SET languages = '{langs}' "
            f"WHERE code = '{code}'"
        )

    # Phase 3c: Fix URLs
    for code, url in URL_FIXES.items():
        op.execute(
            f"UPDATE data_sources SET base_url = '{url}' "
            f"WHERE code = '{code}'"
        )


def downgrade() -> None:
    # Reverse Phase 3c: Restore URLs
    for code, url in URL_ORIGINALS.items():
        op.execute(
            f"UPDATE data_sources SET base_url = '{url}' "
            f"WHERE code = '{code}'"
        )

    # Reverse Phase 3b: Restore languages
    for code, langs in LANGUAGE_ORIGINALS.items():
        op.execute(
            f"UPDATE data_sources SET languages = '{langs}' "
            f"WHERE code = '{code}'"
        )

    # Reverse Phase 3a: Restore regions
    for code, region in REGION_ORIGINALS.items():
        op.execute(
            f"UPDATE data_sources SET region = '{region}' "
            f"WHERE code = '{code}'"
        )

    # Reverse Phase 2: Re-activate dead sources
    deact_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = true "
        f"WHERE code IN ({deact_str})"
    )

    # Reverse Phase 1: Re-insert deleted duplicates
    for rec in DELETED_RECORDS:
        (code, name_zh, name_en, base_url, region, languages,
         has_local, has_remote, supports_search, supports_iiif,
         supports_api, access_type, description) = rec
        name_zh_e = _escape(name_zh)
        name_en_e = _escape(name_en) if name_en else None
        desc_e = _escape(description) if description else None
        name_en_val = f"'{name_en_e}'" if name_en_e else "NULL"
        desc_val = f"'{desc_e}'" if desc_e else "NULL"
        url_val = f"'{base_url}'" if base_url else "NULL"
        op.execute(
            f"INSERT INTO data_sources "
            f"(code, name_zh, name_en, base_url, region, languages, is_active, "
            f"has_local_fulltext, has_remote_fulltext, supports_search, "
            f"supports_iiif, supports_api, access_type, description) "
            f"VALUES ('{code}', '{name_zh_e}', {name_en_val}, {url_val}, "
            f"'{region}', '{languages}', true, "
            f"{has_local}, {has_remote}, {supports_search}, "
            f"{supports_iiif}, {supports_api}, '{access_type}', {desc_val})"
        )
