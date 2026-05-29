"""Retire dead-domain sources and repoint four relocated ones.

From the 2026-05-29 content audit (verified by independent DNS + browser-UA
probes, not the in-VPS cron alone):

DEAD — domain no longer resolves anywhere (DNS NXDOMAIN). Retired from the
public catalog via is_active=false; the resource may still exist behind a new
domain and can be re-added later under the usual "add sources" migration.

  yungang-digital      www.yungang.org          (云冈石窟数字博物馆)
  dunhuang-snupg       dunhuang.snupg.com       (敦煌文献专题数据库)
  bib-buddhiststudies  bib.buddhiststudies.net  (中国佛教数字目录)
  colombo-tripitaka    www.tripitaka.lk         (科伦坡巴利三藏)
  fragile-palm-leaves  www.fragilepalm.org      (脆弱的棕榈叶基金会)
  femc-khmer           femc.huma-num.fr         (柬埔寨写本编辑基金会 FEMC)
  histochtext          www.orioles.uni-mainz.de (历史吐火罗文本库)
  icabs-nara-chokujo   nara-chokyo.icabs.ac.jp  (奈良朝敕定一切经数据库)
  korcis               korcis.nl.go.kr          (韩国 KORCIS 古籍信息系统)
  utokyo-shuanghong    shuanghong.ioc.u-tokyo.ac.jp (东京大学双红堂文库)
  buryat-buddhism      www.imbtit.ru            (布里亚特佛教文献;
                       likely a typo for imbt.ru — left retired pending a
                       confirmed replacement URL)

MOVED — institution alive, base_url relocated. Each new URL was verified by
hand to return the intended content:

  84000-glossary  read.84000.co/glossary/search.html (gone)
                  -> scholar.84000.co/glossary  (84000 moved its glossary)
  bza-dila        buddhistinformatics.dila.edu.tw/BZA/ (old DILA host)
                  -> bza.dila.edu.tw/  (別譯雜阿含經 digital edition)
  adarsha         adarsha.dharma-treasure.org (old domain)
  adarsha-pechamaker  adarsha.dharma-treasure.org
                  -> adarshah.org/  (明镜藏文大藏经 / Adarsha 校勘平台 new domain)

is_active (editorial removal) and health_status (cron reachability) are
independent by design (see migration 0132); this migration only touches
is_active and base_url. The next health-check pass re-probes the four moved
sources at their new URLs and updates their badges.

Revision ID: 0144
Revises: 0143
Create Date: 2026-05-29
"""

from alembic import op
from sqlalchemy import text

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

# Domains that no longer resolve — retired from the public catalog.
DEAD_SOURCES = (
    "yungang-digital",
    "dunhuang-snupg",
    "bib-buddhiststudies",
    "colombo-tripitaka",
    "fragile-palm-leaves",
    "femc-khmer",
    "histochtext",
    "icabs-nara-chokujo",
    "korcis",
    "utokyo-shuanghong",
    "buryat-buddhism",
)

# code -> (old_base_url, new_base_url) for relocated-but-alive sources.
URL_UPDATES = {
    "84000-glossary": (
        "https://read.84000.co/glossary/search.html",
        "https://scholar.84000.co/glossary",
    ),
    "bza-dila": (
        "http://buddhistinformatics.dila.edu.tw/BZA/",
        "https://bza.dila.edu.tw/",
    ),
    "adarsha": (
        "https://adarsha.dharma-treasure.org/",
        "https://adarshah.org/",
    ),
    "adarsha-pechamaker": (
        "https://adarsha.dharma-treasure.org/",
        "https://adarshah.org/",
    ),
}


def _set_active(active: bool) -> None:
    # DEAD_SOURCES are fixed ASCII slugs — safe to inline, and an inline IN-list
    # renders under `alembic --sql` offline mode (a bound list does not).
    codes = ", ".join(f"'{c}'" for c in DEAD_SOURCES)
    value = "true" if active else "false"
    op.execute(text(f"UPDATE data_sources SET is_active = {value} WHERE code IN ({codes})"))


def _set_base_url(code: str, url: str) -> None:
    op.execute(
        text("UPDATE data_sources SET base_url = :u WHERE code = :c").bindparams(u=url, c=code)
    )


def upgrade() -> None:
    _set_active(False)
    for code, (_old, new) in URL_UPDATES.items():
        _set_base_url(code, new)


def downgrade() -> None:
    _set_active(True)
    for code, (old, _new) in URL_UPDATES.items():
        _set_base_url(code, old)
