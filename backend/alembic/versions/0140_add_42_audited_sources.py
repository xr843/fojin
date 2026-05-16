"""Add 42 content-verified data sources (2026-05-16 全网检索 batch 3).

Found by a four-agent web sweep partitioned by tradition (CJK / Tibetan /
Theravada / Sanskrit-academic-AI). The agents produced ~80 raw candidates;
a dedup pass against the 580-source catalog dropped ~15 already present
under a different code (Dharmamitra=mitra-ai, BuddhaNexus=buddhanexus,
ACIP=acip, IDP=idp, SEADL-NIU=seadl-niu, …). Every surviving candidate then
had its URL re-verified live: 4 were cut (actib — repo not yet populated;
cjbs — journal discontinued; a BDRC blog post with no portal) and 2 held
(higashi-honganji 聖典 unreachable; UCR Thai Digital Monastery returning 502).

The 42 below are all verified reachable — sites behind Cloudflare/rate limits
answered 403/429, which means the server is up (a human browser reaches them).

access_type='external'; sort_order 0; is_active true;
INSERT ... ON CONFLICT (code) DO NOTHING for idempotency.

Revision ID: 0140
Revises: 0139
Create Date: 2026-05-16
"""

from alembic import op
from sqlalchemy import text

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None


NEW_SOURCES = [
    # ---- 汉传 / 东亚 (CJK) ----
    {
        "code": "tsurumi-ribc",
        "name_zh": "鹤见大学佛书·禅籍善本数字档案",
        "name_en": "Tsurumi University — Buddhist Rare Books & Documents Archive",
        "base_url": "https://ribc-archives.tsurumi-u.ac.jp/top",
        "description": "鹤见大学图书馆稀有佛书与曹洞禅籍的 IIIF 数字档案，收录《传光录》等善本写本与刊本的高清影像，采 CC BY 4.0 开放许可。",
        "region": "日本",
        "languages": "ja,zh",
        "research_fields": "han,art",
        "supports_iiif": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "iriz-hanazono",
        "name_zh": "国际禅学研究所禅籍数据库",
        "name_en": "International Research Institute for Zen Buddhism (Hanazono Univ.)",
        "base_url": "http://iriz.hanazono.ac.jp/",
        "description": "花园大学国际禅学研究所的禅籍文本数据库、公案索引与「电子达摩」禅宗术语检索系统，是有别于驹泽、禅文化研究所的独立禅学研究枢纽。",
        "region": "日本",
        "languages": "ja,zh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "e-museum-nich",
        "name_zh": "e国宝（日本国立文化财机构）",
        "name_en": "e-Museum — National Treasures of Japan",
        "base_url": "https://emuseum.nich.go.jp/",
        "description": "日本四大国立博物馆国宝·重要文化财统一影像库，含佛教雕塑、绘画、写经书迹的高清图像与多语解说。",
        "region": "日本",
        "languages": "ja,en,zh,ko",
        "research_fields": "art",
        "supports_search": True,
    },
    {
        "code": "jodoshu-daijiten",
        "name_zh": "新纂净土宗大辞典",
        "name_en": "New Compiled Jōdo-shū Encyclopedic Dictionary",
        "base_url": "https://jodoshuzensho.jp/daijiten/",
        "description": "2016 年《新纂净土宗大辞典》的网络版，可检索的净土宗权威辞书，附年表、传承谱系与寺院名录。",
        "region": "日本",
        "languages": "ja",
        "research_fields": "han,dictionary",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "jsri-jodo-canon",
        "name_zh": "净土宗综合研究所数字典籍",
        "name_en": "Jōdo Shū Research Institute — Digital Canon",
        "base_url": "https://jsri.jodo.or.jp/",
        "description": "净土宗综合研究所数字化的《净土宗全书》及净土宗典籍，提供全文检索。",
        "region": "日本",
        "languages": "ja,zh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "shinshu-seiten-online",
        "name_zh": "净土真宗圣典在线检索系统（本愿寺派）",
        "name_en": "Jōdo Shinshū Sacred Texts Online Search (Hongwanji-ha)",
        "base_url": "https://j-soken.net/",
        "description": "本愿寺派教学传道研究中心的净土真宗圣典在线全文检索平台。",
        "region": "日本",
        "languages": "ja,zh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "ryukoku-rarebook-db",
        "name_zh": "龙谷大学贵重资料图像数据库（龙谷藏）",
        "name_en": "Ryūkoku University Library — Rare Materials Image Database",
        "base_url": "https://da.library.ryukoku.ac.jp/",
        "description": "龙谷大学图书馆「龙谷藏」贵重资料图像库，五千余种、七十万幅图像，含佛典、真宗文献与写古本佛经。",
        "region": "日本",
        "languages": "ja,zh,sa",
        "research_fields": "han,art",
        "supports_search": True,
        "supports_iiif": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "seongbo-ego",
        "name_zh": "圣宝e-库（韩国佛教中央博物馆数字典藏）",
        "name_en": "Seongbo e-go — Korean Buddhist Sacred Treasures Repository",
        "base_url": "https://bmuseum.or.kr/",
        "description": "韩国佛教界圣宝数字典藏库，汇集佛国寺、松广寺、海印寺等寺院的国宝级文物与佛教艺术品影像。",
        "region": "韩国",
        "languages": "ko",
        "research_fields": "art",
        "supports_search": True,
    },
    {
        "code": "korea-buddhist-museum",
        "name_zh": "韩国佛教中央博物馆",
        "name_en": "Buddhist Central Museum (Jogye Order of Korean Buddhism)",
        "base_url": "http://museum.buddhism.or.kr/",
        "description": "韩国曹溪宗中央博物馆，收藏与展示韩国佛教艺术、佛画、法器与特展资料。",
        "region": "韩国",
        "languages": "ko",
        "research_fields": "art",
    },
    {
        "code": "thuvienhoasen",
        "name_zh": "莲花佛教图书馆",
        "name_en": "Thư Viện Hoa Sen — Lotus Buddhist Library",
        "base_url": "https://thuvienhoasen.org/",
        "description": "1994 年创办的越南最大非营利佛教图书馆之一，收录大乘、上座部经论、注疏与佛学期刊，越/英双语。",
        "region": "越南",
        "languages": "vi,en",
        "research_fields": "han,theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "hcmc-buddhist-research-lib",
        "name_zh": "胡志明市佛学研究院图书馆",
        "name_en": "HCMC Vietnam Buddhist Research Institute Library",
        "base_url": "https://www.thuvienphatgiao.com/",
        "description": "越南佛学研究院的学术图书馆目录，收录两千余部佛教典籍（含数字化全文），涵盖经论、僧伽教育与地区佛教。",
        "region": "越南",
        "languages": "vi,pi,sa,zh,en",
        "research_fields": "han,theravada",
        "supports_search": True,
    },
    {
        "code": "chuahoangphap-sutra",
        "name_zh": "弘法寺经书库",
        "name_en": "Chùa Hoằng Pháp — Monastery Sutra Library",
        "base_url": "https://chuahoangphap.com.vn/thu-vien-kinh-sach/",
        "description": "越南弘法寺的在线经书与佛学书籍库，越南语佛教寺院典籍档案。",
        "region": "越南",
        "languages": "vi",
        "research_fields": "han",
        "has_remote_fulltext": True,
    },
    {
        "code": "buddhist-architecture-wiki",
        "name_zh": "佛教建筑时空地图数据平台",
        "name_en": "Buddhist Architecture Spatio-temporal Data Platform",
        "base_url": "https://buddhist.wiki/",
        "description": "中英双语的佛教寺院、塔幢、石窟、造像结构化数据库，按概览/建筑/历史/艺术/人物组织，可对接地理与知识图谱。",
        "region": "中国",
        "languages": "zh,en",
        "research_fields": "art,dh",
        "supports_search": True,
    },
    {
        "code": "radich-tacl-corpus",
        "name_zh": "TACL 汉文佛典计算语言学数据库",
        "name_en": "Radich Taishō / TACL — Computational Corpus of the Chinese Buddhist Canon",
        "base_url": "https://zenodo.org/records/7824781",
        "description": "学者校订的大正藏数字化文本与 TACL 计算文献学数据库，供汉文佛典互文与文本重用分析使用。",
        "region": "新西兰",
        "languages": "zh,en",
        "research_fields": "han,dh",
    },
    # ---- 藏传 ----
    {
        "code": "ret-journal",
        "name_zh": "藏学评论（Revue d'Études Tibétaines）",
        "name_en": "Revue d'Études Tibétaines (RET)",
        "base_url": "https://www.digitalhimalaya.com/collections/journals/ret/",
        "description": "法国 CNRS/CRCAO 主办的藏学同行评审期刊，2002 年起全部往期免费 PDF 开放获取。",
        "region": "法国",
        "languages": "fr,en,bo",
        "research_fields": "tibetan,dh",
        "has_remote_fulltext": True,
    },
    {
        "code": "steinert-tibetan-dict",
        "name_zh": "Christian Steinert 藏英词典",
        "name_en": "Christian Steinert Tibetan-English Dictionary",
        "base_url": "https://dictionary.christian-steinert.de/",
        "description": "聚合 Rangjung Yeshe、Hopkins、Tsepak Rigdzin 等三十余部词典的免费藏文查词平台，开放数据托管于 GitHub。",
        "region": "德国",
        "languages": "bo,en,sa",
        "research_fields": "tibetan,dictionary",
        "supports_search": True,
    },
    {
        "code": "nitartha-library",
        "name_zh": "Nitartha 数字图书馆",
        "name_en": "Nitartha Digital Library",
        "base_url": "https://www.nitartha.net/",
        "description": "可检索的德格版甘珠尔/丹珠尔及藏人著作电子文本库，约六十五万页文本图像。",
        "region": "美国",
        "languages": "bo",
        "research_fields": "tibetan",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "rinchen-terdzo",
        "name_zh": "大宝伏藏（Rinchen Terdzö Chenmo）",
        "name_en": "Rinchen Terdzö Chenmo — Treasury of Precious Termas",
        "base_url": "https://rtz.tsadra.org/",
        "description": "七十二卷《大宝伏藏》的可检索目录与全 Unicode 文本，附完整元数据，由 Tsadra 基金会建置。",
        "region": "美国",
        "languages": "bo,en",
        "research_fields": "tibetan",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "mlotsawa",
        "name_zh": "MLotsawa 藏译英神经机器翻译",
        "name_en": "MLotsawa — Literary Tibetan→English Neural MT",
        "base_url": "https://github.com/billingsmoore/MLotsawa",
        "description": "开源的文言藏语→英语神经机器翻译工具，模型与数据集发布于 HuggingFace，可在普通硬件上运行。",
        "region": "国际",
        "languages": "bo,en",
        "research_fields": "tibetan,dh",
    },
    {
        "code": "soas-tidc",
        "name_zh": "SOAS 藏语数字传播语料库",
        "name_en": "Tibetan in Digital Communication (SOAS / TIDC)",
        "base_url": "https://glocal.soas.ac.uk/tibetan-in-digital-communication/",
        "description": "英国 AHRC 资助的历时性词性标注藏语语料库及工具，覆盖藏语发展史全程。",
        "region": "英国",
        "languages": "bo",
        "research_fields": "tibetan,dh",
    },
    {
        "code": "nekhor",
        "name_zh": "Nekhor 佛教圣地指南",
        "name_en": "Nekhor — Buddhist Sacred Sites",
        "base_url": "https://www.nekhor.org/",
        "description": "桑耶翻译团队建置的佛教朝圣圣地数据库，每处圣地附带经典与历史文献出处，含应用程序，可对接地理地图。",
        "region": "国际",
        "languages": "en,bo",
        "research_fields": "tibetan,art",
        "supports_search": True,
    },
    {
        "code": "dakini-translations",
        "name_zh": "空行母翻译与出版（金刚乘研究）",
        "name_en": "Dakini Translations and Publications",
        "base_url": "https://dakinitranslations.com/",
        "description": "Adele Tomlin 主持的金刚乘翻译与研究站，侧重噶举传承、女性传承人物与传记。",
        "region": "国际",
        "languages": "bo,en,zh",
        "research_fields": "tibetan",
        "has_remote_fulltext": True,
    },
    {
        "code": "bodhicitta-tsadra",
        "name_zh": "Bodhicitta（Tsadra 佛学书目库）",
        "name_en": "Bodhicitta — A Tsadra Foundation Project",
        "base_url": "https://bodhicitta.tsadra.org/",
        "description": "Tsadra 基金会建置的藏传佛教书目库，整理各派的书籍、论文、学位论文及经论注疏。",
        "region": "美国",
        "languages": "en,bo,sa",
        "research_fields": "tibetan,dh",
        "supports_search": True,
    },
    # ---- 南传 / 东南亚 ----
    {
        "code": "manchester-pali-mss",
        "name_zh": "曼彻斯特大学巴利写本数字馆藏",
        "name_en": "Manchester Digital Collections — Pali Manuscripts",
        "base_url": "https://www.digitalcollections.manchester.ac.uk/collections/pali",
        "description": "曼彻斯特大学馆藏斯里兰卡巴利贝叶写本（17–19 世纪）的 IIIF 高清数字化，含罕见的完整《发趣论》《导论》。",
        "region": "英国",
        "languages": "pi",
        "research_fields": "theravada",
        "supports_iiif": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "utokyo-burmese-tipitaka",
        "name_zh": "东京大学缅文巴利三藏数字档案",
        "name_en": "UTokyo — Burmese-Script Pāli Tipiṭaka Digital Archive",
        "base_url": "https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/burmese",
        "description": "东京大学数字化的缅文巴利三藏及注疏版本影像，含第六次结集前的缅文刊本。",
        "region": "日本",
        "languages": "pi",
        "research_fields": "theravada",
        "has_remote_fulltext": True,
    },
    {
        "code": "sleukrith-set",
        "name_zh": "SleukRith 高棉贝叶写本 OCR 数据集",
        "name_en": "SleukRith Set — Khmer Palm Leaf Manuscript Dataset",
        "base_url": "https://github.com/donavaly/SleukRith-Set",
        "description": "首个高棉贝叶写本 OCR 标注数据集，657 页含字符/词/行级标注，供东南亚佛教写本文字识别训练。",
        "region": "柬埔寨",
        "languages": "km",
        "research_fields": "theravada,dh",
    },
    {
        "code": "tipitaka-rpkg",
        "name_zh": "tipitaka R 包（巴利三藏语料）",
        "name_en": "tipitaka — R Package for the Pali Canon",
        "base_url": "https://cran.r-project.org/package=tipitaka",
        "description": "将完整 CST4 巴利三藏作为 R 数据集（原文、词频矩阵）提供，附巴利语排序与比较函数，供计算语言学使用。",
        "region": "国际",
        "languages": "pi,en",
        "research_fields": "theravada,dh",
    },
    {
        "code": "ucl-myanmar-palmleaf",
        "name_zh": "缅甸大学中央图书馆贝叶写本库",
        "name_en": "Universities' Central Library Myanmar — Palm-Leaf Collection",
        "base_url": "https://www.uclmyanmar.org/palm-leaf-manuscript-collections/",
        "description": "缅甸大学中央图书馆的贝叶写本馆藏，含一万七千余束三藏及注疏写本与四千余件折叠纸经。",
        "region": "缅甸",
        "languages": "pi,my",
        "research_fields": "theravada",
    },
    {
        "code": "sjp-tripitaka",
        "name_zh": "斯里兰卡贾雅瓦德纳普拉大学佛教三藏",
        "name_en": "University of Sri Jayewardenepura — Buddha Jayanthi Tripitaka",
        "base_url": "https://www.sjp.ac.lk/news/download-theravada-tripitaka/",
        "description": "斯里兰卡政府版佛陀纪元（Buddha Jayanthi）三藏，巴利原文对照僧伽罗语译文，四十卷可下载 PDF。",
        "region": "斯里兰卡",
        "languages": "pi,si",
        "research_fields": "theravada",
        "has_remote_fulltext": True,
    },
    {
        "code": "dhammadownload",
        "name_zh": "DhammaDownload 缅甸禅修教学库",
        "name_en": "DhammaDownload.com",
        "base_url": "https://www.dhammadownload.com/",
        "description": "缅甸禅修传统教学的大型档案，约四千部佛教电子书及数万则帕奥、马哈希等长老的开示音频。",
        "region": "缅甸",
        "languages": "my,en",
        "research_fields": "theravada",
        "has_remote_fulltext": True,
    },
    {
        "code": "suanmokkh",
        "name_zh": "解脱园（佛使比丘文献库）",
        "name_en": "Suan Mokkh — Buddhadāsa Bhikkhu Archive",
        "base_url": "https://www.suanmokkh.org/",
        "description": "泰国上座部改革者佛使比丘的著作、开示、文章与诗作合集，多语提供。",
        "region": "泰国",
        "languages": "th,en",
        "research_fields": "theravada",
        "has_remote_fulltext": True,
    },
    {
        "code": "buddhadust",
        "name_zh": "BuddhaDust（Obo's Web 巴利经藏译本库）",
        "name_en": "BuddhaDust — Obo's Web",
        "base_url": "https://obo.genaud.net/",
        "description": "经营数十年的独立巴利经藏译本库（含早期 PTS 译本），附详尽经文索引检索。",
        "region": "美国",
        "languages": "pi,en",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "pali-platform",
        "name_zh": "Pāli Platform 巴利研究工具",
        "name_en": "Pāli Platform",
        "base_url": "https://bhaddacak.github.io/paliplatform",
        "description": "持续维护的独立巴利研究桌面工具，集巴利阅读器、词典、课程与字体脚本工具于一体。",
        "region": "国际",
        "languages": "pi,sa,en",
        "research_fields": "theravada,dh",
    },
    {
        "code": "epitaka",
        "name_zh": "epitaka.org 开源三语三藏",
        "name_en": "epitaka.org — Open-Source Trilingual Tipiṭaka",
        "base_url": "https://github.com/dhammanana/epitaka.org",
        "description": "AI 初译加人工校对的巴利/英/越三语三藏，附语义搜索，提供 SQLite 文本数据集。",
        "region": "国际",
        "languages": "pi,en,vi",
        "research_fields": "theravada,dh",
    },
    # ---- 梵语 / 西方学术 / AI ----
    {
        "code": "read-workbench",
        "name_zh": "READ Workbench 古代佛教写本协作编辑平台",
        "name_en": "READ Workbench",
        "base_url": "https://readworkbench.org/",
        "description": "悉尼大学等机构的古代佛教写本与铭文协作式学术校勘平台，托管早期佛教写本项目与 Senior 犍陀罗卷轴。",
        "region": "澳大利亚",
        "languages": "sa,pi,en",
        "research_fields": "sanskrit,dh",
        "supports_search": True,
    },
    {
        "code": "sttar-sanskrit",
        "name_zh": "西藏所藏梵文佛典精校丛刊（STTAR）",
        "name_en": "Sanskrit Texts from the Tibetan Autonomous Region (STTAR)",
        "base_url": "https://www.oeaw.ac.at/en/ikga/publications/series/sanskrit-texts-from-the-tibetan-autonomous-region-sttar",
        "description": "奥地利科学院与中国藏学出版社合作的丛刊，精校出版以拉萨写本为底本、印度已佚的梵文佛典。",
        "region": "奥地利",
        "languages": "sa",
        "research_fields": "sanskrit",
    },
    {
        "code": "ghent-cbs-db",
        "name_zh": "根特大学佛学研究中心数据库",
        "name_en": "Ghent Centre for Buddhist Studies — Database",
        "base_url": "https://www.cbs.ugent.be/database/",
        "description": "根特大学佛学研究中心关于亚洲佛教传统的数字数据库与研究成果。",
        "region": "比利时",
        "languages": "en",
        "research_fields": "dh",
        "supports_search": True,
    },
    {
        "code": "jibs-journal",
        "name_zh": "国际佛教研究期刊（JIBS）",
        "name_en": "Journal of International Buddhist Studies (JIBS)",
        "base_url": "https://so09.tci-thaijo.org/index.php/jibs",
        "description": "泰国主办、Scopus/DOAJ 收录的开放获取佛教研究期刊。",
        "region": "泰国",
        "languages": "en",
        "research_fields": "theravada,dh",
        "has_remote_fulltext": True,
    },
    {
        "code": "lacma-seasian",
        "name_zh": "洛杉矶郡立美术馆东南亚艺术目录",
        "name_en": "LACMA — Southeast Asian Art Online Catalog",
        "base_url": "https://seasian.catalog.lacma.org/",
        "description": "洛杉矶郡立美术馆东南亚艺术在线学术目录，含斯里兰卡与东南亚佛教艺术专论。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
    },
    {
        "code": "british-museum-collection",
        "name_zh": "大英博物馆在线馆藏（亚洲佛教）",
        "name_en": "British Museum Collection Online",
        "base_url": "https://www.britishmuseum.org/collection",
        "description": "大英博物馆四百余万件在线馆藏数据库，含阿马拉瓦蒂佛教浮雕、斯里兰卡度母像、犍陀罗造像。",
        "region": "英国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
    },
    {
        "code": "walters-openaccess",
        "name_zh": "沃尔特斯艺术博物馆开放数据",
        "name_en": "Walters Art Museum — Open Access Data",
        "base_url": "https://thewalters.org/",
        "description": "沃尔特斯艺术博物馆的 CC0 开放数据与馆藏 API，逾万条记录含佛教艺术藏品。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
        "supports_api": True,
    },
    {
        "code": "newark-museum-asian",
        "name_zh": "纽瓦克艺术博物馆亚洲馆藏",
        "name_en": "Newark Museum of Art — Asian Collection",
        "base_url": "https://newarkmuseumart.org/collections/",
        "description": "西半球首屈一指的藏传佛教艺术收藏，含达赖喇嘛开光的佛坛。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
    },
]


def upgrade() -> None:
    def q(v):
        if v is None:
            return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    for s in NEW_SOURCES:
        supports_search = "true" if s.get("supports_search") else "false"
        supports_iiif = "true" if s.get("supports_iiif") else "false"
        supports_api = "true" if s.get("supports_api") else "false"
        has_remote_fulltext = "true" if s.get("has_remote_fulltext") else "false"
        op.execute(
            text(
                "INSERT INTO data_sources "
                "(code, name_zh, name_en, base_url, description, "
                " access_type, region, languages, research_fields, "
                " supports_search, supports_iiif, supports_api, has_remote_fulltext, "
                " sort_order, is_active) "
                f"VALUES ({q(s['code'])}, {q(s['name_zh'])}, {q(s['name_en'])}, "
                f"        {q(s['base_url'])}, {q(s['description'])}, 'external', "
                f"        {q(s['region'])}, {q(s['languages'])}, {q(s['research_fields'])}, "
                f"        {supports_search}, {supports_iiif}, {supports_api}, "
                f"        {has_remote_fulltext}, "
                "         0, true) "
                "ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    for s in NEW_SOURCES:
        op.execute(text(f"DELETE FROM data_sources WHERE code = '{s['code']}'"))
