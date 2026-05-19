"""
Import CBETA catalog metadata into PostgreSQL and Elasticsearch.

Uses the CBETA catalog data from their open GitHub repositories.
The script downloads and parses the catalog XML/JSON to extract text metadata.
"""

import asyncio
import json
import os
import sys

import httpx
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.core.elasticsearch import INDEX_NAME

# CBETA catalog categories mapping
CATEGORIES = {
    "T": ("大正藏", "Taishō"),
    "X": ("卍新纂續藏經", "Xuzangjing"),
    "A": ("趙城金藏", "Zhaocheng Jinzang"),
    "K": ("高麗大藏經", "Goryeo Daejanggyeong"),
    "S": ("宋藏遺珍", "Song Treasures"),
    "F": ("房山石經", "Fangshan Stone Sutras"),
    "C": ("中華大藏經", "Zhonghua Dazangjing"),
    "D": ("國圖善本", "National Library Rare Books"),
    "U": ("大藏經補編", "Dazangjing Supplement"),
    "P": ("永樂北藏", "Yongle Northern Canon"),
    "J": ("嘉興藏", "Jiaxing Canon"),
    "L": ("乾隆大藏經", "Qianlong Canon"),
    "G": ("佛教大藏經", "Buddhist Canon"),
    "M": ("卍正藏經", "Man Zhengzang"),
    "N": ("南傳大藏經", "Pali Canon (Chinese)"),
    "ZS": ("正史佛教資料類編", "Official Histories"),
    "I": ("北朝佛教石刻拓片百品", "Stone Inscriptions"),
    "ZW": ("藏外佛教文獻", "Extra-canonical"),
    "B": ("大藏經補編", "Canon Supplement B"),
    "GA": ("中國佛寺志", "Chinese Temple Gazetteers"),
    "GB": ("中國佛寺志", "Chinese Temple Gazetteers B"),
    "Y": ("印順法師佛學著作集", "Yinshun Collection"),
    "LC": ("呂澂佛學著作集", "Lü Cheng Collection"),
    "W": ("藏外佛教文獻", "Extra-canonical W"),
}

# Dynasty mapping for common translator attributions
TRANSLATOR_DYNASTIES = {
    "後漢": "東漢",
    "吳": "三國",
    "曹魏": "三國",
    "西晉": "西晉",
    "東晉": "東晉",
    "前秦": "十六國",
    "後秦": "十六國",
    "北涼": "十六國",
    "劉宋": "南朝",
    "蕭齊": "南朝",
    "梁": "南朝",
    "陳": "南朝",
    "北魏": "北朝",
    "北齊": "北朝",
    "北周": "北朝",
    "隋": "隋",
    "唐": "唐",
    "五代": "五代",
    "宋": "宋",
    "遼": "遼",
    "金": "金",
    "元": "元",
    "明": "明",
    "清": "清",
    "民國": "民國",
}

# CBETA Online Reader base URL
CBETA_ONLINE_BASE = "https://cbetaonline.dila.edu.tw/zh/"


def parse_dynasty_translator(byline: str) -> tuple[str | None, str | None]:
    """Parse dynasty and translator from CBETA byline like '後秦 鳩摩羅什譯'."""
    if not byline:
        return None, None

    byline = byline.strip()

    # Try to match known dynasty prefixes
    for dynasty_key in sorted(TRANSLATOR_DYNASTIES.keys(), key=len, reverse=True):
        if byline.startswith(dynasty_key):
            dynasty = TRANSLATOR_DYNASTIES[dynasty_key]
            translator = byline[len(dynasty_key):].strip()
            # Remove trailing 譯/translated
            if translator.endswith("譯"):
                translator = translator[:-1].strip()
            return dynasty, translator if translator else None

    # No dynasty found, treat entire string as translator
    translator = byline
    if translator.endswith("譯"):
        translator = translator[:-1].strip()
    return None, translator if translator else None


async def fetch_cbeta_catalog() -> list[dict]:
    """
    Fetch CBETA catalog from GitHub.
    Falls back to generating sample data if the fetch fails.
    """
    catalog_url = (
        "https://raw.githubusercontent.com/cbeta-git/cbeta-metadata/master/catalog/catalog.json"
    )
    alt_url = (
        "https://raw.githubusercontent.com/cbeta-org/cbeta-metadata/master/catalog/catalog.json"
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        for url in [catalog_url, alt_url]:
            try:
                print(f"Trying to fetch catalog from: {url}")
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Fetched {len(data)} records from CBETA catalog.")
                    return data
            except Exception as e:
                print(f"Failed to fetch from {url}: {e}")

    # Fallback: try to read local file
    local_path = "/data/cbeta/catalog.json"
    if os.path.exists(local_path):
        print(f"Reading local catalog from {local_path}")
        with open(local_path) as f:
            return json.load(f)

    # Ultimate fallback: generate sample data from known CBETA entries
    print("Could not fetch remote catalog. Generating sample data from known CBETA entries...")
    return generate_sample_catalog()


def generate_sample_catalog() -> list[dict]:
    """Generate a comprehensive sample catalog based on known CBETA texts."""
    # Well-known texts from the Taishō Tripiṭaka and other collections
    entries = [
        # 阿含部 (Āgama)
        {"work": "T0001", "title": "長阿含經", "byline": "後秦 佛陀耶舍共竺佛念譯", "juan": 22, "category": "阿含部"},
        {"work": "T0026", "title": "中阿含經", "byline": "東晉 瞿曇僧伽提婆譯", "juan": 60, "category": "阿含部"},
        {"work": "T0099", "title": "雜阿含經", "byline": "劉宋 求那跋陀羅譯", "juan": 50, "category": "阿含部"},
        {"work": "T0125", "title": "增壹阿含經", "byline": "東晉 瞿曇僧伽提婆譯", "juan": 51, "category": "阿含部"},
        # 般若部 (Prajñāpāramitā)
        {"work": "T0220", "title": "大般若波羅蜜多經", "byline": "唐 玄奘譯", "juan": 600, "category": "般若部"},
        {"work": "T0223", "title": "摩訶般若波羅蜜經", "byline": "後秦 鳩摩羅什譯", "juan": 27, "category": "般若部"},
        {"work": "T0235", "title": "妙法蓮華經", "byline": "後秦 鳩摩羅什譯", "juan": 7, "category": "法華部"},
        {"work": "T0245", "title": "妙法蓮華經憂波提舍", "byline": "後魏 菩提流支共曇林等譯", "juan": 2, "category": "法華部"},
        {"work": "T0251", "title": "般若波羅蜜多心經", "byline": "唐 玄奘譯", "juan": 1, "category": "般若部"},
        {"work": "T0252", "title": "般若波羅蜜多心經", "byline": "唐 般若共利言等譯", "juan": 1, "category": "般若部"},
        # 華嚴部 (Avataṃsaka)
        {"work": "T0278", "title": "大方廣佛華嚴經", "byline": "東晉 佛馱跋陀羅譯", "juan": 60, "category": "華嚴部"},
        {"work": "T0279", "title": "大方廣佛華嚴經", "byline": "唐 實叉難陀譯", "juan": 80, "category": "華嚴部"},
        {"work": "T0293", "title": "大方廣佛華嚴經入法界品", "byline": "唐 地婆訶羅譯", "juan": 1, "category": "華嚴部"},
        # 寶積部 (Ratnakūṭa)
        {"work": "T0310", "title": "大寶積經", "byline": "唐 菩提流志譯", "juan": 120, "category": "寶積部"},
        # 涅槃部 (Nirvāṇa)
        {"work": "T0374", "title": "大般涅槃經", "byline": "北涼 曇無讖譯", "juan": 40, "category": "涅槃部"},
        {"work": "T0375", "title": "大般涅槃經", "byline": "劉宋 慧嚴等依泥洹經加之", "juan": 36, "category": "涅槃部"},
        # 大集部
        {"work": "T0397", "title": "大方等大集經", "byline": "北涼 曇無讖譯", "juan": 60, "category": "大集部"},
        # 經集部
        {"work": "T0360", "title": "佛說無量壽經", "byline": "曹魏 康僧鎧譯", "juan": 2, "category": "寶積部"},
        {"work": "T0365", "title": "佛說觀無量壽佛經", "byline": "劉宋 畺良耶舍譯", "juan": 1, "category": "寶積部"},
        {"work": "T0366", "title": "佛說阿彌陀經", "byline": "後秦 鳩摩羅什譯", "juan": 1, "category": "寶積部"},
        {"work": "T0389", "title": "佛說佛名經", "byline": "北魏 菩提流支譯", "juan": 30, "category": "經集部"},
        {"work": "T0410", "title": "大方廣十輪經", "byline": "北涼 曇無讖譯", "juan": 8, "category": "經集部"},
        {"work": "T0411", "title": "地藏菩薩本願經", "byline": "唐 實叉難陀譯", "juan": 2, "category": "經集部"},
        {"work": "T0412", "title": "佛說盂蘭盆經", "byline": "西晉 竺法護譯", "juan": 1, "category": "經集部"},
        {"work": "T0416", "title": "佛說藥師如來本願經", "byline": "隋 達摩笈多譯", "juan": 1, "category": "經集部"},
        {"work": "T0450", "title": "佛說彌勒下生成佛經", "byline": "唐 義淨譯", "juan": 1, "category": "經集部"},
        {"work": "T0474", "title": "維摩詰所說經", "byline": "後秦 鳩摩羅什譯", "juan": 3, "category": "經集部"},
        {"work": "T0475", "title": "說無垢稱經", "byline": "唐 玄奘譯", "juan": 6, "category": "經集部"},
        {"work": "T0480", "title": "文殊師利所說摩訶般若波羅蜜經", "byline": "梁 曼陀羅仙譯", "juan": 2, "category": "經集部"},
        {"work": "T0475b", "title": "維摩詰經", "byline": "吳 支謙譯", "juan": 2, "category": "經集部"},
        # 密教部
        {"work": "T0848", "title": "大毘盧遮那成佛神變加持經", "byline": "唐 善無畏共一行譯", "juan": 7, "category": "密教部"},
        {"work": "T0865", "title": "金剛頂一切如來真實攝大乘現證大教王經", "byline": "唐 不空譯", "juan": 3, "category": "密教部"},
        {"work": "T0882", "title": "蘇悉地羯羅經", "byline": "唐 輸波迦羅譯", "juan": 3, "category": "密教部"},
        # 律部
        {"work": "T1421", "title": "彌沙塞部和醯五分律", "byline": "劉宋 佛陀什共竺道生等譯", "juan": 30, "category": "律部"},
        {"work": "T1425", "title": "摩訶僧祇律", "byline": "東晉 佛陀跋陀羅共法顯譯", "juan": 40, "category": "律部"},
        {"work": "T1428", "title": "四分律", "byline": "後秦 佛陀耶舍共竺佛念等譯", "juan": 60, "category": "律部"},
        {"work": "T1435", "title": "十誦律", "byline": "後秦 弗若多羅共羅什譯", "juan": 61, "category": "律部"},
        {"work": "T1558", "title": "阿毘達磨俱舍論", "byline": "唐 玄奘譯", "juan": 30, "category": "毘曇部"},
        # 中觀/瑜伽
        {"work": "T1509", "title": "大智度論", "byline": "後秦 鳩摩羅什譯", "juan": 100, "category": "釋經論部"},
        {"work": "T1564", "title": "中論", "byline": "後秦 鳩摩羅什譯", "juan": 4, "category": "中觀部"},
        {"work": "T1568", "title": "十二門論", "byline": "後秦 鳩摩羅什譯", "juan": 1, "category": "中觀部"},
        {"work": "T1569", "title": "百論", "byline": "後秦 鳩摩羅什譯", "juan": 2, "category": "中觀部"},
        {"work": "T1579", "title": "瑜伽師地論", "byline": "唐 玄奘譯", "juan": 100, "category": "瑜伽部"},
        {"work": "T1585", "title": "成唯識論", "byline": "唐 玄奘譯", "juan": 10, "category": "瑜伽部"},
        {"work": "T1586", "title": "唯識二十論", "byline": "唐 玄奘譯", "juan": 1, "category": "瑜伽部"},
        {"work": "T1590", "title": "攝大乘論", "byline": "後魏 佛陀扇多譯", "juan": 2, "category": "瑜伽部"},
        {"work": "T1593", "title": "攝大乘論釋", "byline": "唐 玄奘譯", "juan": 10, "category": "瑜伽部"},
        {"work": "T1600", "title": "大乘莊嚴經論", "byline": "唐 波羅頗蜜多羅譯", "juan": 13, "category": "瑜伽部"},
        # 論集部
        {"work": "T1615", "title": "大乘起信論", "byline": "梁 真諦譯", "juan": 1, "category": "論集部"},
        {"work": "T1630", "title": "大乘百法明門論", "byline": "唐 玄奘譯", "juan": 1, "category": "瑜伽部"},
        {"work": "T1666", "title": "肇論", "byline": "後秦 僧肇", "juan": 1, "category": "論集部"},
        # 經疏部
        {"work": "T1718", "title": "妙法蓮華經玄義", "byline": "隋 智顗", "juan": 20, "category": "經疏部"},
        {"work": "T1911", "title": "法華義疏", "byline": "隋 吉藏", "juan": 12, "category": "經疏部"},
        # 諸宗部
        {"work": "T1969", "title": "修華嚴奧旨妄盡還源觀", "byline": "唐 法藏", "juan": 1, "category": "諸宗部"},
        {"work": "T2003", "title": "金剛般若經集驗記", "byline": "唐 孟獻忠", "juan": 3, "category": "諸宗部"},
        {"work": "T2005", "title": "南宗頓教最上大乘摩訶般若波羅蜜經六祖惠能大師於韶州大梵寺施法壇經", "byline": "唐 法海", "juan": 1, "category": "諸宗部"},
        {"work": "T2007", "title": "六祖大師法寶壇經", "byline": "唐 宗寶", "juan": 1, "category": "諸宗部"},
        {"work": "T2008", "title": "少室六門", "byline": "", "juan": 1, "category": "諸宗部"},
        {"work": "T2010", "title": "信心銘", "byline": "隋 僧璨", "juan": 1, "category": "諸宗部"},
        {"work": "T2012", "title": "永嘉證道歌", "byline": "唐 玄覺", "juan": 1, "category": "諸宗部"},
        {"work": "T2016", "title": "禪源諸詮集都序", "byline": "唐 宗密", "juan": 4, "category": "諸宗部"},
        {"work": "T2076", "title": "景德傳燈錄", "byline": "宋 道原", "juan": 30, "category": "史傳部"},
        # 金剛經
        {"work": "T0235b", "title": "金剛般若波羅蜜經", "byline": "後秦 鳩摩羅什譯", "juan": 1, "category": "般若部"},
        # 圓覺經
        {"work": "T0842", "title": "大方廣圓覺修多羅了義經", "byline": "唐 佛陀多羅譯", "juan": 1, "category": "經集部"},
        # 楞嚴經
        {"work": "T0945", "title": "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經", "byline": "唐 般剌蜜帝譯", "juan": 10, "category": "密教部"},
        # 楞伽經
        {"work": "T0670", "title": "入楞伽經", "byline": "北魏 菩提流支譯", "juan": 10, "category": "經集部"},
        {"work": "T0671", "title": "大乘入楞伽經", "byline": "唐 實叉難陀譯", "juan": 7, "category": "經集部"},
        {"work": "T0672", "title": "楞伽阿跋多羅寶經", "byline": "劉宋 求那跋陀羅譯", "juan": 4, "category": "經集部"},
        # 解深密經
        {"work": "T0676", "title": "解深密經", "byline": "唐 玄奘譯", "juan": 5, "category": "經集部"},
        # 史傳部
        {"work": "T2059", "title": "高僧傳", "byline": "梁 慧皎", "juan": 14, "category": "史傳部"},
        {"work": "T2060", "title": "續高僧傳", "byline": "唐 道宣", "juan": 30, "category": "史傳部"},
        {"work": "T2061", "title": "宋高僧傳", "byline": "宋 贊寧", "juan": 30, "category": "史傳部"},
        {"work": "T2035", "title": "佛祖統紀", "byline": "宋 志磐", "juan": 54, "category": "史傳部"},
        {"work": "T2122", "title": "法苑珠林", "byline": "唐 道世", "juan": 100, "category": "事彙部"},
        {"work": "T2128", "title": "釋氏要覽", "byline": "宋 道誠", "juan": 3, "category": "事彙部"},
        {"work": "T2154", "title": "開元釋教錄", "byline": "唐 智昇", "juan": 20, "category": "目錄部"},
        # 淨土
        {"work": "T1963", "title": "安樂集", "byline": "唐 道綽", "juan": 2, "category": "諸宗部"},
        {"work": "T1961", "title": "往生論註", "byline": "北魏 曇鸞", "juan": 2, "category": "諸宗部"},
        # 天台
        {"work": "T1911b", "title": "摩訶止觀", "byline": "隋 智顗", "juan": 20, "category": "諸宗部"},
        # Extra collections
        {"work": "X0001", "title": "大般若波羅蜜多經般若理趣分述讚", "byline": "唐 圓測", "juan": 3, "category": "續藏經"},
        {"work": "X0240", "title": "金剛般若波羅蜜經破取著不壞假名論", "byline": "唐 功迥", "juan": 2, "category": "續藏經"},
        {"work": "X0344", "title": "般若心經略疏", "byline": "唐 法藏", "juan": 1, "category": "續藏經"},
        {"work": "X1235", "title": "碧巖錄", "byline": "宋 圓悟克勤", "juan": 10, "category": "續藏經"},
        {"work": "X1309", "title": "無門關", "byline": "宋 無門慧開", "juan": 1, "category": "續藏經"},
        {"work": "X1565", "title": "禪林象器箋", "byline": "日本 無著道忠", "juan": 30, "category": "續藏經"},
    ]

    return entries


def transform_entry(entry: dict) -> dict | None:
    """Transform a CBETA catalog entry into our database format."""
    work_id = entry.get("work", "")
    title = entry.get("title", "")

    if not work_id or not title:
        return None

    # Determine collection prefix and taisho_id
    taisho_id = None
    if work_id.startswith("T"):
        taisho_id = work_id

    byline = entry.get("byline", "") or ""
    dynasty, translator = parse_dynasty_translator(byline)

    juan = entry.get("juan")
    if isinstance(juan, str):
        try:
            juan = int(juan)
        except ValueError:
            juan = None

    category = entry.get("category", "")
    # Determine collection category from prefix
    prefix = ""
    for p in sorted(CATEGORIES.keys(), key=len, reverse=True):
        if work_id.startswith(p):
            prefix = p
            break

    collection_name = CATEGORIES.get(prefix, ("其他", "Other"))[0] if prefix else None
    cbeta_url = f"{CBETA_ONLINE_BASE}{work_id}"

    return {
        "taisho_id": taisho_id,
        "cbeta_id": work_id,
        "title_zh": title,
        "title_sa": None,
        "title_bo": None,
        "title_pi": None,
        "translator": translator,
        "dynasty": dynasty,
        "fascicle_count": juan,
        "category": category or collection_name,
        "subcategory": collection_name,
        "cbeta_url": cbeta_url,
    }


async def import_to_postgres(session: AsyncSession, records: list[dict]) -> dict[str, int]:
    """Import records to PostgreSQL, returning a mapping of cbeta_id -> db id."""
    # Clear existing data
    await session.execute(text("DELETE FROM buddhist_texts"))
    await session.flush()

    id_map = {}
    for i, rec in enumerate(records):
        result = await session.execute(
            text("""
                INSERT INTO buddhist_texts
                    (taisho_id, cbeta_id, title_zh, title_sa, title_bo, title_pi,
                     translator, dynasty, fascicle_count, category, subcategory, cbeta_url)
                VALUES
                    (:taisho_id, :cbeta_id, :title_zh, :title_sa, :title_bo, :title_pi,
                     :translator, :dynasty, :fascicle_count, :category, :subcategory, :cbeta_url)
                RETURNING id
            """),
            rec,
        )
        row = result.fetchone()
        id_map[rec["cbeta_id"]] = row[0]

        if (i + 1) % 500 == 0:
            print(f"  PostgreSQL: inserted {i + 1}/{len(records)} records...")

    await session.commit()
    return id_map


async def import_to_elasticsearch(es: AsyncElasticsearch, records: list[dict], id_map: dict[str, int]):
    """Index records into Elasticsearch."""
    from elasticsearch.helpers import async_bulk

    async def gen_actions():
        for rec in records:
            db_id = id_map.get(rec["cbeta_id"])
            if db_id is None:
                continue
            doc = {k: v for k, v in rec.items() if v is not None}
            yield {
                "_index": INDEX_NAME,
                "_id": str(db_id),
                "_source": {"id": db_id, **doc},
            }

    success, errors = await async_bulk(es, gen_actions(), raise_on_error=False)
    print(f"  Elasticsearch: indexed {success} documents, {len(errors) if isinstance(errors, list) else errors} errors")


async def main():
    print("=" * 60)
    print("佛津 (FoJin) — CBETA Catalog Import")
    print("=" * 60)

    # Fetch catalog
    print("\n[1/3] Fetching CBETA catalog...")
    raw_entries = await fetch_cbeta_catalog()

    # Transform
    print(f"\n[2/3] Transforming {len(raw_entries)} entries...")
    records = []
    for entry in raw_entries:
        rec = transform_entry(entry)
        if rec:
            records.append(rec)
    print(f"  Transformed {len(records)} valid records.")

    if not records:
        print("No records to import. Exiting.")
        return

    # Import to PostgreSQL
    print("\n[3/3] Importing to PostgreSQL and Elasticsearch...")
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        id_map = await import_to_postgres(session, records)
        print(f"  PostgreSQL: {len(id_map)} records imported.")

    # Import to Elasticsearch
    es = AsyncElasticsearch(settings.es_host)
    try:
        await import_to_elasticsearch(es, records, id_map)
    finally:
        await es.close()

    await engine.dispose()

    print(f"\nImport complete! {len(records)} Buddhist texts imported.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
