"""add 28 more global Buddhist digital sources

Round 2: niche collections, AI/NLP tools, reference databases,
Silk Road archaeology, Vietnamese Nom, and rare manuscript projects.

Revision ID: 0097
Revises: 0096
Create Date: 2026-03-18
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0097"
down_revision: str | None = "0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES = [
    # ── AI & NLP Tools ──
    {
        "code": "norbu-ai",
        "name_zh": "NORBU佛教AI聊天机器人",
        "name_en": "NORBU AI Buddhist Chatbot",
        "base_url": "https://norbu-ai.org/",
        "description": "基于ChatGPT技术的佛教AI对话机器人，专注早期佛教经典(EBT)，支持实时问答与佛法教学",
        "region": "马来西亚", "languages": "en", "access_type": "open",
    },
    {
        "code": "buddhist-nlp-mitra",
        "name_zh": "MITRA佛教多语言NLP模型",
        "name_en": "Buddhist NLP MITRA Models & Corpus",
        "base_url": "https://huggingface.co/buddhist-nlp",
        "description": "Dharmamitra项目在HuggingFace上发布的佛教NLP模型集合，含70亿token预训练模型、174万平行句对语料库",
        "region": "国际", "languages": "sa,bo,lzh,pi,en", "access_type": "open",
    },
    {
        "code": "bdrc-ocr",
        "name_zh": "BDRC藏文OCR工具",
        "name_en": "BDRC Tibetan OCR App",
        "base_url": "https://github.com/buda-base/tibetan-ocr-app",
        "description": "佛教数字资源中心发布的首个公开藏文OCR桌面应用，识别乌金体及乌美体藏文转为可编辑文字，开源免费",
        "region": "美国", "languages": "bo", "access_type": "open",
    },
    {
        "code": "byt5-sanskrit",
        "name_zh": "ByT5梵文NLP分析工具",
        "name_en": "ByT5-Sanskrit Unified NLP Model",
        "base_url": "https://github.com/sebastian-nehrdich/byt5-sanskrit-analyzers",
        "description": "梵文预训练语言模型，支持分词、词形还原、形态句法标注和OCR后校正等多任务，EMNLP 2024发表",
        "region": "国际", "languages": "sa", "access_type": "open",
    },
    {
        "code": "cbeta-mcp",
        "name_zh": "CBETA MCP服务器",
        "name_en": "CBETA MCP Server",
        "base_url": "https://github.com/hiing/Cbeta-MCP",
        "description": "基于Model Context Protocol的CBETA佛典查询服务器，使AI大模型可直接检索超过2.2亿字汉文佛典",
        "region": "中国台湾", "languages": "lzh", "access_type": "open",
    },
    # ── Silk Road & Archaeology ──
    {
        "code": "dsr-nii-caves",
        "name_zh": "数字丝绸之路佛教石窟数据库",
        "name_en": "Digital Silk Road Buddhist Cave Temples Database",
        "base_url": "https://dsr.nii.ac.jp/china-caves/",
        "description": "日本国立信息学研究所主持的丝路文化遗产数字化项目，含敦煌莫高窟、柏孜克里克、克孜尔石窟等数据库",
        "region": "日本", "languages": "en,ja", "access_type": "open",
    },
    {
        "code": "schoyen-buddhism",
        "name_zh": "舍衍收藏佛教写本",
        "name_en": "Schøyen Collection Buddhism",
        "base_url": "https://www.schoyencollection.com/special-collections-introduction/buddhism-collection",
        "description": "收藏约5000叶阿富汗巴米扬石窟出土桦树皮与贝叶佛教写本(2-8世纪)，被誉为佛教死海古卷",
        "region": "挪威", "languages": "sa,pi,en", "access_type": "restricted",
    },
    {
        "code": "digital-gandhara-harvard",
        "name_zh": "哈佛数字犍陀罗项目",
        "name_en": "Digital Gandhara – Harvard CAMLab",
        "base_url": "https://camlab.fas.harvard.edu/project/digital-gandhara/",
        "description": "哈佛大学CAMLab与巴基斯坦考古部门合作，对白沙瓦博物馆犍陀罗文物进行系统性3D扫描和高清摄影",
        "region": "巴基斯坦", "languages": "en", "access_type": "open",
    },
    {
        "code": "crossasia-turfan",
        "name_zh": "CrossAsia吐鲁番数字档案",
        "name_en": "CrossAsia Turfan Digital Archive",
        "base_url": "https://iiif.crossasia.org/s/turfan/",
        "description": "柏林吐鲁番收藏40000件残片的完整IIIF数字化影像，含回鹘文、粟特语、于阗语佛典残片",
        "region": "德国", "languages": "sa,bo,sog,kho", "access_type": "open",
    },
    {
        "code": "bbaw-sogdian-buddhist",
        "name_zh": "柏林粟特语佛典词汇库",
        "name_en": "BBAW Buddhist Sogdian Text Fragments Lexicon",
        "base_url": "https://www.bbaw.de/en/research/buddhist-sogdian-text-fragments",
        "description": "柏林-勃兰登堡科学院DFG资助项目，编纂吐鲁番出土粟特语佛典手稿的多语词汇数据库",
        "region": "德国", "languages": "sog,sa,de", "access_type": "open",
    },
    # ── Vietnamese Nom & Manchu ──
    {
        "code": "digitizing-vietnam",
        "name_zh": "越南汉喃数字档案",
        "name_en": "Digitizing Vietnam Han-Nom Archive",
        "base_url": "https://www.digitizingvietnam.com/en",
        "description": "哥伦比亚大学与越南国家图书馆合作，收录2300余部汉喃文献，含佛经、寺庙碑记、宗教仪轨",
        "region": "越南", "languages": "vi,lzh", "access_type": "open",
    },
    {
        "code": "nlv-nom-digital",
        "name_zh": "越南国家图书馆汉喃全文库",
        "name_en": "National Library of Vietnam Nom Digital Archive",
        "base_url": "http://nom.nlv.gov.vn/",
        "description": "越南国家图书馆汉喃文献全文数字化库，收录1258种约19.2万页汉喃典籍含佛教经典与寺院碑记",
        "region": "越南", "languages": "vi,lzh", "access_type": "open",
    },
    {
        "code": "temple-vietnam-nom",
        "name_zh": "天普大学越南喃字写本田野数字化",
        "name_en": "Temple University Vietnam Nom Field Digitization",
        "base_url": "https://digital.library.temple.edu/digital/collection/p16002coll24",
        "description": "天普大学越南喃字写本田野数字化项目，收录越南各地寺院与民间喃字佛教手稿高清影像",
        "region": "越南", "languages": "vi,lzh", "access_type": "open",
    },
    {
        "code": "dila-manchu-canon",
        "name_zh": "满文大藏经目录与词汇库",
        "name_en": "DILA Manchu Buddhist Canon Catalog & Glossary",
        "base_url": "http://buddhistinformatics.dila.edu.tw/manchu/",
        "description": "法鼓山数位典藏项目，提供满文大藏经三语对照目录(满/藏/汉)含满文佛典词汇检索",
        "region": "中国台湾", "languages": "mnc,bo,lzh", "access_type": "open",
    },
    {
        "code": "manchu-digital-corpus",
        "name_zh": "满文数字语料库",
        "name_en": "Manc.hu Manchu Digital Corpus",
        "base_url": "https://manc.hu/en",
        "description": "目前最大的可检索满文在线语料库，收录碑文、诏书、萨满文本等满文原始文献含佛典相关材料",
        "region": "国际", "languages": "mnc,lzh", "access_type": "open",
    },
    # ── Reference & Dictionaries ──
    {
        "code": "sutta-pali-dict",
        "name_zh": "巴利多语词典",
        "name_en": "Pali Canon E-Dictionary (PCED)",
        "base_url": "https://dictionary.sutta.org/",
        "description": "多语巴利词典，支持巴利-英、巴利-中、巴利-日、巴利-越、巴利-缅查询，开源项目",
        "region": "国际", "languages": "pi,en,zh,ja,vi,my", "access_type": "open",
    },
    {
        "code": "84000-glossary",
        "name_zh": "84000三语术语表",
        "name_en": "84000 Trilingual Glossary",
        "base_url": "https://read.84000.co/glossary/search.html",
        "description": "84000项目的藏-梵-英三语术语表，汇集已出版译本中数千条术语、人物、地名、典籍的翻译与定义",
        "region": "国际", "languages": "bo,sa,en", "access_type": "open",
    },
    {
        "code": "payutto-dict",
        "name_zh": "帕尤陀泰英佛学词典",
        "name_en": "Payutto Dictionary of Buddhism",
        "base_url": "https://www.tipitaka.org/thai-dict",
        "description": "泰国高僧帕尤陀编纂的佛学词典，提供巴利-泰-英三语对照，是泰国佛教术语的标准参考",
        "region": "泰国", "languages": "th,pi,en", "access_type": "open",
    },
    {
        "code": "pts-dict-pali",
        "name_zh": "巴利圣典学会巴利词典",
        "name_en": "PTS A Dictionary of Pali",
        "base_url": "https://gandhari.org/dop",
        "description": "巴利圣典学会出版的《巴利词典》在线版，已出版3卷，托管于gandhari.org，是巴利语研究的权威工具",
        "region": "英国", "languages": "pi,en", "access_type": "open",
    },
    {
        "code": "rongmo-phathoc",
        "name_zh": "开心越南佛学术语库",
        "name_en": "Rong Mo Tam Hon Buddhist Terminology",
        "base_url": "https://www.rongmotamhon.net/",
        "description": "越南联合佛教基金会维护的佛学术语在线查询系统，含93353条术语，支持越巴梵中英多语检索",
        "region": "越南", "languages": "vi,pi,sa,zh,en", "access_type": "open",
    },
    {
        "code": "himalayanart",
        "name_zh": "喜马拉雅艺术资源",
        "name_en": "Himalayan Art Resources",
        "base_url": "https://www.himalayanart.org/",
        "description": "最大的喜马拉雅佛教图像学数据库，收录16000+张图像含唐卡、雕塑、壁画，支持按本尊风格检索",
        "region": "美国", "languages": "en,bo,sa", "access_type": "open",
    },
    # ── Dunhuang & Niche ──
    {
        "code": "dunhuang-research-db",
        "name_zh": "敦煌学信息资源库",
        "name_en": "Dunhuang Studies Information Resource Database",
        "base_url": "http://dh.dha.ac.cn/",
        "description": "敦煌研究院主办，含馆藏书目、研究论著目录、藏经洞文献目录、石窟内容总录等多个专题数据库",
        "region": "中国大陆", "languages": "lzh,zh", "access_type": "open",
    },
    {
        "code": "jain-elibrary",
        "name_zh": "耆那教电子文献库",
        "name_en": "Jain eLibrary",
        "base_url": "https://jainelibrary.org/",
        "description": "耆那教国际教育基金会主办，收录耆那教经典、手稿与词典，含大量与佛教思想对比的共享文献传统",
        "region": "印度", "languages": "sa,hi,en", "access_type": "restricted",
    },
    {
        "code": "loc-gandhara-scroll",
        "name_zh": "美国国会图书馆犍陀罗卷轴",
        "name_en": "Library of Congress Gandhara Scroll",
        "base_url": "https://www.loc.gov/item/2018305008",
        "description": "公元前一世纪犍陀罗佛教写本，出土于阿富汗，是已知最早的佛教文本之一，已完成修复并全文数字化",
        "region": "美国", "languages": "en,pgd", "access_type": "open",
    },
    # ── Iconography & Numismatics ──
    {
        "code": "numista-kushan",
        "name_zh": "贵霜佛教钱币在线目录",
        "name_en": "Numista Kushan Empire Coin Catalog",
        "base_url": "https://en.numista.com/catalogue/kushan_empire-2.html",
        "description": "全球钱币分类数据库中贵霜帝国专区，含迦腻色伽等贵霜王朝佛教主题钱币图录与铭文信息",
        "region": "国际", "languages": "en", "access_type": "open",
    },
    # ── Evaluation & Benchmarks ──
    {
        "code": "buddhism-eval",
        "name_zh": "佛教LLM评测基准",
        "name_en": "BuddhismEval",
        "base_url": "https://huggingface.co/datasets/Nethmi14/BuddhismEval",
        "description": "首个双语(僧伽罗/英)佛教伦理推理与哲学理解LLM评测基准，基于法句经等上座部佛教经典构建",
        "region": "斯里兰卡", "languages": "si,en", "access_type": "open",
    },
    # ── Audio/Accessibility ──
    {
        "code": "trungpa-digital",
        "name_zh": "创巴仁波切数字图书馆",
        "name_en": "Chogyam Trungpa Digital Library",
        "base_url": "https://library.chogyamtrungpa.com/",
        "description": "创巴仁波切1970-1986年500+场公开教学的音视频与可搜索文字稿数字档案",
        "region": "美国", "languages": "en", "access_type": "open",
    },
]


def _q(s: str) -> str:
    return s.replace("'", "''") if s else ""


def upgrade() -> None:
    for s in SOURCES:
        code = _q(s["code"])
        name_zh = _q(s["name_zh"])
        name_en = _q(s["name_en"])
        base_url = _q(s["base_url"])
        desc = _q(s["description"])
        region = _q(s["region"])
        langs = _q(s["languages"])
        access = _q(s["access_type"])
        op.execute(
            sa_text(f"""
                INSERT INTO data_sources
                    (code, name_zh, name_en, base_url, description,
                     access_type, region, languages, is_active)
                VALUES
                    ('{code}', '{name_zh}', '{name_en}', '{base_url}', '{desc}',
                     '{access}', '{region}', '{langs}', true)
                ON CONFLICT (code) DO NOTHING
            """)
        )


def downgrade() -> None:
    codes = ", ".join(f"'{_q(s['code'])}'" for s in SOURCES)
    op.execute(sa_text(f"DELETE FROM data_sources WHERE code IN ({codes})"))
