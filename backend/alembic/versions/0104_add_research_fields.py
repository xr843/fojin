"""Add research_fields column to data_sources and populate classification.

Revision ID: 0104
Revises: 0103
"""

import sqlalchemy as sa
from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


# 精确匹配规则：code → research_fields
# 这些覆盖自动规则
EXACT_MAPPINGS: dict[str, str] = {
    # === 汉传佛教核心 ===
    "cbeta": "han",
    "cbeta-api": "han,dh",
    "cbeta-mcp": "han",
    "cbeta-concordance": "han,dh",
    "cbeta-tripitaka": "han",
    "cbeta-archive": "han",
    "sat": "han",
    "sat-daizokyo": "han",
    "sat-image": "han,art",
    "jinglu-cbeta": "han",
    "cter": "han",
    "cter-info": "han",

    # === 大藏经 ===
    "dzj-fosss": "han",
    "qldzj": "han",
    "bohanjingzang": "han",
    "jiaxing-zang": "han",
    "yongle-beizang": "han",
    "zhaocheng-jinzang": "han",
    "zhonghua-dazangjing": "han",
    "fodzj-lianhai": "han",
    "hrfjw-dzj": "han",
    "bdk-daizokyo": "han",
    "sd-mingdzj": "han",

    # === 南传/巴利 ===
    "suttacentral": "theravada",
    "suttacentral-voice": "theravada",
    "accesstoinsight": "theravada",
    "dhammachai-tipitaka": "theravada",
    "digital-pali-reader": "theravada,dictionary",
    "pali-canon-online": "theravada",
    "pali-tripitaka-15lang": "theravada",
    "tipitaka-app": "theravada",
    "tipitakapali-org": "theravada",
    "tipitaka-sutta": "theravada",
    "tipitaka-lk": "theravada",
    "pitaka-lk": "theravada",
    "colombo-tripitaka": "theravada",
    "srilanka-tripitaka": "theravada",
    "bps-online": "theravada",
    "vri": "theravada",
    "vri-tipitaka": "theravada",
    "ancient-buddhist-texts": "theravada",
    "readingfaithfully": "theravada",
    "simsapa-dhamma": "theravada",
    "suttafriends": "theravada",
    "sutra-mobi": "theravada",
    "tripitaka-online-th": "theravada",
    "buddhistlexicon-dila": "dictionary",
    "buddhason": "theravada,han",
    "pali-dict-sutta": "theravada,dictionary",
    "cltk-pali": "theravada,dh",
    "dpd-dict": "theravada,dictionary",

    # === 藏传佛教 ===
    "bdrc": "tibetan",
    "84000": "tibetan",
    "84000-glossary": "tibetan,dictionary",
    "esukhia-derge": "tibetan",
    "esukhia-kangyur": "tibetan",
    "openpecha": "tibetan,dh",
    "tibetanclassics": "tibetan",
    "tibetanlibrary-ltwa": "tibetan",
    "ltwa-resource": "tibetan",
    "monlam-ai": "tibetan,dh",
    "sakya-research": "tibetan",
    "sakya-digital-lib": "tibetan",
    "rkts": "tibetan",
    "dps-tibetan": "tibetan",
    "rangjung-yeshe": "tibetan,dictionary",
    "rigpa-wiki": "tibetan",
    "rigzod": "tibetan",
    "samye-translations": "tibetan",
    "padmakara": "tibetan",
    "lotsawa-house": "tibetan",
    "lrannotations": "tibetan",
    "amec-amrtf": "tibetan",
    "classical-tibetan-corpus": "tibetan,dh",
    "tibetan-buddhist-encyclopedia": "tibetan,dictionary",
    "gandan-monastery": "tibetan",
    "mongolian-kanjur": "tibetan",
    "bdrc-nlm": "tibetan",
    "eap-dambadarjaa": "tibetan",
    "mongolia-academy": "tibetan",
    "mongolia-lib": "tibetan",
    "china-tibetan-buddhist-academy": "tibetan",
    "potala-archive": "tibetan",
    "buryat-buddhism": "tibetan",
    "kalmyk-buddhism": "tibetan",
    "tuva-buddhism": "tibetan",
    "eap-menri-bon": "tibetan",
    "pandita-translation": "tibetan",

    # === 梵文佛典 ===
    "gretil": "sanskrit",
    "dcs-sanskrit": "sanskrit,dh",
    "sarit": "sanskrit",
    "siddham": "sanskrit,han",
    "bcbs-eduhk": "sanskrit,han",
    "byt5-sanskrit": "sanskrit,dh",
    "sketchengine-sanskrit": "sanskrit,dh",
    "cdsl-cologne": "sanskrit,dictionary",
    "cdsl-mw": "sanskrit,dictionary",
    "cdsl-bhs": "sanskrit,dictionary",
    "cdsl-pw": "sanskrit,dictionary",
    "cdsl-wilson": "sanskrit,dictionary",
    "cdsl-ap90": "sanskrit,dictionary",
    "fanfoyan-dict": "sanskrit,dictionary",
    "fdict-cn": "sanskrit,dictionary",
    "gyan-bharatam": "sanskrit",

    # === 敦煌学 ===
    "dunhuang-academy": "dunhuang",
    "dunhuang-cave17": "dunhuang",
    "dunhuang-hanji": "dunhuang",
    "dunhuang-iiif": "dunhuang",
    "dunhuang-research-db": "dunhuang",
    "dunhuang-snupg": "dunhuang",
    "ihp-dunhuang": "dunhuang",
    "pelliot-collection": "dunhuang",
    "berlin-turfan": "dunhuang",
    "turfan-studies": "dunhuang",
    "crossasia-turfan": "dunhuang",

    # === 佛教艺术与考古 ===
    "yungang-digital": "art",
    "stonesutras": "art",
    "fangshan-stone": "art,han",
    "yunjusi-stone-museum": "art,han",
    "ihp-buddhist-rubbings": "art,han",
    "chinese-inscription": "art",
    "palace-museum": "art,tibetan",
    "hermitage-buddhism": "art",
    "delhi-national-museum": "art",
    "asi-india": "art",
    "numista-kushan": "art",
    "digital-gandhara-harvard": "art",
    "efeo-angkor-inscriptions": "art",
    "sealang-epigraphy": "art",
    "dharma-epigraphy": "art",
    "cik-khmer-inscriptions": "art",
    "schoyen-buddhism": "art",
    "schoyen-collection": "art",
    "lumbini-research": "art",
    "nalanda-digital": "art,sanskrit",
    "wat-pho": "art",

    # === 辞典工具 ===
    "acmuller-dict": "dictionary,han",
    "dila-glossaries": "dictionary",
    "dila-authority": "dictionary",
    "foguang-dict": "dictionary,han",
    "fgs-digital": "dictionary,han",
    "yixing-dict": "dictionary,han",
    "foxue-dictionary": "dictionary,han",
    "neidian-baike": "dictionary,han",
    "buddhist-glossaries": "dictionary",
    "soothill-hodous": "dictionary,han",
    "sutta-pali-dict": "dictionary,theravada",
    "ncped": "dictionary,theravada",
    "pts-ped": "dictionary,theravada",
    "cpd-cologne": "dictionary,theravada",
    "edict-fp": "dictionary,sanskrit",
    "dila-dfb": "dictionary",
    "dila-hopkins": "dictionary,tibetan",
    "dila-soothill": "dictionary,han",
    "encyclopedia-buddhism": "dictionary",
    "dhammawiki": "dictionary,theravada",
    "lanka-encyclopedia": "dictionary,theravada",

    # === 数字人文/NLP ===
    "buddhanexus": "dh",
    "buddhanexus-data": "dh",
    "buddhist-nlp-mitra": "dh",
    "mitra-ai": "dh",
    "norbu-ai": "dh,theravada",
    "bauda-ai": "dh,han",
    "fashi-ai": "dh,han",
    "rushi-ai": "dh,han",
    "books-fo": "dh,han",
    "texta-studio": "dh,han",
    "histochtext": "dh",
    "intellexus-hamburg": "dh",
    "open-philology": "dh",

    # === 阿含/阿毗达磨 ===
    "agama": "han,theravada",
    "ahanjing": "han",
    "bza-dila": "han,theravada",
    "t1index-dila": "han",
    "kosa-arpcn": "han",
    "vmtd-dila": "han,sanskrit",
    "ybh-dila": "han,sanskrit",
    "mavb-dila": "han,sanskrit",
    "dedu-dila": "han,sanskrit,tibetan",
    "sdp-dila": "han,sanskrit",
    "dharmapearls": "han",

    # === 禅宗/天台/华严/净土 ===
    "chan-buddhism": "han",
    "hua-yan": "han",
    "hysc-dila": "han",
    "tiantai-lib": "han",
    "pure-land-texts": "han",
    "mugenzo": "han",

    # === 综合阅读平台 ===
    "deerpark-app": "theravada",
    "dharma-ebooks": "han",
    "grandsutras": "han",
    "mahayana-texts": "han",
    "wisdom-lib": "theravada",
    "compassion-network": "han",
    "open-buddhist-univ": "theravada",

    # === 写本项目 ===
    "ngmcp": "sanskrit,art",
    "nmc-india": "sanskrit,art",
    "lanna-manuscripts": "theravada,art",
    "nepal-ntca": "sanskrit",
    "rsbmp": "theravada,art",

    # === 翻译项目 ===
    "kumarajiva-project": "han",
    "dharma-torch": "han",
    "xuanzang-project": "han",

    # === 东南亚 ===
    "bdrc-khmer": "theravada",
    "cambodia-buddhism": "theravada",
    "seadl-cambodia": "theravada",
    "preah-sihanouk": "theravada",
    "dllm-laos": "theravada",
    "eap-luangprabang": "theravada",
    "laos-palm-leaf": "theravada",
    "myanmar-tipitaka": "theravada",
    "myanmar-digital-lib": "theravada",
    "mmdl-myanmar": "theravada",
    "mmdl-toronto": "theravada",
    "burmalibrary-buddhist": "theravada",
    "inya-archive": "theravada",
    "hamburg-khmer": "theravada,dh",
    "dreamsea": "theravada,dh",
    "crossasia-lanna": "theravada",
    "chakma-digital-library": "theravada",

    # === 越南 ===
    "vietnamese-nikaaya": "theravada",

    # === 满文/西夏 ===
    "manchu-studies": "han",
    "dila-manchu-canon": "han,tibetan",
    "manchu-digital-corpus": "han,dh",
    "tangut-xixia": "han",
    "ilp-tangut": "han",
    "bbaw-sogdian-buddhist": "han",

    # === 期刊/学术 ===
    "jiats": "tibetan",
    "jiabs": "han",
    "bib-buddhiststudies": "dictionary",

    # === DILA ===
    "dila": "han,dictionary",
    "dharma-drum": "han",
    "cbc-dila": "han",
    "fosizhi-dila": "han",
    "taiwan-buddhism-dila": "han",
    "taiwan-fojiao-dila": "han",
    "minguo-journals-dila": "han",

    # === FROGBEAR ===
    "frogbear": "han,dh",

    # === 佛光山 ===
    "fgs-etext": "han",
    "fgs-lib": "han",
    "hsing-yun-books": "han",
    "chung-tai": "han",

    # === 其他台湾 ===
    "ntu-buddhism": "han",
    "ncl-tw": "han",
    "taipei-npm-guji": "han,art",
    "shengyen-archive": "han",
    "tzu-chi-library": "han",
    "ddm-library": "han",
    "chung-hwa": "han",
    "sutra-humanistic": "han",
    "sutrapearls": "han",
    "suttaworld": "han",
    "ymfz": "han",
    "buddhasaids": "han",
    "bfnn-book": "han",
    "youfun-sinica": "han",
    "academia-sinica": "han",
    "itlr-net": "han",

    # === 韩国 ===
    "abc-tripitaka": "han",

    # === 学术研究机构 (未分领域的) ===
    "buddhiststudies-info": "han",
    "buddhistroad-bochum": "han",
    "hamburg-buddhism": "han",
    "dtab-bonn": "han",
    "gandhari-lmu": "sanskrit",
    "munich-indology": "sanskrit",
    "diga-bochum": "han",
    "copenhagen-buddhism": "han",
    "oslo-polyglotta": "sanskrit,dh",
    "vienna-buddhism": "sanskrit",
    "college-de-france": "han",
    "crcao-paris": "han",
    "efeo": "han,theravada",
    "paris-buddhism": "han",
    "dmct-ghent": "theravada",
    "bristol-pali": "theravada",
    "oxford-pali": "theravada",
    "oxford-bodleian-oriental": "sanskrit",
    "cambridge-sanskrit": "sanskrit",

    # === 中国大陆主要平台 ===
    "nlc": "han",
    "nlc-szgj": "han",
    "nlc-zhgjzhh": "han",
    "guji-cn": "han",
    "shidianguji": "han",
    "cadal": "han",
    "hdcg-wenyuan": "han",
    "dianjin": "han",
    "cass-guji": "han",
    "fo-ancientbooks": "han",

    # === 音频 ===
    "tnh-audio": "theravada",
    "buddhistdoor": "han",

    # === 韩国佛学 ===
    "snu-lib-guji": "han",

    # === 日本 ===
    "taisho-u-lib": "han",
    "komazawa-lib": "han",
    "otani-lib": "han",
    "ryukoku-lib": "han",
    "hanazono-lib": "han",
    "ndl-japan": "han",
    "waseda-kotenseki": "han",
    "nijl-kokubunken": "han",
}


def _classify_source(code: str, name_zh: str, languages: str, description: str) -> str:
    """自动分类没有精确映射的数据源。"""
    if code in EXACT_MAPPINGS:
        return EXACT_MAPPINGS[code]

    fields = set()
    langs = (languages or "").lower()
    name_desc = (name_zh or "") + (description or "")

    # 语言优先规则
    if "pi" in langs.split(","):
        fields.add("theravada")
    if "bo" in langs.split(","):
        fields.add("tibetan")
    if "sa" in langs.split(","):
        fields.add("sanskrit")

    # 名称关键词
    if any(kw in name_desc for kw in ["敦煌", "Dunhuang", "藏经洞", "Turfan"]):
        fields.add("dunhuang")
    if any(kw in name_desc for kw in ["词典", "辞典", "Dictionary", "dictionary", "百科", "Encyclopedia", "Lexicon", "glossar"]):
        fields.add("dictionary")
    if any(kw in name_desc for kw in ["石窟", "石刻", "博物馆", "Museum", "造像", "壁画", "考古", "遗址", "碑铭", "Inscription", "epigraphy", "Art", "拓本"]):
        fields.add("art")
    if any(kw in name_desc for kw in ["AI", "NLP", "数字人文", "Digital Humanities", "语料", "Corpus", "corpus"]):
        fields.add("dh")
    if any(kw in name_desc for kw in ["大藏经", "藏经", "佛典", "佛经", "经藏", "阅藏"]):
        fields.add("han")
    if any(kw in name_desc for kw in ["Tipitaka", "tipitaka", "Pali", "pali", "Sutta", "sutta", "Theravada", "上座部"]):
        fields.add("theravada")

    # 如果含 lzh 且没有其他明确分类，归入 han
    if "lzh" in langs.split(",") and not fields:
        fields.add("han")

    # 如果只有 zh，大概率是汉传佛教相关
    if not fields and "zh" in langs.split(","):
        fields.add("han")

    # fallback
    if not fields:
        fields.add("han")

    return ",".join(sorted(fields))


def upgrade() -> None:
    # 1. 添加列
    op.add_column("data_sources", sa.Column("research_fields", sa.String(500), nullable=True))

    # 2. 用 Python 分类逻辑填充数据
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, code, name_zh, languages, description FROM data_sources")
    ).fetchall()

    for row in rows:
        src_id, code, name_zh, languages, description = row
        fields = _classify_source(code, name_zh or "", languages or "", description or "")
        conn.execute(
            sa.text("UPDATE data_sources SET research_fields = :fields WHERE id = :id"),
            {"fields": fields, "id": src_id},
        )


def downgrade() -> None:
    op.drop_column("data_sources", "research_fields")
