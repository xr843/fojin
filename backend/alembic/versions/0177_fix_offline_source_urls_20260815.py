"""Repoint two sources whose sites are gone from the URL we listed.

Both were flagged by the health cron but neither could be auto-corrected: the
probe reports *reachability*, and only an editor can decide what a dead URL
should become.

* ``cbeta-archive`` — "CBETA大藏经下载(大陆档案站)",
  ``https://archive.cbetaonline.cn/``. CBETA has **officially closed the whole
  mainland mirror**: "CBETA Online 中國大陸鏡像站 (cbetaonline.cn) ... 已於近期
  停止服務，相關資料下載與更新服務亦同步停止" — "為因應當地相關規範與要求"
  (https://cbeta.org/post/30973). The announcement points readers at CBETA
  Online and cbeta.org instead. Verified dead from two independent vantages
  (connection reset / ECONNRESET); the cron only ever saw ``dns_unresolved``,
  which it correctly rates ``low`` confidence, so the row was never badged and
  never dropped — it just kept being served to readers as a live download link.

  This entry is the catalog's only *bulk download* pointer for CBETA (the other
  six CBETA rows are online reading, API, multi-version browsing, concordance,
  catalog and a RAG demo), so it is repointed rather than deactivated:
  ``https://cbeta.org/ebooks`` is CBETA's own 下載電子書 page and offers the same
  function (TXT / ePub / PDF / DOCX / ODT full-canon packages). Region moves
  中国大陆 → 中国台湾, because no mainland-hosted mirror exists any more and
  claiming one would send mainland readers at a host that is gone for
  regulatory reasons. Licence metadata is unchanged: same publisher, same
  CC-BY-NC-SA-3.0-TW terms with the same three excluded collections.

* ``tejaniya`` — ``https://tejaniyasayadaw.space/`` redirects to
  ``https://www.sayadawutejaniya.com/`` (200). The cron already recorded the
  redirect target in ``health_detail`` and classified the row ``moved``; this
  just follows it. The target was checked to be the real teaching archive
  (transcribed talks, guided meditations, four free books, and a pointer to the
  official ashintejaniya.org), not a parked domain.

Health fields are cleared for both rows the way 0166 did, so a stale red verdict
does not outlive the URL that caused it. The next cron pass re-derives them.

Revision ID: 0177
Revises: 0176
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0177"
down_revision: str | None = "0176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CBETA_ARCHIVE_NEW = {
    "base_url": "https://cbeta.org/ebooks",
    "name_zh": "CBETA 大藏经电子书下载(官方)",
    "name_en": "CBETA Official E-Book Downloads",
    "region": "中国台湾",
    "description": (
        "CBETA 官方「下載電子書」页，提供全套大藏经的 TXT/ePub/PDF/DOCX/ODT "
        "离线数据包（TXT 分含注、不含注两种），每年随经文更新三至四次。"
        "原大陆镜像站 archive.cbetaonline.cn 已于 2026 年 8 月由 CBETA 公告关闭，"
        "此处改指官方下载页；XML 原始数据见 CBETA 主站与其 GitHub 仓库。"
    ),
}

CBETA_ARCHIVE_OLD = {
    "base_url": "https://archive.cbetaonline.cn/",
    "name_zh": "CBETA大藏经下载(大陆档案站)",
    "name_en": "CBETA Tripitaka Archive (Mainland Mirror)",
    "region": "中国大陆",
    "description": "CBETA大陆镜像离线下载站，提供多种格式（EPUB/PDF/HTML/XML）的大藏经数据包下载。",
}

TEJANIYA_NEW_URL = "https://www.sayadawutejaniya.com/"
TEJANIYA_OLD_URL = "https://tejaniyasayadaw.space/"


def _update_cbeta_archive(values: dict[str, str]) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = :base_url,
                   name_zh = :name_zh,
                   name_en = :name_en,
                   region = :region,
                   description = :description
             WHERE code = 'cbeta-archive'
            """
        ).bindparams(**values)
    )


def _set_tejaniya_url(url: str) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = :url
             WHERE code = 'tejaniya'
            """
        ).bindparams(url=url)
    )


def _clear_stale_health() -> None:
    """Drop the verdict that belonged to the previous URL.

    ``health_confidence`` goes back to its 'high' default alongside the cleared
    status so the pair stays coherent; nothing is badged until the cron writes a
    real verdict against the new URL."""
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET health_status = 'ok',
                   health_checked_at = NULL,
                   health_detail = NULL,
                   health_confidence = 'high',
                   unreachable_since = NULL
             WHERE code IN ('cbeta-archive', 'tejaniya')
            """
        )
    )


def upgrade() -> None:
    _update_cbeta_archive(CBETA_ARCHIVE_NEW)
    _set_tejaniya_url(TEJANIYA_NEW_URL)
    _clear_stale_health()


def downgrade() -> None:
    _update_cbeta_archive(CBETA_ARCHIVE_OLD)
    _set_tejaniya_url(TEJANIYA_OLD_URL)
