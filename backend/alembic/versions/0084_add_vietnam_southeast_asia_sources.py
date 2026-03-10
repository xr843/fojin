"""Add Vietnam + Southeast Asia Buddhist data sources.

24 sources proposed, 9 excluded as duplicates of existing entries:
  - suttacentral: already exists (code exact match, since 0018/0044)
  - tipitaka-app: already exists (code exact match, since 0022)
  - tipitaka-net: already exists (code exact match, since 0022)
  - bdrc-khmer: already exists (code exact match, since 0045)
  - vridhamma: same site as vri-tipitaka (0081), vridhamma.org
  - tipitakapali: same site as tipitakapali-org (0022), tipitakapali.org
  - crossasia-lanna: same site as lanna-manuscripts (0045), iiif.crossasia.org/s/lanna
  - crossasia-dllm: same site as dllm-laos (0022), laomanuscripts.net

15 new sources added:
  Vietnam (6): daitangkinhvietnam, thuvienphatgiao, giaodiemonline,
               namo84000, vbeta-vn, daophatngaynay, thuvienphatviet
  Myanmar (1): burmalibrary-buddhist
  Thailand (5): etipitaka, pratripitaka, tripitaka91, thaitripidok,
                tripitaka-online-th
  Laos (1): eap-luangprabang
  Cambodia (1): seadl-cambodia
  International (2): tipitaka-sutta

Note: ON CONFLICT (code) DO NOTHING is used as a safety net.

Revision ID: 0084
Revises: 0083
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    # ══════════════════════════════════════════════════════════
    # 越南 (7)
    # ══════════════════════════════════════════════════════════
    {
        "code": "daitangkinhvietnam",
        "name_zh": "越南大藏经在线",
        "name_en": "Dai Tang Kinh Viet Nam",
        "base_url": "https://daitangkinhvietnam.org/",
        "description": "越南大藏经在线，提供37卷越南语大藏经全文，是越南佛教界重要的经藏数字化项目。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "thuvienphatgiao",
        "name_zh": "越南佛教图书馆",
        "name_en": "Thu Vien Phat Giao",
        "base_url": "http://www.thuvienphatgiao.com/",
        "description": "越南佛教在线图书馆，收录经律论各部全文，是越南语佛教文献的综合阅读平台。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "giaodiemonline",
        "name_zh": "教点在线大藏经",
        "name_en": "Giao Diem Online Tripitaka",
        "base_url": "https://giaodiemonline.com/daitangvietnam/",
        "description": "英越双语佛经翻译，收录203卷佛典翻译，提供越南语和英语对照阅读。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "namo84000",
        "name_zh": "84000法门图书馆",
        "name_en": "Namo84000",
        "base_url": "https://namo84000.org/",
        "description": "巴越双语三藏，提供五部尼柯耶对照阅读，支持巴利文、越南语、英语多语种浏览。",
        "access_type": "external",
        "region": "越南",
        "languages": "pi,vi,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "vbeta-vn",
        "name_zh": "越南佛教经书数字化图书馆",
        "name_en": "VBeta.vn",
        "base_url": "https://www.vbeta.vn/",
        "description": "越南佛教经书数字化图书馆，致力于越南语佛教经典的系统性数字化保存与在线阅读。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "daophatngaynay",
        "name_zh": "今日佛教",
        "name_en": "Dao Phat Ngay Nay",
        "base_url": "https://www.daophatngaynay.com/",
        "description": "越南佛教综合门户，含大量经藏全文和PDF下载，涵盖佛学文章、经典翻译和佛教新闻。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "thuvienphatviet",
        "name_zh": "越南佛学研究文库",
        "name_en": "Thu Vien Phat Viet",
        "base_url": "https://thuvienphatviet.com/",
        "description": "越南佛学研究文库，收录学术论文和翻译著作，提供越南语和英语佛学文献。",
        "access_type": "external",
        "region": "越南",
        "languages": "vi,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },

    # ══════════════════════════════════════════════════════════
    # 缅甸 (1) — tipitaka-app, tipitakapali, vridhamma 已存在
    # ══════════════════════════════════════════════════════════
    {
        "code": "burmalibrary-buddhist",
        "name_zh": "缅甸在线图书馆佛教文献",
        "name_en": "Online Burma Library Buddhist Texts",
        "base_url": "https://www.burmalibrary.org/en/category/buddhist-texts",
        "description": "缅甸佛教文献门户，汇集缅甸佛教相关学术文献、历史资料和佛典翻译。",
        "access_type": "external",
        "region": "缅甸",
        "languages": "my,en",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },

    # ══════════════════════════════════════════════════════════
    # 泰国 (5) — crossasia-lanna 已存在 (lanna-manuscripts)
    # ══════════════════════════════════════════════════════════
    {
        "code": "etipitaka",
        "name_zh": "泰国电子三藏",
        "name_en": "E-Tipitaka",
        "base_url": "https://etipitaka.com/",
        "description": "泰国巴利三藏搜索对比平台，支持全平台使用，提供泰文和巴利文三藏全文检索与版本对照。",
        "access_type": "external",
        "region": "泰国",
        "languages": "th,pi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "pratripitaka",
        "name_zh": "泰文三藏在线",
        "name_en": "PraTriPitaka.com",
        "base_url": "https://pratripitaka.com/",
        "description": "泰文三藏两大权威版本在线阅读，提供巴利原典与泰文翻译对照。",
        "access_type": "external",
        "region": "泰国",
        "languages": "th,pi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "tripitaka91",
        "name_zh": "91卷三藏",
        "name_en": "Tripitaka91.com",
        "base_url": "https://www.tripitaka91.com/",
        "description": "摩诃摩骨皇家学院版91卷三藏及义注，提供泰文和巴利文全文在线阅读。",
        "access_type": "external",
        "region": "泰国",
        "languages": "th,pi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "thaitripidok",
        "name_zh": "泰国三藏法音",
        "name_en": "Thai Tripidok",
        "base_url": "https://thaitripidok.com/",
        "description": "三藏法音和有声书版本，提供泰文三藏的音频朗读与文本浏览。",
        "access_type": "external",
        "region": "泰国",
        "languages": "th",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "tripitaka-online-th",
        "name_zh": "泰国三藏在线",
        "name_en": "Tripitaka-Online",
        "base_url": "https://tripitaka-online.blogspot.com/",
        "description": "现代泰语三藏与佛教词典，提供泰文和巴利文三藏在线阅读及术语查询。",
        "access_type": "external",
        "region": "泰国",
        "languages": "th,pi",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },

    # ══════════════════════════════════════════════════════════
    # 老挝 (1) — crossasia-dllm 已存在 (dllm-laos)
    # ══════════════════════════════════════════════════════════
    {
        "code": "eap-luangprabang",
        "name_zh": "琅勃拉邦佛教档案",
        "name_en": "Buddhist Archive of Luang Prabang",
        "base_url": "https://eap.bl.uk/project/EAP691",
        "description": "琅勃拉邦佛教档案，收录340件贝叶经数字化影像，由英国图书馆濒危档案计划支持保护。",
        "access_type": "external",
        "region": "老挝",
        "languages": "lo,pi",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
        "is_active": True,
    },

    # ══════════════════════════════════════════════════════════
    # 柬埔寨 (1) — bdrc-khmer 已存在 (0045)
    # ══════════════════════════════════════════════════════════
    {
        "code": "seadl-cambodia",
        "name_zh": "柬埔寨贝叶经数字化",
        "name_en": "SEADL Cambodia Palm Leaf Manuscripts",
        "base_url": "https://sea.lib.niu.edu/islandora/object/seadl:cambodia",
        "description": "柬埔寨国家图书馆511件贝叶经数字化，由东南亚数字图书馆(SEADL)提供影像浏览。",
        "access_type": "external",
        "region": "柬埔寨",
        "languages": "km,pi",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },

    # ══════════════════════════════════════════════════════════
    # 跨区域 (1) — suttacentral, tipitaka-net 已存在
    # ══════════════════════════════════════════════════════════
    {
        "code": "tipitaka-sutta",
        "name_zh": "巴利三藏多语在线",
        "name_en": "Tipitaka.sutta.org",
        "base_url": "https://tipitaka.sutta.org/",
        "description": "巴利三藏多语在线阅读平台，附带词典工具，支持巴利、英、日、中、越、缅等多种语言。",
        "access_type": "external",
        "region": "国际",
        "languages": "pi,en,ja,zh,vi,my",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
]

CODES = [s["code"] for s in NEW_SOURCES]


def upgrade() -> None:
    conn = op.get_bind()
    for s in NEW_SOURCES:
        conn.execute(
            sa_text("""
                INSERT INTO data_sources (
                    code, name_zh, name_en, base_url, description,
                    access_type, region, languages,
                    supports_search, supports_fulltext,
                    has_local_fulltext, has_remote_fulltext,
                    supports_iiif, supports_api, is_active
                ) VALUES (
                    :code, :name_zh, :name_en, :base_url, :description,
                    :access_type, :region, :languages,
                    :supports_search, :supports_fulltext,
                    :has_local_fulltext, :has_remote_fulltext,
                    :supports_iiif, :supports_api, :is_active
                )
                ON CONFLICT (code) DO NOTHING
            """),
            s,
        )


def downgrade() -> None:
    conn = op.get_bind()
    for code in CODES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": code},
        )
