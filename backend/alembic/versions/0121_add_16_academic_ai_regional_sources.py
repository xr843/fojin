"""Add 16 new data sources: academic institutions, AI/NLP datasets, and regional gaps.

Revision ID: 0121
Revises: 0120
"""

from alembic import op
from sqlalchemy import text

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None

SOURCES = [
    # === Academic / Institutional ===
    {
        "code": "oslo-bibliotheca-polyglotta",
        "name_zh": "奥斯陆多语种佛典对勘库",
        "name_en": "Bibliotheca Polyglotta - Thesaurus Literaturae Buddhicae",
        "base_url": "https://www2.hf.uio.no/polyglotta/index.php?page=library&bid=2",
        "description": "奥斯陆大学 Jens Braarvig 主持的梵藏汉英四语逐句对勘平台，涵盖维摩诘、楞伽、入法界品等大乘核心经典",
        "region": "挪威",
        "languages": "sa,bo,lzh,en",
        "research_fields": "sanskrit,tibetan,han",
        "access_type": "open",
    },
    {
        "code": "heidelberg-buddhist-stone",
        "name_zh": "海德堡中国佛教石经数据库",
        "name_en": "Buddhist Stone Sutras in China",
        "base_url": "https://www.stonesutras.org/",
        "description": "海德堡科学院长期项目，收录山东、四川、河北等地摩崖石经高清拓本与录文，2024年新增房山第三期",
        "region": "德国",
        "languages": "lzh,en,de",
        "research_fields": "han,dh",
        "access_type": "open",
    },
    {
        "code": "vienna-rkts-kanjur",
        "name_zh": "维也纳大学藏文甘珠尔资源网",
        "name_en": "Resources for Kanjur & Tanjur Studies (rKTs)",
        "base_url": "https://www.istb.univie.ac.at/kanjur/rktsneu/",
        "description": "维也纳大学 ISTB 研究所藏文甘珠尔丹珠尔版本学数据库，含20余版本逐函对勘目录",
        "region": "奥地利",
        "languages": "bo,sa,en",
        "research_fields": "tibetan",
        "access_type": "open",
    },
    {
        "code": "ccbs-ntu",
        "name_zh": "台大佛学数位图书馆暨博物馆",
        "name_en": "Digital Library & Museum of Buddhist Studies, NTU",
        "base_url": "http://buddhism.lib.ntu.edu.tw/",
        "description": "国立台湾大学佛学中心（恒清法师创立），全球最早佛学全文书目数据库之一，收录35万笔学术文献",
        "region": "中国台湾",
        "languages": "zh,en,ja",
        "research_fields": "han,dh",
        "access_type": "open",
    },

    # === Regional Gaps ===
    {
        "code": "mongolian-kanjur-nlm",
        "name_zh": "蒙古国国家图书馆蒙文甘珠尔",
        "name_en": "Mongolian Kanjur - National Library of Mongolia",
        "base_url": "https://www.nationallibrary.mn/",
        "description": "蒙古国国家图书馆1718-1720康熙朱印本蒙古文甘珠尔108函数字化项目，含高清IIIF影像",
        "region": "蒙古国",
        "languages": "mn,bo",
        "research_fields": "tibetan",
        "access_type": "open",
    },
    {
        "code": "tongdosa-seongbo",
        "name_zh": "通度寺圣宝博物馆",
        "name_en": "Tongdosa Seongbo Museum",
        "base_url": "http://tongdomuseum.or.kr/",
        "description": "韩国三宝寺之一「佛宝宗刹」通度寺数字藏品，含唐代舍利装藏、高丽华严石经拓本、佛画写经",
        "region": "韩国",
        "languages": "ko,lzh",
        "research_fields": "han,art",
        "access_type": "open",
    },
    {
        "code": "lang-mai-archive",
        "name_zh": "梅村一行禅师数字档案",
        "name_en": "Plum Village (Lang Mai) Digital Library",
        "base_url": "https://plumvillage.org/library/",
        "description": "一行禅师（Thich Nhat Hanh）全集、开示音频、接现派（Tiep Hien）经典，越南佛教海外传承核心档案",
        "region": "法国",
        "languages": "vi,en,fr",
        "research_fields": "theravada,han",
        "access_type": "open",
    },
    {
        "code": "aginsky-datsan",
        "name_zh": "阿金斯克寺",
        "name_en": "Aginsky Datsan",
        "base_url": "http://aginskydatsan.ru/",
        "description": "俄罗斯外贝加尔19世纪布里亚特印经院，俄境内最大藏文木刻出版中心，保存俄藏木刻丹珠尔",
        "region": "俄罗斯",
        "languages": "ru,bo",
        "research_fields": "tibetan",
        "access_type": "open",
    },
    {
        "code": "kalmyk-central-khurul",
        "name_zh": "卡尔梅克中央佛寺",
        "name_en": "Central Khurul of Kalmykia (Burkhan Bakshin Altan Sume)",
        "base_url": "http://khurul.ru/",
        "description": "俄罗斯欧洲境内唯一格鲁派佛教共和国总寺，含卡尔梅克佛教传承、翻译仪轨、藏传密宗法脉档案",
        "region": "俄罗斯",
        "languages": "ru,bo",
        "research_fields": "tibetan",
        "access_type": "open",
    },

    # === AI/NLP Datasets & Tools ===
    {
        "code": "hf-buddhist-classics-translation",
        "name_zh": "HuggingFace 佛典AI译丛",
        "name_en": "Buddhist Classics AI Translation (HF Datasets)",
        "base_url": "https://huggingface.co/datasets/ospx1u/buddhist-classics-vol1-12",
        "description": "HuggingFace 社区发布的藏文甘珠尔丹珠尔英汉AI翻译语料，1.7GB+，CC-BY-4.0，2026持续更新",
        "region": "国际",
        "languages": "bo,zh,en",
        "research_fields": "tibetan,dh",
        "access_type": "open",
    },
    {
        "code": "hf-thai-buddhist-exam",
        "name_zh": "泰国佛学考试 Benchmark",
        "name_en": "Thai Buddhist Studies Exam (Nak Tham Benchmark)",
        "base_url": "https://huggingface.co/datasets/biodatlab/thai_buddhist_studies_exam",
        "description": "4100道泰语佛学 Nak Tham 考试真题（2020/2022/2023），Apache-2.0，用于LLM上座部佛教概念评测",
        "region": "泰国",
        "languages": "th,en",
        "research_fields": "theravada,dh",
        "access_type": "open",
    },
    {
        "code": "hf-vietnamese-buddhist-qa",
        "name_zh": "越南佛学 QA Benchmark",
        "name_en": "Vietnamese Buddhist Scholar Test Set",
        "base_url": "https://huggingface.co/datasets/vanloc1808/buddhist-scholar-test-set",
        "description": "1008条越南语佛学 QA 对，MIT 许可，用于越南佛教聊天机器人与LLM评测",
        "region": "越南",
        "languages": "vi",
        "research_fields": "han,dh",
        "access_type": "open",
    },
    {
        "code": "buda-ocr-app",
        "name_zh": "BDRC 藏文离线 OCR 应用",
        "name_en": "BUDA Tibetan OCR Offline App",
        "base_url": "https://github.com/buda-base/tibetan-ocr-app",
        "description": "BDRC 发布的离线藏文 OCR 桌面程序及训练管线，MIT 许可，2026年活跃更新，面向研究者本地批处理木刻藏文",
        "region": "美国",
        "languages": "bo,en",
        "research_fields": "tibetan,dh",
        "access_type": "open",
    },
    {
        "code": "buddhakg-ssd",
        "name_zh": "佛教知识图谱与语义漂移检测",
        "name_en": "BuddhaKG - Semantic Shift Detection",
        "base_url": "https://github.com/music-mt/BuddhaKG-SSD-v4",
        "description": "模块化数字人文平台，做佛教术语本体、跨时代语义漂移检测、教义知识验证三位一体",
        "region": "国际",
        "languages": "en,lzh",
        "research_fields": "dh,han",
        "access_type": "open",
    },
    {
        "code": "taisho-translation-pipeline",
        "name_zh": "大正藏英译与互文检测",
        "name_en": "Taisho Translation & Digest Detection",
        "base_url": "https://github.com/dangerzig/taisho-translation",
        "description": "大正藏全量英译语料与经文摘录（digest）检测管线，对互文/引文识别研究者稀缺工具",
        "region": "国际",
        "languages": "en,lzh",
        "research_fields": "han,dh",
        "access_type": "open",
    },
    {
        "code": "cbeta-rag-opensource",
        "name_zh": "CBETA 开源 RAG 参考实现",
        "name_en": "CBETA-RAG Open Source Reference",
        "base_url": "https://github.com/guyiicn/cbeta-rag",
        "description": "面向 CBETA 大藏经的开源 RAG 参考实现，支持多 LLM provider，可复刻佛教 AI 问答模块",
        "region": "国际",
        "languages": "zh,lzh,en",
        "research_fields": "han,dh",
        "access_type": "open",
    },
]


def upgrade() -> None:
    for s in SOURCES:
        name_en = f"'{s['name_en']}'" if s["name_en"] else "NULL"
        # Escape single quotes in description
        desc = s["description"].replace("'", "''")
        name_zh = s["name_zh"].replace("'", "''")
        op.execute(
            text(
                f"INSERT INTO data_sources "
                f"(code, name_zh, name_en, base_url, description, "
                f"access_type, region, languages, research_fields, sort_order, is_active) "
                f"VALUES ('{s['code']}', '{name_zh}', {name_en}, '{s['base_url']}', "
                f"'{desc}', '{s['access_type']}', '{s['region']}', "
                f"'{s['languages']}', '{s['research_fields']}', 0, true) "
                f"ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    codes = ", ".join(f"'{s['code']}'" for s in SOURCES)
    op.execute(text(f"DELETE FROM data_sources WHERE code IN ({codes})"))
