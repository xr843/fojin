"""Retire five sources whose hostnames no longer exist; repoint a sixth.

Follow-up to 0177. That one fixed the source a reader reported; this one clears
what a full probe from the cron's own vantage turned up (601 probed, 556 ok,
45 needing attention).

**Only the DNS failures are acted on here, deliberately.** Of the 45, 33 are
``unreachable`` and 11 ``cert_invalid``, but most of those are timeouts and
cert rejections that say more about the prober than the site — 0172 already
established that, and it holds: ``buddhism.lib.ntu.edu.tw`` (recorded as a
timeout for both ``ccbs-ntu`` and ``ntu-buddhism``) resolves and serves fine
from a second vantage. DNS is the one signal that can be settled independently
of any vantage, so each hostname below was re-resolved through a public DoH
resolver rather than trusted from the probe:

  www.tripitaka.or.kr          NXDOMAIN
  femc.huma-num.fr             NXDOMAIN
  budsir.ict.mahidol.ac.th     NXDOMAIN
  voice.suttacentral.net       NXDOMAIN
  orientnet.jp                 SERVFAIL (the domain's own nameservers)
  taiwanbuddhism.dila.edu.tw   NOERROR but no A/AAAA/CNAME — the host record was
                               removed from a zone that is otherwise alive
                               (``cbetaonline.dila.edu.tw`` resolves normally)

Repointed (1)
-------------
``suttacentral-voice`` — the project moved to its own domain. ``sc-voice.net``
serves 200 and redirects to ``www.sc-voice.net``; the sc-voice GitHub org lists
it as the primary site with voice.suttacentral.net as the legacy address. Same
project, so the row follows it.

Deactivated (5)
---------------
``is_active = FALSE`` is editorial removal (the model's own wording), which is
the right verb here: these are not mis-typed URLs to correct but sites that no
longer exist. It also stops the cron re-probing them every night. Three of the
five lose nothing, because a live row already covers the same material:

* ``dongguk-hangul-tripitaka`` — 한글대장경 is served by ``abc-tripitaka``
  (kabc.dongguk.edu) and ``ktk`` (its 통합대장경 list), both ``ok``. Repointing
  would have made a third row for one site.
* ``femc-khmer`` — the FEMC digitisation itself is served by ``bdrc-khmer``
  (khmer-manuscripts.bdrc.io, ``ok``), the BDRC×FEMC Khmer Manuscript Heritage
  Project.
* ``mahidol-tipitaka`` — BUDSIR is broken at the source, not just at our URL:
  the surviving entry host ``budsir.mahidol.ac.th`` resolves but redirects into
  the NXDOMAIN ``budsir.ict.mahidol.ac.th``; ``budsir.org`` is a parked domain.
  No live successor found, so nothing to repoint to.
* ``orientnet-buddhism`` — a link directory; domain SERVFAIL on both apex and
  www, no successor found.
* ``taiwan-buddhism-dila`` — no successor found. ``taiwan-fojiao-dila`` (the
  《台湾佛教》journal archive) is a different resource and stays.

Nothing is deleted: ``downgrade`` restores every row, and the license/metadata
columns are untouched throughout.

Revision ID: 0178
Revises: 0177
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0178"
down_revision: str | None = "0177"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SC_VOICE_NEW_URL = "https://www.sc-voice.net/"
SC_VOICE_OLD_URL = "https://voice.suttacentral.net/"

SC_VOICE_NEW_DESC = (
    "SuttaCentral 经文语音朗读项目，辅助视障用户与听读场景。"
    "已迁出 suttacentral.net，现址 sc-voice.net（旧域名 voice.suttacentral.net 已停止解析）。"
)
SC_VOICE_OLD_DESC = "SuttaCentral 经文语音朗读项目，辅助视障用户阅读"

# Hostname no longer resolves; verified through a public resolver, not the probe.
RETIRED_CODES = (
    "dongguk-hangul-tripitaka",
    "femc-khmer",
    "mahidol-tipitaka",
    "orientnet-buddhism",
    "taiwan-buddhism-dila",
)


def _set_sc_voice(url: str, description: str) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = :url,
                   description = :description
             WHERE code = 'suttacentral-voice'
            """
        ).bindparams(url=url, description=description)
    )


def _set_active(active: bool) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET is_active = :active
             WHERE code IN (
                 'dongguk-hangul-tripitaka',
                 'femc-khmer',
                 'mahidol-tipitaka',
                 'orientnet-buddhism',
                 'taiwan-buddhism-dila'
             )
            """
        ).bindparams(active=active)
    )


def _clear_sc_voice_health() -> None:
    """Drop the verdict earned by the old hostname, as 0166/0177 did."""
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET health_status = 'ok',
                   health_checked_at = NULL,
                   health_detail = NULL,
                   health_confidence = 'high',
                   unreachable_since = NULL
             WHERE code = 'suttacentral-voice'
            """
        )
    )


def upgrade() -> None:
    _set_sc_voice(SC_VOICE_NEW_URL, SC_VOICE_NEW_DESC)
    _clear_sc_voice_health()
    _set_active(False)


def downgrade() -> None:
    _set_active(True)
    _set_sc_voice(SC_VOICE_OLD_URL, SC_VOICE_OLD_DESC)
