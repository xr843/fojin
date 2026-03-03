"""deactivate confirmed-unreachable sources and update migrated URLs

Deactivated (confirmed down 2026-03-02):
- suttacentral-voice: server down since 2026-02-24 (confirmed via SuttaCentral forum)
- sarit: 502 server error, project minimally maintained
- ihp-dunhuang: 503 service unavailable
- hua-yan: huayanzang.com domain defunct

URL updates (projects migrated):
- dharmanexus: dharmanexus.net -> dharmamitra.org/nexus
- buddhanexus: buddhanexus.net -> dharmamitra.org/nexus (project sunset, merged)
- gandhari-texts-sydney: /texts path removed, use root domain

Revision ID: 0030
Revises: 0029
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sources confirmed unreachable
DEACTIVATE_CODES = [
    "suttacentral-voice",
    "sarit",
    "ihp-dunhuang",
    "hua-yan",
]

# URL migrations: (code, old_url, new_url)
URL_UPDATES = [
    ("dharmanexus", "https://dharmanexus.net/", "https://dharmamitra.org/nexus"),
    ("buddhanexus", "https://buddhanexus.net/", "https://dharmamitra.org/nexus"),
    ("gandhari-texts-sydney", "https://gandhari.org/texts", "https://gandhari.org"),
]


def upgrade() -> None:
    # Deactivate unreachable sources
    codes_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = false "
        f"WHERE code IN ({codes_str})"
    )

    # Update migrated URLs
    for code, _old, new in URL_UPDATES:
        op.execute(
            f"UPDATE data_sources SET base_url = '{new}' "
            f"WHERE code = '{code}'"
        )


def downgrade() -> None:
    # Re-activate sources
    codes_str = ", ".join(f"'{c}'" for c in DEACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = true "
        f"WHERE code IN ({codes_str})"
    )

    # Restore original URLs
    for code, old, _new in URL_UPDATES:
        op.execute(
            f"UPDATE data_sources SET base_url = '{old}' "
            f"WHERE code = '{code}'"
        )
