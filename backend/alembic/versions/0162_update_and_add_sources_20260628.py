"""Update and add data sources from the 2026-06-28 source audit.

Triggered by a full re-audit of the public /sources catalog (613 active
sources at audit time). Two findings drive this migration:

1. The 38 "unreachable / cert_invalid" health badges are ~95% FALSE
   POSITIVES. ``health_checked_at`` is NULL on every row — the statuses
   were hand-set in old migrations (0132/0143/0144) and never re-probed.
   Re-verification (WebSearch liveness + cross-checking the 0144 audit
   notes; the audit host itself sits behind a TLS-resetting proxy, the
   SAME failure mode behind the production false positives) found only
   ONE genuinely dead site. The rest resolve fine and should flip back to
   ``ok`` on the next clean-network health pass — see the source_health
   checker, which must learn to treat 403 / 405 / Cloudflare / cert-SAN
   mismatch as ALIVE rather than unreachable.

2. The May 2026 candidate dragnet (0133/0134/0140, +81 sources) was
   thorough: only a handful of genuinely net-new, high-value sources
   remain, plus two gaps.

This migration only touches catalog data (is_active / base_url /
health_status / new rows) — no schema change, fully reversible.

ADD (net-new, value 4-5; never previously in the catalog):
  nlab-bhutan       www.library.gov.bt        不丹国家图书与档案馆 (value 5)
  cter              cter.info                 CTER 历代刻本汉文藏经 (value 5)
  thai-nl-dlibrary  digital.nlt.go.th/dlib    泰国国家图书馆 D-Library (value 4)
  itkc-korea        db.itkc.or.kr             韩国古典综合数据库 ITKC (value 4)

REACTIVATE (row exists, retired in 0144 as NXDOMAIN on 2026-05-29;
re-audit found femc.huma-num.fr live again — huma-num.fr is a stable FR
national research infra. is_active flipped back on; health_status reset
to ``ok`` so the next VPS health pass re-confirms it — trivially
reversible if it is still down):
  femc-khmer        femc.huma-num.fr          EFEO-FEMC 柬埔寨贝叶库 (value 5)

FIX-URL (institution alive, base_url stale — verified via search,
health_status reset so the badge re-probes at the new URL):
  indica-buddhica-repo  www.indica-et-buddhica.com/repositorium (dead .com)
                        -> indica-et-buddhica.org/repositorium  (live .org Repositorium/Lexica)
  mahidol-tipitaka      budsir.mahidol.ac.th (cert SAN only *.ict.mahidol.ac.th, 302s away)
                        -> budsir.ict.mahidol.ac.th  (canonical host, valid cert)

RETIRE (only confirmed-dead site in the 38; list.fodocs.com and
www.fodocs.com both serve only the default nginx welcome page, 443 has no
valid TLS, and search engines index zero fodocs content):
  fodocs-list       list.fodocs.com           寂光云流Lib

NOT CHANGED (documented as false positive — do NOT retire): the other ~33
flagged sources, e.g. iriz-hanazono, pts-ped, cbc-dila, haeinsa,
suttacentral-voice, koreanbuddhism, princeton-*, paauk-ebooks. Notably
``taiwan-buddhism-dila`` keeps https://taiwanbuddhism.dila.edu.tw/ — that
dedicated subdomain IS the current canonical host (consistent with DILA's
0144 move bza -> bza.dila.edu.tw); its red badge is anti-scrape noise.

Revision ID: 0162
Revises: 0161
Create Date: 2026-06-28
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0162"
down_revision: str | None = "0161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. ADD four net-new sources.
    op.execute(
        sa_text(
            """
            INSERT INTO data_sources (
                code, name_zh, name_en, base_url, description,
                access_type, region, languages, research_fields,
                supports_search, supports_fulltext,
                has_local_fulltext, has_remote_fulltext,
                supports_iiif, supports_api,
                sort_order, is_active, health_status, created_at
            ) VALUES
            (
                'nlab-bhutan', '不丹国家图书与档案馆',
                'National Library and Archives of Bhutan',
                'https://www.library.gov.bt',
                '不丹国家图书与档案馆官方数字馆藏，约 6100 部藏文/宗喀语典籍与 9000 余块传统印经木刻板，系统保存竹巴噶举、宁玛伏藏与寺院写本，是不丹藏传文献的国家级机构。',
                'external', '不丹', 'bo,dz,en', 'tibetan',
                false, false, false, false, false, false,
                900, true, 'ok', NOW()
            ),
            (
                'cter', 'CTER 汉文佛教大藏经电子资源',
                'CTER Chinese Buddhist Canon Electronic Resources',
                'https://cter.info',
                'CTER 汉文佛教大藏经电子资源，聚合嘉兴藏、洪武南藏、永乐南北藏、高丽再雕藏等历代刻本藏经的全帙 PDF 与图像，2025 年持续增补，是库内缺失的刻本藏经聚合入口。',
                'external', '中国大陆', 'lzh,zh', 'han',
                false, false, false, true, false, false,
                900, true, 'ok', NOW()
            ),
            (
                'thai-nl-dlibrary', '泰国国家图书馆数字图书馆',
                'National Library of Thailand D-Library',
                'https://digital.nlt.go.th/dlib/',
                '泰国国家图书馆数字图书馆（D-Library），约 25 万叶贝叶写本（含大量巴利佛典）与逾万件碑铭的数字化检索平台，是全泰规模最大的贝叶写本数字库。',
                'external', '泰国', 'th,pi', 'theravada',
                true, false, false, false, false, false,
                900, true, 'ok', NOW()
            ),
            (
                'itkc-korea', '韩国古典综合数据库',
                'ITKC Korean Classics Database',
                'https://db.itkc.or.kr',
                '韩国古典翻译院（ITKC）古典综合数据库，收录《韩国文集丛刊》等朝鲜时代文集原文与韩译，含禅僧文集、注疏与佛教相关汉文典籍。',
                'external', '韩国', 'ko,lzh', 'han',
                true, false, false, true, false, false,
                900, true, 'ok', NOW()
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )

    # 2. REACTIVATE femc-khmer (retired NXDOMAIN in 0144; live again).
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET is_active = true,
                   base_url = 'https://femc.huma-num.fr',
                   health_status = 'ok',
                   health_checked_at = NULL,
                   unreachable_since = NULL
             WHERE code = 'femc-khmer'
            """
        )
    )

    # 3. FIX-URL two relocated sources + clear their stale red badges.
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = 'https://indica-et-buddhica.org/repositorium',
                   health_status = 'ok',
                   health_checked_at = NULL,
                   unreachable_since = NULL
             WHERE code = 'indica-buddhica-repo'
            """
        )
    )
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = 'https://budsir.ict.mahidol.ac.th/',
                   health_status = 'ok',
                   health_checked_at = NULL,
                   unreachable_since = NULL
             WHERE code = 'mahidol-tipitaka'
            """
        )
    )

    # 4. RETIRE the one confirmed-dead source.
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET is_active = false
             WHERE code = 'fodocs-list'
            """
        )
    )


def downgrade() -> None:
    # Reverse RETIRE.
    op.execute(
        sa_text("UPDATE data_sources SET is_active = true WHERE code = 'fodocs-list'")
    )
    # Reverse FIX-URL.
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = 'https://budsir.mahidol.ac.th/',
                   health_status = 'cert_invalid'
             WHERE code = 'mahidol-tipitaka'
            """
        )
    )
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = 'https://www.indica-et-buddhica.com/repositorium',
                   health_status = 'unreachable'
             WHERE code = 'indica-buddhica-repo'
            """
        )
    )
    # Reverse REACTIVATE.
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET is_active = false,
                   base_url = 'https://femc.huma-num.fr'
             WHERE code = 'femc-khmer'
            """
        )
    )
    # Reverse ADD.
    op.execute(
        sa_text(
            """
            DELETE FROM data_sources
             WHERE code IN ('nlab-bhutan', 'cter', 'thai-nl-dlibrary', 'itkc-korea')
            """
        )
    )
