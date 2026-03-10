/**
 * 经典专题数据 — 按经论系列分类
 * 每个专题包含：主要经典、注疏论释、分类外部资源
 */

export interface CollectionText {
  title: string;
  cbeta_id?: string;
  author?: string;
  dynasty?: string;
  note?: string;
}

export interface CollectionLink {
  name: string;
  url: string;
  desc?: string;
}

export const RESOURCE_CATEGORIES = {
  reading: "在线阅读",
  translation: "翻译项目",
  manuscript: "写本善本",
  research: "学术研究",
  temple: "寺院道场",
} as const;

export type ResourceCategory = keyof typeof RESOURCE_CATEGORIES;

export interface CollectionResources {
  reading?: CollectionLink[];
  translation?: CollectionLink[];
  manuscript?: CollectionLink[];
  research?: CollectionLink[];
  temple?: CollectionLink[];
}

export interface Collection {
  id: string;
  name: string;
  tradition: string;
  description: string;
  mainTexts: CollectionText[];
  commentaries: CollectionText[];
  resources: CollectionResources;
}

const collections: Collection[] = [
  // ==================== 1. 华严经系列 ====================
  {
    id: "huayan",
    name: "华严经系列",
    tradition: "华严宗",
    description:
      "《大方广佛华严经》是大乘佛教最重要的经典之一，阐述法界缘起、事事无碍的圆融思想。历代有多种汉译本及大量注疏，华严宗五祖（杜顺、智俨、法藏、澄观、宗密）均留下丰富著作。",
    mainTexts: [
      { title: "大方广佛华严经（六十卷）", cbeta_id: "T0278", author: "佛驮跋陀罗", dynasty: "东晋", note: "旧译/晋译本" },
      { title: "大方广佛华严经（八十卷）", cbeta_id: "T0279", author: "实叉难陀", dynasty: "唐", note: "新译/唐译本，最通行的版本" },
      { title: "大方广佛华严经（四十卷·入不思议解脱境界普贤行愿品）", cbeta_id: "T0293", author: "般若", dynasty: "唐", note: "又称《四十华严》" },
      { title: "渐备一切智德经", cbeta_id: "T0285", author: "竺法护", dynasty: "西晋", note: "十地品早期重要别译" },
      { title: "十住经", cbeta_id: "T0286", author: "鸠摩罗什", dynasty: "姚秦", note: "十地品别译" },
      { title: "佛说十地经", cbeta_id: "T0287", author: "尸罗达摩", dynasty: "唐", note: "十地品，梵文 Daśabhūmika 直译" },
      { title: "佛说兜沙经", cbeta_id: "T0280", author: "支娄迦谶", dynasty: "后汉", note: "华严经最早单品别译" },
      { title: "佛说如来兴显经", cbeta_id: "T0291", author: "竺法护", dynasty: "西晋", note: "如来出现品别译" },
    ],
    commentaries: [
      { title: "华严五教止观", cbeta_id: "T1867", author: "杜顺", dynasty: "隋", note: "华严宗开山之作，初祖杜顺" },
      { title: "华严经搜玄分齐通智方轨（搜玄记）", cbeta_id: "T1732", author: "智俨", dynasty: "唐", note: "华严经最早疏释，二祖智俨" },
      { title: "华严一乘十玄门", cbeta_id: "T1868", author: "智俨", dynasty: "唐", note: "华严十玄门核心教义" },
      { title: "华严经内章门等杂孔目章", cbeta_id: "T1870", author: "智俨", dynasty: "唐", note: "华严教义纲要" },
      { title: "华严经探玄记", cbeta_id: "T1733", author: "法藏", dynasty: "唐", note: "三祖法藏代表作" },
      { title: "华严一乘教义分齐章", cbeta_id: "T1866", author: "法藏", dynasty: "唐", note: "又称《华严五教章》，判教核心" },
      { title: "华严经旨归", cbeta_id: "T1871", author: "法藏", dynasty: "唐", note: "华严经总纲" },
      { title: "修华严奥旨妄尽还源观", cbeta_id: "T1876", author: "法藏", dynasty: "唐", note: "修行观法核心著作" },
      { title: "华严经义海百门", cbeta_id: "T1875", author: "法藏", dynasty: "唐" },
      { title: "华严金师子章", cbeta_id: "T1880", author: "法藏", dynasty: "唐" },
      { title: "华严经疏", cbeta_id: "T1735", author: "澄观", dynasty: "唐", note: "四祖澄观所撰" },
      { title: "华严经随疏演义钞", cbeta_id: "T1736", author: "澄观", dynasty: "唐" },
      { title: "华严法界玄镜", cbeta_id: "T1883", author: "澄观", dynasty: "唐", note: "法界观门注释" },
      { title: "注华严法界观门", cbeta_id: "T1884", author: "宗密注杜顺原作", dynasty: "唐", note: "法界三观" },
      { title: "原人论", cbeta_id: "T1886", author: "宗密", dynasty: "唐", note: "五祖宗密代表作，判摄儒释道" },
      { title: "新华严经论", cbeta_id: "T1739", author: "李通玄", dynasty: "唐", note: "居士解华严的巨著，40卷" },
      { title: "十地经论", cbeta_id: "T1522", author: "世亲造，菩提流支译", dynasty: "元魏", note: "世亲注十地经，地论宗根本" },
    ],
    resources: {
      reading: [
        { name: "CBETA 华严部", url: "https://cbetaonline.dila.edu.tw/zh/T0279", desc: "大正藏华严经全文，支持全文检索" },
        { name: "SAT 大正藏数据库", url: "https://21dzk.l.u-tokyo.ac.jp/SAT/", desc: "东京大学，含原版影像对照" },
        { name: "NTI Reader", url: "https://ntireader.org/taisho/t0279.html", desc: "中英佛典阅读器，即时词汇查询" },
        { name: "CText 中国哲学书电子化", url: "https://ctext.org/datawiki.pl?if=en&res=725377", desc: "华严经全文与影像" },
        { name: "Deerpark 佛经阅读器", url: "https://deerpark.app/", desc: "优雅排版，支持 PDF 下载" },
      ],
      translation: [
        { name: "84000 入法界品英译", url: "https://84000.co/translation/toh44-45", desc: "The Stem Array (Gandavyuha)，藏译英" },
        { name: "Kalavinka Press 完整英译", url: "http://kalavinka.org/", desc: "Bhikshu Dharmamitra 英译全三卷，目前唯一完整英译" },
        { name: "DRBA 华严英译项目", url: "https://www.buddhisttexts.org/pages/the-avatamsaka-sutra-english-translation-project", desc: "法界佛教总会华严经英译" },
        { name: "DSBC 梵文佛典", url: "https://www.dsbcproject.org/", desc: "入法界品、十地经等梵文残存部分" },
        { name: "BDK 英译大藏经", url: "https://www.bdkamerica.org/the-translation-project/", desc: "Numata 基金会英译项目" },
      ],
      manuscript: [
        { name: "京都国立博物馆 金字写本", url: "https://knmdb.kyohaku.go.jp/eng/2922.html", desc: "华严经金字写本高清数字影像" },
        { name: "大都会博物馆 入法界品贝叶", url: "https://www.metmuseum.org/art/collection/search/856355", desc: "尼泊尔 Gandavyuha 贝叶残页" },
        { name: "克利夫兰美术馆 高丽金字写本", url: "https://www.clevelandart.org/art/1994.25", desc: "高丽时代华严经金字写本" },
        { name: "IDP 国际敦煌项目", url: "https://idp.bl.uk/", desc: "敦煌华严经写卷数字影像" },
        { name: "曼彻斯特大学 华严经写卷", url: "https://www.digitalcollections.manchester.ac.uk/view/PR-CHCR-00459", desc: "馆藏华严经写卷数字影像" },
      ],
      research: [
        { name: "华严专宗学院", url: "https://www.huayencollege.org/", desc: "台湾，专门研究华严宗的佛学院" },
        { name: "华严学术论文库 (Indra)", url: "https://indra.huayen.org.tw/", desc: "华严研究所论文电子全文" },
        { name: "斯坦福哲学百科 · 华严佛学", url: "https://plato.stanford.edu/entries/buddhism-huayan/", desc: "华严思想权威学术条目" },
        { name: "BuddhaNexus 跨语种对照", url: "https://buddhanexus2.kc-tbts.uni-hamburg.de/db/skt", desc: "汉堡大学，AI 驱动跨语种佛典文本比对" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "大量华严研究论文全文" },
      ],
      temple: [
        { name: "东大寺（华严宗总本山）", url: "https://www.todaiji.or.jp/en/", desc: "日本奈良，毗卢遮那大佛，世界遗产" },
        { name: "大华严寺", url: "https://www.huayenworld.org/", desc: "台湾，华严宗道场" },
        { name: "万佛圣城 华严讲堂", url: "https://www.cttbusa.org/avatamsaka/avatamsaka_contents.asp.html", desc: "美国，宣化上人华严经讲解全文" },
      ],
    },
  },

  // ==================== 2. 般若经系列 ====================
  {
    id: "prajna",
    name: "般若经系列",
    tradition: "般若/中观",
    description:
      "般若经类是大乘佛教最早期的经典群，以「空」为核心思想。包括《大般若经》《心经》《金刚经》等，以及龙树菩萨的《大智度论》《中论》《十二门论》等重要注释，是三论宗的根本经论。",
    mainTexts: [
      { title: "大般若波罗蜜多经（六百卷）", cbeta_id: "T0220", author: "玄奘", dynasty: "唐", note: "般若经总集，玄奘法师翻译的最大部头经典" },
      { title: "摩诃般若波罗蜜经", cbeta_id: "T0223", author: "鸠摩罗什", dynasty: "姚秦", note: "又称《大品般若》" },
      { title: "小品般若波罗蜜经", cbeta_id: "T0227", author: "鸠摩罗什", dynasty: "姚秦" },
      { title: "道行般若经", cbeta_id: "T0224", author: "支娄迦谶", dynasty: "后汉", note: "中国般若学之始，最早的般若汉译" },
      { title: "放光般若经", cbeta_id: "T0221", author: "无罗叉", dynasty: "西晋", note: "二万五千颂般若重要译本" },
      { title: "光赞经", cbeta_id: "T0222", author: "竺法护", dynasty: "西晋", note: "二万五千颂般若异译" },
      { title: "金刚般若波罗蜜经", cbeta_id: "T0235", author: "鸠摩罗什", dynasty: "姚秦", note: "最流行的般若经典之一" },
      { title: "般若波罗蜜多心经", cbeta_id: "T0251", author: "玄奘", dynasty: "唐", note: "最短最精要的般若经" },
      { title: "文殊师利所说摩诃般若波罗蜜经", cbeta_id: "T0232", author: "曼陀罗仙", dynasty: "梁", note: "重要别部般若" },
      { title: "佛说仁王般若波罗蜜经", cbeta_id: "T0245", author: "鸠摩罗什", dynasty: "姚秦", note: "护国般若" },
    ],
    commentaries: [
      { title: "大智度论", cbeta_id: "T1509", author: "龙树菩萨造，鸠摩罗什译", dynasty: "姚秦", note: "般若经最重要的释论，百卷巨著" },
      { title: "中论", cbeta_id: "T1564", author: "龙树菩萨造，鸠摩罗什译", dynasty: "姚秦", note: "中观学派根本论典，三论之一" },
      { title: "十二门论", cbeta_id: "T1568", author: "龙树", dynasty: "姚秦", note: "三论宗三论之一" },
      { title: "百论", cbeta_id: "T1569", author: "提婆造，鸠摩罗什译", dynasty: "姚秦", note: "三论宗三论之一" },
      { title: "广百论本", cbeta_id: "T1570", author: "圣天造，玄奘译", dynasty: "唐", note: "百论扩充版" },
      { title: "大乘掌珍论", cbeta_id: "T1578", author: "清辩造，玄奘译", dynasty: "唐", note: "中观自续派代表论著" },
      { title: "回诤论", cbeta_id: "T1631", author: "龙树造，毗目智仙译", dynasty: "元魏", note: "龙树反驳空义质疑" },
      { title: "十住毗婆沙论", cbeta_id: "T1521", author: "龙树造，鸠摩罗什译", dynasty: "姚秦", note: "含「易行品」，净土宗亦重视" },
      { title: "般若波罗蜜多心经幽赞", cbeta_id: "T1710", author: "窥基", dynasty: "唐", note: "最重要的心经注疏之一" },
      { title: "般若心经略疏", cbeta_id: "T1712", author: "法藏", dynasty: "唐", note: "华严宗三祖注心经" },
      { title: "金刚般若经疏", cbeta_id: "T1698", author: "智顗", dynasty: "隋", note: "天台宗祖师注金刚经" },
      { title: "金刚般若疏", cbeta_id: "T1699", author: "吉藏", dynasty: "隋", note: "三论宗祖师注金刚经" },
      { title: "金刚经纂要刊定记", cbeta_id: "T1702", author: "宗密", dynasty: "唐" },
    ],
    resources: {
      reading: [
        { name: "CBETA 般若部", url: "https://cbetaonline.dila.edu.tw/zh/T0220", desc: "大般若经全文" },
        { name: "CBETA 大智度论", url: "https://cbetaonline.dila.edu.tw/zh/T1509", desc: "大智度论全 100 卷" },
        { name: "SAT 大正藏数据库", url: "https://21dzk.l.u-tokyo.ac.jp/SAT/", desc: "东京大学，含大正藏原版影像" },
        { name: "Deerpark 佛经阅读器", url: "https://deerpark.app/reader/T1509/1", desc: "优雅阅读界面，支持 PDF 下载" },
        { name: "WisdomLib 大智度论英译全文", url: "https://www.wisdomlib.org/buddhism/book/maha-prajnaparamita-sastra", desc: "Lamotte 法译转英译，免费在线" },
      ],
      translation: [
        { name: "Lamotte 法译本（Internet Archive）", url: "https://archive.org/details/EtienneLamotteLeTraiteDeLaGrandeVertuDeSagesseDeNagarjunaVol.I1944", desc: "比利时鲁汶大学，法文经典译本，免费 PDF" },
        { name: "84000 般若经英译", url: "https://84000.co/canon-sections/perfection-of-wisdom", desc: "般若部藏译英全部索引" },
        { name: "Kalavinka 大智度论选译", url: "https://www.kalavinka.org/", desc: "六度品英译 + 130 则故事选译" },
        { name: "Lotsawa House 龙树著作英译", url: "https://www.lotsawahouse.org/indian-masters/nagarjuna/", desc: "龙树菩萨著作藏译英，免费下载" },
        { name: "BDK 英译大藏经", url: "https://www.bdkamerica.org/the-translation-project/", desc: "Numata 基金会英译项目" },
      ],
      manuscript: [
        { name: "京都大学 石山寺本大智度论", url: "https://rmda.kulib.kyoto-u.ac.jp/en/item/rb00012918/explanation/manabinosekai", desc: "100 卷存 41 卷，高清 IIIF 影像" },
        { name: "故宫博物院 大智度论写本", url: "https://www.dpm.org.cn/", desc: "中唐楷书，首尾完整" },
        { name: "IDP 国际敦煌项目", url: "https://idp.bl.uk/", desc: "敦煌般若经/大智度论残卷影像" },
        { name: "剑桥大学 八千颂般若梵文写本", url: "https://cudl.lib.cam.ac.uk/view/MS-ADD-01643/1", desc: "Prajnaparamita 梵文贝叶写本数字化" },
        { name: "V&A 般若经彩绘写本", url: "https://collections.vam.ac.uk/item/O18839/", desc: "Astasahasrika Prajnaparamita 彩绘贝叶" },
      ],
      research: [
        { name: "印顺法师佛学著作集", url: "https://yinshun-edu.org.tw/Master_yinshun/books", desc: "大量大智度论研究，全文在线" },
        { name: "鲁汶大学 (UCLouvain)", url: "https://www.uclouvain.be/en", desc: "Lamotte 母校，东方学研究所" },
        { name: "BuddhaNexus 文本比对", url: "https://buddhanexus2.kc-tbts.uni-hamburg.de/", desc: "AI 驱动跨语种佛典平行对照" },
        { name: "JIABS 国际佛学研究期刊", url: "https://poj.peeters-leuven.be/content.php?url=journal&journal_code=JIABS", desc: "般若/中观研究权威期刊" },
        { name: "CBC@ 佛典归属数据库", url: "https://dazangthings.nz/cbc/", desc: "T1509 大智度论作者归属专条" },
      ],
      temple: [
        { name: "龙树菩萨研究所", url: "https://www.nagarjunainstitute.com/", desc: "尼泊尔加德满都，梵文佛典研究" },
        { name: "法鼓文理学院 (DILA)", url: "https://www.dila.edu.tw/", desc: "台湾，CBETA 核心支持机构" },
        { name: "Maitripa College 中观专题", url: "https://maitripa.org/library/subject-guides/madhyamaka/", desc: "美国波特兰，中观学资源指南" },
      ],
    },
  },

  // ==================== 3. 法华经系列 ====================
  {
    id: "lotus",
    name: "法华经系列",
    tradition: "天台宗",
    description:
      "《妙法莲华经》被誉为「经中之王」，提出「开权显实」「会三归一」的思想，是天台宗的根本经典。天台三大部（玄义、文句、止观）以法华经义理为基础构建了完整的教观体系。",
    mainTexts: [
      { title: "妙法莲华经", cbeta_id: "T0262", author: "鸠摩罗什", dynasty: "姚秦", note: "最通行的译本" },
      { title: "正法华经", cbeta_id: "T0263", author: "竺法护", dynasty: "西晋", note: "最早的汉译本" },
      { title: "添品妙法莲华经", cbeta_id: "T0264", author: "阇那崛多、达摩笈多", dynasty: "隋" },
    ],
    commentaries: [
      { title: "妙法莲华经玄义", cbeta_id: "T1716", author: "智顗说，灌顶记", dynasty: "隋", note: "天台三大部之一，十重玄义" },
      { title: "妙法莲华经文句", cbeta_id: "T1718", author: "智顗说，灌顶记", dynasty: "隋", note: "天台三大部之一，逐句解释" },
      { title: "摩诃止观", cbeta_id: "T1911", author: "智顗说，灌顶记", dynasty: "隋", note: "天台三大部之一，止观修行体系" },
      { title: "法华玄义释签", cbeta_id: "T1717", author: "湛然", dynasty: "唐", note: "天台中兴祖师疏记" },
      { title: "法华文句记", cbeta_id: "T1719", author: "湛然", dynasty: "唐" },
      { title: "止观辅行传弘决", cbeta_id: "T1912", author: "湛然", dynasty: "唐", note: "摩诃止观疏记" },
      { title: "法华义疏", cbeta_id: "T1721", author: "吉藏", dynasty: "隋", note: "三论宗立场的法华注疏，12卷" },
      { title: "法华玄论", cbeta_id: "T1720", author: "吉藏", dynasty: "隋", note: "三论宗法华宗旨概论" },
      { title: "妙法莲华经玄赞", cbeta_id: "T1723", author: "窥基", dynasty: "唐", note: "唯识宗角度的法华注疏" },
      { title: "观音玄义", cbeta_id: "T1726", author: "智顗", dynasty: "隋", note: "释普门品玄义" },
      { title: "观音义疏", cbeta_id: "T1728", author: "智顗", dynasty: "隋", note: "释普门品经文" },
    ],
    resources: {
      reading: [
        { name: "CBETA 法华部", url: "https://cbetaonline.dila.edu.tw/zh/T0262", desc: "法华经全文在线阅读" },
        { name: "SAT 大正藏", url: "https://21dzk.l.u-tokyo.ac.jp/SAT/", desc: "东京大学大正藏数据库" },
        { name: "Deerpark 佛经阅读器", url: "https://deerpark.app/", desc: "优雅排版，支持PDF下载" },
        { name: "维基文库 妙法莲华经", url: "https://zh.wikisource.org/zh-hans/妙法蓮華經", desc: "公有领域全文" },
      ],
      translation: [
        { name: "84000 妙法莲华经", url: "https://84000.co/translation/toh113", desc: "The White Lotus of the Good Dharma，藏译英" },
        { name: "BDK 法华经英译 PDF", url: "https://www.bdk.or.jp/document/dgtl-dl/dBET_T0262_LotusSutra_2007.pdf", desc: "Kubo & Yuyama 英译，免费 PDF" },
        { name: "BTTS 法华经中英版", url: "https://www.buddhisttexts.org/products/the-wonderful-dharma-lotus-sutra", desc: "宣化上人讲解中英双语" },
        { name: "Nichiren Buddhism Library", url: "https://www.nichirenlibrary.org/en/lsoc/toc", desc: "Burton Watson 英译全文在线" },
        { name: "DSBC 梵文法华经", url: "https://www.dsbcproject.org/", desc: "法华经梵文校本 (Vaidya 版)" },
      ],
      manuscript: [
        { name: "IDP 法华经写本数字化项目", url: "https://idp.bl.uk/blog/the-lotus-sutra-project/", desc: "793件敦煌法华经写本，5-11世纪" },
        { name: "数字敦煌", url: "https://www.e-dunhuang.com/", desc: "法华经变壁画全景漫游" },
        { name: "吉尔吉特写本 (UNESCO)", url: "https://en.unesco.org/memoryoftheworld/registry/303", desc: "5-6世纪梵文法华经，现存最古" },
        { name: "书格 宋刊妙法莲华经", url: "https://www.shuge.org/view/miao_fa_lian_hua_jing/", desc: "宋刊经折装本高清 PDF" },
      ],
      research: [
        { name: "东洋哲学研究所 (IOP)", url: "https://www.totetu.org/en/", desc: "每年举办国际法华经学术研讨会" },
        { name: "WisdomLib 法华经梵文", url: "https://www.wisdomlib.org/buddhism/book/lotus-sutra-sanskrit", desc: "Kern 英译本及梵文原文" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "法华经研究论文全文" },
      ],
      temple: [
        { name: "日本天台宗（延历寺）", url: "https://www.tendai.or.jp/", desc: "比叡山，天台宗总本山" },
        { name: "立正佼成会", url: "https://rk-world.org/lotus-sutra/", desc: "全球 300+ 道场，法华经修行" },
        { name: "500 Yojanas", url: "https://www.500yojanas.org/", desc: "法华经 28 品全文在线，修行指南" },
      ],
    },
  },

  // ==================== 4. 楞严经系列 ====================
  {
    id: "shurangama",
    name: "楞严经系列",
    tradition: "禅宗/教下通用",
    description:
      "《楞严经》全称《大佛顶如来密因修证了义诸菩萨万行首楞严经》，涵盖禅修、破魔、二十五圆通等。历代注疏极为丰富，明代一朝即达六十余种，是汉传佛教中注疏最多的经典之一。",
    mainTexts: [
      { title: "大佛顶如来密因修证了义诸菩萨万行首楞严经", cbeta_id: "T0945", author: "般剌蜜帝", dynasty: "唐", note: "唯一汉译本，10卷" },
    ],
    commentaries: [
      { title: "首楞严义疏注经", cbeta_id: "T1799", author: "子璇（长水）", dynasty: "宋", note: "20卷，讲楞严三十余遍，赐号「楞严大师」" },
      { title: "楞严经正脉疏", cbeta_id: "X0275", author: "交光真鉴", dynasty: "明", note: "干支标科法分析经文，明代最重要注疏" },
      { title: "楞严经通议", cbeta_id: "X0276", author: "憨山德清", dynasty: "明", note: "四大高僧之一，以一心三观贯穿全经" },
      { title: "楞严经玄义", cbeta_id: "X0278", author: "蕅益智旭", dynasty: "明", note: "仿天台体例，玄义 2 卷" },
      { title: "楞严经文句", cbeta_id: "X0279", author: "蕅益智旭", dynasty: "明", note: "仿天台体例，文句 10 卷" },
      { title: "楞严经宝镜疏", cbeta_id: "X0283", author: "溥畹", dynasty: "清", note: "集前人注疏之大成" },
      { title: "楞严经义疏", cbeta_id: "X0268", author: "子璿", dynasty: "宋" },
    ],
    resources: {
      reading: [
        { name: "CBETA 楞严经", url: "https://cbetaonline.dila.edu.tw/zh/T0945", desc: "楞严经全文在线阅读" },
        { name: "WisdomLib 楞严经英文讲解", url: "https://www.wisdomlib.org/buddhism/book/shurangama-sutra-with-commentary", desc: "宣化上人讲解英文全文" },
        { name: "CText 楞严经", url: "https://ctext.org/datawiki.pl?if=en&res=453706", desc: "原文在线，支持繁简切换" },
        { name: "BuddhaNet 楞严经 PDF", url: "https://www.buddhanet.net/pdf_file/surangama.pdf", desc: "陆宽昱经典英译本 PDF" },
      ],
      translation: [
        { name: "BTTS 楞严经新译", url: "https://www.buddhisttexts.org/", desc: "David Rounds 新英译，含宣化上人注释" },
        { name: "万佛圣城 楞严讲解", url: "https://www.cttbusa.org/shurangama1/shurangama_contents.asp.html", desc: "宣化上人楞严经 10 卷讲解全文" },
        { name: "Internet Archive 楞严经", url: "https://archive.org/details/ShurangamaSutra_201407", desc: "陆宽昱译本免费下载" },
      ],
      manuscript: [
        { name: "CBETA 楞严经校勘", url: "https://www.cbeta.org/cn/node/5238", desc: "十三部藏经楞严经文异同对比" },
        { name: "书格 古籍善本", url: "https://www.shuge.org/", desc: "楞严经宋元明刻本影像" },
      ],
      research: [
        { name: "DRBU 楞严经学术资源", url: "https://repstein.faculty.drbu.edu/Buddhism/Shurangama/Shurangama.htm", desc: "Ron Epstein 编辑，含注疏列表、真伪考证" },
        { name: "楞严经真伪考辨", url: "https://repstein.faculty.drbu.edu/Buddhism/authenticity.htm", desc: "系统回应伪经说，百条论证" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "楞严经研究论文" },
      ],
      temple: [
        { name: "万佛圣城", url: "https://www.cttbusa.org/", desc: "美国，每日早课诵楞严咒" },
        { name: "杭州灵隐寺", url: "https://www.lingyinsi.com/", desc: "定期开讲楞严经法义" },
      ],
    },
  },

  // ==================== 5. 净土经系列 ====================
  {
    id: "pureland",
    name: "净土经系列",
    tradition: "净土宗",
    description:
      "净土三经（《无量寿经》《观无量寿佛经》《阿弥陀经》）加上《往生论》，构成净土宗核心经典。善导、昙鸾、道绰三位祖师的著作奠定了净土宗的教义基础，莲池、蕅益、印光三位大师则在明清时期将净土思想推向新高峰。",
    mainTexts: [
      { title: "佛说无量寿经", cbeta_id: "T0360", author: "康僧铠", dynasty: "曹魏", note: "净土三经之一，又称《大经》" },
      { title: "佛说观无量寿佛经", cbeta_id: "T0365", author: "畺良耶舍", dynasty: "刘宋", note: "净土三经之一" },
      { title: "佛说阿弥陀经", cbeta_id: "T0366", author: "鸠摩罗什", dynasty: "姚秦", note: "净土三经之一，又称《小经》" },
      { title: "无量寿经优波提舍愿生偈", cbeta_id: "T1524", author: "天亲菩萨造，菩提流支译", dynasty: "北魏", note: "又称《往生论》" },
    ],
    commentaries: [
      { title: "观无量寿佛经疏（观经四帖疏）", cbeta_id: "T1753", author: "善导", dynasty: "唐", note: "净土宗开宗判教之典籍" },
      { title: "观念法门", cbeta_id: "T1959", author: "善导", dynasty: "唐", note: "观佛念佛实修指南" },
      { title: "法事赞", cbeta_id: "T1979", author: "善导", dynasty: "唐", note: "净土法会赞偈仪轨" },
      { title: "往生礼赞", cbeta_id: "T1980", author: "善导", dynasty: "唐", note: "日课礼拜赞偈" },
      { title: "般舟赞", cbeta_id: "T1981", author: "善导", dynasty: "唐", note: "般舟三昧念佛赞偈" },
      { title: "往生论注", cbeta_id: "T1819", author: "昙鸾", dynasty: "北魏", note: "注释世亲《往生论》，他力信仰理论基石" },
      { title: "安乐集", cbeta_id: "T1958", author: "道绰", dynasty: "唐", note: "建立圣道门/净土门二门判教" },
      { title: "无量寿经义疏", cbeta_id: "T1745", author: "慧远", dynasty: "隋" },
      { title: "阿弥陀经疏钞", cbeta_id: "X0424", author: "莲池", dynasty: "明", note: "莲池大师，融合天台华严" },
      { title: "阿弥陀经要解", cbeta_id: "T1762", author: "智旭", dynasty: "明", note: "蕅益大师，印光赞为「最精最妙」" },
    ],
    resources: {
      reading: [
        { name: "CBETA 净土部", url: "https://cbetaonline.dila.edu.tw/zh/T0360", desc: "净土三经及全部注疏" },
        { name: "SAT 大正藏", url: "https://21dzk.l.u-tokyo.ac.jp/SAT/", desc: "东京大学大正藏数据库" },
        { name: "Deerpark 佛经阅读器", url: "https://deerpark.app/", desc: "优雅阅读界面" },
      ],
      translation: [
        { name: "BDK 三净土经英译", url: "https://www.bdk.or.jp/document/dgtl-dl/dBET_ThreePureLandSutras_2003.pdf", desc: "稻垣久雄英译，免费 PDF" },
        { name: "84000 无量寿经", url: "https://84000.co/translation/toh115", desc: "藏文 Sukhavativyuha 首个英译" },
        { name: "Shingan's Portal 净土祖师英译", url: "https://sites.google.com/view/shingans-portal/pure-land-text-translations", desc: "善导等净土祖师著作英译" },
        { name: "佛光山国际翻译中心", url: "https://www.fgsitc.org/", desc: "阿弥陀经英文著作" },
      ],
      manuscript: [
        { name: "IDP 国际敦煌项目", url: "https://idp.bl.uk/", desc: "敦煌净土经写本数字化" },
        { name: "剑桥大学 梵文无量寿经写本", url: "https://cudl.lib.cam.ac.uk/view/MS-ADD-01368", desc: "尼泊尔 Sukhavativyuha 写本" },
        { name: "数字敦煌", url: "https://www.e-dunhuang.com/", desc: "净土变相壁画全景" },
      ],
      research: [
        { name: "浄土宗総合研究所", url: "https://jsri.jodo.or.jp/", desc: "日本净土宗官方学术机构" },
        { name: "浄土真宗聖典検索", url: "https://j-soken.jp/", desc: "净土真宗全部圣典电子化" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "善导、昙鸾、道绰研究论文" },
      ],
      temple: [
        { name: "知恩院（浄土宗総本山）", url: "https://www.chion-in.or.jp/en/", desc: "日本京都，法然上人创净土宗之地" },
        { name: "西本願寺", url: "https://www.hongwanji.or.jp/", desc: "日本京都，净土真宗本山" },
        { name: "净土宗文教基金会", url: "https://www.plb.tw/", desc: "台湾净土宗资源" },
        { name: "PLB 全球净土道场", url: "https://www.plb-sea.org/world", desc: "全球净土宗道场网络" },
      ],
    },
  },

  // ==================== 6. 唯识系列 ====================
  {
    id: "yogacara",
    name: "唯识系列",
    tradition: "唯识宗",
    description:
      "唯识学以「万法唯识」为核心，由弥勒、无著、世亲创立，玄奘法师在中国大力弘扬，窥基继承发展。核心论典包括「一本十支」体系，以《瑜伽师地论》为本，十部支论阐发其义。",
    mainTexts: [
      { title: "解深密经", cbeta_id: "T0676", author: "玄奘", dynasty: "唐", note: "唯识学的根本经典，三时判教" },
      { title: "瑜伽师地论", cbeta_id: "T1579", author: "弥勒菩萨说，玄奘译", dynasty: "唐", note: "唯识学最重要的论典，百卷巨著" },
      { title: "成唯识论", cbeta_id: "T1585", author: "护法等菩萨造，玄奘译", dynasty: "唐", note: "糅合十大论师注释，法相宗根本论" },
      { title: "摄大乘论", cbeta_id: "T1593", author: "无著菩萨造，玄奘译", dynasty: "唐", note: "阿赖耶识缘起纲要" },
      { title: "唯识三十论颂", cbeta_id: "T1586", author: "世亲菩萨造，玄奘译", dynasty: "唐", note: "唯识学最精练纲要" },
      { title: "唯识二十论", cbeta_id: "T1590", author: "世亲菩萨造，玄奘译", dynasty: "唐", note: "破外境实有论" },
      { title: "大乘百法明门论", cbeta_id: "T1614", author: "世亲造，玄奘译", dynasty: "唐", note: "唯识入门基础，五位百法" },
      { title: "辨中边论", cbeta_id: "T1600", author: "弥勒造，玄奘译", dynasty: "唐", note: "辨中道与边见，三性说经典表述" },
      { title: "大乘庄严经论", cbeta_id: "T1604", author: "无著造，波罗颇蜜多罗译", dynasty: "唐", note: "大乘修行阶位" },
      { title: "大乘阿毘达磨集论", cbeta_id: "T1605", author: "无著造，玄奘译", dynasty: "唐", note: "大乘阿毗达磨体系" },
    ],
    commentaries: [
      { title: "成唯识论述记", cbeta_id: "T1830", author: "窥基", dynasty: "唐", note: "窥基最权威注释，20卷" },
      { title: "瑜伽师地论略纂", cbeta_id: "T1829", author: "窥基", dynasty: "唐", note: "瑜伽论前66卷注释" },
      { title: "瑜伽论记", cbeta_id: "T1828", author: "遁伦", dynasty: "唐", note: "集录玄奘弟子众家注说" },
      { title: "摄大乘论释", cbeta_id: "T1597", author: "世亲菩萨造，玄奘译", dynasty: "唐" },
      { title: "唯识三十论直解", cbeta_id: "X0818", author: "智旭", dynasty: "明", note: "蕅益大师以天台融通唯识" },
    ],
    resources: {
      reading: [
        { name: "CBETA 瑜伽部", url: "https://cbetaonline.dila.edu.tw/zh/T1579", desc: "瑜伽师地论全文" },
        { name: "CBETA 成唯识论", url: "https://cbetaonline.dila.edu.tw/zh/T1585", desc: "成唯识论全文" },
        { name: "A.C. Muller 唯识学资源", url: "http://www.acmuller.net/yogacara/thinkers/xuanzang-works.html", desc: "玄奘译著完整列表与 DDB 术语" },
        { name: "CText 成唯识论", url: "https://ctext.org/wiki.pl?if=en&res=255278", desc: "全文在线，逐段阅读" },
      ],
      translation: [
        { name: "BDK 唯识三论英译", url: "https://www.bdkamerica.org/product/three-texts-on-consciousness-only/", desc: "唯识二十论/三十颂/成唯识论英译" },
        { name: "84000 解深密经英译", url: "https://84000.co/translation/toh106", desc: "Samdhinirmocana 藏译英" },
        { name: "Tsadra 唯识资源", url: "https://buddhanature.tsadra.org/index.php/Key_Terms/Yogācāra", desc: "唯识核心术语与文本" },
        { name: "斯坦福哲学百科 Yogacara", url: "https://plato.stanford.edu/entries/yogacara/", desc: "学术级唯识哲学导论" },
      ],
      manuscript: [
        { name: "DSBC 梵文佛典", url: "https://www.dsbcproject.org/", desc: "唯识系梵文原典数字化" },
        { name: "GRETIL 梵文文本库", url: "https://gretil.sub.uni-goettingen.de/", desc: "唯识论典梵文电子文本" },
        { name: "剑桥大学 菩萨地写本", url: "https://cudl.lib.cam.ac.uk/view/MS-ADD-01702/1", desc: "Bodhisattvabhumi 梵文贝叶写本" },
        { name: "BDRC 藏文文献", url: "https://library.bdrc.io/", desc: "唯识学藏文传本" },
      ],
      research: [
        { name: "汉堡大学 Numata 佛教研究中心", url: "https://www.buddhismuskunde.uni-hamburg.de/en.html", desc: "瑜伽师地论英译工程" },
        { name: "杭州佛学院《唯识研究》", url: "https://www.hzfxy.net/", desc: "中国唯一唯识学专业期刊" },
        { name: "牛津佛教研究中心", url: "https://ocbs.org/", desc: "瑜伽行派与中观比较研究" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "唯识研究论文全文" },
      ],
      temple: [
        { name: "兴福寺（法相宗大本山）", url: "https://www.kohfukuji.com/", desc: "日本奈良，南都七大寺之一" },
        { name: "药师寺（法相宗大本山）", url: "https://yakushiji.or.jp/", desc: "日本奈良，设玄奘三蔵院" },
      ],
    },
  },

  // ==================== 7. 禅宗经典系列 ====================
  {
    id: "chan",
    name: "禅宗经典系列",
    tradition: "禅宗",
    description:
      "禅宗虽然强调「不立文字」，但历代留下了丰富的灯录、语录和公案集。这些典籍记载了禅宗的传承和修行方法，从初祖达摩到唐宋五家七宗的开展，形成了独特的禅宗文献体系。",
    mainTexts: [
      { title: "六祖大师法宝坛经", cbeta_id: "T2008", author: "惠能", dynasty: "唐", note: "禅宗最核心的典籍，唯一被称为「经」的祖师著作" },
      { title: "碧岩录", cbeta_id: "T2003", author: "圆悟克勤", dynasty: "宋", note: "禅门第一书，百则公案" },
      { title: "从容录", cbeta_id: "T2004", author: "万松行秀评唱", dynasty: "宋/金", note: "曹洞宗百则公案，与碧岩录并称「禅门双璧」" },
      { title: "无门关", cbeta_id: "T2005", author: "无门慧开", dynasty: "宋", note: "四十八则公案" },
      { title: "临济录", cbeta_id: "T1985", author: "慧然集", dynasty: "唐", note: "临济宗祖师义玄语录，「喝」法代表" },
      { title: "景德传灯录", cbeta_id: "T2076", author: "道原", dynasty: "宋", note: "禅宗第一部灯录，30卷录1701位祖师" },
      { title: "五灯会元", cbeta_id: "X1565", author: "普济", dynasty: "宋", note: "综合五部灯录" },
      { title: "黄檗传心法要", cbeta_id: "T2012A", author: "裴休集", dynasty: "唐", note: "黄檗希运禅师心法" },
    ],
    commentaries: [
      { title: "信心铭", cbeta_id: "T2010", author: "僧璨", dynasty: "隋", note: "禅宗三祖，「至道无难，唯嫌拣择」" },
      { title: "永嘉证道歌", cbeta_id: "T2014", author: "玄觉", dynasty: "唐", note: "六祖法嗣，禅宗最著名偈颂" },
      { title: "禅源诸诠集都序", cbeta_id: "T2015", author: "宗密", dynasty: "唐", note: "禅教一致的代表作" },
      { title: "敕修百丈清规", cbeta_id: "T2025", author: "德辉重编", dynasty: "元", note: "禅宗僧团制度根本典籍" },
      { title: "禅苑清规", cbeta_id: "X1245", author: "宗赜", dynasty: "宋", note: "现存最早的完整禅宗清规 (1103)" },
    ],
    resources: {
      reading: [
        { name: "CBETA 禅宗部", url: "https://cbetaonline.dila.edu.tw/zh/T2008", desc: "坛经及全部禅宗典籍原文" },
        { name: "Terebess Asia Online", url: "https://terebess.hu/zen/textindex.html", desc: "最全面的禅宗英译在线图书馆，73+ 部" },
        { name: "TheZenSite", url: "http://www.thezensite.com/MainPages/translation_sutras.html", desc: "免费禅宗翻译集合" },
        { name: "SAT 大正藏", url: "https://21dzk.l.u-tokyo.ac.jp/SAT/", desc: "东京大学大正藏数据库" },
      ],
      translation: [
        { name: "BDK 禅宗经典英译", url: "https://www.bdkamerica.org/", desc: "含黄檗传心法要、坛经等英译" },
        { name: "Zen Library 经典目录", url: "https://zenlibrary.org/comprehensive-canon-of-classical-zen-texts/", desc: "禅宗经典综合目录，标注英译可得性" },
        { name: "84000 禅宗文献", url: "https://84000.co/", desc: "部分禅宗经典藏译英" },
      ],
      manuscript: [
        { name: "DILA 敦煌禅宗写本", url: "http://dev.dila.edu.tw/Dunhuang_Manuscripts/", desc: "早期禅宗敦煌写本 TEI 数字化" },
        { name: "IDP 国际敦煌项目", url: "https://idp.bl.uk/", desc: "坛经敦煌本等大量禅宗写本" },
        { name: "书格 禅宗古籍", url: "https://www.shuge.org/", desc: "百丈清规、传灯录等善本影像" },
      ],
      research: [
        { name: "花园大学国际禅学研究所 (IRIZ)", url: "http://iriz.hanazono.ac.jp/", desc: "禅籍数据库、电子达磨系统" },
        { name: "禅文化研究所", url: "https://www.zenbunka.or.jp/", desc: "京都，60年历史，黑豆数据库" },
        { name: "临济宗黄檗宗联合官网", url: "https://zen.rinnou.net/", desc: "临济宗 14 派与黄檗宗" },
      ],
      temple: [
        { name: "柏林禅寺（赵州祖庭）", url: "https://www.bailinsi.net/", desc: "河北，设禅学研究所" },
        { name: "妙心寺", url: "https://www.myoshinji.or.jp/", desc: "日本最大临济宗禅寺" },
        { name: "San Francisco Zen Center", url: "https://www.sfzc.org/", desc: "美国最大禅修中心之一" },
        { name: "Zen Mountain Monastery", url: "https://zmm.org/", desc: "美国纽约，法话与禅修直播" },
      ],
    },
  },

  // ==================== 8. 律典系列 ====================
  {
    id: "vinaya",
    name: "律典系列",
    tradition: "律宗",
    description:
      "佛教戒律是僧团生活的根本规范。汉传佛教中有四部广律的完整翻译，道宣律师创立的南山律宗以「南山三大部」为核心。菩萨戒则以《梵网经》和《瑜伽菩萨戒》两大系统为主。",
    mainTexts: [
      { title: "四分律", cbeta_id: "T1428", author: "佛陀耶舍、竺佛念", dynasty: "姚秦", note: "法藏部律，汉传最通行" },
      { title: "摩诃僧祇律", cbeta_id: "T1425", author: "佛陀跋陀罗、法显", dynasty: "东晋", note: "大众部律，法显从印度带回" },
      { title: "十诵律", cbeta_id: "T1435", author: "弗若多罗、鸠摩罗什", dynasty: "姚秦", note: "说一切有部律" },
      { title: "五分律", cbeta_id: "T1421", author: "佛陀什、竺道生", dynasty: "刘宋", note: "化地部律" },
      { title: "根本说一切有部毗奈耶", cbeta_id: "T1442", author: "义净", dynasty: "唐", note: "50卷，义净从印度带回" },
      { title: "梵网经", cbeta_id: "T1484", author: "鸠摩罗什", dynasty: "姚秦", note: "十重四十八轻戒，东亚菩萨戒最通行本" },
      { title: "菩萨戒本（瑜伽菩萨戒）", cbeta_id: "T1501", author: "玄奘", dynasty: "唐", note: "出自瑜伽师地论·菩萨地" },
      { title: "优婆塞戒经", cbeta_id: "T1488", author: "昙无谶", dynasty: "北凉", note: "在家菩萨戒根本经典" },
    ],
    commentaries: [
      { title: "四分律删繁补阙行事钞", cbeta_id: "T1804", author: "道宣", dynasty: "唐", note: "南山三大部之一，指导僧团行事" },
      { title: "四分律含注戒本疏", cbeta_id: "T1805", author: "道宣", dynasty: "唐", note: "南山三大部之一，逐条解释250戒" },
      { title: "四分律删补随机羯磨疏", cbeta_id: "T1808", author: "道宣", dynasty: "唐", note: "南山三大部之一，僧团法律程序" },
      { title: "梵网经菩萨戒本疏", cbeta_id: "T1813", author: "法藏", dynasty: "唐" },
      { title: "善见律毗婆沙", cbeta_id: "T1462", author: "僧伽跋陀罗", dynasty: "南齐", note: "巴利律藏注释书汉译" },
    ],
    resources: {
      reading: [
        { name: "CBETA 律部", url: "https://cbetaonline.dila.edu.tw/zh/T1428", desc: "四分律及全部律典原文" },
        { name: "SuttaCentral 律藏", url: "https://suttacentral.net/vinaya-guide-brahmali", desc: "巴利律藏首个完整英译（六卷）" },
        { name: "DhammaTalks 佛教僧伽法典", url: "https://www.dhammatalks.org/vinaya/bmc/", desc: "Thanissaro Bhikkhu 逐条解释 227 条比丘戒" },
        { name: "Access to Insight 律藏", url: "https://www.accesstoinsight.org/tipitaka/vin/index.html", desc: "巴利律藏部分资料" },
      ],
      translation: [
        { name: "四分律英译项目", url: "https://dharmaguptakavinaya.wordpress.com/", desc: "Dharmaguptaka Vinaya 犍度部英译" },
        { name: "BDK 百丈清规英译", url: "https://www.bdkamerica.org/", desc: "含百丈清规等英译" },
        { name: "梵网经中英对照", url: "https://www.sutrasmantras.info/sutra32.html", desc: "菩萨心地戒品在线" },
        { name: "Pali Text Society 律藏", url: "https://palitextsociety.org/", desc: "I.B. Horner 经典英译六卷" },
      ],
      manuscript: [
        { name: "吉尔吉特写本 (UNESCO)", url: "https://en.unesco.org/memoryoftheworld/registry/303", desc: "5-6世纪，含有部律梵文原典" },
        { name: "IDP 国际敦煌项目", url: "https://idp.bl.uk/", desc: "敦煌律藏抄本、戒律文献写本" },
      ],
      research: [
        { name: "Open Buddhist University 律学", url: "https://buddhistuniversity.net/tags/vinaya-studies", desc: "免费在线律学课程与文献" },
        { name: "Sravasti Abbey 律学资源", url: "https://sravastiabbey.org/discover-monastic-life/living-in-vinaya/vinaya-resources/", desc: "比丘尼戒律研究中心" },
        { name: "台大佛学数位图书馆", url: "https://buddhism.lib.ntu.edu.tw/", desc: "南山律宗研究论文" },
      ],
      temple: [
        { name: "西园戒幢律寺", url: "https://www.jcedu.org/", desc: "苏州，律宗重要道场，设佛学研究所" },
        { name: "灵隐寺 律宗专题", url: "https://www.lingyinsi.com/", desc: "定期举办传戒法会" },
      ],
    },
  },
];

export default collections;
