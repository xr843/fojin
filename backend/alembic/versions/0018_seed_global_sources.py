"""seed global Buddhist digital library sources

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    # ===== 中国大陆 =====
    {"code": "nlc", "name_zh": "中国国家图书馆古籍部", "name_en": "National Library of China", "base_url": "http://read.nlc.cn/", "region": "中国"},
    {"code": "shanghai-lib", "name_zh": "上海图书馆古籍善本", "name_en": "Shanghai Library Rare Books", "base_url": "https://www.library.sh.cn/", "region": "中国"},
    {"code": "nanjing-lib", "name_zh": "南京图书馆古籍部", "name_en": "Nanjing Library", "base_url": "http://www.jslib.org.cn/", "region": "中国"},
    {"code": "zhejiang-lib", "name_zh": "浙江省图书馆古籍", "name_en": "Zhejiang Library", "base_url": "https://www.zjlib.cn/", "region": "中国"},
    {"code": "sichuan-lib", "name_zh": "四川省图书馆古籍", "name_en": "Sichuan Provincial Library", "base_url": "https://www.sclib.org/", "region": "中国"},
    {"code": "yunnan-lib", "name_zh": "云南省图书馆贝叶经", "name_en": "Yunnan Library Palm Leaf MSS", "base_url": "https://www.ynlib.cn/", "region": "中国"},
    {"code": "gansu-lib", "name_zh": "甘肃省图书馆敦煌文献", "name_en": "Gansu Library Dunhuang MSS", "base_url": "http://www.gslib.com.cn/", "region": "中国"},
    {"code": "tianjin-lib", "name_zh": "天津图书馆古籍", "name_en": "Tianjin Library", "base_url": "https://www.tjl.tj.cn/", "region": "中国"},
    {"code": "hubei-lib", "name_zh": "湖北省图书馆古籍", "name_en": "Hubei Provincial Library", "base_url": "http://www.library.hb.cn/", "region": "中国"},
    {"code": "suzhou-lib", "name_zh": "苏州图书馆古籍", "name_en": "Suzhou Library", "base_url": "http://www.szlib.com/", "region": "中国"},
    {"code": "hangzhou-lib", "name_zh": "杭州图书馆佛教文献", "name_en": "Hangzhou Library", "base_url": "https://www.hzlib.net/", "region": "中国"},
    {"code": "dunhuang-academy", "name_zh": "敦煌研究院数字敦煌", "name_en": "Dunhuang Academy Digital Archive", "base_url": "https://www.e-dunhuang.com/", "region": "中国"},
    {"code": "dunhuang-iiif", "name_zh": "敦煌遗书数据库", "name_en": "Dunhuang Manuscript Database", "base_url": "http://idp.nlc.cn/", "region": "中国"},
    {"code": "cass-religion", "name_zh": "中国社科院世界宗教研究所", "name_en": "CASS Institute of World Religions", "base_url": "http://iwr.cass.cn/", "region": "中国"},
    {"code": "pku-buddhism", "name_zh": "北京大学佛教典籍与艺术研究中心", "name_en": "PKU Center for Buddhist Studies", "base_url": "https://www.pku.edu.cn/", "region": "中国"},
    {"code": "tsinghua-dh", "name_zh": "清华大学数字人文中心", "name_en": "Tsinghua Digital Humanities", "base_url": "https://www.tsinghua.edu.cn/", "region": "中国"},
    {"code": "fudan-buddhism", "name_zh": "复旦大学佛学研究中心", "name_en": "Fudan Buddhist Studies", "base_url": "https://www.fudan.edu.cn/", "region": "中国"},
    {"code": "zju-buddhism", "name_zh": "浙江大学佛教文献研究中心", "name_en": "ZJU Buddhist Literature Center", "base_url": "https://www.zju.edu.cn/", "region": "中国"},
    {"code": "wuhan-univ", "name_zh": "武汉大学古籍研究所", "name_en": "Wuhan Univ Ancient Texts Institute", "base_url": "https://www.whu.edu.cn/", "region": "中国"},
    {"code": "renmin-buddhism", "name_zh": "中国人民大学佛教与宗教学研究所", "name_en": "RUC Buddhist Studies", "base_url": "https://www.ruc.edu.cn/", "region": "中国"},
    {"code": "nanjing-univ", "name_zh": "南京大学域外汉籍研究所", "name_en": "NJU Overseas Chinese Texts", "base_url": "https://www.nju.edu.cn/", "region": "中国"},
    {"code": "shandong-univ", "name_zh": "山东大学佛学研究中心", "name_en": "SDU Buddhist Studies", "base_url": "https://www.sdu.edu.cn/", "region": "中国"},
    {"code": "putuo-lib", "name_zh": "普陀山佛教文化研究所", "name_en": "Putuo Buddhist Culture Institute", "base_url": "https://www.ثبت.cn/", "region": "中国"},
    {"code": "lingyin-temple", "name_zh": "灵隐寺云林藏经阁", "name_en": "Lingyin Temple Scripture Library", "base_url": "https://www.ثبت.cn/", "region": "中国"},
    {"code": "longquan-temple", "name_zh": "龙泉寺数字佛典", "name_en": "Longquan Temple Digital Archive", "base_url": "https://www.longquanzs.org/", "region": "中国"},
    {"code": "fgs-lib", "name_zh": "佛光山佛教文献数据库", "name_en": "Fo Guang Shan Archives", "base_url": "https://www.fgs.org.tw/", "region": "中国"},
    {"code": "palace-museum", "name_zh": "故宫博物院藏传佛教文物", "name_en": "Palace Museum Tibetan Buddhist Art", "base_url": "https://www.dpm.org.cn/", "region": "中国"},
    {"code": "tibet-lib", "name_zh": "西藏自治区图书馆贝叶经", "name_en": "Tibet Autonomous Region Library", "base_url": "http://www.xzlib.com/", "region": "中国"},
    {"code": "potala-archive", "name_zh": "布达拉宫古籍数字化", "name_en": "Potala Palace Digital Archive", "base_url": "https://www.potalapalace.cn/", "region": "中国"},
    {"code": "cnki-buddhism", "name_zh": "中国知网佛学专题库", "name_en": "CNKI Buddhist Studies DB", "base_url": "https://www.cnki.net/", "region": "中国"},
    {"code": "zhonghua-dazangjing", "name_zh": "中华大藏经数据库", "name_en": "Chinese Buddhist Canon Database", "base_url": "https://www.zhonghuadazangjing.cn/", "region": "中国"},
    {"code": "jiaxing-zang", "name_zh": "嘉兴藏数字化项目", "name_en": "Jiaxing Canon Digital Project", "base_url": "https://www.cbeta.org/", "region": "中国"},
    {"code": "fangshan-stone", "name_zh": "房山石经数据库", "name_en": "Fangshan Stone Sutra Database", "base_url": "https://www.nlc.cn/", "region": "中国"},
    {"code": "inner-mongolia", "name_zh": "内蒙古图书馆蒙文佛典", "name_en": "Inner Mongolia Library Mongolian MSS", "base_url": "http://www.nmglib.com/", "region": "中国"},
    {"code": "guangzhou-lib", "name_zh": "广州大典佛教文献", "name_en": "Guangzhou Canon Buddhist Texts", "base_url": "https://www.gzlib.org.cn/", "region": "中国"},

    # ===== 台湾地区 =====
    {"code": "ncl-tw", "name_zh": "台湾国家图书馆古籍", "name_en": "National Central Library Taiwan", "base_url": "https://www.ncl.edu.tw/", "region": "台湾"},
    {"code": "dharma-drum", "name_zh": "法鼓文理学院 DILA", "name_en": "Dharma Drum Institute", "base_url": "https://www.dila.edu.tw/", "region": "台湾"},
    {"code": "ntu-buddhism", "name_zh": "台湾大学佛学数位图书馆", "name_en": "NTU Buddhist Digital Library", "base_url": "https://buddhism.lib.ntu.edu.tw/", "region": "台湾"},
    {"code": "fgs-digital", "name_zh": "佛光大辞典数位版", "name_en": "Fo Guang Dictionary Digital", "base_url": "https://www.fgs.org.tw/", "region": "台湾"},
    {"code": "chung-hwa", "name_zh": "中华佛学研究所", "name_en": "Chung-Hwa Inst. of Buddhist Studies", "base_url": "https://www.chibs.edu.tw/", "region": "台湾"},
    {"code": "academia-sinica", "name_zh": "中央研究院汉籍电子文献", "name_en": "Academia Sinica Chinese Texts", "base_url": "https://hanchi.ihp.sinica.edu.tw/", "region": "台湾"},

    # ===== 日本 =====
    {"code": "ndl-japan", "name_zh": "日本国立国会图书馆", "name_en": "National Diet Library Japan", "base_url": "https://www.ndl.go.jp/", "region": "日本"},
    {"code": "sat-utokyo", "name_zh": "东京大学 SAT 大藏经", "name_en": "SAT Daizōkyō Text Database", "base_url": "https://21dzk.l.u-tokyo.ac.jp/SAT/", "region": "日本"},
    {"code": "kyoto-univ", "name_zh": "京都大学贵重资料数字档案", "name_en": "Kyoto Univ Rare Materials Archive", "base_url": "https://rmda.kulib.kyoto-u.ac.jp/", "region": "日本"},
    {"code": "otani-univ", "name_zh": "大谷大学佛教综合研究所", "name_en": "Otani University Buddhist Research", "base_url": "https://www.otani.ac.jp/", "region": "日本"},
    {"code": "komazawa-univ", "name_zh": "驹泽大学禅学研究所", "name_en": "Komazawa Univ Zen Studies", "base_url": "https://www.komazawa-u.ac.jp/", "region": "日本"},
    {"code": "ryukoku-univ", "name_zh": "龙谷大学佛教文化研究所", "name_en": "Ryukoku Univ Buddhist Culture", "base_url": "https://www.ryukoku.ac.jp/", "region": "日本"},
    {"code": "taisho-univ", "name_zh": "大正大学综合佛教研究所", "name_en": "Taisho University Buddhist Institute", "base_url": "https://www.tais.ac.jp/", "region": "日本"},
    {"code": "koyasan-univ", "name_zh": "高野山大学密教学研究所", "name_en": "Koyasan Univ Esoteric Studies", "base_url": "https://www.koyasan-u.ac.jp/", "region": "日本"},
    {"code": "waseda-kotenseki", "name_zh": "早稻田大学古典籍数据库", "name_en": "Waseda Univ Kotenseki DB", "base_url": "https://www.wul.waseda.ac.jp/kotenseki/", "region": "日本"},
    {"code": "toyo-bunko", "name_zh": "东洋文库佛教文献", "name_en": "Toyo Bunko Buddhist Collection", "base_url": "http://www.toyo-bunko.or.jp/", "region": "日本"},
    {"code": "nara-museum", "name_zh": "奈良国立博物馆佛教美术", "name_en": "Nara National Museum", "base_url": "https://www.narahaku.go.jp/", "region": "日本"},
    {"code": "tnm-japan", "name_zh": "东京国立博物馆佛教文物", "name_en": "Tokyo National Museum Buddhist Art", "base_url": "https://www.tnm.jp/", "region": "日本"},
    {"code": "shosoin", "name_zh": "正仓院宝物数据库", "name_en": "Shosoin Treasure Database", "base_url": "https://shosoin.kunaicho.go.jp/", "region": "日本"},
    {"code": "daizokyo-society", "name_zh": "大藏经学术用语研究会", "name_en": "Daizōkyō Research Society", "base_url": "https://www.l.u-tokyo.ac.jp/", "region": "日本"},
    {"code": "jodo-shu", "name_zh": "净土宗综合研究所", "name_en": "Jodo Shu Research Institute", "base_url": "https://www.jodo.or.jp/", "region": "日本"},
    {"code": "nichiren-lib", "name_zh": "日莲宗电子图书馆", "name_en": "Nichiren Shu Digital Library", "base_url": "https://www.nichiren.or.jp/", "region": "日本"},
    {"code": "iriz-hanazono", "name_zh": "花园大学国际禅学研究所", "name_en": "IRIZ Hanazono University", "base_url": "https://iriz.hanazono.ac.jp/", "region": "日本"},
    {"code": "nii-japan", "name_zh": "日本国立情报学研究所 CiNii", "name_en": "NII CiNii Buddhist Articles", "base_url": "https://cir.nii.ac.jp/", "region": "日本"},

    # ===== 韩国 =====
    {"code": "korean-tripitaka-db", "name_zh": "高丽大藏经知识库", "name_en": "Korean Tripitaka Knowledgebase", "base_url": "https://kb.sutra.re.kr/", "region": "韩国"},
    {"code": "dongguk-univ", "name_zh": "东国大学佛教学术院", "name_en": "Dongguk Univ Buddhist Academy", "base_url": "https://www.dongguk.edu/", "region": "韩国"},
    {"code": "snu-kyujanggak", "name_zh": "首尔大学奎章阁古籍", "name_en": "SNU Kyujanggak Archives", "base_url": "https://kyujanggak.snu.ac.kr/", "region": "韩国"},
    {"code": "haeinsa", "name_zh": "海印寺八万大藏经", "name_en": "Haeinsa Temple Tripitaka Koreana", "base_url": "https://www.haeinsa.or.kr/", "region": "韩国"},
    {"code": "jogye-order", "name_zh": "大韩佛教曹溪宗数据库", "name_en": "Jogye Order of Korean Buddhism", "base_url": "http://www.buddhism.or.kr/", "region": "韩国"},
    {"code": "aks-korea", "name_zh": "韩国学中央研究院佛教资料", "name_en": "AKS Buddhist Materials", "base_url": "https://www.aks.ac.kr/", "region": "韩国"},
    {"code": "nfm-korea", "name_zh": "韩国国立中央博物馆佛教艺术", "name_en": "National Museum of Korea Buddhist Art", "base_url": "https://www.museum.go.kr/", "region": "韩国"},

    # ===== 东南亚 =====
    {"code": "mahidol-tipitaka", "name_zh": "泰国玛希隆大学巴利三藏", "name_en": "Mahidol University Pali Tipitaka", "base_url": "https://budsir.mahidol.ac.th/", "region": "泰国"},
    {"code": "wat-pho", "name_zh": "卧佛寺巴利文献数字化", "name_en": "Wat Pho Pali Manuscripts", "base_url": "https://www.watpho.com/", "region": "泰国"},
    {"code": "chula-pali", "name_zh": "朱拉隆功大学巴利佛学", "name_en": "Chulalongkorn Univ Pali Studies", "base_url": "https://www.chula.ac.th/", "region": "泰国"},
    {"code": "myanmar-tipitaka", "name_zh": "缅甸第六次结集三藏", "name_en": "Myanmar Chaṭṭha Saṅgāyana", "base_url": "https://tipitaka.org/", "region": "缅甸"},
    {"code": "srilanka-tripitaka", "name_zh": "斯里兰卡巴利三藏协会", "name_en": "Sri Lanka Tripitaka Project", "base_url": "https://www.pali.lk/", "region": "斯里兰卡"},
    {"code": "kelaniya-univ", "name_zh": "凯拉尼亚大学巴利佛学", "name_en": "Univ of Kelaniya Pali Studies", "base_url": "https://www.kln.ac.lk/", "region": "斯里兰卡"},
    {"code": "cambodia-buddhism", "name_zh": "柬埔寨佛教研究所", "name_en": "Buddhist Institute Cambodia", "base_url": "https://www.bid.org.kh/", "region": "柬埔寨"},
    {"code": "laos-palm-leaf", "name_zh": "老挝贝叶经数字档案", "name_en": "Laos Palm Leaf MSS Archive", "base_url": "https://www.digitalpreservation.la/", "region": "老挝"},
    {"code": "vietnam-buddhism", "name_zh": "越南佛教大学文献库", "name_en": "Vietnam Buddhist Univ Library", "base_url": "https://www.vbu.edu.vn/", "region": "越南"},

    # ===== 南亚 =====
    {"code": "nalanda-digital", "name_zh": "那烂陀大学数字遗产", "name_en": "Nalanda University Digital Heritage", "base_url": "https://nalandauniv.edu.in/", "region": "印度"},
    {"code": "asi-india", "name_zh": "印度考古调查局佛教遗址", "name_en": "Archaeological Survey of India", "base_url": "https://asi.nic.in/", "region": "印度"},
    {"code": "bhu-sanskrit", "name_zh": "贝纳勒斯印度大学梵文系", "name_en": "BHU Sanskrit Department", "base_url": "https://www.bhu.ac.in/", "region": "印度"},
    {"code": "pune-bori", "name_zh": "浦那东方学研究所", "name_en": "Bhandarkar Oriental Research Inst", "base_url": "https://www.bfrInstitute.org/", "region": "印度"},
    {"code": "delhi-national-museum", "name_zh": "印度国家博物馆佛教文物", "name_en": "National Museum New Delhi Buddhist Art", "base_url": "https://www.nationalmuseumindia.gov.in/", "region": "印度"},
    {"code": "nepal-ntca", "name_zh": "尼泊尔国家档案馆梵文写本", "name_en": "Nepal National Archives Sanskrit MSS", "base_url": "https://www.ntca.gov.np/", "region": "尼泊尔"},
    {"code": "lumbini-research", "name_zh": "蓝毗尼发展基金会", "name_en": "Lumbini Development Trust Research", "base_url": "https://www.lumbinidevtrust.gov.np/", "region": "尼泊尔"},
    {"code": "bhutan-lib", "name_zh": "不丹国家图书馆佛教文献", "name_en": "National Library of Bhutan", "base_url": "https://www.library.gov.bt/", "region": "不丹"},

    # ===== 中亚（丝绸之路） =====
    {"code": "turfan-studies", "name_zh": "吐鲁番学研究院", "name_en": "Turfan Studies Collection", "base_url": "https://turfan.bbaw.de/", "region": "德国"},
    {"code": "otani-collection", "name_zh": "大谷探险队中亚收集品", "name_en": "Otani Collection Central Asia", "base_url": "https://www.ryukoku.ac.jp/", "region": "日本"},
    {"code": "stein-collection", "name_zh": "斯坦因敦煌收集品", "name_en": "Stein Collection", "base_url": "https://www.bl.uk/collection-guides/stein-collection", "region": "英国"},
    {"code": "pelliot-collection", "name_zh": "伯希和敦煌收集品", "name_en": "Pelliot Collection", "base_url": "https://gallica.bnf.fr/", "region": "法国"},

    # ===== 蒙古 =====
    {"code": "mongolia-lib", "name_zh": "蒙古国国家图书馆佛经", "name_en": "National Library of Mongolia", "base_url": "https://www.nationallibrary.mn/", "region": "蒙古"},
    {"code": "gandan-monastery", "name_zh": "甘丹寺佛教文献", "name_en": "Gandantegchinlen Monastery", "base_url": "https://www.gandan.mn/", "region": "蒙古"},

    # ===== 欧洲 =====
    {"code": "bl-buddhism", "name_zh": "大英图书馆佛教写本", "name_en": "British Library Buddhist MSS", "base_url": "https://www.bl.uk/", "region": "英国"},
    {"code": "oxford-bodleian", "name_zh": "牛津大学博德利图书馆梵文", "name_en": "Bodleian Library Sanskrit MSS", "base_url": "https://www.bodleian.ox.ac.uk/", "region": "英国"},
    {"code": "cambridge-sanskrit", "name_zh": "剑桥大学梵文佛教写本", "name_en": "Cambridge Univ Sanskrit Buddhist MSS", "base_url": "https://www.lib.cam.ac.uk/", "region": "英国"},
    {"code": "soas-buddhism", "name_zh": "伦敦大学 SOAS 佛学", "name_en": "SOAS Buddhist Studies", "base_url": "https://www.soas.ac.uk/", "region": "英国"},
    {"code": "pali-text-society", "name_zh": "巴利圣典协会", "name_en": "Pali Text Society", "base_url": "https://www.palitext.com/", "region": "英国"},
    {"code": "bnf-buddhism", "name_zh": "法国国家图书馆东方写本", "name_en": "BnF Oriental Manuscripts", "base_url": "https://www.bnf.fr/", "region": "法国"},
    {"code": "efeo", "name_zh": "法国远东学院佛学", "name_en": "EFEO Buddhist Studies", "base_url": "https://www.efeo.fr/", "region": "法国"},
    {"code": "crcao-paris", "name_zh": "巴黎东亚文明研究中心", "name_en": "CRCAO Paris Buddhist Studies", "base_url": "https://www.crcao.fr/", "region": "法国"},
    {"code": "hamburg-buddhism", "name_zh": "汉堡大学印度学与藏学", "name_en": "Univ Hamburg Indology & Tibetology", "base_url": "https://www.buddhismuskunde.uni-hamburg.de/", "region": "德国"},
    {"code": "goettingen-sanskrit", "name_zh": "哥廷根大学梵文学", "name_en": "Göttingen Univ Sanskrit Studies", "base_url": "https://www.uni-goettingen.de/", "region": "德国"},
    {"code": "bavarian-state-lib", "name_zh": "巴伐利亚州立图书馆东亚", "name_en": "Bavarian State Library East Asia", "base_url": "https://www.bsb-muenchen.de/", "region": "德国"},
    {"code": "berlin-turfan", "name_zh": "柏林国家图书馆吐鲁番收藏", "name_en": "Berlin State Library Turfan Collection", "base_url": "https://www.staatsbibliothek-berlin.de/", "region": "德国"},
    {"code": "leiden-univ", "name_zh": "莱顿大学佛学研究所", "name_en": "Leiden Univ Buddhist Studies", "base_url": "https://www.universiteitleiden.nl/", "region": "荷兰"},
    {"code": "oslo-polyglotta", "name_zh": "奥斯陆大学多语佛典", "name_en": "Univ Oslo Bibliotheca Polyglotta", "base_url": "https://www2.hf.uio.no/polyglotta/", "region": "挪威"},
    {"code": "vienna-buddhism", "name_zh": "维也纳大学佛教学", "name_en": "Univ Vienna Buddhist Studies", "base_url": "https://stb.univie.ac.at/", "region": "奥地利"},
    {"code": "ghent-buddhism", "name_zh": "根特大学东方语言佛学", "name_en": "Ghent Univ Buddhist Studies", "base_url": "https://www.ugent.be/", "region": "比利时"},
    {"code": "nagarjuna-inst", "name_zh": "龙树学院(DSBC)", "name_en": "Nagarjuna Institute DSBC", "base_url": "https://www.dsbcproject.org/", "region": "丹麦"},
    {"code": "russian-academy", "name_zh": "俄罗斯科学院东方写本研究所", "name_en": "IOM RAS Oriental Manuscripts", "base_url": "https://www.orientalstudies.ru/", "region": "俄罗斯"},
    {"code": "hermitage-buddhism", "name_zh": "冬宫博物馆佛教艺术", "name_en": "Hermitage Museum Buddhist Art", "base_url": "https://www.hermitagemuseum.org/", "region": "俄罗斯"},
    {"code": "vatican-lib", "name_zh": "梵蒂冈图书馆东方写本", "name_en": "Vatican Library Oriental MSS", "base_url": "https://www.vaticanlibrary.va/", "region": "意大利"},
    {"code": "turin-tibetan", "name_zh": "都灵大学藏学研究", "name_en": "Univ Turin Tibetan Studies", "base_url": "https://www.unito.it/", "region": "意大利"},
    {"code": "barcelona-buddhism", "name_zh": "巴塞罗那自治大学东亚佛学", "name_en": "UAB East Asian Buddhist Studies", "base_url": "https://www.uab.cat/", "region": "西班牙"},
    {"code": "copenhagen-buddhism", "name_zh": "哥本哈根大学跨文化佛教研究", "name_en": "Univ Copenhagen Buddhist Studies", "base_url": "https://ccrs.ku.dk/", "region": "丹麦"},
    {"code": "lmu-buddhism", "name_zh": "慕尼黑大学印度学与藏学", "name_en": "LMU Munich Indology & Tibetology", "base_url": "https://www.lmu.de/", "region": "德国"},
    {"code": "sbb-asian", "name_zh": "柏林国家图书馆亚洲部", "name_en": "Berlin State Library Asian Division", "base_url": "https://www.staatsbibliothek-berlin.de/", "region": "德国"},

    # ===== 北美 =====
    {"code": "loc-asian", "name_zh": "美国国会图书馆亚洲部", "name_en": "Library of Congress Asian Division", "base_url": "https://www.loc.gov/rr/asian/", "region": "美国"},
    {"code": "harvard-yenching", "name_zh": "哈佛燕京图书馆", "name_en": "Harvard-Yenching Library", "base_url": "https://library.harvard.edu/libraries/harvard-yenching-library", "region": "美国"},
    {"code": "harvard-buddhism", "name_zh": "哈佛大学南亚佛学研究", "name_en": "Harvard South Asian Buddhist Studies", "base_url": "https://www.harvard.edu/", "region": "美国"},
    {"code": "yale-divinity", "name_zh": "耶鲁大学东亚佛学", "name_en": "Yale Divinity School Buddhist Studies", "base_url": "https://divinity.yale.edu/", "region": "美国"},
    {"code": "princeton-east-asian", "name_zh": "普林斯顿大学东亚图书馆", "name_en": "Princeton East Asian Library", "base_url": "https://library.princeton.edu/eastasian", "region": "美国"},
    {"code": "columbia-starr", "name_zh": "哥伦比亚大学东亚图书馆", "name_en": "Columbia Starr East Asian Library", "base_url": "https://library.columbia.edu/libraries/eastasian.html", "region": "美国"},
    {"code": "berkeley-ceas", "name_zh": "加州大学伯克利分校佛学", "name_en": "UC Berkeley Buddhist Studies", "base_url": "https://buddhiststudies.berkeley.edu/", "region": "美国"},
    {"code": "stanford-buddhism", "name_zh": "斯坦福大学 Ho 佛学图书馆", "name_en": "Stanford Ho Buddhist Library", "base_url": "https://library.stanford.edu/", "region": "美国"},
    {"code": "chicago-divinity", "name_zh": "芝加哥大学佛学研究", "name_en": "Univ Chicago Buddhist Studies", "base_url": "https://divinity.uchicago.edu/", "region": "美国"},
    {"code": "michigan-buddhism", "name_zh": "密歇根大学佛学研究", "name_en": "Univ Michigan Buddhist Studies", "base_url": "https://lsa.umich.edu/", "region": "美国"},
    {"code": "virginia-buddhism", "name_zh": "弗吉尼亚大学藏传佛教资源", "name_en": "UVA Tibetan Buddhist Resource Center", "base_url": "https://www.virginia.edu/", "region": "美国"},
    {"code": "washington-gandhari", "name_zh": "华盛顿大学犍陀罗研究", "name_en": "Univ Washington Gandhāran Studies", "base_url": "https://gandhari.org/", "region": "美国"},
    {"code": "ucla-buddhism", "name_zh": "加州大学洛杉矶分校佛学", "name_en": "UCLA Buddhist Studies", "base_url": "https://www.ucla.edu/", "region": "美国"},
    {"code": "wisconsin-buddhism", "name_zh": "威斯康辛大学佛教研究", "name_en": "UW-Madison Buddhist Studies", "base_url": "https://www.wisc.edu/", "region": "美国"},
    {"code": "ubc-buddhism", "name_zh": "不列颠哥伦比亚大学佛学", "name_en": "UBC Buddhist Studies", "base_url": "https://www.ubc.ca/", "region": "加拿大"},
    {"code": "toronto-buddhism", "name_zh": "多伦多大学佛学研究", "name_en": "Univ Toronto Buddhist Studies", "base_url": "https://www.utoronto.ca/", "region": "加拿大"},
    {"code": "mcgill-buddhism", "name_zh": "麦吉尔大学佛教研究", "name_en": "McGill Buddhist Studies", "base_url": "https://www.mcgill.ca/", "region": "加拿大"},

    # ===== 大洋洲 =====
    {"code": "melbourne-chinese", "name_zh": "墨尔本大学中国古代文学典籍", "name_en": "Univ Melbourne Chinese Classics", "base_url": "https://www.unimelb.edu.au/", "region": "澳大利亚"},
    {"code": "sydney-buddhism", "name_zh": "悉尼大学佛学与道学研究", "name_en": "Univ Sydney Buddhist Studies", "base_url": "https://www.sydney.edu.au/", "region": "澳大利亚"},
    {"code": "anu-buddhism", "name_zh": "澳大利亚国立大学佛学", "name_en": "ANU Buddhist Studies", "base_url": "https://www.anu.edu.au/", "region": "澳大利亚"},

    # ===== 国际数字项目 =====
    {"code": "tbrc-bdrc", "name_zh": "佛教数字资源中心 BDRC", "name_en": "Buddhist Digital Resource Center", "base_url": "https://www.bdrc.io/", "region": "国际"},
    {"code": "suttacentral-org", "name_zh": "SuttaCentral 早期佛典", "name_en": "SuttaCentral Early Buddhist Texts", "base_url": "https://suttacentral.net/", "region": "国际"},
    {"code": "accesstoinsight", "name_zh": "Access to Insight 巴利英译", "name_en": "Access to Insight", "base_url": "https://www.accesstoinsight.org/", "region": "国际"},
    {"code": "dharmapearls", "name_zh": "法珠翻译项目", "name_en": "Dharma Pearls Translation", "base_url": "https://dharmapearls.net/", "region": "国际"},
    {"code": "bdk-tripitaka", "name_zh": "BDK 英译大藏经", "name_en": "BDK English Tripiṭaka", "base_url": "https://www.bdkamerica.org/", "region": "国际"},
    {"code": "wisdom-lib", "name_zh": "Wisdom Library 佛学百科", "name_en": "Wisdom Library", "base_url": "https://www.wisdomlib.org/", "region": "国际"},
    {"code": "lotus-sutra", "name_zh": "法华经多语种数据库", "name_en": "Lotus Sutra Multilingual DB", "base_url": "https://www.ثبت.cn/", "region": "国际"},
    {"code": "open-philology", "name_zh": "开放语文学佛教文献", "name_en": "Open Philology Buddhist Texts", "base_url": "https://www.openphilology.org/", "region": "国际"},
    {"code": "eap-bl", "name_zh": "大英图书馆濒危档案项目", "name_en": "Endangered Archives Programme", "base_url": "https://eap.bl.uk/", "region": "国际"},
    {"code": "iiif-buddhist", "name_zh": "IIIF 佛教写本联盟", "name_en": "IIIF Buddhist Manuscripts Consortium", "base_url": "https://iiif.io/", "region": "国际"},
    {"code": "cbeta-org", "name_zh": "CBETA 中华电子佛典", "name_en": "Chinese Buddhist Electronic Text Assn", "base_url": "https://www.cbeta.org/", "region": "国际"},
    {"code": "kanseki-repo", "name_zh": "漢籍リポジトリ(Kanseki)", "name_en": "Kanseki Repository", "base_url": "https://www.kanripo.org/", "region": "国际"},
]


def upgrade() -> None:
    from sqlalchemy import text as sa_text
    conn = op.get_bind()
    for src in SOURCES:
        conn.execute(
            sa_text("""
                INSERT INTO data_sources (code, name_zh, name_en, base_url, description)
                VALUES (:code, :name_zh, :name_en, :base_url, :description)
                ON CONFLICT (code) DO UPDATE SET
                    name_zh = EXCLUDED.name_zh,
                    name_en = EXCLUDED.name_en,
                    base_url = EXCLUDED.base_url
            """),
            {
                "code": src["code"],
                "name_zh": src["name_zh"],
                "name_en": src["name_en"],
                "base_url": src.get("base_url"),
                "description": f'{src.get("region", "")}地区佛教数字资源',
            },
        )


def downgrade() -> None:
    from sqlalchemy import text as sa_text
    conn = op.get_bind()
    codes = [s["code"] for s in SOURCES]
    for code in codes:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": code},
        )
