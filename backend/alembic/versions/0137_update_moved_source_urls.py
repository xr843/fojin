"""Update base_url for relocated sources; deactivate suttaworld.

Acting on the 2026-05-16 health-check audit. The cron flagged 13 sources as
``moved``; this migration applies the editorial follow-up.

base_url updates — sources that genuinely relocated to a different site, each
redirect target verified by hand to be the same project at its new home:

  deerpark-ai         deerpark.ai            -> deerpark.app
  ymfz                ymfz.org               -> buddha.now (圓滿法藏 佛語今譯)
  sutra-mobi          sutra.mobi             -> sutra.yjsword.com (巴利经藏)
  vienna-rkts-kanjur  istb.univie.ac.at/...  -> rkts.org/rktsneu/
  dllm-laos           laomanuscripts.net     -> digital.crossasia.org/...
  munich-indology     indologie.uni-muenchen -> kw.lmu.de/indotib/de/
  hamburg-khmer       manuscript-cultures... -> csmc.uni-hamburg.de
  cetom               univie.ac.at/tocharian -> cetom.univie.ac.at/
  va-museum           collections.vam.ac.uk  -> www.vam.ac.uk/collections

NOT touched: 84000 / 84000-glossary redirect read.84000.co -> 84000.co, a
same-site sub-domain restructure — the reading-room URL stays more specific.

Deactivation — suttaworld: suttaworld.org has lapsed and now redirects to an
unrelated commercial gambling site (vob.uk.com). is_active=false so it leaves
the public catalog; base_url is left intact for the record.

Revision ID: 0137
Revises: 0136
Create Date: 2026-05-16
"""

from alembic import op
from sqlalchemy import text

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None

# code -> (old_base_url, new_base_url)
URL_UPDATES = {
    "deerpark-ai": ("https://deerpark.ai/", "https://deerpark.app"),
    "ymfz": ("https://www.ymfz.org/", "https://buddha.now/"),
    "sutra-mobi": ("https://sutra.mobi/", "https://sutra.yjsword.com/"),
    "vienna-rkts-kanjur": (
        "https://www.istb.univie.ac.at/kanjur/rktsneu/",
        "http://www.rkts.org/rktsneu/",
    ),
    "dllm-laos": (
        "https://www.laomanuscripts.net/",
        "https://digital.crossasia.org/digital-library-of-lao-manuscripts/?lang=en",
    ),
    "munich-indology": (
        "https://www.indologie.uni-muenchen.de/",
        "https://www.kw.lmu.de/indotib/de/",
    ),
    "hamburg-khmer": (
        "https://www.manuscript-cultures.uni-hamburg.de/",
        "https://www.csmc.uni-hamburg.de",
    ),
    "cetom": ("https://www.univie.ac.at/tocharian/", "https://cetom.univie.ac.at/"),
    "va-museum": ("https://collections.vam.ac.uk/", "https://www.vam.ac.uk/collections"),
}


def _set_base_url(code: str, url: str) -> None:
    op.execute(
        text("UPDATE data_sources SET base_url = :u WHERE code = :c").bindparams(u=url, c=code)
    )


def _set_active(code: str, active: bool) -> None:
    op.execute(
        text("UPDATE data_sources SET is_active = :a WHERE code = :c").bindparams(
            a=active, c=code
        )
    )


def upgrade() -> None:
    for code, (_old, new) in URL_UPDATES.items():
        _set_base_url(code, new)
    _set_active("suttaworld", False)


def downgrade() -> None:
    for code, (old, _new) in URL_UPDATES.items():
        _set_base_url(code, old)
    _set_active("suttaworld", True)
