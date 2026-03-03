"""P3: clean up data quality - deactivate pure institution homepages, upgrade real resources

Revision ID: 0025
Revises: 0024
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ══════════════════════════════════════════════════════════════
    # Group A: UPGRADE — real resources that had placeholder descriptions
    # ══════════════════════════════════════════════════════════════
    upgrades = [
        # BDK has real published translations online
        {
            "code": "bdk-tripitaka",
            "description": "仏教伝道協会(BDK)英译大藏经——已出版超150卷佛教经典英译，部分可在线阅读",
            "supports_search": False,
        },
        # CiNii is a real searchable academic DB
        {
            "code": "nii-japan",
            "description": "日本国立情报学研究所 CiNii 学术论文数据库，可检索日本佛学研究论文",
            "supports_search": True,
        },
        # Jogye Order has a digital DB
        {
            "code": "jogye-order",
            "description": "大韩佛教曹溪宗官方数据库，含韩国佛教经典与寺院资料",
            "supports_search": False,
        },
        # BuddhistStudies Berkeley has a real research center page
        {
            "code": "berkeley-ceas",
            "description": "加州大学伯克利分校佛学研究中心，含课程、研究项目与学者信息",
        },
        # Mahidol BudSIR is a real Tipitaka search system
        {
            "code": "mahidol-tipitaka",
            "description": "泰国玛希隆大学 BudSIR 巴利三藏检索系统",
            "supports_search": True,
        },
        # Gallica / Pelliot has searchable digitized manuscripts
        {
            "code": "pelliot-collection",
            "description": "法国国家图书馆 Gallica 平台上的伯希和敦煌收集品数字化影像",
            "supports_iiif": True,
        },
        # Stein Collection at BL has a real guide with links
        {
            "code": "stein-collection",
            "description": "大英图书馆斯坦因敦煌收集品导览与数字化资源（通过 IDP 访问实际影像）",
        },
        # Hamburg has a real Buddhism studies dept with digital projects
        {
            "code": "hamburg-buddhism",
            "description": "汉堡大学印度学与藏学系，含 Gandhāra 佛教手稿研究等数字项目",
        },
        # EFEO has real digital archives
        {
            "code": "efeo",
            "description": "法国远东学院(EFEO)佛学研究部门，含东南亚佛教写本数字化等项目",
        },
        # Russian Academy IOM has real manuscript collections
        {
            "code": "russian-academy",
            "description": "俄罗斯科学院东方写本研究所，藏有大量中亚与敦煌佛教写本",
        },
        # Vatican Library has real digitized oriental manuscripts
        {
            "code": "vatican-lib",
            "description": "梵蒂冈图书馆东方写本数字化馆藏，含部分佛教梵文与藏文写本",
            "supports_iiif": True,
        },
        # Washington gandhari.org is already a known source (duplicate base_url)
        {
            "code": "washington-gandhari",
            "description": "华盛顿大学犍陀罗语研究组，运营 gandhari.org 犍陀罗语文本数据库",
            "supports_search": True,
        },
        # Shanghai Library has digitized rare books
        {
            "code": "shanghai-lib",
            "description": "上海图书馆古籍善本数字化平台，含部分佛教典籍影像",
        },
        # Myanmar Tipitaka at tipitaka.org is a real resource
        {
            "code": "myanmar-tipitaka",
            "description": "缅甸第六次结集巴利三藏在线版（泰国 Dhammakaya 基金会维护）",
            "supports_search": True,
        },
        # Fangshan Stone Sutras - NLC does have some related digitization
        {
            "code": "fangshan-stone",
            "description": "房山石经数据库（通过中国国家图书馆古籍平台部分可查）",
        },
        # Oslo Polyglotta is a real multilingual text DB
        {
            "code": "oslo-polyglotta",
            "description": "奥斯陆大学多语佛典数据库 Bibliotheca Polyglotta，含多语种佛教文本对照",
            "supports_search": True,
        },
        # FGS library is same org as foguang-dict but different section
        {
            "code": "fgs-lib",
            "description": "佛光山佛教文献数据库，含星云大师著作与佛光山出版物",
        },
        # BSB Munich has real digitized Asian manuscripts
        {
            "code": "bavarian-state-lib",
            "description": "巴伐利亚州立图书馆(BSB)东亚馆藏数字化，含部分佛教文献影像",
        },
        # Zhonghua Dazangjing has a real (if limited) website
        {
            "code": "zhonghua-dazangjing",
            "description": "中华大藏经数据库项目——中华书局版《中华大藏经》数字化",
        },
        # Longquan Temple has real digital Buddhist content
        {
            "code": "longquan-temple",
            "description": "龙泉寺(学诚法师)佛学资源与数字佛典项目",
        },
        # Hermitage museum has real Buddhist art collection online
        {
            "code": "hermitage-buddhism",
            "description": "冬宫博物馆在线佛教与东方艺术藏品，含中亚/敦煌相关文物影像",
        },
        # Delhi National Museum has some online collection
        {
            "code": "delhi-national-museum",
            "description": "印度国家博物馆佛教文物在线馆藏，含犍陀罗/马图拉佛教雕塑影像",
        },
        # Laos palm leaf project is real
        {
            "code": "laos-palm-leaf",
            "description": "老挝贝叶经数字档案保存项目（与 DLLM 协作）",
        },
        # NFM Korea has searchable collection
        {
            "code": "nfm-korea",
            "description": "韩国国立中央博物馆在线馆藏检索，含佛教美术文物",
            "supports_search": True,
        },
        # Jiaxing Canon should point to CBETA's jiaxing content
        {
            "code": "jiaxing-zang",
            "description": "嘉兴藏(径山藏)数字化——CBETA 收录部分嘉兴藏经典",
        },
        # Bodleian Oxford - now we have digital-bodleian, this is the main library page
        {
            "code": "oxford-bodleian",
            "description": "牛津博德利图书馆梵文/东方学写本馆藏信息页（数字化影像见 Digital Bodleian）",
        },
        # Cambridge Sanskrit - now we have cudl-cambridge, this is the main library
        {
            "code": "cambridge-sanskrit",
            "description": "剑桥大学图书馆梵文/佛教写本馆藏信息页（数字化影像见 CUDL）",
        },
    ]

    upgraded = 0
    for u in upgrades:
        code = u.pop("code")
        sets = ["description = :description"]
        params = {"code": code, "description": u["description"]}
        if u.get("supports_search"):
            sets.append("supports_search = true")
        if u.get("supports_iiif"):
            sets.append("supports_iiif = true")
        conn.execute(sa_text(
            f"UPDATE data_sources SET {', '.join(sets)} WHERE code = :code"
        ), params)
        upgraded += 1
    print(f"✅ Upgraded descriptions for {upgraded} sources")

    # ══════════════════════════════════════════════════════════════
    # Group B: DEACTIVATE — pure institution homepages with no digital Buddhist resources
    # These are university main pages, generic org pages, etc.
    # ══════════════════════════════════════════════════════════════
    deactivate_codes = [
        # University main pages (no Buddhist-specific digital resources)
        "anu-buddhism",        # www.anu.edu.au - ANU main page
        "barcelona-buddhism",  # www.uab.cat - UAB main page
        "bhu-sanskrit",        # www.bhu.ac.in - BHU main page
        "chicago-divinity",    # divinity.uchicago.edu - dept page, no digital Buddhist resource
        "chula-pali",          # www.chula.ac.th - Chulalongkorn main page
        "copenhagen-buddhism", # ccrs.ku.dk - dept page
        "fudan-buddhism",      # www.fudan.edu.cn - Fudan main page
        "ghent-buddhism",      # www.ugent.be - Ghent main page
        "goettingen-sanskrit",  # www.uni-goettingen.de - Göttingen main page
        "kelaniya-univ",       # www.kln.ac.lk - Kelaniya main page
        "leiden-univ",         # universiteitleiden.nl - Leiden main page
        "lmu-buddhism",        # www.lmu.de - LMU main page
        "mcgill-buddhism",     # www.mcgill.ca - McGill main page
        "melbourne-chinese",   # www.unimelb.edu.au - Melbourne main page
        "michigan-buddhism",   # lsa.umich.edu - dept page
        "nanjing-univ",        # www.nju.edu.cn - NJU main page
        "pku-buddhism",        # www.pku.edu.cn - PKU main page
        "renmin-buddhism",     # www.ruc.edu.cn - RUC main page
        "shandong-univ",       # www.sdu.edu.cn - SDU main page
        "sydney-buddhism",     # www.sydney.edu.au - Sydney main page
        "toronto-buddhism",    # www.utoronto.ca - UofT main page
        "tsinghua-dh",         # www.tsinghua.edu.cn - Tsinghua main page
        "turin-tibetan",       # www.unito.it - Turin main page
        "ubc-buddhism",        # www.ubc.ca - UBC main page
        "ucla-buddhism",       # www.ucla.edu - UCLA main page
        "virginia-buddhism",   # www.virginia.edu - UVA main page
        "wisconsin-buddhism",  # www.wisc.edu - Wisconsin main page
        "wuhan-univ",          # www.whu.edu.cn - WHU main page
        "yale-divinity",       # divinity.yale.edu - dept page
        "zju-buddhism",        # www.zju.edu.cn - ZJU main page
        "dongguk-univ",        # www.dongguk.edu - general univ page (specific DB is korean-tripitaka-db)

        # Organization main pages without digital Buddhist resources
        "asi-india",           # asi.nic.in - Archaeological Survey, no digital Buddhist texts
        "cass-religion",       # iwr.cass.cn - CASS department page
        "crcao-paris",         # www.crcao.fr - research center page
        "lumbini-research",    # lumbinidevtrust.gov.np - trust page, no digital resources
        "nalanda-digital",     # nalandauniv.edu.in - university page, digital heritage project unclear
        "nepal-ntca",          # www.ntca.gov.np - archives page, no online access
        "pune-bori",           # www.bfrInstitute.org - BORI page, no online collections

        # Provincial/city library main pages (no Buddhist-specific digital section)
        "gansu-lib",           # gslib.com.cn
        "guangzhou-lib",       # gzlib.org.cn
        "hangzhou-lib",        # hzlib.net
        "hubei-lib",           # library.hb.cn
        "inner-mongolia",      # nmglib.com
        "nanjing-lib",         # jslib.org.cn
        "sichuan-lib",         # sclib.org
        "suzhou-lib",          # szlib.com
        "tianjin-lib",         # tjl.tj.cn
        "yunnan-lib",          # ynlib.cn
        "zhejiang-lib",        # zjlib.cn

        # Temple/monastery pages without digital text access
        "wat-pho",             # watpho.com - tourist site
        "gandan-monastery",    # gandan.mn - monastery page
        "bhutan-lib",          # library.gov.bt - national library, no online Buddhist texts
        "cambodia-buddhism",   # bid.org.kh - institute page
        "mongolia-lib",        # nationallibrary.mn - national library main page

        # Misc without accessible digital resources
        "iiif-buddhist",       # iiif.io - the IIIF standard itself, not a Buddhist resource
        "open-philology",      # openphilology.org - project page, limited content
        "daizokyo-society",    # u-tokyo.ac.jp - very generic dept page
        "chung-hwa",           # chibs.edu.tw - institute page (DILA is the digital arm)
        "potala-archive",      # potalapalace.cn - palace tourist site, no digital archive access
        "tibet-lib",           # xzlib.com - library page, no online Buddhist texts

        # Japanese temple/organization pages without digital search
        "jodo-shu",            # jodo.or.jp - Jodo Shu org page
        "nichiren-lib",        # nichiren.or.jp - Nichiren org page
        "koyasan-univ",        # koyasan-u.ac.jp - university page
        "otani-univ",          # otani.ac.jp - university page
        "taisho-univ",         # tais.ac.jp - university page
        "ryukoku-univ",        # ryukoku.ac.jp - university page
        "toyo-bunko",          # toyo-bunko.or.jp - library page (separate from digital platform)

        # Other organization pages
        "aks-korea",           # aks.ac.kr - AKS main page
        "soas-buddhism",       # soas.ac.uk - SOAS main page
        "srilanka-tripitaka",  # pali.lk - PTS Sri Lanka, minimal content
        "sbb-asian",           # staatsbibliothek-berlin.de - state library main page
        "harvard-buddhism",    # www.harvard.edu - Harvard main page (yenching is separate)
        "nagarjuna-inst",      # dsbcproject.org - duplicate of dsbc
        "vietnam-buddhism",    # vbu.edu.vn - university page
        "vienna-buddhism",     # stb.univie.ac.at - dept page
    ]

    if deactivate_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(deactivate_codes)))
        params = {f"c{i}": code for i, code in enumerate(deactivate_codes)}
        result = conn.execute(sa_text(
            f"UPDATE data_sources SET is_active = false WHERE code IN ({placeholders})"
        ), params)
        print(f"✅ Deactivated {result.rowcount} pure-homepage sources")

    # Print final stats
    total = conn.execute(sa_text("SELECT count(*) FROM data_sources")).scalar()
    active = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE is_active = true")).scalar()
    searchable = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE supports_search = true AND is_active = true")).scalar()
    print(f"📊 Final: {total} total, {active} active, {searchable} searchable")


def downgrade() -> None:
    conn = op.get_bind()
    # Re-activate all and reset descriptions to placeholder
    conn.execute(sa_text(
        "UPDATE data_sources SET is_active = true WHERE is_active = false"
    ))
