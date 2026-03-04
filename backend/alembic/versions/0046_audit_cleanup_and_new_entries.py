"""manual audit cleanup: dedup, fix failures, reactivate, add BUDA + distributions

Based on hands-on audit of 333 active sources with URL reachability testing
(271 OK / 62 problems). This migration addresses the 6-step priority plan:

STEP 1 — Delete 5 remaining hard duplicates:
  titus-thesaurus (=titus, already deleted in 0044)
  fpl (=fragile-palm-leaves, keep fragilepalm.org)
  pali-text-society (=palitextsociety, keep palitextsociety.org)
  budsir (=mahidol-tipitaka, same URL)
  dongguk-univ (=abc-tripitaka, same URL kabc.dongguk.edu)

STEP 2 — Deactivate 7 hard failures (400/404/405/NO_URL):
  iriz-hanazono (400), tnh-audio (404), wellcome-buddhist (405),
  manchu-studies (NO_URL), mongolian-kanjur (NO_URL), preah-sihanouk (NO_URL)
  + fix harvard-yenching URL (404 → working Harvard Library URL)
  + fix cass-guji URL (already inactive, update to guji.cssn.cn)

STEP 3 — Reactivate 3 confirmed-accessible sources:
  sarit, tianjin-lib, zhejiang-lib

STEP 4 — Add BUDA (BDRC reading portal)

STEP 5 — Add 2 CBETA source_distributions:
  cbeta-normal-text, cbeta-txt

STEP 6 — Add 2 84000 source_distributions:
  84000-ekangyur, 84000-etengyur

Revision ID: 0046
Revises: 0045
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── STEP 1: Hard duplicates to delete ──
DELETE_CODES = [
    "titus-thesaurus",   # dup of titus (deleted in 0044), same URL
    "fpl",               # dup of fragile-palm-leaves
    "pali-text-society",  # dup of palitextsociety
    "budsir",            # dup of mahidol-tipitaka, same URL
    "dongguk-univ",      # dup of abc-tripitaka, same URL
]

# For downgrade restoration
DELETED_RECORDS = [
    ("titus-thesaurus", "TITUS 印欧语文本库",
     "TITUS Thesaurus Indogermanischer Text",
     "https://titus.uni-frankfurt.de/", "德国", "sa,pi,pgd,xto,txb",
     False, False, True, False, False, "external",
     "法兰克福大学印欧语系文本数据库（含梵/巴/犍陀罗/吐火罗佛教经典）"),
    ("fpl", "脆弱贝叶写本项目", "Fragile Palm Leaves Foundation",
     "https://fragile-palm-leaves.org/", "泰国", "pi,my,th,km",
     False, False, False, False, False, "external",
     "东南亚贝叶经手稿保存与数字化基金会"),
    ("pali-text-society", "巴利圣典协会", "Pali Text Society",
     "https://www.palitext.com/", "英国", "en,sa,pi",
     False, False, True, False, False, "external",
     "英国地区佛教数字资源"),
    ("budsir", "泰国巴利三藏", "Budsir Thai Pali Canon",
     "https://budsir.mahidol.ac.th", "泰国", "pi,th",
     False, False, False, False, False, "external",
     "泰国Mahidol大学维护的巴利三藏电子版"),
    ("dongguk-univ", "东国大学佛教学术院", "Dongguk Univ Buddhist Academy",
     "https://kabc.dongguk.edu/", "韩国", "lzh,ko",
     False, False, False, False, False, "external",
     "韩国地区佛教数字资源"),
]

# ── STEP 2: Hard failures to deactivate ──
DEACTIVATE_CODES = [
    "iriz-hanazono",     # 400 error
    "tnh-audio",         # 404 error
    "wellcome-buddhist", # 405 error
    "manchu-studies",    # NO_URL placeholder
    "mongolian-kanjur",  # NO_URL placeholder
    "preah-sihanouk",    # NO_URL placeholder
]

# URL fixes (step 2 also)
URL_FIXES = {
    "harvard-yenching": "https://library.harvard.edu/libraries/yenching",
    "cass-guji": "https://www.guji.cssn.cn/",
}
URL_ORIGINALS = {
    "harvard-yenching": "https://library.harvard.edu/libraries/harvard-yenching-library",
    "cass-guji": "https://www.ncpssd.cn/guji/",
}

# ── STEP 3: Reactivate confirmed-accessible sources ──
REACTIVATE_CODES = ["sarit", "tianjin-lib", "zhejiang-lib"]


def _escape(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    # STEP 1: Delete 5 hard duplicates
    del_str = ", ".join(f"'{c}'" for c in DELETE_CODES)
    op.execute(f"DELETE FROM data_sources WHERE code IN ({del_str})")

    # STEP 2a: Deactivate 6 hard failures
    deact_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = false "
        f"WHERE code IN ({deact_str})"
    )

    # STEP 2b: Fix URLs
    for code, url in URL_FIXES.items():
        op.execute(
            f"UPDATE data_sources SET base_url = '{url}' "
            f"WHERE code = '{code}'"
        )

    # STEP 3: Reactivate 3 sources
    react_str = ", ".join(f"'{c}'" for c in REACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = true "
        f"WHERE code IN ({react_str})"
    )

    # STEP 4: Add BUDA
    op.execute(
        "INSERT INTO data_sources "
        "(code, name_zh, name_en, base_url, region, languages, "
        "is_active, has_local_fulltext, has_remote_fulltext, "
        "supports_search, supports_iiif, supports_api, "
        "access_type, description) "
        "VALUES ('buda', 'BUDA 佛教数字档案馆', 'Buddhist Digital Archives (BUDA)', "
        "'https://buda.bdrc.io/', '美国', 'bo,sa,lzh,en', "
        "true, false, true, "
        "true, true, true, "
        "'external', "
        "'BDRC 阅读与浏览入口，提供藏文、梵文、汉文佛典在线阅读与 IIIF 影像浏览')"
    )

    # STEP 5: Add 2 CBETA source_distributions
    op.execute(
        "INSERT INTO source_distributions "
        "(source_id, code, name, channel_type, url, format, "
        "is_primary_ingest, priority, is_active) "
        "SELECT id, 'cbeta-normal-text', 'CBETA Normal Text', 'git', "
        "'https://github.com/DILA-edu/cbeta-normal-text', 'txt', "
        "false, 50, true "
        "FROM data_sources WHERE code = 'cbeta'"
    )
    op.execute(
        "INSERT INTO source_distributions "
        "(source_id, code, name, channel_type, url, format, "
        "is_primary_ingest, priority, is_active) "
        "SELECT id, 'cbeta-txt', 'CBETA TXT', 'git', "
        "'https://github.com/DILA-edu/CBETA-txt', 'txt', "
        "false, 50, true "
        "FROM data_sources WHERE code = 'cbeta'"
    )

    # STEP 6: Add 2 84000 source_distributions (eKangyur + eTengyur)
    op.execute(
        "INSERT INTO source_distributions "
        "(source_id, code, name, channel_type, url, format, "
        "is_primary_ingest, priority, is_active) "
        "SELECT id, '84000-ekangyur', '84000 eKangyur', 'api', "
        "'https://84000.co/resources/', 'html', "
        "false, 40, true "
        "FROM data_sources WHERE code = '84000'"
    )
    op.execute(
        "INSERT INTO source_distributions "
        "(source_id, code, name, channel_type, url, format, "
        "is_primary_ingest, priority, is_active) "
        "SELECT id, '84000-etengyur', '84000 eTengyur', 'api', "
        "'https://84000.co/resources/', 'html', "
        "false, 40, true "
        "FROM data_sources WHERE code = '84000'"
    )


def downgrade() -> None:
    # Reverse STEP 6
    op.execute(
        "DELETE FROM source_distributions "
        "WHERE code IN ('84000-ekangyur', '84000-etengyur')"
    )

    # Reverse STEP 5
    op.execute(
        "DELETE FROM source_distributions "
        "WHERE code IN ('cbeta-normal-text', 'cbeta-txt')"
    )

    # Reverse STEP 4
    op.execute("DELETE FROM data_sources WHERE code = 'buda'")

    # Reverse STEP 3
    react_str = ", ".join(f"'{c}'" for c in REACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = false "
        f"WHERE code IN ({react_str})"
    )

    # Reverse STEP 2b
    for code, url in URL_ORIGINALS.items():
        op.execute(
            f"UPDATE data_sources SET base_url = '{url}' "
            f"WHERE code = '{code}'"
        )

    # Reverse STEP 2a
    deact_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = true "
        f"WHERE code IN ({deact_str})"
    )

    # Reverse STEP 1
    for rec in DELETED_RECORDS:
        (code, name_zh, name_en, base_url, region, languages,
         has_local, has_remote, supports_search, supports_iiif,
         supports_api, access_type, description) = rec
        name_zh_e = _escape(name_zh)
        name_en_e = _escape(name_en)
        desc_e = _escape(description)
        url_val = f"'{base_url}'" if base_url else "NULL"
        op.execute(
            f"INSERT INTO data_sources "
            f"(code, name_zh, name_en, base_url, region, languages, is_active, "
            f"has_local_fulltext, has_remote_fulltext, supports_search, "
            f"supports_iiif, supports_api, access_type, description) "
            f"VALUES ('{code}', '{name_zh_e}', '{name_en_e}', {url_val}, "
            f"'{region}', '{languages}', true, "
            f"{has_local}, {has_remote}, {supports_search}, "
            f"{supports_iiif}, {supports_api}, '{access_type}', '{desc_e}')"
        )
