"""seed place and concept entities with relations to existing persons/texts

Adds ~30 important Buddhist places and ~20 core Buddhist concepts
to kg_entities, plus located_in / related_to relations.

Idempotent: checks by (entity_type, name_zh) before inserting.

Revision ID: 0094
Revises: 0093
Create Date: 2026-03-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0094"
down_revision: str | None = "0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Place definitions ─────────────────────────────────────────
PLACES = [
    # 印度佛教圣地
    {"name_zh": "菩提伽耶", "name_en": "Bodh Gaya", "name_sa": "Bodhgayā",
     "desc": "释迦牟尼成道之地，位于今印度比哈尔邦"},
    {"name_zh": "鹿野苑", "name_en": "Sarnath", "name_sa": "Ṛṣipatana",
     "desc": "释迦牟尼初转法轮之地，位于今印度瓦拉纳西附近"},
    {"name_zh": "王舍城", "name_en": "Rajgir", "name_sa": "Rājagṛha",
     "desc": "摩揭陀国首都，第一次佛经结集之地"},
    {"name_zh": "舍卫城", "name_en": "Shravasti", "name_sa": "Śrāvastī",
     "desc": "拘萨罗国首都，祇园精舍所在地，佛陀说法最多之处"},
    {"name_zh": "拘尸那揭罗", "name_en": "Kushinagar", "name_sa": "Kuśinagara",
     "desc": "释迦牟尼涅槃之地，位于今印度北方邦"},
    {"name_zh": "蓝毗尼", "name_en": "Lumbini", "name_sa": "Lumbinī",
     "desc": "释迦牟尼诞生之地，位于今尼泊尔"},
    {"name_zh": "那烂陀", "name_en": "Nalanda", "name_sa": "Nālandā",
     "desc": "古印度最著名的佛教大学，玄奘曾于此学法"},
    {"name_zh": "超戒寺", "name_en": "Vikramashila", "name_sa": "Vikramaśīla",
     "desc": "波罗王朝时期重要的密教学府"},
    {"name_zh": "吠舍离", "name_en": "Vaishali", "name_sa": "Vaiśālī",
     "desc": "第二次佛经结集之地，维摩诘居住之处"},
    # 中国佛教圣地
    {"name_zh": "五台山", "name_en": "Mount Wutai", "name_sa": None,
     "desc": "文殊菩萨道场，中国佛教四大名山之首，位于山西省"},
    {"name_zh": "峨眉山", "name_en": "Mount Emei", "name_sa": None,
     "desc": "普贤菩萨道场，中国佛教四大名山之一，位于四川省"},
    {"name_zh": "普陀山", "name_en": "Mount Putuo", "name_sa": "Potalaka",
     "desc": "观世音菩萨道场，中国佛教四大名山之一，位于浙江省"},
    {"name_zh": "九华山", "name_en": "Mount Jiuhua", "name_sa": None,
     "desc": "地藏菩萨道场，中国佛教四大名山之一，位于安徽省"},
    {"name_zh": "嵩山", "name_en": "Mount Song", "name_sa": None,
     "desc": "少林寺所在地，禅宗祖庭，位于河南省"},
    {"name_zh": "天台山", "name_en": "Mount Tiantai", "name_sa": None,
     "desc": "天台宗发祥地，国清寺所在地，位于浙江省"},
    {"name_zh": "庐山", "name_en": "Mount Lu", "name_sa": None,
     "desc": "东林寺所在地，净土宗发祥地，位于江西省"},
    {"name_zh": "终南山", "name_en": "Mount Zhongnan", "name_sa": None,
     "desc": "净业寺所在地，律宗祖庭，位于陕西省"},
    # 中亚/丝路佛教遗址
    {"name_zh": "龟兹", "name_en": "Kucha", "name_sa": "Kucīna",
     "desc": "古西域佛教中心，鸠摩罗什故乡，位于今新疆库车"},
    {"name_zh": "犍陀罗", "name_en": "Gandhara", "name_sa": "Gandhāra",
     "desc": "古印度西北部佛教艺术中心，佛像艺术发源地"},
    {"name_zh": "敦煌", "name_en": "Dunhuang", "name_sa": None,
     "desc": "莫高窟所在地，丝绸之路佛教文化交汇处，位于甘肃省"},
    # 东南亚/斯里兰卡
    {"name_zh": "阿努拉德普勒", "name_en": "Anuradhapura", "name_sa": "Anurādhapura",
     "desc": "斯里兰卡古都，上座部佛教传播中心"},
    # 日本
    {"name_zh": "高野山", "name_en": "Mount Koya", "name_sa": None,
     "desc": "空海创立的真言宗总本山，位于日本和歌山县"},
    {"name_zh": "比叡山", "name_en": "Mount Hiei", "name_sa": None,
     "desc": "最澄创立的天台宗总本山，位于日本滋贺县"},
    # 西藏
    {"name_zh": "拉萨", "name_en": "Lhasa", "name_sa": None,
     "desc": "西藏首府，布达拉宫、大昭寺所在地，藏传佛教圣城"},
    {"name_zh": "桑耶寺", "name_en": "Samye Monastery", "name_sa": None,
     "desc": "西藏第一座佛教寺院，寂护和莲花生大士创建"},
]

# ── Concept definitions ─────────────────────────────────────────
CONCEPTS = [
    {"name_zh": "缘起", "name_en": "Dependent Origination", "name_sa": "Pratītyasamutpāda",
     "name_pi": "Paṭiccasamuppāda",
     "desc": "佛教核心教义，一切法因缘和合而生，无自性"},
    {"name_zh": "四圣谛", "name_en": "Four Noble Truths", "name_sa": "Catvāry āryasatyāni",
     "name_pi": "Cattāri ariyasaccāni",
     "desc": "苦谛、集谛、灭谛、道谛，佛教最根本的教理框架"},
    {"name_zh": "八正道", "name_en": "Noble Eightfold Path", "name_sa": "Āryāṣṭāṅgamārga",
     "name_pi": "Ariyo aṭṭhaṅgiko maggo",
     "desc": "正见、正思惟、正语、正业、正命、正精进、正念、正定"},
    {"name_zh": "空性", "name_en": "Emptiness", "name_sa": "Śūnyatā",
     "name_pi": "Suññatā",
     "desc": "大乘佛教核心概念，一切法无自性、无实体"},
    {"name_zh": "唯识", "name_en": "Consciousness-Only", "name_sa": "Vijñaptimātratā",
     "name_pi": None,
     "desc": "瑜伽行派核心教义，万法唯识所现"},
    {"name_zh": "佛性", "name_en": "Buddha-nature", "name_sa": "Tathāgatagarbha",
     "name_pi": None,
     "desc": "如来藏思想，一切众生皆具成佛之性"},
    {"name_zh": "般若", "name_en": "Prajñā (Wisdom)", "name_sa": "Prajñā",
     "name_pi": "Paññā",
     "desc": "超越世间智慧的究竟智慧，大乘六波罗蜜之首"},
    {"name_zh": "涅槃", "name_en": "Nirvāṇa", "name_sa": "Nirvāṇa",
     "name_pi": "Nibbāna",
     "desc": "烦恼寂灭、生死解脱的究竟境界"},
    {"name_zh": "菩提", "name_en": "Bodhi (Awakening)", "name_sa": "Bodhi",
     "name_pi": "Bodhi",
     "desc": "觉悟、正觉，佛教修行的终极目标"},
    {"name_zh": "三法印", "name_en": "Three Marks of Existence", "name_sa": "Trilakṣaṇa",
     "name_pi": "Tilakkhaṇa",
     "desc": "诸行无常、诸法无我、涅槃寂静，判断佛法的标准"},
    {"name_zh": "十二因缘", "name_en": "Twelve Nidānas", "name_sa": "Dvādaśa-nidāna",
     "name_pi": "Dvādasanidāna",
     "desc": "无明至老死的十二环节，详细阐释缘起法则"},
    {"name_zh": "六波罗蜜", "name_en": "Six Pāramitās", "name_sa": "Ṣaṭ-pāramitā",
     "name_pi": None,
     "desc": "布施、持戒、忍辱、精进、禅定、般若，菩萨修行的六种德行"},
    {"name_zh": "中道", "name_en": "Middle Way", "name_sa": "Madhyamā-pratipad",
     "name_pi": "Majjhimā paṭipadā",
     "desc": "远离苦行与纵欲两极端的修行路线"},
    {"name_zh": "三学", "name_en": "Three Trainings", "name_sa": "Triśikṣā",
     "name_pi": "Tisso sikkhā",
     "desc": "戒、定、慧，佛教修行的三大纲要"},
    {"name_zh": "五蕴", "name_en": "Five Aggregates", "name_sa": "Pañcaskandha",
     "name_pi": "Pañcakkhandha",
     "desc": "色、受、想、行、识，构成有情众生身心的五种要素"},
    {"name_zh": "禅定", "name_en": "Dhyāna (Meditation)", "name_sa": "Dhyāna",
     "name_pi": "Jhāna",
     "desc": "专注一境的修行方法，佛教核心修行实践"},
    {"name_zh": "业", "name_en": "Karma", "name_sa": "Karma",
     "name_pi": "Kamma",
     "desc": "身口意三业，因果报应的核心概念"},
    {"name_zh": "轮回", "name_en": "Saṃsāra", "name_sa": "Saṃsāra",
     "name_pi": "Saṃsāra",
     "desc": "众生在六道中不断流转的生死循环"},
]

# ── Person-Place relations: (person_name_zh, place_name_zh) ──
# predicate: "active_in" (person was active at this place)
PERSON_PLACE = [
    ("鳩摩羅什", "龟兹"),
    ("玄奘", "那烂陀"),
    ("菩提達摩", "嵩山"),
    ("智顗", "天台山"),
    ("慧遠", "庐山"),
    ("道宣", "终南山"),
    ("法藏", "五台山"),
]

# ── School-Concept relations: (school_name_zh, concept_name_zh) ──
# predicate: "associated_with"
SCHOOL_CONCEPT = [
    ("三论宗", "空性"),
    ("三论宗", "中道"),
    ("法相宗", "唯识"),
    ("天台宗", "中道"),
    ("禅宗", "禅定"),
    ("禅宗", "菩提"),
    ("净土宗", "涅槃"),
    ("密宗", "禅定"),
    ("华严宗", "缘起"),
]

SOURCE_PLACE = "seed:place"
SOURCE_CONCEPT = "seed:concept"
SOURCE_PERSON_PLACE = "seed:person_place"
SOURCE_SCHOOL_CONCEPT = "seed:school_concept"


def _q(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    return s.replace("'", "''") if s else ""


def upgrade() -> None:
    # ── 1. Insert place entities ──
    for place in PLACES:
        name_zh = _q(place["name_zh"])
        name_en = _q(place["name_en"])
        name_sa = _q(place.get("name_sa") or "")
        desc = _q(place["desc"])
        name_sa_val = f"'{name_sa}'" if place.get("name_sa") else "NULL"
        op.execute(f"""
            INSERT INTO kg_entities (entity_type, name_zh, name_en, name_sa, description)
            SELECT 'place', '{name_zh}', '{name_en}', {name_sa_val}, '{desc}'
            WHERE NOT EXISTS (
                SELECT 1 FROM kg_entities
                WHERE entity_type = 'place' AND name_zh = '{name_zh}'
            )
        """)

    # ── 2. Insert concept entities ──
    for concept in CONCEPTS:
        name_zh = _q(concept["name_zh"])
        name_en = _q(concept["name_en"])
        name_sa = _q(concept.get("name_sa") or "")
        name_pi = _q(concept.get("name_pi") or "")
        desc = _q(concept["desc"])
        name_sa_val = f"'{name_sa}'" if concept.get("name_sa") else "NULL"
        name_pi_val = f"'{name_pi}'" if concept.get("name_pi") else "NULL"
        op.execute(f"""
            INSERT INTO kg_entities (entity_type, name_zh, name_en, name_sa, name_pi, description)
            SELECT 'concept', '{name_zh}', '{name_en}', {name_sa_val}, {name_pi_val}, '{desc}'
            WHERE NOT EXISTS (
                SELECT 1 FROM kg_entities
                WHERE entity_type = 'concept' AND name_zh = '{name_zh}'
            )
        """)

    # ── 3. Insert person-place relations (active_in) ──
    for person_name, place_name in PERSON_PLACE:
        pn = _q(person_name)
        pl = _q(place_name)
        op.execute(f"""
            INSERT INTO kg_relations (subject_id, predicate, object_id, source, confidence)
            SELECT p.id, 'active_in', pl.id, '{SOURCE_PERSON_PLACE}', 0.9
            FROM kg_entities p, kg_entities pl
            WHERE p.entity_type = 'person' AND p.name_zh = '{pn}'
              AND pl.entity_type = 'place' AND pl.name_zh = '{pl}'
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations
                  WHERE subject_id = p.id AND predicate = 'active_in'
                    AND object_id = pl.id AND source = '{SOURCE_PERSON_PLACE}'
              )
        """)

    # ── 4. Insert school-concept relations (associated_with) ──
    for school_name, concept_name in SCHOOL_CONCEPT:
        sn = _q(school_name)
        cn = _q(concept_name)
        op.execute(f"""
            INSERT INTO kg_relations (subject_id, predicate, object_id, source, confidence)
            SELECT s.id, 'associated_with', c.id, '{SOURCE_SCHOOL_CONCEPT}', 0.9
            FROM kg_entities s, kg_entities c
            WHERE s.entity_type = 'school' AND s.name_zh = '{sn}'
              AND c.entity_type = 'concept' AND c.name_zh = '{cn}'
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations
                  WHERE subject_id = s.id AND predicate = 'associated_with'
                    AND object_id = c.id AND source = '{SOURCE_SCHOOL_CONCEPT}'
              )
        """)


def downgrade() -> None:
    op.execute(f"DELETE FROM kg_relations WHERE source = '{SOURCE_SCHOOL_CONCEPT}'")
    op.execute(f"DELETE FROM kg_relations WHERE source = '{SOURCE_PERSON_PLACE}'")
    for concept in CONCEPTS:
        name = _q(concept["name_zh"])
        op.execute(f"DELETE FROM kg_entities WHERE entity_type = 'concept' AND name_zh = '{name}'")
    for place in PLACES:
        name = _q(place["name_zh"])
        op.execute(f"DELETE FROM kg_entities WHERE entity_type = 'place' AND name_zh = '{name}'")
