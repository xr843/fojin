/**
 * 统一的外部数据源搜索 URL 构建器
 * 所有需要生成外部搜索链接的组件都应使用此文件
 */

/** 已验证可用的搜索 URL 模板 */
const SEARCH_PATTERNS: Record<string, (q: string) => string> = {
  // ===== 佛学数字项目 =====
  "cbeta-org": (q) => `https://cbetaonline.dila.edu.tw/zh/search?q=${q}`,
  "cbeta": (q) => `https://cbetaonline.dila.edu.tw/zh/search?q=${q}`,
  "cbeta-api": (q) => `https://cbetaonline.dila.edu.tw/zh/search?q=${q}`,
  "suttacentral-org": (q) => `https://suttacentral.net/search?query=${q}`,
  "suttacentral": (q) => `https://suttacentral.net/search?query=${q}`,
  "accesstoinsight": (q) => `https://www.accesstoinsight.org/search_results.html?q=${q}`,
  "tbrc-bdrc": (q) => `https://library.bdrc.io/search?q=${q}&lg=zh`,
  "bdrc": (q) => `https://library.bdrc.io/search?q=${q}&lg=zh`,
  "kanseki-repo": (q) => `https://www.kanripo.org/search?q=${q}`,
  "wisdom-lib": (q) => `https://www.wisdomlib.org/search?q=${q}`,
  "dharmapearls": (q) => `https://dharmapearls.net/?s=${q}`,
  "ddb": (q) => `http://www.buddhism-dict.net/cgi-bin/xpr-ddb.pl?q=${q}`,
  "sat-utokyo": (q) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?mode=search&keyword=${q}`,
  "sat": (q) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?mode=search&keyword=${q}`,
  "dila": (q) => `https://authority.dila.edu.tw/person/?keyword=${q}`,
  "dharma-drum": (q) => `https://authority.dila.edu.tw/person/?keyword=${q}`,
  "ctext": (q) => `https://ctext.org/searchbooks.pl?if=en&searchu=${q}`,
  "84000": (q) => `https://read.84000.co/search.html?search=${q}`,

  // ===== 巴利/上座部 =====
  "digital-pali-reader": (q) => `https://www.digitalpalireader.online/_pali/index.html?search=${q}`,
  "tipitaka-org": (q) => `https://tipitaka.org/romn/?search=${q}`,
  "dhammatalks": (q) => `https://www.dhammatalks.org/search.html?q=${q}`,
  "palikanon": (q) => `https://www.palikanon.com/suche/?q=${q}`,
  "dhammawiki": (q) => `https://dhammawiki.com/index.php?search=${q}`,
  "buddhanet": (q) => `https://www.buddhanet.net/search?q=${q}`,
  "pali-text-society": (q) => `https://www.palitext.com/?s=${q}`,
  "suttafriends": (q) => `https://agama.buddhason.org/search.php?str=${q}`,

  // ===== 藏传/藏文 =====
  "lotsawa-house": (q) => `https://www.lotsawahouse.org/search?query=${q}`,
  "buddhanexus": (q) => `https://dharmamitra.org/nexus?query=${q}`,
  "dharmanexus": (q) => `https://dharmamitra.org/nexus?query=${q}`,
  "treasury-of-lives": (q) => `https://treasuryoflives.org/search?search=${q}`,
  "rigpa-wiki": (q) => `https://www.rigpawiki.org/index.php?search=${q}`,
  "adarsha": (q) => `https://adarsha.dharma-treasure.org/search?query=${q}`,

  // ===== 梵文/印度学 =====
  // sarit: deactivated (502, project minimally maintained)
  "gretil": (q) => `http://gretil.sub.uni-goettingen.de/gretil.html#${q}`,
  "dsbc": (q) => `https://www.dsbcproject.org/canon-text/search?query=${q}`,

  // ===== 国家图书馆 =====
  "nlc": (q) => `http://read.nlc.cn/allSearch/searchList?searchType=1001&showType=1&keyword=${q}`,
  "ndl-japan": (q) => `https://dl.ndl.go.jp/search?keyword=${q}`,
  "loc-asian": (q) => `https://www.loc.gov/search/?q=${q}&fa=partof:asian+division`,
  "bl-buddhism": (q) => `https://www.bl.uk/search?q=${q}`,
  "bnf-buddhism": (q) => `https://gallica.bnf.fr/services/engine/search/sru?query=${q}`,
  "ncl-tw": (q) => `https://rbook.ncl.edu.tw/NCLSearch/Search/SearchDetail?q=${q}`,

  // ===== 大学图书馆 =====
  "harvard-yenching": (q) => `https://hollis.harvard.edu/primo-explore/search?query=any,contains,${q}&vid=HVD2`,
  "waseda-kotenseki": (q) => `https://www.wul.waseda.ac.jp/kotenseki/search.php?cndbn=${q}`,
  "kyoto-univ": (q) => `https://rmda.kulib.kyoto-u.ac.jp/search?q=${q}`,
  "snu-kyujanggak": (q) => `https://kyujanggak.snu.ac.kr/search?q=${q}`,
  "ntu-buddhism": (q) => `https://buddhism.lib.ntu.edu.tw/search?q=${q}`,
  "princeton-east-asian": (q) => `https://catalog.princeton.edu/catalog?q=${q}`,
  "stanford-buddhism": (q) => `https://searchworks.stanford.edu/catalog?q=${q}`,
  "columbia-starr": (q) => `https://clio.columbia.edu/catalog?q=${q}`,

  // ===== 韩国 =====
  "korean-tripitaka-db": (q) => `https://kb.sutra.re.kr/ritk/index.do?keyword=${q}`,
  "haeinsa": (q) => `https://kb.sutra.re.kr/ritk/index.do?keyword=${q}`,

  // ===== 日本佛学 =====
  "inbuds": (q) => `https://www.inbuds.net/search?q=${q}`,
  "iriz-hanazono": (q) => `https://iriz.hanazono.ac.jp/search?q=${q}`,
  "komazawa-univ": (q) => `https://repo.komazawa-u.ac.jp/search?q=${q}`,

  // ===== 中文学术 =====
  "cnki-buddhism": (q) => `https://kns.cnki.net/kns8s/search?classid=YSTT4HG0&kw=${q}`,
  "academia-sinica": (q) => `https://hanchi.ihp.sinica.edu.tw/ihpc/hanjiquery?keyword=${q}`,
  "fgs-digital": (q) => `https://www.fgs.org.tw/search?q=${q}`,

  // ===== 博物馆 =====
  "palace-museum": (q) => `https://www.dpm.org.cn/searchs.html?query=${q}`,
  "nara-museum": (q) => `https://www.narahaku.go.jp/english/collection/search.php?q=${q}`,
  "tnm-japan": (q) => `https://colbase.nich.go.jp/collection_items?keyword=${q}`,

  // ===== 德国学术 =====
  "turfan-studies": (q) => `https://turfan.bbaw.de/suche?search=${q}`,
  "berlin-turfan": (q) => `https://turfan.bbaw.de/suche?search=${q}`,

  // ===== 敦煌 =====
  "dunhuang-academy": (q) => `https://www.e-dunhuang.com/search?q=${q}`,
  "idp": (q) => `http://idp.bl.uk/database/search.a4d?searchfield=${q}`,
  "idp-bl": (q) => `http://idp.bl.uk/database/search.a4d?searchfield=${q}`,

  // ===== 百科/参考 =====
  "buddhistdoor": (q) => `https://www.buddhistdoor.net/search?q=${q}`,

  // ===== 0022 新增 — 巴利/上座部工具 =====
  "tipitakapali-org": (q) => `https://tipitakapali.org/?search=${q}`,
  "tipitaka-app": (q) => `https://tipitaka.app/search?q=${q}`,
  "tipitaka-lk": (q) => `https://tipitaka.lk/search?q=${q}`,
  "dpd-dict": (q) => `https://dpdict.net/?q=${q}`,
  "cpd-cologne": (q) => `https://cpd.uni-koeln.de/search?q=${q}`,
  "pali-dict-sutta": (q) => `https://dictionary.sutta.org/?search=${q}`,
  "ped-dsal": (q) => `https://dsal.uchicago.edu/cgi-bin/app/pali_query.py?ession=&matchtype=default&query=${q}`,
  "pali-canon-online": (q) => `https://www.palicanon.org/?s=${q}`,

  // ===== 0022 新增 — 藏文 =====
  "tibetan-buddhist-encyclopedia": (q) => `https://tibetanbuddhistencyclopedia.com/en/index.php?search=${q}`,
  "monlam-ai": (q) => `https://monlam.ai/dictionary?q=${q}`,
  "openpecha": (q) => `https://openpecha.org/search?q=${q}`,
  "rywiki": (q) => `https://rywiki.tsadra.org/index.php?search=${q}`,
  "adarsha-pechamaker": (q) => `https://adarsha.dharma-treasure.org/search?query=${q}`,
  "nitartha-dict": (q) => `https://nitartha.net/search?q=${q}`,

  // ===== 0022 新增 — 梵文/语言学 =====
  "dcs-sanskrit": (q) => `http://www.sanskrit-linguistics.org/dcs/index.php?contents=search&search=${q}`,
  "cdsl-cologne": (q) => `https://www.sanskrit-lexicon.uni-koeln.de/scans/MWScan/2020/web/webtc/indexcaller.php?input=slp1&output=deva&key=${q}`,
  "titus-thesaurus": (q) => `https://titus.uni-frankfurt.de/texte/texte.htm?search=${q}`,
  "gandhari-texts-sydney": (q) => `https://gandhari.org/dictionary?q=${q}`,
  "gandhari": (q) => `https://gandhari.org/dictionary?q=${q}`,

  // ===== 0022 新增 — 汉日韩 =====
  "stonesutras": (q) => `https://www.stonesutras.org/search?q=${q}`,
  "foguang-dict": (q) => `https://www.fgs.org.tw/fgs_book/fgs_drser.aspx?search=${q}`,
  "nti-reader": (q) => `https://ntireader.org/words?query=${q}`,
  "frogbear": (q) => `https://frogbear.org/search?q=${q}`,
  "jinglu-cbeta": (q) => `https://jinglu.cbeta.org/search?q=${q}`,
  "acmuller-dict": (q) => `https://www.acmuller.net/cgi-bin/xprsearch.pl?query=${q}`,
  "lancaster-catalog": (q) => `https://www.acmuller.net/descriptive_catalogue/search.html?q=${q}`,
  "ddm-library": (q) => `https://ddc.shengyen.org/search?q=${q}`,
  "koreanbuddhism": (q) => `https://www.koreanbuddhism.net/search?q=${q}`,
  "himalayan-art": (q) => `https://www.himalayanart.org/search?q=${q}`,

  // ===== 0022 新增 — 现代/翻译/教育 =====
  "btts": (q) => `https://www.buddhisttexts.org/?s=${q}`,
  "open-buddhist-univ": (q) => `https://buddhistuniversity.net/search?q=${q}`,
  "h-buddhism-zotero": (q) => `https://networks.h-net.org/h-buddhism?search=${q}`,
  "dila-glossaries": (q) => `https://authority.dila.edu.tw/person/?keyword=${q}`,
  "mitra-ai": (q) => `https://dharmamitra.org/search?q=${q}`,

  // ===== 0022 新增 — 期刊 =====
  "jbe-ethics": (q) => `https://blogs.dickinson.edu/buddhistethics/?s=${q}`,
  "jgb-global": (q) => `https://www.globalbuddhism.org/?s=${q}`,
  "jiabs": (q) => `https://journals.ub.uni-heidelberg.de/index.php/jiabs/search?query=${q}`,

  // ===== 0022 新增 — 音频 =====
  "audiodharma": (q) => `https://www.audiodharma.org/search?search=${q}`,
  "dharmaseed": (q) => `https://dharmaseed.org/talks/?search=${q}`,
  "free-buddhist-audio": (q) => `https://www.freebuddhistaudio.com/search?q=${q}`,

  // ===== 0023 新增 — P1 高价值源 =====
  "dharmacloud": (q) => `https://dharmacloud.tsadra.org/search/?search=${q}`,
  "compassion-network": (q) => `https://thecompassionnetwork.org/digital-english-canon/?s=${q}`,
  "otdo": (q) => `https://otdo.aa-ken.jp/search.cgi?query=${q}`,
  "ltwa-resource": (q) => `https://ltwaresource.info/?s=${q}`,
  "dtab-bonn": (q) => `https://dtab.crossasia.org/search?q=${q}`,
  "cudl-cambridge": (q) => `https://cudl.lib.cam.ac.uk/search?keyword=${q}`,
  "digital-bodleian": (q) => `https://digital.bodleian.ox.ac.uk/search?q=${q}`,
  "dharma-torch": (q) => `https://dharmatorch.com/?s=${q}`,

  // ===== 0027 新增 — 典津平台审计 =====
  "dianjin": (q) => `https://guji.cckb.cn/search?q=${q}`,
  "shidianguji": (q) => `https://www.shidianguji.com/search?q=${q}`,
  "hathitrust": (q) => `https://catalog.hathitrust.org/Search/Home?lookfor=${q}&type=all`,
  "nl-korea": (q) => `https://www.nl.go.kr/korcis/search?q=${q}`,
  "naikaku-bunko": (q) => `https://www.digital.archives.go.jp/DAS/meta/default?DEF_XSL=default&keyword=${q}`,
  "kokusho-nijl": (q) => `https://kokusho.nijl.ac.jp/?q=${q}`,
  "tianyige": (q) => `https://gj.tianyige.com.cn/#/SearchPage?q=${q}`,
  "zhaocheng-jinzang": (q) => `http://read.nlc.cn/advanceSearch/gujiSearch?keyword=${q}`,
  "yongle-beizang": (q) => `http://read.nlc.cn/advanceSearch/gujiSearch?keyword=${q}`,
  "neidian-baike": (q) => `https://baike.yuezang.org/#/search/${q}`,
  "wenxianxue": (q) => `https://www.wenxianxue.cn/search?q=${q}`,

  // ===== 0032 新增 — 典津公开 API 数据源 =====
  // 佛教文献
  "sd-mingdzj": (q) => `https://sdgj.sdlib.com/dzj/search?keyword=${q}`,
  // 大型综合古籍库
  "souyun-guji": (q) => `https://sou-yun.cn/Query.aspx?type=allBook&QueryWord=${q}`,
  "cass-guji": (q) => `https://www.ncpssd.cn/guji/searchguji?keyword=${q}`,
  "nlc-szgj": (q) => `http://read.nlc.cn/allSearch/searchList?searchType=1001&showType=1&keyword=${q}`,
  "nlc-zhgjzhh": (q) => `https://zhgj.nlc.cn/#/search?keyword=${q}`,
  // 日本
  "keio-dc": (q) => `https://dcollections.lib.keio.ac.jp/ja/search?q=${q}`,
  "kansai-u-dc": (q) => `https://www.iiif.ku-orcas.kansai-u.ac.jp/search?q=${q}`,
  "rekihaku-khirin": (q) => `https://khirin-a.rekihaku.ac.jp/search?q=${q}`,
  // 韩国
  "korcis": (q) => `https://korcis.nl.go.kr/search?q=${q}`,
  "nl-korea-guji": (q) => `https://lod.nl.go.kr/search?q=${q}`,
  "kyujanggak": (q) => `https://kyudb.snu.ac.kr/search?q=${q}`,
  "kr-confucian-net": (q) => `https://www.ugyo.net/search?q=${q}`,
  // 中国省市
  "guangzhou-dadian": (q) => `https://gzdd.gzlib.org.cn/Search/index?key=${q}`,
  "jiangsu-guji": (q) => `https://guji.jslib.org.cn/search?q=${q}`,
  "shoudu-guji": (q) => `https://www.clcn.net.cn/search?q=${q}`,
  // 港澳
  "cuhk-rarebook": (q) => `https://repository.lib.cuhk.edu.hk/en/search?q=${q}`,
  "cuhk-daojing": (q) => `https://repository.lib.cuhk.edu.hk/en/search?q=${q}`,
  "cuhk-tcm": (q) => `https://repository.lib.cuhk.edu.hk/en/search?q=${q}`,
  // 法国
  "gallica-guji": (q) => `https://gallica.bnf.fr/services/engine/search/sru?query=${q}`,
  // 越南
  "hannom-heritage": (q) => `https://lib.nomfoundation.org/collection/1/?search=${q}`,

  // ===== 0033 新增 — 全网搜索发现 =====
  // 梵文写本
  "hmml-buddhist": (q) => `https://www.vhmml.org/readingRoom/?search=${q}`,
  "utokyo-sanskrit-mss": (q) => `https://da.dl.itc.u-tokyo.ac.jp/portal/en/search?q=${q}`,
  "wellcome-buddhist": (q) => `https://wellcomecollection.org/search/works?query=${q}`,
  // 藏文
  "pktc-tibetan-lib": (q) => `https://pktc.org/?s=${q}`,
  "mandala-peking": (q) => `https://sources.mandala.library.virginia.edu/search?q=${q}`,
  "tibetanlibrary-ltwa": (q) => `https://tibetanlibrary.org/?s=${q}`,
  // 大藏经全文
  "bdk-daizokyo": (q) => `https://www.bdk.or.jp/bdk/digital/?search=${q}`,
  "rushi-ai": (q) => `https://reader.rushi-ai.com/search?q=${q}`,
  "rushiwowen": (q) => `https://rushiwowen.co/search?q=${q}`,
  "dzj-fosss": (q) => `http://www.dzj.fosss.net/search?q=${q}`,
  // 经典目录
  "aibs-canons-db": (q) => `http://databases.aibs.columbia.edu/?sub=search&q=${q}`,
  "toyobunko-butten": (q) => `https://toyobunko-lab.jp/butten-shoshi/en/search?q=${q}`,
  "dongguk-abc": (q) => `https://abchome.dongguk.edu/search?q=${q}`,
  // 巴利
  "palitextsociety": (q) => `https://palitextsociety.org/?s=${q}`,
  // 导航
  "nalanda-wiki": (q) => `http://www.nalanda.kr/wiki/index.php?search=${q}`,

  // ===== 0034 新增 — 综合全球搜集 =====
  // 东南亚写本与铭文
  "inya-archive": (q) => `https://archive-inyainstitute.org/?search=${q}`,
  "mmdl-myanmar": (q) => `https://mmdl.utoronto.ca/?search=${q}`,
  "sealang-epigraphy": (q) => `http://sealang.net/library/search.htm?q=${q}`,
  "efeo-angkor-inscriptions": (q) => `https://cik.efeo.fr/?search=${q}`,
  "vietnamese-nikaaya": (q) => `http://www.buddhist-canon.com/PALI/VIET/?search=${q}`,
  // 喜马拉雅/藏传
  "digital-himalaya": (q) => `http://www.digitalhimalaya.com/search.php?search=${q}`,
  "dharma-ebooks": (q) => `https://dharmaebooks.org/?s=${q}`,
  "sakya-digital-lib": (q) => `http://www.sakyalibrary.com/?s=${q}`,
  // 上座部/巴利
  "bps-online": (q) => `http://www.bps.lk/search?q=${q}`,
  "jataka-edinburgh": (q) => `https://jatakastories.div.ed.ac.uk/?s=${q}`,
  // 日本数字档案
  "ryukoku-u-archives": (q) => `http://www.afc.ryukoku.ac.jp/search?q=${q}`,
  "nii-digital-silk-road": (q) => `http://dsr.nii.ac.jp/search?q=${q}`,
  "zinbun-kyoto-chinese-buddhist": (q) => `http://kanji.zinbun.kyoto-u.ac.jp/db-machine/ShisoDB/searchquery.html?query=${q}`,
  // 梵文 & 英译
  "clay-sanskrit": (q) => `https://claysanskritlibrary.org/?s=${q}`,
  "btts-sutra-texts": (q) => `http://www.cttbusa.org/search?q=${q}`,
  // 开源数据集
  "pali-tripitaka-15lang": (q) => `https://github.com/x39826/Pali_Tripitaka/search?q=${q}`,

  // ===== 0035 新增 — 典津交叉比对补充 =====
  "taipei-npm-guji": (q) => `https://catalog.npm.gov.tw/search?q=${q}`,
  "kr-aks-jangseogak": (q) => `https://jsg.aks.ac.kr/search?q=${q}`,
  "utokyo-toyo-bunka": (q) => `https://shanben.ioc.u-tokyo.ac.jp/search?q=${q}`,
  "utokyo-tobunken-nlc": (q) => `http://read.nlc.cn/allSearch/searchList?searchType=6&keyword=${q}`,
  "utokyo-shuanghong": (q) => `https://shuanghong.ioc.u-tokyo.ac.jp/search?q=${q}`,
  "russian-nel-guji": (q) => `https://rusneb.ru/search/?q=${q}`,
  "hdcg-wenyuan": (q) => `https://wenyuan.aliyun.com/hdcg/search?q=${q}`,
};

/**
 * 为指定数据源和查询词生成搜索 URL
 * @returns 搜索 URL 或 null（无已知模板时）
 */
export function buildSearchUrl(code: string, query: string): string | null {
  const q = encodeURIComponent(query);
  const fn = SEARCH_PATTERNS[code];
  return fn ? fn(q) : null;
}

/**
 * 为指定数据源和查询词生成搜索 URL，如果没有已知模板则回退到 Google site: 搜索
 */
export function buildSearchUrlWithFallback(code: string, baseUrl: string | null, query: string): string | null {
  const url = buildSearchUrl(code, query);
  if (url) return url;
  if (baseUrl) {
    const domain = baseUrl.replace(/https?:\/\//, "").replace(/\/.*/, "");
    const q = encodeURIComponent(query);
    return `https://www.google.com/search?q=site:${domain}+${q}`;
  }
  return null;
}

/**
 * 判断数据源是否有直接搜索 URL（非 Google 回退）
 */
export function hasDirectSearchUrl(code: string): boolean {
  return code in SEARCH_PATTERNS;
}

/** 已验证搜索 URL 的数据源数量 */
export const SEARCHABLE_SOURCE_COUNT = Object.keys(SEARCH_PATTERNS).length;

/**
 * 为 CBETA 编号生成 CBETA Online 阅读链接
 */
export function buildCbetaReadUrl(cbetaId: string): string | null {
  if (/^[TX]\d+[a-z]?$/i.test(cbetaId)) {
    return `https://cbetaonline.dila.edu.tw/zh/${cbetaId}`;
  }
  return null;
}

/** 数据源 code → 中文显示名称 */
const SOURCE_LABELS: Record<string, string> = {
  cbeta: "CBETA",
  "cbeta-org": "CBETA",
  suttacentral: "SuttaCentral",
  "suttacentral-org": "SuttaCentral",
  gretil: "GRETIL",
  "84000": "84000",
  bdrc: "BDRC",
  "tbrc-bdrc": "BDRC",
  ctext: "中國哲學書電子化計劃",
  sat: "SAT 大正藏",
  "sat-utokyo": "SAT 大正藏",
  shidianguji: "识典古籍",
  dianjin: "典津",
  "kanseki-repo": "漢籍リポジトリ",
  "lotsawa-house": "Lotsawa House",
  buddhanexus: "Dharmamitra (原BuddhaNexus)",
  dharmanexus: "DharmaNexus",
  accesstoinsight: "Access to Insight",
  dhammatalks: "Dhammatalks",
  dharmacloud: "Dharma Cloud",
  ddb: "DDB 電子佛教辭典",
};

/**
 * 获取数据源的中文显示名称
 */
export function getSourceLabel(code: string): string {
  return SOURCE_LABELS[code] || code.toUpperCase();
}

/** 阅读 URL 模板（非搜索，而是具体文本阅读） */
const READ_URL_PATTERNS: Record<string, (id: string) => string> = {
  cbeta: (id) => `https://cbetaonline.dila.edu.tw/zh/${id}`,
  "cbeta-org": (id) => `https://cbetaonline.dila.edu.tw/zh/${id}`,
  suttacentral: (id) => `https://suttacentral.net/${id}`,
  "suttacentral-org": (id) => `https://suttacentral.net/${id}`,
  "84000": (id) => `https://read.84000.co/translation/${id}.html`,
  ctext: (id) => `https://ctext.org/${id}`,
  sat: (id) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=${id}`,
  "sat-utokyo": (id) => `https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=${id}`,
  accesstoinsight: (id) => `https://www.accesstoinsight.org/tipitaka/${id}`,
  "kanseki-repo": (id) => `https://www.kanripo.org/text/${id}`,
};

/**
 * 为指定数据源和标识符生成阅读 URL
 * @returns 阅读 URL 或 null（无已知模板时）
 */
export function buildSourceReadUrl(sourceCode: string, identifier: string): string | null {
  const fn = READ_URL_PATTERNS[sourceCode];
  return fn ? fn(identifier) : null;
}

/** 语言代码 → 中文名称映射 */
export const LANG_NAMES: Record<string, string> = {
  lzh: "古典汉文",
  sa: "梵文",
  pi: "巴利文",
  bo: "藏文",
  pgd: "犍陀罗语",
  kho: "和阗语",
  sog: "粟特语",
  xto: "吐火罗语A（焉耆语）",
  txb: "吐火罗语B（龟兹语）",
  oui: "古维吾尔语",
  txg: "西夏文",
  cmg: "蒙文",
  mnc: "满文",
  th: "泰文",
  my: "缅文",
  si: "僧伽罗文",
  km: "高棉文",
  ja: "日文",
  ko: "韩文",
  vi: "越南文",
  en: "英文",
  de: "德文",
  fr: "法文",
  lo: "老挝文",
  zh: "中文",
  ru: "俄文",
  nl: "荷兰文",
  pt: "葡萄牙文",
  ne: "尼泊尔文",
  hi: "印地文",
  jv: "爪哇文",
};

export function getLangName(code: string): string {
  return LANG_NAMES[code] || code;
}
